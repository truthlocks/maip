# Copyright 2026 Truthlocks Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""CLI extension for ``dvc maip`` commands.

Registers as a DVC command plugin via the ``dvc.command`` entry point.
Provides sub-commands:

- ``dvc maip receipt create --stage <stage>``
- ``dvc maip receipt verify --id <receipt_id>``
- ``dvc maip receipt list --file <path>``
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

from dvc_maip.client import MAIPClient
from dvc_maip.config import MAIPConfig
from dvc_maip.exceptions import MAIPError
from dvc_maip.receipts import generate_pipeline_receipt

logger = logging.getLogger(__name__)


def _run_async(coro: Any) -> Any:
    """Run an async coroutine from the synchronous CLI context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def _load_lock_file(pipeline_file: str = "dvc.yaml") -> dict[str, Any]:
    """Load and parse the DVC lock file corresponding to the pipeline file.

    Args:
        pipeline_file: Path to the pipeline definition (e.g. ``dvc.yaml``).

    Returns:
        Parsed dict from ``dvc.lock``.

    Raises:
        SystemExit: If the lock file cannot be read.
    """
    import os

    lock_file = pipeline_file.replace(".yaml", ".lock").replace(".yml", ".lock")
    if not os.path.isfile(lock_file):
        _error(f"Lock file not found: {lock_file}")

    try:
        import yaml  # type: ignore[import-untyped]

        with open(lock_file, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}  # type: ignore[no-any-return]
    except Exception as exc:
        _error(f"Failed to parse lock file {lock_file}: {exc}")
        return {}  # unreachable, but keeps type checkers happy


def _error(message: str) -> None:
    """Print an error message to stderr and exit with code 1."""
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(1)


def _print_json(obj: Any) -> None:
    """Pretty-print a Pydantic model or dict as JSON to stdout."""
    if hasattr(obj, "model_dump"):
        data = obj.model_dump(mode="json")
    elif isinstance(obj, list):
        data = [
            item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in obj
        ]
    else:
        data = obj
    print(json.dumps(data, indent=2, default=str))


# ------------------------------------------------------------------
# Command implementations
# ------------------------------------------------------------------


def cmd_receipt_create(
    stage: str,
    *,
    pipeline_file: str = "dvc.yaml",
    config: MAIPConfig | None = None,
) -> int:
    """Create a MAIP receipt for a DVC pipeline stage.

    Reads the lock file, extracts the stage data, generates a receipt,
    and submits it to the MAIP API.

    Args:
        stage: Name of the pipeline stage.
        pipeline_file: Path to the pipeline definition file.
        config: Optional config override.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    cfg = config or MAIPConfig()
    lock = _load_lock_file(pipeline_file)

    stages = lock.get("stages", lock)
    if stage not in stages:
        _error(f"Stage '{stage}' not found in lock file")

    stage_data = stages[stage]
    receipt = generate_pipeline_receipt(
        stage,
        stage_data,
        pipeline_file=pipeline_file,
        config=cfg,
    )

    try:
        response = _run_async(_submit_receipt(receipt, cfg))
        _print_json(response)
        return 0
    except MAIPError as exc:
        _error(f"MAIP API error: {exc}")
        return 1


def cmd_receipt_verify(
    receipt_id: str,
    *,
    config: MAIPConfig | None = None,
) -> int:
    """Verify a MAIP receipt by its identifier.

    Args:
        receipt_id: The receipt ID to verify.
        config: Optional config override.

    Returns:
        Exit code (0 for valid, 1 for invalid or error).
    """
    cfg = config or MAIPConfig()

    try:
        response = _run_async(_verify_receipt(receipt_id, cfg))
        _print_json(response)
        return 0 if response.valid else 1
    except MAIPError as exc:
        _error(f"MAIP API error: {exc}")
        return 1


def cmd_receipt_list(
    *,
    file_path: str | None = None,
    stage_name: str | None = None,
    config: MAIPConfig | None = None,
) -> int:
    """List MAIP receipts, optionally filtered by file or stage.

    Args:
        file_path: Filter by tracked file path.
        stage_name: Filter by pipeline stage name.
        config: Optional config override.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    cfg = config or MAIPConfig()

    try:
        receipts = _run_async(_list_receipts(file_path, stage_name, cfg))
        _print_json(receipts)
        return 0
    except MAIPError as exc:
        _error(f"MAIP API error: {exc}")
        return 1


# ------------------------------------------------------------------
# Async helpers
# ------------------------------------------------------------------


async def _submit_receipt(receipt: Any, config: MAIPConfig) -> Any:
    """Submit a receipt to the MAIP API."""
    async with MAIPClient(config) as client:
        return await client.create_receipt(receipt)


async def _verify_receipt(receipt_id: str, config: MAIPConfig) -> Any:
    """Verify a receipt via the MAIP API."""
    async with MAIPClient(config) as client:
        return await client.verify_receipt(receipt_id)


async def _list_receipts(
    file_path: str | None,
    stage_name: str | None,
    config: MAIPConfig,
) -> list[Any]:
    """List receipts via the MAIP API."""
    async with MAIPClient(config) as client:
        return await client.list_receipts(file_path=file_path, stage_name=stage_name)


# ------------------------------------------------------------------
# DVC command plugin interface
# ------------------------------------------------------------------


class MAIPCommand:
    """DVC command plugin entry point.

    Registered via the ``[project.entry-points."dvc.command"]`` section
    of ``pyproject.toml``.  DVC discovers this class and calls its
    ``run`` method when the user invokes ``dvc maip ...``.
    """

    @staticmethod
    def run(args: list[str] | None = None) -> int:
        """Parse arguments and dispatch to the appropriate sub-command.

        Args:
            args: Raw CLI arguments (defaults to ``sys.argv[1:]``).

        Returns:
            Process exit code.
        """
        import argparse

        parser = argparse.ArgumentParser(prog="dvc maip", description="MAIP receipt commands")
        subparsers = parser.add_subparsers(dest="command")

        # -- receipt create
        create_parser = subparsers.add_parser("receipt-create", help="Create a receipt")
        create_parser.add_argument(
            "--stage",
            required=True,
            help="Pipeline stage name",
        )
        create_parser.add_argument(
            "--pipeline-file",
            default="dvc.yaml",
            help="Path to pipeline file",
        )

        # -- receipt verify
        verify_parser = subparsers.add_parser("receipt-verify", help="Verify a receipt")
        verify_parser.add_argument(
            "--id",
            required=True,
            dest="receipt_id",
            help="Receipt ID to verify",
        )

        # -- receipt list
        list_parser = subparsers.add_parser("receipt-list", help="List receipts")
        list_parser.add_argument("--file", dest="file_path", help="Filter by file path")
        list_parser.add_argument("--stage", dest="stage_name", help="Filter by stage name")

        parsed = parser.parse_args(args)

        if parsed.command == "receipt-create":
            return cmd_receipt_create(
                parsed.stage,
                pipeline_file=parsed.pipeline_file,
            )
        elif parsed.command == "receipt-verify":
            return cmd_receipt_verify(parsed.receipt_id)
        elif parsed.command == "receipt-list":
            return cmd_receipt_list(
                file_path=parsed.file_path,
                stage_name=parsed.stage_name,
            )
        else:
            parser.print_help()
            return 1

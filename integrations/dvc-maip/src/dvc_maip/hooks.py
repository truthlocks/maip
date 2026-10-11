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

"""DVC lifecycle hooks that auto-generate MAIP receipts.

These functions are intended to be called from DVC post-checkout, post-push,
post-pull, and post-pipeline hooks.  They bridge the synchronous DVC hook
context to the async MAIP client using ``asyncio.run()``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from dvc_maip.client import MAIPClient
from dvc_maip.config import MAIPConfig
from dvc_maip.exceptions import MAIPError
from dvc_maip.receipts import generate_data_receipt, generate_pipeline_receipt
from dvc_maip.schemas import ReceiptResponse

logger = logging.getLogger(__name__)


def _run_async(coro: Any) -> Any:
    """Run an async coroutine from synchronous hook context.

    Handles the case where an event loop is already running (e.g. inside
    Jupyter or an async framework) by offloading to a thread.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def _parse_dvc_file_info(file_path: str) -> tuple[str, int]:
    """Read the .dvc sidecar file to extract MD5 hash and file size.

    DVC sidecar files (``<filename>.dvc``) are YAML files containing an
    ``outs`` list with ``md5`` and ``size`` fields.

    Args:
        file_path: Path of the tracked file (the sidecar path is derived
                   by appending ``.dvc``).

    Returns:
        A tuple of ``(md5, size)``.  Falls back to ``("", 0)`` if the
        sidecar cannot be read.
    """
    import os

    sidecar = file_path + ".dvc" if not file_path.endswith(".dvc") else file_path

    if not os.path.isfile(sidecar):
        return "", 0

    try:
        import yaml  # type: ignore[import-untyped]

        with open(sidecar, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        if isinstance(data, dict):
            for out in data.get("outs", []):
                if isinstance(out, dict):
                    return out.get("md5", ""), out.get("size", 0)
    except Exception:
        logger.debug("Failed to parse DVC sidecar %s", sidecar, exc_info=True)

    return "", 0


def post_checkout_hook(
    files: list[str],
    *,
    config: MAIPConfig | None = None,
) -> list[ReceiptResponse]:
    """Generate receipts for files checked out from DVC cache.

    This hook should be invoked after ``dvc checkout`` completes.  It
    creates a ``DVCDataReceipt`` for each file with ``operation="checkout"``.

    Args:
        files: List of file paths that were checked out.
        config: Optional plugin config override.

    Returns:
        A list of ``ReceiptResponse`` objects for successfully created receipts.
    """
    cfg = config or MAIPConfig()
    if not cfg.auto_receipt:
        logger.debug("Auto-receipt disabled; skipping post-checkout hook")
        return []

    return _run_async(_create_data_receipts(files, "checkout", "", cfg))


def post_push_hook(
    files: list[str],
    remote: str,
    *,
    config: MAIPConfig | None = None,
) -> list[ReceiptResponse]:
    """Generate receipts for files pushed to a DVC remote.

    This hook should be invoked after ``dvc push`` completes.

    Args:
        files: List of file paths that were pushed.
        remote: Name of the DVC remote.
        config: Optional plugin config override.

    Returns:
        A list of ``ReceiptResponse`` objects for successfully created receipts.
    """
    cfg = config or MAIPConfig()
    if not cfg.auto_receipt:
        logger.debug("Auto-receipt disabled; skipping post-push hook")
        return []

    return _run_async(_create_data_receipts(files, "push", remote, cfg))


def post_pull_hook(
    files: list[str],
    remote: str,
    *,
    config: MAIPConfig | None = None,
) -> list[ReceiptResponse]:
    """Generate receipts for files pulled from a DVC remote.

    This hook should be invoked after ``dvc pull`` completes.

    Args:
        files: List of file paths that were pulled.
        remote: Name of the DVC remote.
        config: Optional plugin config override.

    Returns:
        A list of ``ReceiptResponse`` objects for successfully created receipts.
    """
    cfg = config or MAIPConfig()
    if not cfg.auto_receipt:
        logger.debug("Auto-receipt disabled; skipping post-pull hook")
        return []

    return _run_async(_create_data_receipts(files, "pull", remote, cfg))


def post_pipeline_hook(
    stage_name: str,
    lock_data: dict[str, Any],
    *,
    pipeline_file: str = "dvc.yaml",
    config: MAIPConfig | None = None,
) -> ReceiptResponse | None:
    """Generate a receipt after a DVC pipeline stage completes.

    This hook should be invoked after ``dvc repro`` finishes a stage.  It
    reads the lock data to construct a ``DVCPipelineReceipt``.

    Args:
        stage_name: Name of the pipeline stage.
        lock_data: Parsed lock data dict for the stage (from ``dvc.lock``).
        pipeline_file: Path to the pipeline definition file.
        config: Optional plugin config override.

    Returns:
        A ``ReceiptResponse`` if the receipt was created, or ``None`` on failure.
    """
    cfg = config or MAIPConfig()
    if not cfg.auto_receipt:
        logger.debug("Auto-receipt disabled; skipping post-pipeline hook")
        return None

    return _run_async(
        _create_pipeline_receipt(stage_name, lock_data, pipeline_file, cfg)
    )


# ------------------------------------------------------------------
# Async internals
# ------------------------------------------------------------------


async def _create_data_receipts(
    files: list[str],
    operation: str,
    remote: str,
    config: MAIPConfig,
) -> list[ReceiptResponse]:
    """Create data receipts for a batch of files.

    Failures for individual files are logged and skipped so that one bad
    file does not prevent receipts for the others.
    """
    responses: list[ReceiptResponse] = []

    async with MAIPClient(config) as client:
        for file_path in files:
            try:
                md5, size = _parse_dvc_file_info(file_path)
                receipt = generate_data_receipt(
                    file_path=file_path,
                    md5=md5,
                    size=size,
                    operation=operation,  # type: ignore[arg-type]
                    remote=remote,
                    config=config,
                )
                response = await client.create_receipt(receipt)
                responses.append(response)
                logger.info(
                    "MAIP receipt %s created for %s %s",
                    response.receipt_id,
                    operation,
                    file_path,
                )
            except MAIPError:
                logger.exception(
                    "Failed to create MAIP receipt for %s %s",
                    operation,
                    file_path,
                )
            except Exception:
                logger.exception(
                    "Unexpected error creating MAIP receipt for %s %s",
                    operation,
                    file_path,
                )

    return responses


async def _create_pipeline_receipt(
    stage_name: str,
    lock_data: dict[str, Any],
    pipeline_file: str,
    config: MAIPConfig,
) -> ReceiptResponse | None:
    """Create a single pipeline receipt for a completed stage."""
    try:
        receipt = generate_pipeline_receipt(
            stage_name,
            lock_data,
            pipeline_file=pipeline_file,
            config=config,
        )
        async with MAIPClient(config) as client:
            response = await client.create_receipt(receipt)
        logger.info(
            "MAIP receipt %s created for pipeline stage %s",
            response.receipt_id,
            stage_name,
        )
        return response
    except MAIPError:
        logger.exception(
            "Failed to create MAIP receipt for pipeline stage %s",
            stage_name,
        )
    except Exception:
        logger.exception(
            "Unexpected error creating MAIP receipt for pipeline stage %s",
            stage_name,
        )
    return None

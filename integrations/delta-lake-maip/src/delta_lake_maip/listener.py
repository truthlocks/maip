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

"""Delta Lake commit listener with automatic MAIP receipt generation."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Callable

from delta_lake_maip.client import MAIPClient
from delta_lake_maip.config import DeltaMAIPConfig
from delta_lake_maip.exceptions import DeltaTableError, MAIPError
from delta_lake_maip.receipts import generate_merge_receipt, generate_write_receipt
from delta_lake_maip.schemas import ReceiptResponse
from delta_lake_maip.tracker import DeltaTableTracker

logger = logging.getLogger(__name__)

# Delta operations classified by type
_WRITE_OPERATIONS = frozenset({"WRITE", "APPEND", "OVERWRITE", "CREATE TABLE", "CREATE TABLE AS SELECT"})
_MERGE_OPERATIONS = frozenset({"MERGE", "MERGE INTO"})


def _run_async(coro: Any) -> Any:
    """Run an async coroutine from synchronous code, handling event-loop reuse."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


class DeltaCommitListener:
    """Monitors Delta Lake transaction log for new commits and auto-generates receipts.

    The listener tracks the last-known version and, on each poll cycle (or
    explicit ``on_commit`` call), generates and submits a MAIP receipt for
    every new commit detected.

    Args:
        table_path: Filesystem path or URI of the Delta table to monitor.
        config: Optional plugin configuration.
        table_name: Optional logical name for the table.
        on_receipt: Optional callback invoked after each successful receipt submission.
    """

    def __init__(
        self,
        table_path: str,
        config: DeltaMAIPConfig | None = None,
        table_name: str = "",
        on_receipt: Callable[[ReceiptResponse], None] | None = None,
    ) -> None:
        self._config = config or DeltaMAIPConfig()
        self._table_path = table_path
        self._table_name = table_name
        self._on_receipt = on_receipt
        self._tracker = DeltaTableTracker(table_path, self._config)
        self._client = MAIPClient(self._config)
        self._last_version: int = self._tracker.get_current_version()
        self._watching = False
        self._watch_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    @property
    def last_version(self) -> int:
        """Return the last version that has been processed."""
        return self._last_version

    # ------------------------------------------------------------------
    # Commit handling
    # ------------------------------------------------------------------

    async def on_commit(
        self,
        version: int,
        actions: list[dict[str, Any]] | None = None,
    ) -> ReceiptResponse:
        """Process a single commit and submit a MAIP receipt.

        When *actions* is ``None``, metadata is read directly from the
        Delta transaction log via the tracker.

        Args:
            version: The Delta version number of the new commit.
            actions: Optional list of action dicts from the transaction log.
                     If ``None``, the tracker reads them automatically.

        Returns:
            The ``ReceiptResponse`` from the MAIP API.

        Raises:
            MAIPError: If the receipt submission fails.
            DeltaTableError: If commit metadata cannot be read.
        """
        commit_info = self._tracker.get_commit_info(version)
        operation = commit_info.get("operation", "WRITE").upper()

        schema_json = self._tracker.get_schema_json(version)

        if operation in _MERGE_OPERATIONS:
            receipt = generate_merge_receipt(
                table_path=self._table_path,
                version=version,
                condition=commit_info.get("operationParameters", {}).get("predicate", ""),
                commit_info=commit_info,
                table_name=self._table_name,
                config=self._config,
            )
        else:
            add_actions = self._tracker.get_add_actions(version)
            # Compute remove actions from the provided actions list if available
            remove_actions: list[dict[str, Any]] = []
            if actions:
                remove_actions = [a for a in actions if "remove" in a]

            partition_columns: list[str] = []
            metadata_action = commit_info.get("operationParameters", {})
            if isinstance(metadata_action, dict):
                partition_cols = metadata_action.get("partitionBy", [])
                if isinstance(partition_cols, list):
                    partition_columns = partition_cols

            receipt = generate_write_receipt(
                table_path=self._table_path,
                version=version,
                operation=operation if operation in _WRITE_OPERATIONS else "WRITE",
                commit_info=commit_info,
                add_actions=add_actions,
                remove_actions=remove_actions,
                schema_json=schema_json,
                partition_columns=partition_columns,
                table_name=self._table_name,
                config=self._config,
            )

        # Check for schema evolution and submit a separate receipt if detected
        if version > 0:
            schema_receipt = self._tracker.detect_schema_changes(version - 1, version)
            if schema_receipt is not None:
                try:
                    await self._client.create_receipt(schema_receipt)
                    logger.info(
                        "Schema evolution receipt submitted for %s version %d",
                        self._table_path,
                        version,
                    )
                except MAIPError:
                    logger.exception(
                        "Failed to submit schema evolution receipt for %s version %d",
                        self._table_path,
                        version,
                    )

        response = await self._client.create_receipt(receipt)

        self._last_version = version
        logger.info(
            "MAIP receipt %s created for %s version %d",
            response.receipt_id,
            self._table_path,
            version,
        )

        if self._on_receipt is not None:
            self._on_receipt(response)

        return response

    # ------------------------------------------------------------------
    # Background polling
    # ------------------------------------------------------------------

    def start_watching(self, poll_interval: float | None = None) -> None:
        """Start polling the transaction log for new commits in a background thread.

        Each new commit detected triggers receipt generation and submission.
        Errors during individual commit processing are logged but do not stop
        the polling loop.

        Args:
            poll_interval: Seconds between polls.  Defaults to the config value.

        Raises:
            RuntimeError: If the listener is already watching.
        """
        if self._watching:
            raise RuntimeError("Listener is already watching")

        interval = poll_interval if poll_interval is not None else self._config.poll_interval
        self._stop_event.clear()
        self._watching = True
        self._watch_thread = threading.Thread(
            target=self._poll_loop,
            args=(interval,),
            daemon=True,
            name=f"delta-maip-watcher-{self._table_path}",
        )
        self._watch_thread.start()
        logger.info("Started watching %s (interval=%.1fs)", self._table_path, interval)

    def stop_watching(self) -> None:
        """Stop the background polling thread.

        This method is idempotent; calling it when not watching is a no-op.
        """
        if not self._watching:
            return
        self._stop_event.set()
        if self._watch_thread is not None:
            self._watch_thread.join(timeout=30.0)
            self._watch_thread = None
        self._watching = False
        logger.info("Stopped watching %s", self._table_path)

    @property
    def is_watching(self) -> bool:
        """Return whether the background polling thread is active."""
        return self._watching

    def _poll_loop(self, interval: float) -> None:
        """Internal polling loop executed in a background thread."""
        while not self._stop_event.is_set():
            try:
                self._tracker.reload()
                current_version = self._tracker.get_current_version()

                while self._last_version < current_version:
                    next_version = self._last_version + 1
                    try:
                        _run_async(self.on_commit(next_version))
                    except (MAIPError, DeltaTableError):
                        logger.exception(
                            "Error processing commit %d for %s",
                            next_version,
                            self._table_path,
                        )
                        # Advance past failed version to avoid infinite retry
                        self._last_version = next_version
                    except Exception:
                        logger.exception(
                            "Unexpected error processing commit %d for %s",
                            next_version,
                            self._table_path,
                        )
                        self._last_version = next_version

            except DeltaTableError:
                logger.exception("Error reloading Delta table %s", self._table_path)
            except Exception:
                logger.exception("Unexpected error in poll loop for %s", self._table_path)

            self._stop_event.wait(interval)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Stop watching and close the underlying HTTP client."""
        self.stop_watching()
        await self._client.close()

    async def __aenter__(self) -> DeltaCommitListener:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

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

"""PySpark DataFrame writer wrapper that auto-generates MAIP receipts."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from delta_lake_maip.client import MAIPClient
from delta_lake_maip.config import DeltaMAIPConfig
from delta_lake_maip.exceptions import DeltaTableError, MAIPError
from delta_lake_maip.receipts import generate_merge_receipt, generate_write_receipt
from delta_lake_maip.schemas import ReceiptResponse
from delta_lake_maip.tracker import DeltaTableTracker

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession

logger = logging.getLogger(__name__)


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


class MAIPDeltaWriter:
    """Wraps PySpark Delta writes with automatic MAIP receipt generation.

    After each write or merge operation, this class reads the resulting
    Delta transaction log and submits a cryptographic receipt to the MAIP
    API.  Failures during receipt submission are logged but never propagate
    to the caller so that the core Spark workflow is unaffected.

    Args:
        spark_session: An active PySpark ``SparkSession`` with Delta support.
        config: Optional plugin configuration.
    """

    def __init__(
        self,
        spark_session: SparkSession,
        config: DeltaMAIPConfig | None = None,
    ) -> None:
        self._spark = spark_session
        self._config = config or DeltaMAIPConfig()
        self._client = MAIPClient(self._config)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def write(
        self,
        df: DataFrame,
        table_path: str,
        mode: str = "append",
        *,
        table_name: str = "",
        partition_by: list[str] | None = None,
        **kwargs: Any,
    ) -> ReceiptResponse | None:
        """Write a DataFrame to a Delta table and generate a MAIP receipt.

        The DataFrame is written using PySpark's Delta writer, then the
        resulting commit is used to produce and submit a receipt.

        Args:
            df: The PySpark DataFrame to write.
            table_path: Filesystem path or URI of the Delta table.
            mode: Write mode (``append``, ``overwrite``, ``error``, ``ignore``).
            table_name: Optional logical name for the table.
            partition_by: Optional list of partition columns.
            **kwargs: Additional options forwarded to the Delta writer.

        Returns:
            The ``ReceiptResponse`` from the MAIP API, or ``None`` if
            receipt generation fails.
        """
        writer = df.write.format("delta").mode(mode)
        if partition_by:
            writer = writer.partitionBy(*partition_by)
        for key, value in kwargs.items():
            writer = writer.option(key, value)
        writer.save(table_path)

        if not self._config.auto_receipt:
            return None

        return self._generate_write_receipt(
            table_path=table_path,
            table_name=table_name,
            mode=mode,
            partition_by=partition_by,
        )

    # ------------------------------------------------------------------
    # Merge
    # ------------------------------------------------------------------

    def merge(
        self,
        target_table: str,
        source_df: DataFrame,
        condition: str,
        *,
        table_name: str = "",
        source_description: str = "",
        when_matched_update: dict[str, str] | None = None,
        when_not_matched_insert: dict[str, str] | None = None,
        when_matched_delete: bool = False,
        **kwargs: Any,
    ) -> ReceiptResponse | None:
        """Execute a MERGE INTO and generate a MAIP receipt.

        This method uses PySpark's DeltaTable API to perform the merge,
        then reads the resulting transaction log to produce a receipt.

        Args:
            target_table: Filesystem path or URI of the target Delta table.
            source_df: The source DataFrame to merge from.
            condition: The SQL merge condition expression.
            table_name: Optional logical name for the table.
            source_description: Human-readable description of the merge source.
            when_matched_update: Column mapping for the WHEN MATCHED UPDATE clause.
            when_not_matched_insert: Column mapping for the WHEN NOT MATCHED INSERT clause.
            when_matched_delete: If ``True``, delete matched rows.
            **kwargs: Reserved for future use.

        Returns:
            The ``ReceiptResponse`` from the MAIP API, or ``None`` if
            receipt generation fails.
        """
        from delta.tables import DeltaTable as SparkDeltaTable

        target = SparkDeltaTable.forPath(self._spark, target_table)
        merger = target.alias("target").merge(source_df.alias("source"), condition)

        if when_matched_delete:
            merger = merger.whenMatchedDelete()
        elif when_matched_update is not None:
            merger = merger.whenMatchedUpdate(set=when_matched_update)
        else:
            merger = merger.whenMatchedUpdateAll()

        if when_not_matched_insert is not None:
            merger = merger.whenNotMatchedInsert(values=when_not_matched_insert)
        else:
            merger = merger.whenNotMatchedInsertAll()

        merger.execute()

        if not self._config.auto_receipt:
            return None

        return self._generate_merge_receipt(
            table_path=target_table,
            table_name=table_name,
            condition=condition,
            source_description=source_description,
            source_row_count=source_df.count(),
        )

    # ------------------------------------------------------------------
    # Internal receipt generation
    # ------------------------------------------------------------------

    def _generate_write_receipt(
        self,
        *,
        table_path: str,
        table_name: str,
        mode: str,
        partition_by: list[str] | None,
    ) -> ReceiptResponse | None:
        """Read the latest commit from a Delta table and submit a write receipt."""
        try:
            tracker = DeltaTableTracker(table_path, self._config)
            version = tracker.get_current_version()
            commit_info = tracker.get_commit_info(version)
            add_actions = tracker.get_add_actions(version)
            schema_json = tracker.get_schema_json(version)

            operation_map = {
                "append": "APPEND",
                "overwrite": "OVERWRITE",
                "error": "WRITE",
                "errorifexists": "WRITE",
                "ignore": "WRITE",
            }
            operation = operation_map.get(mode.lower(), "WRITE")

            receipt = generate_write_receipt(
                table_path=table_path,
                version=version,
                operation=operation,
                commit_info=commit_info,
                add_actions=add_actions,
                remove_actions=[],
                schema_json=schema_json,
                partition_columns=partition_by or [],
                table_name=table_name,
                config=self._config,
            )

            response = self._client.create_receipt_sync(receipt)
            logger.info(
                "MAIP write receipt %s created for %s version %d",
                response.receipt_id,
                table_path,
                version,
            )
            return response

        except (MAIPError, DeltaTableError):
            logger.exception(
                "Failed to create MAIP write receipt for %s",
                table_path,
            )
            return None
        except Exception:
            logger.exception(
                "Unexpected error creating MAIP write receipt for %s",
                table_path,
            )
            return None

    def _generate_merge_receipt(
        self,
        *,
        table_path: str,
        table_name: str,
        condition: str,
        source_description: str,
        source_row_count: int,
    ) -> ReceiptResponse | None:
        """Read the latest commit from a Delta table and submit a merge receipt."""
        try:
            tracker = DeltaTableTracker(table_path, self._config)
            version = tracker.get_current_version()
            commit_info = tracker.get_commit_info(version)

            receipt = generate_merge_receipt(
                table_path=table_path,
                version=version,
                condition=condition,
                commit_info=commit_info,
                source_description=source_description,
                num_source_rows=source_row_count,
                table_name=table_name,
                config=self._config,
            )

            response = self._client.create_receipt_sync(receipt)
            logger.info(
                "MAIP merge receipt %s created for %s version %d",
                response.receipt_id,
                table_path,
                version,
            )
            return response

        except (MAIPError, DeltaTableError):
            logger.exception(
                "Failed to create MAIP merge receipt for %s",
                table_path,
            )
            return None
        except Exception:
            logger.exception(
                "Unexpected error creating MAIP merge receipt for %s",
                table_path,
            )
            return None

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.close()

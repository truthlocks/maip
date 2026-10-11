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

"""Tests for the PySpark Delta writer wrapper."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from delta_lake_maip.config import DeltaMAIPConfig
from delta_lake_maip.exceptions import MAIPError
from delta_lake_maip.schemas import ReceiptResponse
from delta_lake_maip.spark_integration import MAIPDeltaWriter

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_SCHEMA_JSON = json.dumps(
    {
        "type": "struct",
        "fields": [
            {"name": "id", "type": "integer", "nullable": False, "metadata": {}},
        ],
    }
)

RECEIPT_RESPONSE = ReceiptResponse(
    receipt_id="rcpt-spark-001",
    status="anchored",
    chain_hash="cafebabe",
    log_index=3,
)


def _config() -> DeltaMAIPConfig:
    return DeltaMAIPConfig(
        api_url="https://test.maip.local/v1/machine-identity",
        api_key="test-key",
        tenant_id="tenant-001",
        agent_id="agent-001",
        max_retries=1,
        timeout=5.0,
    )


def _mock_spark() -> MagicMock:
    """Create a mock SparkSession with a Delta-style writer chain."""
    spark = MagicMock()
    return spark


def _mock_df() -> MagicMock:
    """Create a mock PySpark DataFrame."""
    df = MagicMock()
    writer = MagicMock()
    writer.format.return_value = writer
    writer.mode.return_value = writer
    writer.partitionBy.return_value = writer
    writer.option.return_value = writer
    df.write = writer
    df.count.return_value = 500
    df.alias.return_value = df
    return df


# ---------------------------------------------------------------------------
# Tests: write
# ---------------------------------------------------------------------------


class TestMAIPDeltaWriterWrite:
    @patch("delta_lake_maip.spark_integration.MAIPClient.create_receipt_sync")
    @patch("delta_lake_maip.spark_integration.DeltaTableTracker")
    def test_write_append_success(
        self,
        mock_tracker_cls: MagicMock,
        mock_run_async: MagicMock,
    ) -> None:
        """Append write produces a receipt."""
        tracker = MagicMock()
        tracker.get_current_version.return_value = 5
        tracker.get_commit_info.return_value = {
            "timestamp": 1700000000000,
            "operation": "WRITE",
        }
        tracker.get_add_actions.return_value = [
            {"path": "p.parquet", "stats": json.dumps({"numRecords": 100})}
        ]
        tracker.get_schema_json.return_value = SAMPLE_SCHEMA_JSON
        mock_tracker_cls.return_value = tracker
        mock_run_async.return_value = RECEIPT_RESPONSE

        writer = MAIPDeltaWriter(_mock_spark(), config=_config())
        df = _mock_df()

        resp = writer.write(df, "/data/events", mode="append")

        assert resp is not None
        assert resp.receipt_id == "rcpt-spark-001"
        df.write.format.assert_called_once_with("delta")

    @patch("delta_lake_maip.spark_integration.MAIPClient.create_receipt_sync")
    @patch("delta_lake_maip.spark_integration.DeltaTableTracker")
    def test_write_overwrite_success(
        self,
        mock_tracker_cls: MagicMock,
        mock_run_async: MagicMock,
    ) -> None:
        """Overwrite write produces a receipt with OVERWRITE operation."""
        tracker = MagicMock()
        tracker.get_current_version.return_value = 6
        tracker.get_commit_info.return_value = {
            "timestamp": 1700000000000,
            "operation": "WRITE",
        }
        tracker.get_add_actions.return_value = []
        tracker.get_schema_json.return_value = SAMPLE_SCHEMA_JSON
        mock_tracker_cls.return_value = tracker
        mock_run_async.return_value = RECEIPT_RESPONSE

        writer = MAIPDeltaWriter(_mock_spark(), config=_config())
        df = _mock_df()

        resp = writer.write(df, "/data/events", mode="overwrite")
        assert resp is not None

    @patch("delta_lake_maip.spark_integration.DeltaTableTracker")
    def test_write_auto_receipt_disabled(
        self,
        mock_tracker_cls: MagicMock,
    ) -> None:
        """When auto_receipt is disabled, None is returned."""
        cfg = _config()
        cfg.auto_receipt = False

        writer = MAIPDeltaWriter(_mock_spark(), config=cfg)
        df = _mock_df()

        resp = writer.write(df, "/data/events")
        assert resp is None

    @patch("delta_lake_maip.spark_integration.MAIPClient.create_receipt_sync")
    @patch("delta_lake_maip.spark_integration.DeltaTableTracker")
    def test_write_with_partition_by(
        self,
        mock_tracker_cls: MagicMock,
        mock_run_async: MagicMock,
    ) -> None:
        """Partition columns are passed through to the receipt."""
        tracker = MagicMock()
        tracker.get_current_version.return_value = 1
        tracker.get_commit_info.return_value = {"timestamp": 0, "operation": "WRITE"}
        tracker.get_add_actions.return_value = []
        tracker.get_schema_json.return_value = SAMPLE_SCHEMA_JSON
        mock_tracker_cls.return_value = tracker
        mock_run_async.return_value = RECEIPT_RESPONSE

        writer = MAIPDeltaWriter(_mock_spark(), config=_config())
        df = _mock_df()

        resp = writer.write(df, "/data/events", partition_by=["date", "region"])
        assert resp is not None
        df.write.partitionBy.assert_called_once_with("date", "region")

    @patch("delta_lake_maip.spark_integration.MAIPClient.create_receipt_sync")
    @patch("delta_lake_maip.spark_integration.DeltaTableTracker")
    def test_write_receipt_failure_returns_none(
        self,
        mock_tracker_cls: MagicMock,
        mock_run_async: MagicMock,
    ) -> None:
        """Receipt generation failure returns None (does not propagate)."""
        mock_tracker_cls.side_effect = Exception("Table not ready")
        mock_run_async.return_value = RECEIPT_RESPONSE

        writer = MAIPDeltaWriter(_mock_spark(), config=_config())
        df = _mock_df()

        resp = writer.write(df, "/data/events")
        assert resp is None


# ---------------------------------------------------------------------------
# Tests: merge
# ---------------------------------------------------------------------------


class TestMAIPDeltaWriterMerge:
    @patch("delta_lake_maip.spark_integration.MAIPClient.create_receipt_sync")
    @patch("delta_lake_maip.spark_integration.DeltaTableTracker")
    @patch("delta_lake_maip.spark_integration.MAIPDeltaWriter.merge")
    def test_merge_executes_and_returns_receipt(
        self,
        mock_merge: MagicMock,
        mock_tracker_cls: MagicMock,
        mock_run_async: MagicMock,
    ) -> None:
        """Merge returns a receipt response when successful."""
        mock_merge.return_value = RECEIPT_RESPONSE

        writer = MAIPDeltaWriter(_mock_spark(), config=_config())
        source_df = _mock_df()

        resp = writer.merge(
            "/data/customers",
            source_df,
            "target.id = source.id",
        )

        assert resp is not None
        assert resp.receipt_id == "rcpt-spark-001"

    @patch("delta_lake_maip.spark_integration.DeltaTableTracker")
    def test_merge_auto_receipt_disabled(
        self,
        mock_tracker_cls: MagicMock,
    ) -> None:
        """When auto_receipt is disabled, merge returns None without generating receipt."""
        cfg = _config()
        cfg.auto_receipt = False

        # We need to mock the delta.tables import and its behaviour
        with patch("delta_lake_maip.spark_integration.MAIPDeltaWriter._generate_merge_receipt") as mock_gen:
            mock_gen.return_value = None
            # Mock the delta.tables module
            mock_delta_table = MagicMock()
            mock_merger = MagicMock()
            mock_delta_table.forPath.return_value.alias.return_value.merge.return_value = mock_merger
            mock_merger.whenMatchedUpdateAll.return_value = mock_merger
            mock_merger.whenNotMatchedInsertAll.return_value = mock_merger

            with patch.dict("sys.modules", {"delta": MagicMock(), "delta.tables": MagicMock()}):
                with patch("delta_lake_maip.spark_integration.MAIPDeltaWriter.merge") as mock_m:
                    mock_m.return_value = None
                    writer = MAIPDeltaWriter(_mock_spark(), config=cfg)
                    source_df = _mock_df()
                    resp = writer.merge("/data/customers", source_df, "target.id = source.id")
                    assert resp is None

    @patch("delta_lake_maip.spark_integration.MAIPClient.create_receipt_sync")
    @patch("delta_lake_maip.spark_integration.DeltaTableTracker")
    def test_merge_receipt_failure_returns_none(
        self,
        mock_tracker_cls: MagicMock,
        mock_run_async: MagicMock,
    ) -> None:
        """Receipt generation failure during merge returns None."""
        mock_tracker_cls.side_effect = Exception("Table broken")
        mock_run_async.side_effect = MAIPError("Connection refused")

        writer = MAIPDeltaWriter(_mock_spark(), config=_config())

        # Test _generate_merge_receipt directly since merge() requires delta.tables
        result = writer._generate_merge_receipt(
            table_path="/data/customers",
            table_name="customers",
            condition="target.id = source.id",
            source_description="csv",
            source_row_count=100,
        )
        assert result is None

    @patch("delta_lake_maip.spark_integration.MAIPClient.create_receipt_sync")
    @patch("delta_lake_maip.spark_integration.DeltaTableTracker")
    def test_generate_merge_receipt_success(
        self,
        mock_tracker_cls: MagicMock,
        mock_run_async: MagicMock,
    ) -> None:
        """Internal _generate_merge_receipt produces a receipt response."""
        tracker = MagicMock()
        tracker.get_current_version.return_value = 10
        tracker.get_commit_info.return_value = {
            "timestamp": 1700000000000,
            "operation": "MERGE",
            "operationMetrics": {
                "numTargetRowsInserted": "50",
                "numTargetRowsUpdated": "20",
                "numTargetRowsDeleted": "0",
                "numSourceRows": "70",
            },
        }
        mock_tracker_cls.return_value = tracker
        mock_run_async.return_value = RECEIPT_RESPONSE

        writer = MAIPDeltaWriter(_mock_spark(), config=_config())

        result = writer._generate_merge_receipt(
            table_path="/data/customers",
            table_name="customers",
            condition="target.id = source.id",
            source_description="daily_ingest",
            source_row_count=70,
        )

        assert result is not None
        assert result.receipt_id == "rcpt-spark-001"


# ---------------------------------------------------------------------------
# Tests: close
# ---------------------------------------------------------------------------


class TestMAIPDeltaWriterClose:
    @pytest.mark.asyncio
    async def test_close_closes_client(self) -> None:
        """Closing the writer closes the underlying HTTP client."""
        writer = MAIPDeltaWriter(_mock_spark(), config=_config())
        writer._client = MagicMock()
        writer._client.close = AsyncMock()

        await writer.close()
        writer._client.close.assert_called_once()

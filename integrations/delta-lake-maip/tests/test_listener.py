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

"""Tests for the DeltaCommitListener."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from delta_lake_maip.config import DeltaMAIPConfig
from delta_lake_maip.exceptions import DeltaTableError, MAIPError
from delta_lake_maip.listener import DeltaCommitListener
from delta_lake_maip.schemas import ReceiptResponse

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_SCHEMA_JSON = json.dumps(
    {
        "type": "struct",
        "fields": [
            {"name": "id", "type": "integer", "nullable": False, "metadata": {}},
            {"name": "value", "type": "string", "nullable": True, "metadata": {}},
        ],
    }
)

RECEIPT_RESPONSE = ReceiptResponse(
    receipt_id="rcpt-listen-001",
    status="anchored",
    chain_hash="feedface",
    log_index=7,
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


# ---------------------------------------------------------------------------
# Tests: on_commit
# ---------------------------------------------------------------------------


class TestOnCommit:
    @patch("delta_lake_maip.listener.DeltaTableTracker")
    @pytest.mark.asyncio
    async def test_write_commit_generates_receipt(
        self,
        mock_tracker_cls: MagicMock,
    ) -> None:
        """A WRITE commit produces a write receipt and submits it."""
        tracker = MagicMock()
        tracker.get_current_version.return_value = 5
        tracker.get_commit_info.return_value = {
            "timestamp": 1700000000000,
            "operation": "WRITE",
            "operationParameters": {},
        }
        tracker.get_schema_json.return_value = SAMPLE_SCHEMA_JSON
        tracker.get_add_actions.return_value = [
            {"path": "p.parquet", "stats": json.dumps({"numRecords": 100})}
        ]
        tracker.detect_schema_changes.return_value = None
        mock_tracker_cls.return_value = tracker

        listener = DeltaCommitListener("/data/events", config=_config())
        listener._client = MagicMock()
        listener._client.create_receipt = AsyncMock(return_value=RECEIPT_RESPONSE)

        resp = await listener.on_commit(5)

        assert resp.receipt_id == "rcpt-listen-001"
        listener._client.create_receipt.assert_called_once()
        receipt_arg = listener._client.create_receipt.call_args[0][0]
        assert receipt_arg.receipt_type == "delta_write_receipt"

    @patch("delta_lake_maip.listener.DeltaTableTracker")
    @pytest.mark.asyncio
    async def test_merge_commit_generates_receipt(
        self,
        mock_tracker_cls: MagicMock,
    ) -> None:
        """A MERGE commit produces a merge receipt and submits it."""
        tracker = MagicMock()
        tracker.get_current_version.return_value = 10
        tracker.get_commit_info.return_value = {
            "timestamp": 1700000000000,
            "operation": "MERGE",
            "operationParameters": {"predicate": "t.id = s.id"},
            "operationMetrics": {
                "numTargetRowsInserted": "50",
                "numTargetRowsUpdated": "20",
                "numTargetRowsDeleted": "0",
                "numSourceRows": "70",
            },
        }
        tracker.get_schema_json.return_value = SAMPLE_SCHEMA_JSON
        tracker.detect_schema_changes.return_value = None
        mock_tracker_cls.return_value = tracker

        listener = DeltaCommitListener("/data/customers", config=_config())
        listener._client = MagicMock()
        listener._client.create_receipt = AsyncMock(return_value=RECEIPT_RESPONSE)

        resp = await listener.on_commit(10)

        assert resp.receipt_id == "rcpt-listen-001"
        receipt_arg = listener._client.create_receipt.call_args[0][0]
        assert receipt_arg.receipt_type == "delta_merge_receipt"
        assert receipt_arg.condition == "t.id = s.id"

    @patch("delta_lake_maip.listener.DeltaTableTracker")
    @pytest.mark.asyncio
    async def test_schema_evolution_detected(
        self,
        mock_tracker_cls: MagicMock,
    ) -> None:
        """When schema changes between versions, a separate schema receipt is created."""
        from delta_lake_maip.schemas import DeltaSchemaEvolutionReceipt

        schema_receipt = DeltaSchemaEvolutionReceipt(
            table_path="/data/events",
            version=5,
            previous_schema_hash="aaa",
            new_schema_hash="bbb",
            columns_added=["email"],
        )
        tracker = MagicMock()
        tracker.get_current_version.return_value = 5
        tracker.get_commit_info.return_value = {
            "timestamp": 1700000000000,
            "operation": "WRITE",
            "operationParameters": {},
        }
        tracker.get_schema_json.return_value = SAMPLE_SCHEMA_JSON
        tracker.get_add_actions.return_value = []
        tracker.detect_schema_changes.return_value = schema_receipt
        mock_tracker_cls.return_value = tracker

        listener = DeltaCommitListener("/data/events", config=_config())
        listener._client = MagicMock()
        listener._client.create_receipt = AsyncMock(return_value=RECEIPT_RESPONSE)

        await listener.on_commit(5)

        # Two receipts: one for schema evolution, one for the write
        assert listener._client.create_receipt.call_count == 2

    @patch("delta_lake_maip.listener.DeltaTableTracker")
    @pytest.mark.asyncio
    async def test_on_receipt_callback_invoked(
        self,
        mock_tracker_cls: MagicMock,
    ) -> None:
        """The on_receipt callback is called with the response."""
        tracker = MagicMock()
        tracker.get_current_version.return_value = 1
        tracker.get_commit_info.return_value = {
            "timestamp": 1700000000000,
            "operation": "WRITE",
            "operationParameters": {},
        }
        tracker.get_schema_json.return_value = SAMPLE_SCHEMA_JSON
        tracker.get_add_actions.return_value = []
        tracker.detect_schema_changes.return_value = None
        mock_tracker_cls.return_value = tracker

        callback = MagicMock()
        listener = DeltaCommitListener("/data/events", config=_config(), on_receipt=callback)
        listener._client = MagicMock()
        listener._client.create_receipt = AsyncMock(return_value=RECEIPT_RESPONSE)

        await listener.on_commit(1)

        callback.assert_called_once_with(RECEIPT_RESPONSE)

    @patch("delta_lake_maip.listener.DeltaTableTracker")
    @pytest.mark.asyncio
    async def test_api_failure_propagates(
        self,
        mock_tracker_cls: MagicMock,
    ) -> None:
        """When the MAIP API fails, the error propagates from on_commit."""
        tracker = MagicMock()
        tracker.get_current_version.return_value = 1
        tracker.get_commit_info.return_value = {
            "timestamp": 1700000000000,
            "operation": "WRITE",
            "operationParameters": {},
        }
        tracker.get_schema_json.return_value = SAMPLE_SCHEMA_JSON
        tracker.get_add_actions.return_value = []
        tracker.detect_schema_changes.return_value = None
        mock_tracker_cls.return_value = tracker

        listener = DeltaCommitListener("/data/events", config=_config())
        listener._client = MagicMock()
        listener._client.create_receipt = AsyncMock(
            side_effect=MAIPError("Server error", status_code=500)
        )

        with pytest.raises(MAIPError, match="Server error"):
            await listener.on_commit(1)

    @patch("delta_lake_maip.listener.DeltaTableTracker")
    @pytest.mark.asyncio
    async def test_last_version_updated_after_commit(
        self,
        mock_tracker_cls: MagicMock,
    ) -> None:
        """After successful on_commit, last_version is updated."""
        tracker = MagicMock()
        tracker.get_current_version.return_value = 3
        tracker.get_commit_info.return_value = {
            "timestamp": 1700000000000,
            "operation": "APPEND",
            "operationParameters": {},
        }
        tracker.get_schema_json.return_value = SAMPLE_SCHEMA_JSON
        tracker.get_add_actions.return_value = []
        tracker.detect_schema_changes.return_value = None
        mock_tracker_cls.return_value = tracker

        listener = DeltaCommitListener("/data/events", config=_config())
        listener._client = MagicMock()
        listener._client.create_receipt = AsyncMock(return_value=RECEIPT_RESPONSE)

        await listener.on_commit(3)
        assert listener.last_version == 3


# ---------------------------------------------------------------------------
# Tests: start/stop watching
# ---------------------------------------------------------------------------


class TestWatching:
    @patch("delta_lake_maip.listener.DeltaTableTracker")
    def test_start_watching_sets_flag(self, mock_tracker_cls: MagicMock) -> None:
        """start_watching sets is_watching to True."""
        tracker = MagicMock()
        tracker.get_current_version.return_value = 0
        mock_tracker_cls.return_value = tracker

        listener = DeltaCommitListener("/data/events", config=_config())
        listener.start_watching(poll_interval=60.0)  # Long interval to prevent actual polling
        assert listener.is_watching is True
        listener.stop_watching()
        assert listener.is_watching is False

    @patch("delta_lake_maip.listener.DeltaTableTracker")
    def test_double_start_raises(self, mock_tracker_cls: MagicMock) -> None:
        """Starting while already watching raises RuntimeError."""
        tracker = MagicMock()
        tracker.get_current_version.return_value = 0
        mock_tracker_cls.return_value = tracker

        listener = DeltaCommitListener("/data/events", config=_config())
        listener.start_watching(poll_interval=60.0)
        with pytest.raises(RuntimeError, match="already watching"):
            listener.start_watching()
        listener.stop_watching()

    @patch("delta_lake_maip.listener.DeltaTableTracker")
    def test_stop_watching_idempotent(self, mock_tracker_cls: MagicMock) -> None:
        """Stopping when not watching is a no-op."""
        tracker = MagicMock()
        tracker.get_current_version.return_value = 0
        mock_tracker_cls.return_value = tracker

        listener = DeltaCommitListener("/data/events", config=_config())
        listener.stop_watching()  # Should not raise

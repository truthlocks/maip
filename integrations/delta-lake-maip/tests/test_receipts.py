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

"""Tests for receipt generation and hashing utilities."""

from __future__ import annotations

import json

import pytest

from delta_lake_maip.config import DeltaMAIPConfig
from delta_lake_maip.receipts import (
    generate_merge_receipt,
    generate_schema_evolution_receipt,
    generate_write_receipt,
    hash_receipt_payload,
)
from delta_lake_maip.schemas import DeltaMergeReceipt, DeltaWriteReceipt

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_SCHEMA_JSON = json.dumps(
    {
        "type": "struct",
        "fields": [
            {"name": "id", "type": "integer", "nullable": False, "metadata": {}},
            {"name": "name", "type": "string", "nullable": True, "metadata": {}},
            {"name": "amount", "type": "double", "nullable": True, "metadata": {}},
        ],
    }
)

EVOLVED_SCHEMA_JSON = json.dumps(
    {
        "type": "struct",
        "fields": [
            {"name": "id", "type": "long", "nullable": False, "metadata": {}},
            {"name": "name", "type": "string", "nullable": True, "metadata": {}},
            {"name": "email", "type": "string", "nullable": True, "metadata": {}},
        ],
    }
)


def _add_actions(num_records: int = 1000) -> list[dict]:
    return [
        {
            "path": f"part-0000{i}.parquet",
            "size": 4096,
            "stats": json.dumps({"numRecords": num_records}),
        }
        for i in range(3)
    ]


def _commit_info(
    *,
    timestamp: int = 1700000000000,
    operation: str = "WRITE",
    operation_metrics: dict | None = None,
) -> dict:
    info: dict = {"timestamp": timestamp, "operation": operation}
    if operation_metrics is not None:
        info["operationMetrics"] = operation_metrics
    return info


# ---------------------------------------------------------------------------
# Tests: generate_write_receipt
# ---------------------------------------------------------------------------


class TestGenerateWriteReceipt:
    def test_basic_fields(self) -> None:
        """Core write receipt fields are populated correctly."""
        receipt = generate_write_receipt(
            table_path="/data/events",
            version=5,
            operation="APPEND",
            commit_info=_commit_info(),
            add_actions=_add_actions(),
            remove_actions=[],
            schema_json=SAMPLE_SCHEMA_JSON,
        )

        assert receipt.table_path == "/data/events"
        assert receipt.version == 5
        assert receipt.operation == "APPEND"
        assert receipt.num_files_added == 3
        assert receipt.num_files_removed == 0
        assert receipt.num_rows_affected == 3000
        assert receipt.commit_timestamp == 1700000000000
        assert receipt.receipt_type == "delta_write_receipt"

    def test_overwrite_operation(self) -> None:
        """Overwrite operation is normalised to uppercase."""
        receipt = generate_write_receipt(
            table_path="/data/events",
            version=6,
            operation="overwrite",
            commit_info=_commit_info(),
            add_actions=_add_actions(500),
            remove_actions=[{"path": "old-file.parquet"}],
            schema_json=SAMPLE_SCHEMA_JSON,
        )

        assert receipt.operation == "OVERWRITE"
        assert receipt.num_files_removed == 1
        assert receipt.num_rows_affected == 1500

    def test_config_fields_injected(self) -> None:
        """Agent and tenant IDs come from config."""
        cfg = DeltaMAIPConfig(agent_id="agent-x", tenant_id="tenant-y")
        receipt = generate_write_receipt(
            table_path="/data/events",
            version=1,
            operation="WRITE",
            commit_info=_commit_info(),
            add_actions=[],
            remove_actions=[],
            schema_json=SAMPLE_SCHEMA_JSON,
            config=cfg,
        )

        assert receipt.agent_id == "agent-x"
        assert receipt.tenant_id == "tenant-y"

    def test_payload_hash_set(self) -> None:
        """The payload hash is a 64-char hex SHA-256 digest."""
        receipt = generate_write_receipt(
            table_path="/data/events",
            version=1,
            operation="WRITE",
            commit_info=_commit_info(),
            add_actions=[],
            remove_actions=[],
            schema_json=SAMPLE_SCHEMA_JSON,
        )

        assert receipt.payload_hash != ""
        assert len(receipt.payload_hash) == 64

    def test_partition_columns_forwarded(self) -> None:
        """Partition columns are included in the receipt."""
        receipt = generate_write_receipt(
            table_path="/data/events",
            version=1,
            operation="WRITE",
            commit_info=_commit_info(),
            add_actions=[],
            remove_actions=[],
            schema_json=SAMPLE_SCHEMA_JSON,
            partition_columns=["date", "region"],
        )

        assert receipt.partition_columns == ["date", "region"]

    def test_stats_as_dict(self) -> None:
        """Add actions with stats as a dict (not JSON string) are handled."""
        actions = [{"path": "p.parquet", "stats": {"numRecords": 42}}]
        receipt = generate_write_receipt(
            table_path="/data/events",
            version=1,
            operation="WRITE",
            commit_info=_commit_info(),
            add_actions=actions,
            remove_actions=[],
            schema_json=SAMPLE_SCHEMA_JSON,
        )

        assert receipt.num_rows_affected == 42

    def test_float_timestamp_converted(self) -> None:
        """A float timestamp in commit_info is converted to int."""
        receipt = generate_write_receipt(
            table_path="/data/events",
            version=1,
            operation="WRITE",
            commit_info={"timestamp": 1700000000000.0, "operation": "WRITE"},
            add_actions=[],
            remove_actions=[],
            schema_json=SAMPLE_SCHEMA_JSON,
        )

        assert receipt.commit_timestamp == 1700000000000
        assert isinstance(receipt.commit_timestamp, int)


# ---------------------------------------------------------------------------
# Tests: generate_merge_receipt
# ---------------------------------------------------------------------------


class TestGenerateMergeReceipt:
    def test_basic_fields(self) -> None:
        """Core merge receipt fields are populated correctly."""
        receipt = generate_merge_receipt(
            table_path="/data/customers",
            version=12,
            condition="target.id = source.id",
            commit_info=_commit_info(operation="MERGE"),
            source_description="daily_csv_ingest",
            num_target_rows_inserted=100,
            num_target_rows_updated=50,
            num_target_rows_deleted=5,
            num_source_rows=155,
        )

        assert receipt.table_path == "/data/customers"
        assert receipt.version == 12
        assert receipt.condition == "target.id = source.id"
        assert receipt.source_description == "daily_csv_ingest"
        assert receipt.num_target_rows_inserted == 100
        assert receipt.num_target_rows_updated == 50
        assert receipt.num_target_rows_deleted == 5
        assert receipt.num_source_rows == 155
        assert receipt.receipt_type == "delta_merge_receipt"

    def test_operation_metrics_fallback(self) -> None:
        """Row counts fall back to operationMetrics when explicit values are zero."""
        receipt = generate_merge_receipt(
            table_path="/data/customers",
            version=12,
            condition="target.id = source.id",
            commit_info=_commit_info(
                operation="MERGE",
                operation_metrics={
                    "numTargetRowsInserted": "200",
                    "numTargetRowsUpdated": "50",
                    "numTargetRowsDeleted": "3",
                    "numSourceRows": "253",
                },
            ),
        )

        assert receipt.num_target_rows_inserted == 200
        assert receipt.num_target_rows_updated == 50
        assert receipt.num_target_rows_deleted == 3
        assert receipt.num_source_rows == 253

    def test_explicit_values_override_metrics(self) -> None:
        """When explicit row counts are provided, operationMetrics are ignored."""
        receipt = generate_merge_receipt(
            table_path="/data/customers",
            version=12,
            condition="target.id = source.id",
            commit_info=_commit_info(
                operation="MERGE",
                operation_metrics={
                    "numTargetRowsInserted": "200",
                    "numTargetRowsUpdated": "50",
                },
            ),
            num_target_rows_inserted=999,
            num_target_rows_updated=888,
        )

        assert receipt.num_target_rows_inserted == 999
        assert receipt.num_target_rows_updated == 888

    def test_payload_hash_set(self) -> None:
        """The payload hash is a valid SHA-256 digest."""
        receipt = generate_merge_receipt(
            table_path="/data/customers",
            version=1,
            condition="1=1",
            commit_info=_commit_info(),
        )

        assert len(receipt.payload_hash) == 64

    def test_config_fields_injected(self) -> None:
        """Agent and tenant IDs come from config."""
        cfg = DeltaMAIPConfig(agent_id="merge-agent", tenant_id="t-100")
        receipt = generate_merge_receipt(
            table_path="/data/customers",
            version=1,
            condition="1=1",
            commit_info=_commit_info(),
            config=cfg,
        )

        assert receipt.agent_id == "merge-agent"
        assert receipt.tenant_id == "t-100"


# ---------------------------------------------------------------------------
# Tests: generate_schema_evolution_receipt
# ---------------------------------------------------------------------------


class TestGenerateSchemaEvolutionReceipt:
    def test_columns_added(self) -> None:
        """New columns are detected."""
        receipt = generate_schema_evolution_receipt(
            table_path="/data/events",
            version=10,
            previous_schema_json=SAMPLE_SCHEMA_JSON,
            new_schema_json=EVOLVED_SCHEMA_JSON,
        )

        assert "email" in receipt.columns_added

    def test_columns_removed(self) -> None:
        """Removed columns are detected."""
        receipt = generate_schema_evolution_receipt(
            table_path="/data/events",
            version=10,
            previous_schema_json=SAMPLE_SCHEMA_JSON,
            new_schema_json=EVOLVED_SCHEMA_JSON,
        )

        assert "amount" in receipt.columns_removed

    def test_type_changes(self) -> None:
        """Type changes are detected (id: integer -> long)."""
        receipt = generate_schema_evolution_receipt(
            table_path="/data/events",
            version=10,
            previous_schema_json=SAMPLE_SCHEMA_JSON,
            new_schema_json=EVOLVED_SCHEMA_JSON,
        )

        type_changes = {tc.column_name: tc for tc in receipt.columns_type_changed}
        assert "id" in type_changes
        assert type_changes["id"].old_type == "integer"
        assert type_changes["id"].new_type == "long"

    def test_schema_hashes_differ(self) -> None:
        """Previous and new schema hashes are different."""
        receipt = generate_schema_evolution_receipt(
            table_path="/data/events",
            version=10,
            previous_schema_json=SAMPLE_SCHEMA_JSON,
            new_schema_json=EVOLVED_SCHEMA_JSON,
        )

        assert receipt.previous_schema_hash != receipt.new_schema_hash
        assert len(receipt.previous_schema_hash) == 64
        assert len(receipt.new_schema_hash) == 64

    def test_payload_hash_set(self) -> None:
        """The payload hash is a valid SHA-256 digest."""
        receipt = generate_schema_evolution_receipt(
            table_path="/data/events",
            version=10,
            previous_schema_json=SAMPLE_SCHEMA_JSON,
            new_schema_json=EVOLVED_SCHEMA_JSON,
        )

        assert len(receipt.payload_hash) == 64

    def test_identical_schemas_no_changes(self) -> None:
        """Identical schemas produce empty diff lists."""
        receipt = generate_schema_evolution_receipt(
            table_path="/data/events",
            version=10,
            previous_schema_json=SAMPLE_SCHEMA_JSON,
            new_schema_json=SAMPLE_SCHEMA_JSON,
        )

        assert receipt.columns_added == []
        assert receipt.columns_removed == []
        assert receipt.columns_type_changed == []
        assert receipt.previous_schema_hash == receipt.new_schema_hash


# ---------------------------------------------------------------------------
# Tests: hash_receipt_payload
# ---------------------------------------------------------------------------


class TestHashReceiptPayload:
    def test_deterministic(self) -> None:
        """The same receipt always produces the same hash."""
        receipt = DeltaWriteReceipt(
            table_path="/data/events",
            version=1,
            operation="WRITE",
        )
        h1 = hash_receipt_payload(receipt)
        h2 = hash_receipt_payload(receipt)
        assert h1 == h2

    def test_hex_length(self) -> None:
        """SHA-256 hex digest is 64 characters."""
        receipt = DeltaWriteReceipt(
            table_path="/data/events",
            version=1,
            operation="WRITE",
        )
        h = hash_receipt_payload(receipt)
        assert len(h) == 64

    def test_different_inputs_produce_different_hashes(self) -> None:
        """Different receipts produce different hashes."""
        r1 = DeltaWriteReceipt(table_path="/data/events", version=1, operation="WRITE")
        r2 = DeltaWriteReceipt(table_path="/data/events", version=2, operation="WRITE")
        assert hash_receipt_payload(r1) != hash_receipt_payload(r2)

    def test_hash_excludes_payload_hash_field(self) -> None:
        """Setting payload_hash does not change the computed digest."""
        r1 = DeltaWriteReceipt(table_path="/data/events", version=1, operation="WRITE")
        h_before = hash_receipt_payload(r1)
        r1.payload_hash = "should-be-ignored"
        h_after = hash_receipt_payload(r1)
        assert h_before == h_after

    def test_works_with_merge_receipt(self) -> None:
        """hash_receipt_payload works with DeltaMergeReceipt."""
        receipt = DeltaMergeReceipt(
            table_path="/data/customers",
            version=5,
            condition="target.id = source.id",
        )
        h = hash_receipt_payload(receipt)
        assert len(h) == 64

    def test_canonical_json_order_independent(self) -> None:
        """Logically identical receipts hash the same regardless of construction order."""
        r1 = DeltaWriteReceipt(
            table_path="/data/events",
            version=1,
            operation="WRITE",
            agent_id="a",
            tenant_id="t",
        )
        r2 = DeltaWriteReceipt(
            tenant_id="t",
            agent_id="a",
            operation="WRITE",
            version=1,
            table_path="/data/events",
        )
        assert hash_receipt_payload(r1) == hash_receipt_payload(r2)

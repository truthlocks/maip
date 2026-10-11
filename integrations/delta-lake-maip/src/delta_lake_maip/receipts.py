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

"""Receipt generation utilities for converting Delta Lake operations into MAIP receipts."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Union

from delta_lake_maip.config import DeltaMAIPConfig
from delta_lake_maip.schemas import (
    ColumnTypeChange,
    DeltaMergeReceipt,
    DeltaSchemaEvolutionReceipt,
    DeltaWriteReceipt,
)

logger = logging.getLogger(__name__)

AnyDeltaReceipt = Union[DeltaWriteReceipt, DeltaMergeReceipt, DeltaSchemaEvolutionReceipt]


def hash_receipt_payload(receipt: AnyDeltaReceipt) -> str:
    """Compute a SHA-256 digest of the canonical JSON representation.

    The receipt is serialised with sorted keys and no whitespace to ensure
    deterministic hashing regardless of field insertion order.

    Args:
        receipt: The receipt to hash.

    Returns:
        A lowercase hex-encoded SHA-256 digest.
    """
    payload = receipt.model_dump(mode="json", exclude={"payload_hash"})
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _compute_schema_hash(schema_json: str) -> str:
    """Compute a deterministic SHA-256 hash of a Delta table schema.

    The schema JSON is parsed, re-serialised with sorted keys and no
    whitespace, then hashed.  This ensures that logically equivalent
    schemas always produce the same hash regardless of original formatting.

    Args:
        schema_json: Raw JSON string of the Delta table schema.

    Returns:
        A lowercase hex-encoded SHA-256 digest of the canonical schema.
    """
    parsed = json.loads(schema_json)
    canonical = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def generate_write_receipt(
    *,
    table_path: str,
    version: int,
    operation: str,
    commit_info: dict[str, Any],
    add_actions: list[dict[str, Any]],
    remove_actions: list[dict[str, Any]],
    schema_json: str,
    partition_columns: list[str] | None = None,
    table_name: str = "",
    config: DeltaMAIPConfig | None = None,
) -> DeltaWriteReceipt:
    """Build a ``DeltaWriteReceipt`` from Delta Lake commit metadata.

    This function extracts file-level and row-level statistics from the
    add/remove actions produced by a Delta commit and assembles them into
    a receipt suitable for submission to the MAIP API.

    Args:
        table_path: Filesystem path or URI of the Delta table.
        version: Delta version number after the commit.
        operation: The write operation type (``WRITE``, ``APPEND``, ``OVERWRITE``).
        commit_info: The ``commitInfo`` action from the transaction log.
        add_actions: List of ``add`` actions from the transaction log.
        remove_actions: List of ``remove`` actions from the transaction log.
        schema_json: JSON string of the table schema at this version.
        partition_columns: Partition column names, if any.
        table_name: Optional logical name for the table.
        config: Optional plugin config used to populate agent/tenant fields.

    Returns:
        A fully populated ``DeltaWriteReceipt`` with its ``payload_hash`` set.
    """
    cfg = config or DeltaMAIPConfig()

    num_rows = 0
    for action in add_actions:
        stats = action.get("stats")
        if stats:
            if isinstance(stats, str):
                stats = json.loads(stats)
            num_rows += stats.get("numRecords", 0)

    timestamp = commit_info.get("timestamp", 0)
    if isinstance(timestamp, float):
        timestamp = int(timestamp)

    receipt = DeltaWriteReceipt(
        table_path=table_path,
        table_name=table_name,
        version=version,
        operation=operation.upper(),
        num_files_added=len(add_actions),
        num_files_removed=len(remove_actions),
        num_rows_affected=num_rows,
        partition_columns=partition_columns or [],
        schema_hash=_compute_schema_hash(schema_json),
        commit_timestamp=timestamp,
        receipt_type="delta_write_receipt",
        agent_id=cfg.agent_id,
        tenant_id=cfg.tenant_id,
    )

    receipt.payload_hash = hash_receipt_payload(receipt)
    return receipt


def generate_merge_receipt(
    *,
    table_path: str,
    version: int,
    condition: str,
    commit_info: dict[str, Any],
    source_description: str = "",
    num_target_rows_inserted: int = 0,
    num_target_rows_updated: int = 0,
    num_target_rows_deleted: int = 0,
    num_source_rows: int = 0,
    table_name: str = "",
    config: DeltaMAIPConfig | None = None,
) -> DeltaMergeReceipt:
    """Build a ``DeltaMergeReceipt`` from Delta Lake MERGE INTO metadata.

    Args:
        table_path: Filesystem path or URI of the target Delta table.
        version: Delta version number after the merge commit.
        condition: The SQL merge condition expression.
        commit_info: The ``commitInfo`` action from the transaction log.
        source_description: Human-readable description of the merge source.
        num_target_rows_inserted: Rows inserted into the target.
        num_target_rows_updated: Rows updated in the target.
        num_target_rows_deleted: Rows deleted from the target.
        num_source_rows: Total rows in the merge source.
        table_name: Optional logical name for the table.
        config: Optional plugin config used to populate agent/tenant fields.

    Returns:
        A fully populated ``DeltaMergeReceipt`` with its ``payload_hash`` set.
    """
    cfg = config or DeltaMAIPConfig()

    timestamp = commit_info.get("timestamp", 0)
    if isinstance(timestamp, float):
        timestamp = int(timestamp)

    # Extract row counts from operationMetrics when explicit values are zero
    op_metrics = commit_info.get("operationMetrics", {})
    if num_target_rows_inserted == 0:
        num_target_rows_inserted = int(op_metrics.get("numTargetRowsInserted", 0))
    if num_target_rows_updated == 0:
        num_target_rows_updated = int(op_metrics.get("numTargetRowsUpdated", 0))
    if num_target_rows_deleted == 0:
        num_target_rows_deleted = int(op_metrics.get("numTargetRowsDeleted", 0))
    if num_source_rows == 0:
        num_source_rows = int(op_metrics.get("numSourceRows", 0))

    receipt = DeltaMergeReceipt(
        table_path=table_path,
        table_name=table_name,
        version=version,
        source_description=source_description,
        condition=condition,
        num_target_rows_inserted=num_target_rows_inserted,
        num_target_rows_updated=num_target_rows_updated,
        num_target_rows_deleted=num_target_rows_deleted,
        num_source_rows=num_source_rows,
        commit_timestamp=timestamp,
        receipt_type="delta_merge_receipt",
        agent_id=cfg.agent_id,
        tenant_id=cfg.tenant_id,
    )

    receipt.payload_hash = hash_receipt_payload(receipt)
    return receipt


def generate_schema_evolution_receipt(
    *,
    table_path: str,
    version: int,
    previous_schema_json: str,
    new_schema_json: str,
    commit_timestamp: int = 0,
    table_name: str = "",
    config: DeltaMAIPConfig | None = None,
) -> DeltaSchemaEvolutionReceipt:
    """Build a ``DeltaSchemaEvolutionReceipt`` by diffing two Delta schemas.

    The function compares the field sets of two schema JSON strings to detect
    added columns, removed columns, and columns whose data type has changed.

    Args:
        table_path: Filesystem path or URI of the Delta table.
        version: Delta version number after the schema change.
        previous_schema_json: JSON string of the schema before the change.
        new_schema_json: JSON string of the schema after the change.
        commit_timestamp: Commit timestamp in milliseconds since epoch.
        table_name: Optional logical name for the table.
        config: Optional plugin config used to populate agent/tenant fields.

    Returns:
        A fully populated ``DeltaSchemaEvolutionReceipt`` with its ``payload_hash`` set.
    """
    cfg = config or DeltaMAIPConfig()

    previous_schema = json.loads(previous_schema_json)
    new_schema = json.loads(new_schema_json)

    prev_fields = _extract_fields(previous_schema)
    new_fields = _extract_fields(new_schema)

    prev_names = set(prev_fields.keys())
    new_names = set(new_fields.keys())

    columns_added = sorted(new_names - prev_names)
    columns_removed = sorted(prev_names - new_names)

    columns_type_changed: list[ColumnTypeChange] = []
    for col_name in sorted(prev_names & new_names):
        old_type = prev_fields[col_name]
        new_type = new_fields[col_name]
        if old_type != new_type:
            columns_type_changed.append(
                ColumnTypeChange(
                    column_name=col_name,
                    old_type=old_type,
                    new_type=new_type,
                )
            )

    receipt = DeltaSchemaEvolutionReceipt(
        table_path=table_path,
        table_name=table_name,
        version=version,
        previous_schema_hash=_compute_schema_hash(previous_schema_json),
        new_schema_hash=_compute_schema_hash(new_schema_json),
        columns_added=columns_added,
        columns_removed=columns_removed,
        columns_type_changed=columns_type_changed,
        commit_timestamp=commit_timestamp,
        receipt_type="delta_schema_evolution_receipt",
        agent_id=cfg.agent_id,
        tenant_id=cfg.tenant_id,
    )

    receipt.payload_hash = hash_receipt_payload(receipt)
    return receipt


def _extract_fields(schema: dict[str, Any]) -> dict[str, str]:
    """Extract a mapping of field name to type string from a Delta schema dict.

    Handles both the ``{\"type\": \"struct\", \"fields\": [...]}`` format and
    a flat list-of-fields format.

    Args:
        schema: Parsed JSON schema dictionary.

    Returns:
        A dict mapping column name to its type as a string.
    """
    fields: list[dict[str, Any]] = []
    if isinstance(schema, dict):
        fields = schema.get("fields", [])
    elif isinstance(schema, list):
        fields = schema

    result: dict[str, str] = {}
    for field in fields:
        name = field.get("name", "")
        field_type = field.get("type", "")
        if isinstance(field_type, dict):
            field_type = json.dumps(field_type, sort_keys=True, separators=(",", ":"))
        else:
            field_type = str(field_type)
        if name:
            result[name] = field_type
    return result

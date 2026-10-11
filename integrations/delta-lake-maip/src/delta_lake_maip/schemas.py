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

"""Pydantic models for MAIP receipt payloads and API responses."""

from __future__ import annotations

from datetime import datetime, timezone

UTC = timezone.utc

from pydantic import BaseModel, Field


class DeltaWriteReceipt(BaseModel):
    """Payload representing a Delta Lake write operation for MAIP receipt generation.

    Captures essential metadata of a write/append/overwrite operation so that it
    can be submitted to the MAIP API for cryptographic anchoring.
    """

    table_path: str = Field(..., description="Path or URI to the Delta table")
    table_name: str = Field(default="", description="Logical name of the Delta table")
    version: int = Field(..., description="Delta version number after the commit")
    operation: str = Field(
        ...,
        description="Write operation type: WRITE, APPEND, or OVERWRITE",
    )
    num_files_added: int = Field(default=0, description="Number of data files added")
    num_files_removed: int = Field(default=0, description="Number of data files removed")
    num_rows_affected: int = Field(default=0, description="Number of rows written")
    partition_columns: list[str] = Field(
        default_factory=list,
        description="Partition column names of the Delta table",
    )
    schema_hash: str = Field(
        default="",
        description="SHA-256 hash of the Delta table schema JSON",
    )
    commit_timestamp: int = Field(
        default=0,
        description="Commit timestamp in milliseconds since epoch",
    )
    receipt_type: str = Field(
        default="delta_write_receipt",
        description="MAIP receipt type discriminator",
    )
    agent_id: str = Field(default="", description="Calling agent identifier")
    tenant_id: str = Field(default="", description="Tenant identifier")
    payload_hash: str = Field(default="", description="SHA-256 hash of the canonical payload")


class DeltaMergeReceipt(BaseModel):
    """Payload representing a Delta Lake MERGE INTO operation for MAIP receipt generation.

    Captures the merge condition, row-level statistics, and commit metadata so
    that the merge can be cryptographically anchored via the MAIP API.
    """

    table_path: str = Field(..., description="Path or URI to the target Delta table")
    table_name: str = Field(default="", description="Logical name of the Delta table")
    version: int = Field(..., description="Delta version number after the merge commit")
    source_description: str = Field(
        default="",
        description="Description of the data source used in the merge",
    )
    condition: str = Field(..., description="SQL merge condition expression")
    num_target_rows_inserted: int = Field(
        default=0,
        description="Number of rows inserted into the target",
    )
    num_target_rows_updated: int = Field(
        default=0,
        description="Number of rows updated in the target",
    )
    num_target_rows_deleted: int = Field(
        default=0,
        description="Number of rows deleted from the target",
    )
    num_source_rows: int = Field(default=0, description="Total rows in the merge source")
    commit_timestamp: int = Field(
        default=0,
        description="Commit timestamp in milliseconds since epoch",
    )
    receipt_type: str = Field(
        default="delta_merge_receipt",
        description="MAIP receipt type discriminator",
    )
    agent_id: str = Field(default="", description="Calling agent identifier")
    tenant_id: str = Field(default="", description="Tenant identifier")
    payload_hash: str = Field(default="", description="SHA-256 hash of the canonical payload")


class ColumnTypeChange(BaseModel):
    """Represents a single column type change in a schema evolution event."""

    column_name: str = Field(..., description="Name of the column whose type changed")
    old_type: str = Field(..., description="Previous data type")
    new_type: str = Field(..., description="New data type")


class DeltaSchemaEvolutionReceipt(BaseModel):
    """Payload representing a Delta Lake schema evolution event for MAIP receipt generation.

    Captures added, removed, and type-changed columns between two Delta versions
    so that schema evolution can be cryptographically anchored via the MAIP API.
    """

    table_path: str = Field(..., description="Path or URI to the Delta table")
    table_name: str = Field(default="", description="Logical name of the Delta table")
    version: int = Field(..., description="Delta version number after schema change")
    previous_schema_hash: str = Field(
        ...,
        description="SHA-256 hash of the schema before the change",
    )
    new_schema_hash: str = Field(
        ...,
        description="SHA-256 hash of the schema after the change",
    )
    columns_added: list[str] = Field(
        default_factory=list,
        description="Names of columns added in this version",
    )
    columns_removed: list[str] = Field(
        default_factory=list,
        description="Names of columns removed in this version",
    )
    columns_type_changed: list[ColumnTypeChange] = Field(
        default_factory=list,
        description="Columns whose data type changed",
    )
    commit_timestamp: int = Field(
        default=0,
        description="Commit timestamp in milliseconds since epoch",
    )
    receipt_type: str = Field(
        default="delta_schema_evolution_receipt",
        description="MAIP receipt type discriminator",
    )
    agent_id: str = Field(default="", description="Calling agent identifier")
    tenant_id: str = Field(default="", description="Tenant identifier")
    payload_hash: str = Field(default="", description="SHA-256 hash of the canonical payload")


from maip_ai_connectors.schemas import ReceiptResponse, ReceiptVerifyResponse

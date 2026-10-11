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
from typing import Any, Literal

from pydantic import BaseModel, Field


class DVCFileEntry(BaseModel):
    """Metadata for a single file tracked by DVC (dependency or output)."""

    path: str = Field(..., description="Relative path of the file within the repository")
    md5: str = Field(..., description="MD5 hash of the file contents")
    size: int = Field(..., description="File size in bytes")


class DVCPipelineReceipt(BaseModel):
    """Payload representing a DVC pipeline stage execution for MAIP receipt generation.

    This model captures the essential metadata of a DVC pipeline stage so that it
    can be submitted to the MAIP API for cryptographic anchoring.
    """

    stage_name: str = Field(..., description="Name of the DVC pipeline stage")
    pipeline_file: str = Field(
        default="dvc.yaml",
        description="Path to the DVC pipeline definition file",
    )
    deps: list[DVCFileEntry] = Field(
        default_factory=list,
        description="Stage dependencies with their hashes and sizes",
    )
    outs: list[DVCFileEntry] = Field(
        default_factory=list,
        description="Stage outputs with their hashes and sizes",
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Parameter values used by the stage",
    )
    metrics: dict[str, Any] = Field(
        default_factory=dict,
        description="Metric values produced by the stage",
    )
    cmd: str = Field(default="", description="The command executed by the stage")
    receipt_type: str = Field(
        default="dvc_pipeline_receipt",
        description="MAIP receipt type discriminator",
    )
    agent_id: str = Field(default="", description="Calling agent identifier")
    tenant_id: str = Field(default="", description="Tenant identifier")
    payload_hash: str = Field(default="", description="SHA-256 hash of the canonical payload")


class DVCDataReceipt(BaseModel):
    """Payload representing a DVC data operation for MAIP receipt generation.

    Captures metadata when files are pushed to, pulled from, or checked out of
    DVC remote storage for cryptographic anchoring.
    """

    file_path: str = Field(..., description="Path of the tracked file")
    md5: str = Field(..., description="MD5 hash of the file contents")
    size: int = Field(..., description="File size in bytes")
    remote: str = Field(default="", description="DVC remote name")
    operation: Literal["push", "pull", "checkout"] = Field(
        ...,
        description="The DVC operation that triggered this receipt",
    )
    receipt_type: str = Field(
        default="dvc_data_receipt",
        description="MAIP receipt type discriminator",
    )
    agent_id: str = Field(default="", description="Calling agent identifier")
    tenant_id: str = Field(default="", description="Tenant identifier")
    payload_hash: str = Field(default="", description="SHA-256 hash of the canonical payload")


from maip_ai_connectors.schemas import ReceiptResponse, ReceiptVerifyResponse

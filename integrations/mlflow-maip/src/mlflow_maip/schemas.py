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


class MLPipelineReceipt(BaseModel):
    """Payload representing an ML pipeline execution for MAIP receipt generation.

    This model captures the essential metadata of an MLflow run so that it can
    be submitted to the MAIP API for cryptographic anchoring.
    """

    run_id: str = Field(..., description="MLflow run identifier")
    experiment_id: str = Field(..., description="MLflow experiment identifier")
    model_name: str = Field(default="", description="Registered model name, if any")
    model_version: str = Field(default="", description="Registered model version, if any")
    metrics: dict[str, float] = Field(
        default_factory=dict,
        description="Final metric values logged during the run",
    )
    params: dict[str, str] = Field(
        default_factory=dict,
        description="Parameters recorded for the run",
    )
    artifact_uri: str = Field(default="", description="URI of the run artifact store")
    start_time: int = Field(..., description="Run start timestamp in milliseconds since epoch")
    end_time: int = Field(default=0, description="Run end timestamp in milliseconds since epoch")
    status: str = Field(default="FINISHED", description="Terminal status of the run")
    receipt_type: str = Field(
        default="ml_pipeline_receipt",
        description="MAIP receipt type discriminator",
    )
    agent_id: str = Field(default="", description="Calling agent identifier")
    tenant_id: str = Field(default="", description="Tenant identifier")
    payload_hash: str = Field(default="", description="SHA-256 hash of the canonical payload")


from maip_ai_connectors.schemas import ReceiptResponse, ReceiptVerifyResponse

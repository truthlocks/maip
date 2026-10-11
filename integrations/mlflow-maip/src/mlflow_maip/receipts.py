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

"""Receipt generation utilities for converting MLflow runs into MAIP receipts."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import TYPE_CHECKING

from mlflow_maip.config import MAIPConfig
from mlflow_maip.schemas import MLPipelineReceipt

if TYPE_CHECKING:
    from mlflow.entities import Run

logger = logging.getLogger(__name__)


def generate_receipt_from_run(
    run: Run,
    config: MAIPConfig | None = None,
) -> MLPipelineReceipt:
    """Extract metadata from an MLflow run and build an ``MLPipelineReceipt``.

    This function reads the run's info, parameters, metrics, and artifact URI
    to construct a receipt suitable for submission to the MAIP API.

    Args:
        run: An MLflow ``Run`` entity.
        config: Optional plugin config used to populate agent/tenant fields.

    Returns:
        A fully populated ``MLPipelineReceipt`` with its ``payload_hash`` set.
    """
    cfg = config or MAIPConfig()
    info = run.info
    data = run.data

    metrics: dict[str, float] = {}
    if data.metrics:
        metrics = {k: float(v) for k, v in data.metrics.items()}

    params: dict[str, str] = {}
    if data.params:
        params = dict(data.params)

    # Determine model name / version from run tags when available
    tags = data.tags or {}
    model_name = tags.get("mlflow.runName", "")
    model_version = tags.get("mlflow.source.git.commit", "")

    receipt = MLPipelineReceipt(
        run_id=info.run_id,
        experiment_id=info.experiment_id,
        model_name=model_name,
        model_version=model_version,
        metrics=metrics,
        params=params,
        artifact_uri=info.artifact_uri or "",
        start_time=info.start_time or 0,
        end_time=info.end_time or 0,
        status=info.status or "FINISHED",
        receipt_type=cfg.receipt_type,
        agent_id=cfg.agent_id,
        tenant_id=cfg.tenant_id,
    )

    receipt.payload_hash = hash_receipt_payload(receipt)
    return receipt


def hash_receipt_payload(receipt: MLPipelineReceipt) -> str:
    """Compute a SHA-256 digest of the canonical JSON representation.

    The receipt is serialised with sorted keys and no whitespace to ensure
    deterministic hashing regardless of field insertion order.

    Args:
        receipt: The receipt to hash.

    Returns:
        A lowercase hex-encoded SHA-256 digest.
    """
    # Exclude the hash field itself from the canonical form
    payload = receipt.model_dump(mode="json", exclude={"payload_hash"})
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

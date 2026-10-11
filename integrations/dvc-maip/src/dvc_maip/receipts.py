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

"""Receipt generation utilities for converting DVC operations into MAIP receipts."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Literal, Union

from dvc_maip.config import MAIPConfig
from dvc_maip.schemas import DVCDataReceipt, DVCFileEntry, DVCPipelineReceipt

logger = logging.getLogger(__name__)


def generate_pipeline_receipt(
    stage_name: str,
    lock_data: dict[str, Any],
    *,
    pipeline_file: str = "dvc.yaml",
    config: MAIPConfig | None = None,
) -> DVCPipelineReceipt:
    """Build a ``DVCPipelineReceipt`` from DVC lock data for a pipeline stage.

    The lock data is the parsed content of ``dvc.lock`` for a single stage,
    following the schema DVC uses internally.

    Args:
        stage_name: Name of the pipeline stage.
        lock_data: Parsed lock data dict for the stage (from ``dvc.lock``).
        pipeline_file: Path to the pipeline definition file.
        config: Optional plugin config used to populate agent/tenant fields.

    Returns:
        A fully populated ``DVCPipelineReceipt`` with its ``payload_hash`` set.
    """
    cfg = config or MAIPConfig()

    deps: list[DVCFileEntry] = []
    for dep in lock_data.get("deps", []):
        deps.append(
            DVCFileEntry(
                path=dep.get("path", ""),
                md5=dep.get("md5", dep.get("hash", "")),
                size=dep.get("size", 0),
            )
        )

    outs: list[DVCFileEntry] = []
    for out in lock_data.get("outs", []):
        outs.append(
            DVCFileEntry(
                path=out.get("path", ""),
                md5=out.get("md5", out.get("hash", "")),
                size=out.get("size", 0),
            )
        )

    params: dict[str, Any] = {}
    for param_group in lock_data.get("params", []):
        if isinstance(param_group, dict):
            # DVC params format: {"params.yaml": {"lr": 0.001, ...}}
            for _file, values in param_group.items():
                if isinstance(values, dict):
                    params.update(values)
                else:
                    params[_file] = values

    metrics: dict[str, Any] = {}
    for metric_entry in lock_data.get("metrics", []):
        if isinstance(metric_entry, dict):
            for _file, values in metric_entry.items():
                if isinstance(values, dict):
                    metrics.update(values)
                else:
                    metrics[_file] = values

    cmd = lock_data.get("cmd", "")

    receipt = DVCPipelineReceipt(
        stage_name=stage_name,
        pipeline_file=pipeline_file,
        deps=deps,
        outs=outs,
        params=params,
        metrics=metrics,
        cmd=cmd,
        agent_id=cfg.agent_id,
        tenant_id=cfg.tenant_id,
    )

    receipt.payload_hash = hash_receipt_payload(receipt)
    return receipt


def generate_data_receipt(
    file_path: str,
    md5: str,
    size: int,
    operation: Literal["push", "pull", "checkout"],
    *,
    remote: str = "",
    config: MAIPConfig | None = None,
) -> DVCDataReceipt:
    """Build a ``DVCDataReceipt`` for a DVC data transfer or checkout operation.

    Args:
        file_path: Path of the tracked file.
        md5: MD5 hash of the file contents.
        size: File size in bytes.
        operation: The DVC operation that triggered the receipt.
        remote: Name of the DVC remote, if applicable.
        config: Optional plugin config used to populate agent/tenant fields.

    Returns:
        A fully populated ``DVCDataReceipt`` with its ``payload_hash`` set.
    """
    cfg = config or MAIPConfig()

    receipt = DVCDataReceipt(
        file_path=file_path,
        md5=md5,
        size=size,
        remote=remote,
        operation=operation,
        agent_id=cfg.agent_id,
        tenant_id=cfg.tenant_id,
    )

    receipt.payload_hash = hash_receipt_payload(receipt)
    return receipt


def hash_receipt_payload(receipt: Union[DVCPipelineReceipt, DVCDataReceipt]) -> str:
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

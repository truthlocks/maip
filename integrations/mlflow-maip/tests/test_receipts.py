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

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from mlflow_maip.config import MAIPConfig
from mlflow_maip.receipts import generate_receipt_from_run, hash_receipt_payload
from mlflow_maip.schemas import MLPipelineReceipt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_run(
    *,
    run_id: str = "run-001",
    experiment_id: str = "exp-001",
    artifact_uri: str = "s3://bucket/run-001",
    start_time: int = 1700000000000,
    end_time: int = 1700003600000,
    status: str = "FINISHED",
    metrics: dict | None = None,
    params: dict | None = None,
    tags: dict | None = None,
) -> MagicMock:
    """Build a lightweight mock of ``mlflow.entities.Run``."""
    run = MagicMock()
    run.info = SimpleNamespace(
        run_id=run_id,
        experiment_id=experiment_id,
        artifact_uri=artifact_uri,
        start_time=start_time,
        end_time=end_time,
        status=status,
    )
    run.data = SimpleNamespace(
        metrics=metrics if metrics is not None else {"accuracy": 0.95, "loss": 0.05},
        params=params if params is not None else {"lr": "0.001", "epochs": "10"},
        tags=tags if tags is not None else {"mlflow.runName": "my-model"},
    )
    return run


# ---------------------------------------------------------------------------
# Tests: generate_receipt_from_run
# ---------------------------------------------------------------------------


class TestGenerateReceiptFromRun:
    def test_basic_fields(self) -> None:
        run = _mock_run()
        receipt = generate_receipt_from_run(run)

        assert receipt.run_id == "run-001"
        assert receipt.experiment_id == "exp-001"
        assert receipt.artifact_uri == "s3://bucket/run-001"
        assert receipt.start_time == 1700000000000
        assert receipt.end_time == 1700003600000
        assert receipt.status == "FINISHED"

    def test_metrics_and_params(self) -> None:
        run = _mock_run(metrics={"f1": 0.88}, params={"batch_size": "32"})
        receipt = generate_receipt_from_run(run)

        assert receipt.metrics == {"f1": 0.88}
        assert receipt.params == {"batch_size": "32"}

    def test_model_name_from_tags(self) -> None:
        run = _mock_run(tags={"mlflow.runName": "fraud-detector"})
        receipt = generate_receipt_from_run(run)

        assert receipt.model_name == "fraud-detector"

    def test_config_fields_injected(self) -> None:
        cfg = MAIPConfig(
            agent_id="agent-x",
            tenant_id="tenant-y",
            receipt_type="custom_type",
        )
        run = _mock_run()
        receipt = generate_receipt_from_run(run, cfg)

        assert receipt.agent_id == "agent-x"
        assert receipt.tenant_id == "tenant-y"
        assert receipt.receipt_type == "custom_type"

    def test_payload_hash_set(self) -> None:
        run = _mock_run()
        receipt = generate_receipt_from_run(run)

        assert receipt.payload_hash != ""
        assert len(receipt.payload_hash) == 64  # SHA-256 hex digest

    def test_empty_metrics_and_params(self) -> None:
        run = _mock_run(metrics={}, params={}, tags={})
        receipt = generate_receipt_from_run(run)

        assert receipt.metrics == {}
        assert receipt.params == {}
        assert receipt.model_name == ""

    def test_none_tags(self) -> None:
        run = _mock_run()
        run.data.tags = None
        receipt = generate_receipt_from_run(run)

        assert receipt.model_name == ""
        assert receipt.model_version == ""


# ---------------------------------------------------------------------------
# Tests: hash_receipt_payload
# ---------------------------------------------------------------------------


class TestHashReceiptPayload:
    def test_deterministic(self) -> None:
        receipt = MLPipelineReceipt(
            run_id="run-001",
            experiment_id="exp-001",
            start_time=1700000000000,
        )
        h1 = hash_receipt_payload(receipt)
        h2 = hash_receipt_payload(receipt)
        assert h1 == h2

    def test_hex_length(self) -> None:
        receipt = MLPipelineReceipt(
            run_id="run-001",
            experiment_id="exp-001",
            start_time=1700000000000,
        )
        h = hash_receipt_payload(receipt)
        assert len(h) == 64

    def test_different_inputs_produce_different_hashes(self) -> None:
        r1 = MLPipelineReceipt(
            run_id="run-001",
            experiment_id="exp-001",
            start_time=1700000000000,
        )
        r2 = MLPipelineReceipt(
            run_id="run-002",
            experiment_id="exp-001",
            start_time=1700000000000,
        )
        assert hash_receipt_payload(r1) != hash_receipt_payload(r2)

    def test_hash_excludes_payload_hash_field(self) -> None:
        """Setting payload_hash should not change the computed digest."""
        r1 = MLPipelineReceipt(
            run_id="run-001",
            experiment_id="exp-001",
            start_time=1700000000000,
        )
        h_before = hash_receipt_payload(r1)
        r1.payload_hash = "should-be-ignored"
        h_after = hash_receipt_payload(r1)
        assert h_before == h_after

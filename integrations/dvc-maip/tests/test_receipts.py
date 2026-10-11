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

import pytest

from dvc_maip.config import MAIPConfig
from dvc_maip.receipts import generate_data_receipt, generate_pipeline_receipt, hash_receipt_payload
from dvc_maip.schemas import DVCDataReceipt, DVCFileEntry, DVCPipelineReceipt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sample_lock_data() -> dict:
    """Return a realistic DVC lock data structure for a 'train' stage."""
    return {
        "cmd": "python train.py --lr 0.001",
        "deps": [
            {"path": "data/train.csv", "md5": "aabbccdd", "size": 1048576},
            {"path": "src/train.py", "md5": "11223344", "size": 2048},
        ],
        "outs": [
            {"path": "models/model.pkl", "md5": "deadbeef", "size": 524288},
        ],
        "params": [
            {"params.yaml": {"lr": 0.001, "epochs": 10}},
        ],
        "metrics": [
            {"metrics.json": {"accuracy": 0.95, "loss": 0.05}},
        ],
    }


# ---------------------------------------------------------------------------
# Tests: generate_pipeline_receipt
# ---------------------------------------------------------------------------


class TestGeneratePipelineReceipt:
    def test_basic_fields(self) -> None:
        """Verify stage name, cmd, and pipeline file are set correctly."""
        lock = _sample_lock_data()
        receipt = generate_pipeline_receipt("train", lock)

        assert receipt.stage_name == "train"
        assert receipt.cmd == "python train.py --lr 0.001"
        assert receipt.pipeline_file == "dvc.yaml"
        assert receipt.receipt_type == "dvc_pipeline_receipt"

    def test_deps_parsed(self) -> None:
        """Verify dependencies are parsed from lock data."""
        lock = _sample_lock_data()
        receipt = generate_pipeline_receipt("train", lock)

        assert len(receipt.deps) == 2
        assert receipt.deps[0].path == "data/train.csv"
        assert receipt.deps[0].md5 == "aabbccdd"
        assert receipt.deps[0].size == 1048576
        assert receipt.deps[1].path == "src/train.py"

    def test_outs_parsed(self) -> None:
        """Verify outputs are parsed from lock data."""
        lock = _sample_lock_data()
        receipt = generate_pipeline_receipt("train", lock)

        assert len(receipt.outs) == 1
        assert receipt.outs[0].path == "models/model.pkl"
        assert receipt.outs[0].md5 == "deadbeef"
        assert receipt.outs[0].size == 524288

    def test_params_parsed(self) -> None:
        """Verify params are flattened from lock data."""
        lock = _sample_lock_data()
        receipt = generate_pipeline_receipt("train", lock)

        assert receipt.params == {"lr": 0.001, "epochs": 10}

    def test_metrics_parsed(self) -> None:
        """Verify metrics are flattened from lock data."""
        lock = _sample_lock_data()
        receipt = generate_pipeline_receipt("train", lock)

        assert receipt.metrics == {"accuracy": 0.95, "loss": 0.05}

    def test_config_fields_injected(self) -> None:
        """Verify agent_id and tenant_id come from config."""
        cfg = MAIPConfig(agent_id="agent-x", tenant_id="tenant-y")
        lock = _sample_lock_data()
        receipt = generate_pipeline_receipt("train", lock, config=cfg)

        assert receipt.agent_id == "agent-x"
        assert receipt.tenant_id == "tenant-y"

    def test_payload_hash_set(self) -> None:
        """Verify the payload_hash is computed and is a 64-char hex digest."""
        lock = _sample_lock_data()
        receipt = generate_pipeline_receipt("train", lock)

        assert receipt.payload_hash != ""
        assert len(receipt.payload_hash) == 64

    def test_custom_pipeline_file(self) -> None:
        """Verify a custom pipeline file path is recorded."""
        lock = _sample_lock_data()
        receipt = generate_pipeline_receipt(
            "train",
            lock,
            pipeline_file="pipelines/ml.yaml",
        )

        assert receipt.pipeline_file == "pipelines/ml.yaml"

    def test_empty_lock_data(self) -> None:
        """Verify graceful handling of empty lock data."""
        receipt = generate_pipeline_receipt("empty", {})

        assert receipt.stage_name == "empty"
        assert receipt.deps == []
        assert receipt.outs == []
        assert receipt.params == {}
        assert receipt.metrics == {}
        assert receipt.cmd == ""
        assert len(receipt.payload_hash) == 64

    def test_hash_field_in_deps(self) -> None:
        """Verify deps using 'hash' key instead of 'md5' are handled."""
        lock = {
            "cmd": "echo test",
            "deps": [{"path": "data.csv", "hash": "ffff0000", "size": 100}],
        }
        receipt = generate_pipeline_receipt("test", lock)

        assert receipt.deps[0].md5 == "ffff0000"


# ---------------------------------------------------------------------------
# Tests: generate_data_receipt
# ---------------------------------------------------------------------------


class TestGenerateDataReceipt:
    def test_push_operation(self) -> None:
        """Verify a push data receipt is generated correctly."""
        receipt = generate_data_receipt(
            file_path="data/train.csv",
            md5="aabbccdd",
            size=1048576,
            operation="push",
            remote="s3remote",
        )

        assert receipt.file_path == "data/train.csv"
        assert receipt.md5 == "aabbccdd"
        assert receipt.size == 1048576
        assert receipt.operation == "push"
        assert receipt.remote == "s3remote"
        assert receipt.receipt_type == "dvc_data_receipt"

    def test_pull_operation(self) -> None:
        """Verify a pull data receipt is generated correctly."""
        receipt = generate_data_receipt(
            file_path="data/val.csv",
            md5="11223344",
            size=512000,
            operation="pull",
            remote="gcs",
        )

        assert receipt.operation == "pull"
        assert receipt.remote == "gcs"

    def test_checkout_operation(self) -> None:
        """Verify a checkout data receipt is generated correctly."""
        receipt = generate_data_receipt(
            file_path="models/model.pkl",
            md5="deadbeef",
            size=524288,
            operation="checkout",
        )

        assert receipt.operation == "checkout"
        assert receipt.remote == ""

    def test_config_fields_injected(self) -> None:
        """Verify agent_id and tenant_id come from config."""
        cfg = MAIPConfig(agent_id="agent-z", tenant_id="tenant-w")
        receipt = generate_data_receipt(
            file_path="data.csv",
            md5="abcd",
            size=100,
            operation="push",
            config=cfg,
        )

        assert receipt.agent_id == "agent-z"
        assert receipt.tenant_id == "tenant-w"

    def test_payload_hash_set(self) -> None:
        """Verify the payload_hash is computed and is a 64-char hex digest."""
        receipt = generate_data_receipt(
            file_path="data.csv",
            md5="abcd",
            size=100,
            operation="push",
        )

        assert receipt.payload_hash != ""
        assert len(receipt.payload_hash) == 64


# ---------------------------------------------------------------------------
# Tests: hash_receipt_payload
# ---------------------------------------------------------------------------


class TestHashReceiptPayload:
    def test_deterministic_pipeline(self) -> None:
        """Verify hashing is deterministic for pipeline receipts."""
        receipt = DVCPipelineReceipt(stage_name="train", cmd="python train.py")
        h1 = hash_receipt_payload(receipt)
        h2 = hash_receipt_payload(receipt)
        assert h1 == h2

    def test_deterministic_data(self) -> None:
        """Verify hashing is deterministic for data receipts."""
        receipt = DVCDataReceipt(
            file_path="data.csv",
            md5="abcd",
            size=100,
            operation="push",
        )
        h1 = hash_receipt_payload(receipt)
        h2 = hash_receipt_payload(receipt)
        assert h1 == h2

    def test_hex_length(self) -> None:
        """Verify the hash is a 64-character hex string."""
        receipt = DVCPipelineReceipt(stage_name="test", cmd="echo test")
        h = hash_receipt_payload(receipt)
        assert len(h) == 64

    def test_different_inputs_produce_different_hashes(self) -> None:
        """Verify that different receipts produce different hashes."""
        r1 = DVCPipelineReceipt(stage_name="train", cmd="python train.py")
        r2 = DVCPipelineReceipt(stage_name="evaluate", cmd="python eval.py")
        assert hash_receipt_payload(r1) != hash_receipt_payload(r2)

    def test_hash_excludes_payload_hash_field(self) -> None:
        """Setting payload_hash should not change the computed digest."""
        r1 = DVCPipelineReceipt(stage_name="train", cmd="python train.py")
        h_before = hash_receipt_payload(r1)
        r1.payload_hash = "should-be-ignored"
        h_after = hash_receipt_payload(r1)
        assert h_before == h_after

    def test_data_receipt_different_operations(self) -> None:
        """Verify different operations on the same file produce different hashes."""
        base = {"file_path": "data.csv", "md5": "abcd", "size": 100}
        r_push = DVCDataReceipt(**base, operation="push")
        r_pull = DVCDataReceipt(**base, operation="pull")
        assert hash_receipt_payload(r_push) != hash_receipt_payload(r_pull)

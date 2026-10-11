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

"""Tests for the MAIPTrackingStore plugin and factory."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mlflow_maip.config import MAIPConfig
from mlflow_maip.exceptions import MAIPError
from mlflow_maip.plugin import MAIPTrackingStore, MAIPTrackingStoreFactory
from mlflow_maip.schemas import ReceiptResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_run() -> MagicMock:
    run = MagicMock()
    run.info = SimpleNamespace(
        run_id="run-001",
        experiment_id="exp-001",
        artifact_uri="s3://bucket/run-001",
        start_time=1700000000000,
        end_time=1700003600000,
        status="FINISHED",
    )
    run.data = SimpleNamespace(
        metrics={"accuracy": 0.95},
        params={"lr": "0.001"},
        tags={"mlflow.runName": "test-model"},
    )
    return run


def _receipt_response() -> ReceiptResponse:
    return ReceiptResponse(
        receipt_id="rcpt-abc",
        status="anchored",
        chain_hash="deadbeef",
        log_index=1,
    )


# ---------------------------------------------------------------------------
# Tests: MAIPTrackingStoreFactory
# ---------------------------------------------------------------------------


class TestMAIPTrackingStoreFactory:
    @patch("mlflow_maip.plugin.FileStore")
    def test_call_creates_store(self, mock_file_store: MagicMock) -> None:
        factory = MAIPTrackingStoreFactory()
        store = factory("file:///tmp/mlruns")
        assert isinstance(store, MAIPTrackingStore)

    @patch("mlflow_maip.plugin.FileStore")
    def test_create_store(self, mock_file_store: MagicMock) -> None:
        factory = MAIPTrackingStoreFactory()
        store = factory.create_store("file:///tmp/mlruns", "/tmp/artifacts")
        assert isinstance(store, MAIPTrackingStore)


# ---------------------------------------------------------------------------
# Tests: MAIPTrackingStore — delegation
# ---------------------------------------------------------------------------


class TestMAIPTrackingStoreDelegation:
    @patch("mlflow_maip.plugin.FileStore")
    def test_get_run_delegates(self, mock_file_store_cls: MagicMock) -> None:
        inner = MagicMock()
        mock_file_store_cls.return_value = inner
        store = MAIPTrackingStore("file:///tmp/mlruns")

        store.get_run("run-001")
        inner.get_run.assert_called_once_with("run-001")

    @patch("mlflow_maip.plugin.FileStore")
    def test_log_metric_delegates(self, mock_file_store_cls: MagicMock) -> None:
        inner = MagicMock()
        mock_file_store_cls.return_value = inner
        store = MAIPTrackingStore("file:///tmp/mlruns")

        metric = MagicMock()
        store.log_metric("run-001", metric)
        inner.log_metric.assert_called_once_with("run-001", metric)

    @patch("mlflow_maip.plugin.FileStore")
    def test_create_experiment_delegates(self, mock_file_store_cls: MagicMock) -> None:
        inner = MagicMock()
        mock_file_store_cls.return_value = inner
        store = MAIPTrackingStore("file:///tmp/mlruns")

        store.create_experiment("my-exp")
        inner.create_experiment.assert_called_once_with("my-exp")

    @patch("mlflow_maip.plugin.FileStore")
    def test_search_runs_delegates(self, mock_file_store_cls: MagicMock) -> None:
        inner = MagicMock()
        mock_file_store_cls.return_value = inner
        store = MAIPTrackingStore("file:///tmp/mlruns")

        from mlflow.entities import ViewType

        store.search_runs(["exp-001"], "", ViewType.ACTIVE_ONLY)
        inner.search_runs.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: MAIPTrackingStore — receipt creation
# ---------------------------------------------------------------------------


class TestMAIPTrackingStoreReceipt:
    @patch("mlflow_maip.plugin.MAIPClient.create_receipt_sync")
    @patch("mlflow_maip.plugin.FileStore")
    def test_update_run_info_creates_receipt_on_finished(
        self,
        mock_file_store_cls: MagicMock,
        mock_run_async: MagicMock,
    ) -> None:
        inner = MagicMock()
        inner.get_run.return_value = _mock_run()
        mock_file_store_cls.return_value = inner

        mock_run_async.return_value = _receipt_response()

        store = MAIPTrackingStore("file:///tmp/mlruns")
        store.update_run_info("run-001", "FINISHED", 1700003600000, "test-run")

        inner.update_run_info.assert_called_once()
        mock_run_async.assert_called_once()
        # Verify receipt ID tag was set
        assert inner.set_tag.call_count == 2
        tag_calls = [call.args for call in inner.set_tag.call_args_list]
        assert tag_calls[0][0] == "run-001"
        assert tag_calls[1][0] == "run-001"

    @patch("mlflow_maip.plugin.MAIPClient.create_receipt_sync")
    @patch("mlflow_maip.plugin.FileStore")
    def test_update_run_info_creates_receipt_on_failed(
        self,
        mock_file_store_cls: MagicMock,
        mock_run_async: MagicMock,
    ) -> None:
        inner = MagicMock()
        inner.get_run.return_value = _mock_run()
        mock_file_store_cls.return_value = inner

        mock_run_async.return_value = _receipt_response()

        store = MAIPTrackingStore("file:///tmp/mlruns")
        store.update_run_info("run-001", "FAILED", 1700003600000, "test-run")

        mock_run_async.assert_called_once()

    @patch("mlflow_maip.plugin.MAIPClient.create_receipt_sync")
    @patch("mlflow_maip.plugin.FileStore")
    def test_update_run_info_skips_receipt_for_running(
        self,
        mock_file_store_cls: MagicMock,
        mock_run_async: MagicMock,
    ) -> None:
        inner = MagicMock()
        mock_file_store_cls.return_value = inner

        store = MAIPTrackingStore("file:///tmp/mlruns")
        store.update_run_info("run-001", "RUNNING", 0, "test-run")

        mock_run_async.assert_not_called()

    @patch("mlflow_maip.plugin.MAIPClient.create_receipt_sync")
    @patch("mlflow_maip.plugin.FileStore")
    def test_receipt_failure_does_not_propagate(
        self,
        mock_file_store_cls: MagicMock,
        mock_run_async: MagicMock,
    ) -> None:
        """MAIP errors must not break the core MLflow workflow."""
        inner = MagicMock()
        inner.get_run.return_value = _mock_run()
        mock_file_store_cls.return_value = inner

        mock_run_async.side_effect = MAIPError("Server error", status_code=500)

        store = MAIPTrackingStore("file:///tmp/mlruns")
        # This must NOT raise
        store.update_run_info("run-001", "FINISHED", 1700003600000, "test-run")
        inner.update_run_info.assert_called_once()

    @patch("mlflow_maip.plugin.MAIPClient.create_receipt_sync")
    @patch("mlflow_maip.plugin.FileStore")
    def test_auto_receipt_disabled(
        self,
        mock_file_store_cls: MagicMock,
        mock_run_async: MagicMock,
    ) -> None:
        inner = MagicMock()
        mock_file_store_cls.return_value = inner

        store = MAIPTrackingStore("file:///tmp/mlruns")
        store._config.auto_receipt = False
        store.update_run_info("run-001", "FINISHED", 1700003600000, "test-run")

        mock_run_async.assert_not_called()

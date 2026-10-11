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

"""Tests for DVC lifecycle hooks."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dvc_maip.config import MAIPConfig
from dvc_maip.exceptions import MAIPError
from dvc_maip.hooks import (
    post_checkout_hook,
    post_pipeline_hook,
    post_pull_hook,
    post_push_hook,
)
from dvc_maip.schemas import ReceiptResponse


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _config() -> MAIPConfig:
    return MAIPConfig(
        api_url="https://test.maip.local/v1/machine-identity",
        api_key="test-key",
        tenant_id="tenant-001",
        agent_id="agent-001",
        auto_receipt=True,
        max_retries=1,
    )


def _receipt_response(receipt_id: str = "rcpt-001") -> ReceiptResponse:
    return ReceiptResponse(
        receipt_id=receipt_id,
        status="anchored",
        chain_hash="deadbeef",
        log_index=1,
    )


def _sample_lock_data() -> dict:
    return {
        "cmd": "python train.py",
        "deps": [{"path": "data.csv", "md5": "aabb", "size": 100}],
        "outs": [{"path": "model.pkl", "md5": "ccdd", "size": 200}],
        "params": [{"params.yaml": {"lr": 0.001}}],
        "metrics": [],
    }


# ---------------------------------------------------------------------------
# Tests: post_checkout_hook
# ---------------------------------------------------------------------------


class TestPostCheckoutHook:
    @patch("dvc_maip.hooks._parse_dvc_file_info", return_value=("aabb", 100))
    @patch("dvc_maip.hooks.MAIPClient")
    def test_creates_receipts_for_files(
        self,
        mock_client_cls: MagicMock,
        mock_parse: MagicMock,
    ) -> None:
        """Verify receipts are created for each checked-out file."""
        mock_client = AsyncMock()
        mock_client.create_receipt.return_value = _receipt_response()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        results = post_checkout_hook(["data.csv", "labels.csv"], config=_config())

        assert len(results) == 2
        assert mock_client.create_receipt.call_count == 2

    @patch("dvc_maip.hooks.MAIPClient")
    def test_auto_receipt_disabled(self, mock_client_cls: MagicMock) -> None:
        """Verify no receipts are created when auto_receipt is disabled."""
        cfg = _config()
        cfg.auto_receipt = False

        results = post_checkout_hook(["data.csv"], config=cfg)

        assert results == []
        mock_client_cls.assert_not_called()

    @patch("dvc_maip.hooks._parse_dvc_file_info", return_value=("aabb", 100))
    @patch("dvc_maip.hooks.MAIPClient")
    def test_partial_failure_continues(
        self,
        mock_client_cls: MagicMock,
        mock_parse: MagicMock,
    ) -> None:
        """Verify that failure on one file does not stop processing others."""
        mock_client = AsyncMock()
        mock_client.create_receipt.side_effect = [
            MAIPError("server error", status_code=500),
            _receipt_response("rcpt-002"),
        ]
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        results = post_checkout_hook(["bad.csv", "good.csv"], config=_config())

        assert len(results) == 1
        assert results[0].receipt_id == "rcpt-002"

    @patch("dvc_maip.hooks._parse_dvc_file_info", return_value=("aabb", 100))
    @patch("dvc_maip.hooks.MAIPClient")
    def test_empty_file_list(
        self,
        mock_client_cls: MagicMock,
        mock_parse: MagicMock,
    ) -> None:
        """Verify empty file list returns empty results."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        results = post_checkout_hook([], config=_config())

        assert results == []

    @patch("dvc_maip.hooks._parse_dvc_file_info", return_value=("aabb", 100))
    @patch("dvc_maip.hooks.MAIPClient")
    def test_unexpected_error_is_caught(
        self,
        mock_client_cls: MagicMock,
        mock_parse: MagicMock,
    ) -> None:
        """Verify unexpected exceptions are caught and do not propagate."""
        mock_client = AsyncMock()
        mock_client.create_receipt.side_effect = RuntimeError("unexpected")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        results = post_checkout_hook(["data.csv"], config=_config())

        assert results == []


# ---------------------------------------------------------------------------
# Tests: post_push_hook
# ---------------------------------------------------------------------------


class TestPostPushHook:
    @patch("dvc_maip.hooks._parse_dvc_file_info", return_value=("aabb", 100))
    @patch("dvc_maip.hooks.MAIPClient")
    def test_creates_receipts_with_remote(
        self,
        mock_client_cls: MagicMock,
        mock_parse: MagicMock,
    ) -> None:
        """Verify push receipts include the remote name."""
        mock_client = AsyncMock()
        mock_client.create_receipt.return_value = _receipt_response()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        results = post_push_hook(["data.csv"], "s3remote", config=_config())

        assert len(results) == 1
        # Verify the receipt was called with a data receipt that has the remote
        call_args = mock_client.create_receipt.call_args
        receipt = call_args[0][0]
        assert receipt.remote == "s3remote"
        assert receipt.operation == "push"

    @patch("dvc_maip.hooks.MAIPClient")
    def test_auto_receipt_disabled(self, mock_client_cls: MagicMock) -> None:
        """Verify no receipts are created when auto_receipt is disabled."""
        cfg = _config()
        cfg.auto_receipt = False

        results = post_push_hook(["data.csv"], "remote", config=cfg)

        assert results == []


# ---------------------------------------------------------------------------
# Tests: post_pull_hook
# ---------------------------------------------------------------------------


class TestPostPullHook:
    @patch("dvc_maip.hooks._parse_dvc_file_info", return_value=("aabb", 100))
    @patch("dvc_maip.hooks.MAIPClient")
    def test_creates_receipts_with_remote(
        self,
        mock_client_cls: MagicMock,
        mock_parse: MagicMock,
    ) -> None:
        """Verify pull receipts include the remote name and operation."""
        mock_client = AsyncMock()
        mock_client.create_receipt.return_value = _receipt_response()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        results = post_pull_hook(["data.csv"], "gcs", config=_config())

        assert len(results) == 1
        call_args = mock_client.create_receipt.call_args
        receipt = call_args[0][0]
        assert receipt.remote == "gcs"
        assert receipt.operation == "pull"


# ---------------------------------------------------------------------------
# Tests: post_pipeline_hook
# ---------------------------------------------------------------------------


class TestPostPipelineHook:
    @patch("dvc_maip.hooks.MAIPClient")
    def test_creates_pipeline_receipt(self, mock_client_cls: MagicMock) -> None:
        """Verify a pipeline receipt is created from lock data."""
        mock_client = AsyncMock()
        mock_client.create_receipt.return_value = _receipt_response()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        result = post_pipeline_hook("train", _sample_lock_data(), config=_config())

        assert result is not None
        assert result.receipt_id == "rcpt-001"

    @patch("dvc_maip.hooks.MAIPClient")
    def test_auto_receipt_disabled(self, mock_client_cls: MagicMock) -> None:
        """Verify pipeline receipts are skipped when auto_receipt is False."""
        cfg = _config()
        cfg.auto_receipt = False

        result = post_pipeline_hook("train", _sample_lock_data(), config=cfg)

        assert result is None
        mock_client_cls.assert_not_called()

    @patch("dvc_maip.hooks.MAIPClient")
    def test_maip_error_returns_none(self, mock_client_cls: MagicMock) -> None:
        """Verify MAIP errors are caught and None is returned."""
        mock_client = AsyncMock()
        mock_client.create_receipt.side_effect = MAIPError("server error", status_code=500)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        result = post_pipeline_hook("train", _sample_lock_data(), config=_config())

        assert result is None

    @patch("dvc_maip.hooks.MAIPClient")
    def test_unexpected_error_returns_none(self, mock_client_cls: MagicMock) -> None:
        """Verify unexpected errors are caught and None is returned."""
        mock_client = AsyncMock()
        mock_client.create_receipt.side_effect = RuntimeError("unexpected")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        result = post_pipeline_hook("train", _sample_lock_data(), config=_config())

        assert result is None

    @patch("dvc_maip.hooks.MAIPClient")
    def test_custom_pipeline_file(self, mock_client_cls: MagicMock) -> None:
        """Verify the pipeline_file argument is passed through."""
        mock_client = AsyncMock()
        mock_client.create_receipt.return_value = _receipt_response()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        result = post_pipeline_hook(
            "train",
            _sample_lock_data(),
            pipeline_file="pipelines/ml.yaml",
            config=_config(),
        )

        assert result is not None
        call_args = mock_client.create_receipt.call_args
        receipt = call_args[0][0]
        assert receipt.pipeline_file == "pipelines/ml.yaml"

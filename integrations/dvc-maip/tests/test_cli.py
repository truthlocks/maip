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

"""Tests for the DVC MAIP CLI extension."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from dvc_maip.cli import (
    MAIPCommand,
    cmd_receipt_create,
    cmd_receipt_list,
    cmd_receipt_verify,
)
from dvc_maip.config import MAIPConfig
from dvc_maip.schemas import ReceiptResponse, ReceiptVerifyResponse


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _config() -> MAIPConfig:
    return MAIPConfig(
        api_url="https://test.maip.local/v1/machine-identity",
        api_key="test-key",
        tenant_id="tenant-001",
        agent_id="agent-001",
    )


def _receipt_response(receipt_id: str = "rcpt-001") -> ReceiptResponse:
    return ReceiptResponse(
        receipt_id=receipt_id,
        status="anchored",
        chain_hash="deadbeef",
        log_index=1,
    )


def _verify_response(*, valid: bool = True) -> ReceiptVerifyResponse:
    return ReceiptVerifyResponse(
        valid=valid, verdict="VALID" if valid else "INVALID", receipt_id="rcpt-12345", signature_verified=valid,
        chain_verified=valid,
        receipt=_receipt_response(),
    )


def _sample_lock() -> dict:
    return {
        "stages": {
            "train": {
                "cmd": "python train.py",
                "deps": [{"path": "data.csv", "md5": "aabb", "size": 100}],
                "outs": [{"path": "model.pkl", "md5": "ccdd", "size": 200}],
                "params": [],
                "metrics": [],
            },
        },
    }


# ---------------------------------------------------------------------------
# Tests: cmd_receipt_create
# ---------------------------------------------------------------------------


class TestCmdReceiptCreate:
    @patch("dvc_maip.cli._run_async")
    @patch("dvc_maip.cli._load_lock_file")
    def test_create_success(
        self,
        mock_load: MagicMock,
        mock_run_async: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Verify successful receipt creation prints JSON and returns 0."""
        mock_load.return_value = _sample_lock()
        mock_run_async.return_value = _receipt_response()

        code = cmd_receipt_create("train", config=_config())

        assert code == 0
        captured = capsys.readouterr()
        assert "rcpt-001" in captured.out

    @patch("dvc_maip.cli._load_lock_file")
    def test_create_stage_not_found(
        self,
        mock_load: MagicMock,
    ) -> None:
        """Verify missing stage exits with code 1."""
        mock_load.return_value = _sample_lock()

        with pytest.raises(SystemExit) as exc_info:
            cmd_receipt_create("nonexistent", config=_config())

        assert exc_info.value.code == 1

    @patch("dvc_maip.cli._run_async")
    @patch("dvc_maip.cli._load_lock_file")
    def test_create_api_error(
        self,
        mock_load: MagicMock,
        mock_run_async: MagicMock,
    ) -> None:
        """Verify MAIP API errors exit with code 1."""
        from dvc_maip.exceptions import MAIPError

        mock_load.return_value = _sample_lock()
        mock_run_async.side_effect = MAIPError("Server error", status_code=500)

        with pytest.raises(SystemExit) as exc_info:
            cmd_receipt_create("train", config=_config())

        assert exc_info.value.code == 1

    @patch("dvc_maip.cli._run_async")
    @patch("dvc_maip.cli._load_lock_file")
    def test_create_with_custom_pipeline_file(
        self,
        mock_load: MagicMock,
        mock_run_async: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Verify custom pipeline file is passed through."""
        mock_load.return_value = _sample_lock()
        mock_run_async.return_value = _receipt_response()

        code = cmd_receipt_create(
            "train",
            pipeline_file="pipelines/ml.yaml",
            config=_config(),
        )

        assert code == 0
        mock_load.assert_called_once_with("pipelines/ml.yaml")

    @patch("dvc_maip.cli._load_lock_file")
    def test_create_flat_lock_format(
        self,
        mock_load: MagicMock,
    ) -> None:
        """Verify the flat lock format (no 'stages' wrapper) is handled."""
        flat_lock = {
            "train": {
                "cmd": "python train.py",
                "deps": [],
                "outs": [],
                "params": [],
                "metrics": [],
            },
        }
        mock_load.return_value = flat_lock

        with patch("dvc_maip.cli._run_async") as mock_run_async:
            mock_run_async.return_value = _receipt_response()
            code = cmd_receipt_create("train", config=_config())

        assert code == 0


# ---------------------------------------------------------------------------
# Tests: cmd_receipt_verify
# ---------------------------------------------------------------------------


class TestCmdReceiptVerify:
    @patch("dvc_maip.cli._run_async")
    def test_verify_valid(
        self,
        mock_run_async: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Verify valid receipt returns code 0."""
        mock_run_async.return_value = _verify_response(valid=True)

        code = cmd_receipt_verify("rcpt-001", config=_config())

        assert code == 0
        captured = capsys.readouterr()
        assert '"valid": true' in captured.out

    @patch("dvc_maip.cli._run_async")
    def test_verify_invalid(
        self,
        mock_run_async: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Verify invalid receipt returns code 1."""
        mock_run_async.return_value = _verify_response(valid=False)

        code = cmd_receipt_verify("rcpt-001", config=_config())

        assert code == 1

    @patch("dvc_maip.cli._run_async")
    def test_verify_api_error(self, mock_run_async: MagicMock) -> None:
        """Verify MAIP API errors exit with code 1."""
        from dvc_maip.exceptions import MAIPError

        mock_run_async.side_effect = MAIPError("Not found", status_code=404)

        with pytest.raises(SystemExit) as exc_info:
            cmd_receipt_verify("rcpt-999", config=_config())

        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Tests: cmd_receipt_list
# ---------------------------------------------------------------------------


class TestCmdReceiptList:
    @patch("dvc_maip.cli._run_async")
    def test_list_by_file(
        self,
        mock_run_async: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Verify listing by file path returns receipts."""
        mock_run_async.return_value = [_receipt_response()]

        code = cmd_receipt_list(file_path="data.csv", config=_config())

        assert code == 0
        captured = capsys.readouterr()
        assert "rcpt-001" in captured.out

    @patch("dvc_maip.cli._run_async")
    def test_list_by_stage(
        self,
        mock_run_async: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Verify listing by stage name returns receipts."""
        mock_run_async.return_value = [_receipt_response()]

        code = cmd_receipt_list(stage_name="train", config=_config())

        assert code == 0

    @patch("dvc_maip.cli._run_async")
    def test_list_empty(
        self,
        mock_run_async: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Verify empty results are printed correctly."""
        mock_run_async.return_value = []

        code = cmd_receipt_list(config=_config())

        assert code == 0
        captured = capsys.readouterr()
        assert "[]" in captured.out

    @patch("dvc_maip.cli._run_async")
    def test_list_api_error(self, mock_run_async: MagicMock) -> None:
        """Verify MAIP API errors exit with code 1."""
        from dvc_maip.exceptions import MAIPError

        mock_run_async.side_effect = MAIPError("Forbidden", status_code=403)

        with pytest.raises(SystemExit) as exc_info:
            cmd_receipt_list(config=_config())

        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Tests: MAIPCommand (argparse dispatch)
# ---------------------------------------------------------------------------


class TestMAIPCommand:
    @patch("dvc_maip.cli.cmd_receipt_create", return_value=0)
    def test_dispatch_receipt_create(self, mock_create: MagicMock) -> None:
        """Verify argparse dispatches receipt-create to cmd_receipt_create."""
        code = MAIPCommand.run(["receipt-create", "--stage", "train"])

        assert code == 0
        mock_create.assert_called_once()

    @patch("dvc_maip.cli.cmd_receipt_verify", return_value=0)
    def test_dispatch_receipt_verify(self, mock_verify: MagicMock) -> None:
        """Verify argparse dispatches receipt-verify to cmd_receipt_verify."""
        code = MAIPCommand.run(["receipt-verify", "--id", "rcpt-001"])

        assert code == 0
        mock_verify.assert_called_once()

    @patch("dvc_maip.cli.cmd_receipt_list", return_value=0)
    def test_dispatch_receipt_list(self, mock_list: MagicMock) -> None:
        """Verify argparse dispatches receipt-list to cmd_receipt_list."""
        code = MAIPCommand.run(["receipt-list", "--file", "data.csv"])

        assert code == 0
        mock_list.assert_called_once()

    def test_no_command_returns_1(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Verify that no arguments returns exit code 1 and prints help."""
        code = MAIPCommand.run([])

        assert code == 1

    @patch("dvc_maip.cli.cmd_receipt_list", return_value=0)
    def test_dispatch_receipt_list_with_stage(self, mock_list: MagicMock) -> None:
        """Verify the --stage filter is passed through for receipt-list."""
        code = MAIPCommand.run(["receipt-list", "--stage", "train"])

        assert code == 0
        mock_list.assert_called_once()

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

"""Tests for the MAIP async HTTP client."""

from __future__ import annotations

import httpx
import pytest
import respx

from dvc_maip.client import MAIPClient
from dvc_maip.config import MAIPConfig
from dvc_maip.exceptions import (
    MAIPAuthError,
    MAIPConnectionError,
    MAIPNotFoundError,
    MAIPValidationError,
)
from dvc_maip.schemas import DVCDataReceipt, DVCPipelineReceipt

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BASE_URL = "https://test.maip.local/v1"


def _config() -> MAIPConfig:
    return MAIPConfig(
        api_url=BASE_URL,
        api_key="test-key",
        tenant_id="tenant-001",
        agent_id="agent-001",
        max_retries=1,
        timeout=5.0,
    )


def _sample_pipeline_receipt() -> DVCPipelineReceipt:
    return DVCPipelineReceipt(
        stage_name="train",
        pipeline_file="dvc.yaml",
        deps=[],
        outs=[],
        params={"lr": 0.001},
        metrics={"accuracy": 0.95},
        cmd="python train.py",
        agent_id="agent-001",
        tenant_id="tenant-001",
    )


def _sample_data_receipt() -> DVCDataReceipt:
    return DVCDataReceipt(
        file_path="data/train.csv",
        md5="abc123def456",
        size=1048576,
        remote="s3remote",
        operation="push",
        agent_id="agent-001",
        tenant_id="tenant-001",
    )


RECEIPT_RESPONSE_JSON = {
    "receipt_id": "rcpt-12345",
    "status": "anchored",
    "metadata": {"file_path": "data/train.csv", "stage_name": "train", "run_id": "run-abc", "table_path": "/data/warehouse/events"},
    "chain_hash": "abc123def456",
    "log_index": 42,
    "issued_at": "2026-04-07T12:00:00",
}


# ---------------------------------------------------------------------------
# Tests: create_receipt (pipeline)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_pipeline_receipt_success() -> None:
    """Verify that a pipeline receipt is submitted and the response is parsed."""
    with respx.mock(base_url=BASE_URL) as router:
        router.post("/agent-receipts").mock(
            return_value=httpx.Response(200, json=RECEIPT_RESPONSE_JSON),
        )
        async with MAIPClient(_config()) as client:
            resp = await client.create_receipt(_sample_pipeline_receipt())

    assert resp.receipt_id == "rcpt-12345"
    assert resp.status == "anchored"
    assert resp.chain_hash == "abc123def456"
    assert resp.log_index == 42


@pytest.mark.asyncio
async def test_create_data_receipt_success() -> None:
    """Verify that a data receipt is submitted and the response is parsed."""
    with respx.mock(base_url=BASE_URL) as router:
        router.post("/agent-receipts").mock(
            return_value=httpx.Response(200, json=RECEIPT_RESPONSE_JSON),
        )
        async with MAIPClient(_config()) as client:
            resp = await client.create_receipt(_sample_data_receipt())

    assert resp.receipt_id == "rcpt-12345"
    assert resp.status == "anchored"


@pytest.mark.asyncio
async def test_create_receipt_auth_error() -> None:
    """Verify 401 responses are mapped to MAIPAuthError."""
    with respx.mock(base_url=BASE_URL) as router:
        router.post("/agent-receipts").mock(
            return_value=httpx.Response(401, text="Unauthorized"),
        )
        async with MAIPClient(_config()) as client:
            with pytest.raises(MAIPAuthError, match="Authentication failed"):
                await client.create_receipt(_sample_pipeline_receipt())


@pytest.mark.asyncio
async def test_create_receipt_validation_error() -> None:
    """Verify 422 responses are mapped to MAIPValidationError."""
    with respx.mock(base_url=BASE_URL) as router:
        router.post("/agent-receipts").mock(
            return_value=httpx.Response(422, text="Invalid payload"),
        )
        async with MAIPClient(_config()) as client:
            with pytest.raises(MAIPValidationError, match="Validation error"):
                await client.create_receipt(_sample_data_receipt())


@pytest.mark.asyncio
async def test_create_receipt_generic_server_error() -> None:
    """Verify non-retryable server errors are raised as MAIPError."""
    with respx.mock(base_url=BASE_URL) as router:
        router.post("/agent-receipts").mock(
            return_value=httpx.Response(500, text="Internal Server Error"),
        )
        async with MAIPClient(_config()) as client:
            from dvc_maip.exceptions import MAIPError

            with pytest.raises(MAIPError, match="MAIP API returned"):
                await client.create_receipt(_sample_pipeline_receipt())


# ---------------------------------------------------------------------------
# Tests: get_receipt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_receipt_success() -> None:
    """Verify a receipt can be retrieved by ID."""
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/agent-receipts/rcpt-12345").mock(
            return_value=httpx.Response(200, json=RECEIPT_RESPONSE_JSON),
        )
        async with MAIPClient(_config()) as client:
            resp = await client.get_receipt("rcpt-12345")

    assert resp.receipt_id == "rcpt-12345"


@pytest.mark.asyncio
async def test_get_receipt_not_found() -> None:
    """Verify 404 responses are mapped to MAIPNotFoundError."""
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/agent-receipts/no-such-id").mock(
            return_value=httpx.Response(404, text="Not found"),
        )
        async with MAIPClient(_config()) as client:
            with pytest.raises(MAIPNotFoundError):
                await client.get_receipt("no-such-id")


# ---------------------------------------------------------------------------
# Tests: verify_receipt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_receipt_success() -> None:
    """Verify the verify endpoint returns parsed verification data."""
    verify_json = {
        "valid": True,
        "chain_verified": False,
        "signature_verified": True,
        "verdict": "VALID",
        "receipt_id": RECEIPT_RESPONSE_JSON["receipt_id"],
        "receipt": RECEIPT_RESPONSE_JSON,
    }
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/agent-receipts/verify/rcpt-12345").mock(
            return_value=httpx.Response(200, json=verify_json),
        )
        async with MAIPClient(_config()) as client:
            resp = await client.verify_receipt("rcpt-12345")

    assert resp.valid is True
    assert resp.chain_verified is False
    assert resp.signature_verified is True
    assert resp.receipt.receipt_id == "rcpt-12345"


@pytest.mark.asyncio
async def test_verify_receipt_invalid() -> None:
    """Verify that an invalid receipt is correctly reported."""
    verify_json = {
        "valid": False,
        "verdict": "INVALID",
        "receipt_id": RECEIPT_RESPONSE_JSON["receipt_id"],
        "chain_verified": False,
        "receipt": RECEIPT_RESPONSE_JSON,
    }
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/agent-receipts/verify/rcpt-12345").mock(
            return_value=httpx.Response(200, json=verify_json),
        )
        async with MAIPClient(_config()) as client:
            resp = await client.verify_receipt("rcpt-12345")

    assert resp.valid is False
    assert resp.chain_verified is False


# ---------------------------------------------------------------------------
# Tests: list_receipts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_receipts_by_file() -> None:
    """Verify listing receipts with a file_path filter."""
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/agent-receipts/agent/agent-001").mock(
            return_value=httpx.Response(
                200,
                json={"receipts": [RECEIPT_RESPONSE_JSON]},
            ),
        )
        async with MAIPClient(_config()) as client:
            receipts = await client.list_receipts(file_path="data/train.csv")

    assert len(receipts) == 1
    assert receipts[0].receipt_id == "rcpt-12345"


@pytest.mark.asyncio
async def test_list_receipts_flat_array() -> None:
    """Ensure the client handles a bare list response."""
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/agent-receipts/agent/agent-001").mock(
            return_value=httpx.Response(200, json=[RECEIPT_RESPONSE_JSON]),
        )
        async with MAIPClient(_config()) as client:
            receipts = await client.list_receipts(stage_name="train")

    assert len(receipts) == 1


@pytest.mark.asyncio
async def test_list_receipts_empty() -> None:
    """Verify an empty result set is handled correctly."""
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/agent-receipts/agent/agent-001").mock(
            return_value=httpx.Response(200, json={"receipts": []}),
        )
        async with MAIPClient(_config()) as client:
            receipts = await client.list_receipts()

    assert receipts == []


# ---------------------------------------------------------------------------
# Tests: retry logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_on_503() -> None:
    """Verify the client retries on 503 and succeeds on the second attempt."""
    cfg = _config()
    cfg.max_retries = 2
    call_count = 0

    def _side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            return httpx.Response(503, text="Unavailable")
        return httpx.Response(200, json=RECEIPT_RESPONSE_JSON)

    with respx.mock(base_url=BASE_URL) as router:
        router.get("/agent-receipts/retry-id").mock(side_effect=_side_effect)
        async with MAIPClient(cfg) as client:
            resp = await client.get_receipt("retry-id")

    assert resp.receipt_id == "rcpt-12345"
    assert call_count == 2


@pytest.mark.asyncio
async def test_retry_on_429() -> None:
    """Verify the client retries on 429 rate-limit responses."""
    cfg = _config()
    cfg.max_retries = 2
    call_count = 0

    def _side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            return httpx.Response(429, text="Rate limited")
        return httpx.Response(200, json=RECEIPT_RESPONSE_JSON)

    with respx.mock(base_url=BASE_URL) as router:
        router.get("/agent-receipts/retry-id").mock(side_effect=_side_effect)
        async with MAIPClient(cfg) as client:
            resp = await client.get_receipt("retry-id")

    assert resp.receipt_id == "rcpt-12345"
    assert call_count == 2


@pytest.mark.asyncio
async def test_connection_error_after_retries() -> None:
    """Verify transport failures are raised as MAIPConnectionError after exhausting retries."""
    cfg = _config()
    cfg.max_retries = 1

    with respx.mock(base_url=BASE_URL) as router:
        router.post("/agent-receipts").mock(side_effect=httpx.ConnectError("refused"))
        async with MAIPClient(cfg) as client:
            with pytest.raises(MAIPConnectionError):
                await client.create_receipt(_sample_pipeline_receipt())


# ---------------------------------------------------------------------------
# Tests: client lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_client_context_manager_closes() -> None:
    """Verify the async context manager properly closes the HTTP client."""
    client = MAIPClient(_config())
    async with client:
        inner = client._get_client()
        assert not inner.is_closed
    assert client._client is None


@pytest.mark.asyncio
async def test_client_reuse_after_close() -> None:
    """Verify a new inner client is created after close."""
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/agent-receipts/rcpt-1").mock(
            return_value=httpx.Response(200, json=RECEIPT_RESPONSE_JSON),
        )
        client = MAIPClient(_config())
        # Force client creation
        client._get_client()
        # Close and re-use
        await client.close()
        assert client._client is None
        async with client:
            resp = await client.get_receipt("rcpt-1")
        assert resp.receipt_id == "rcpt-12345"

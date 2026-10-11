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

from delta_lake_maip.client import MAIPClient
from delta_lake_maip.config import DeltaMAIPConfig
from delta_lake_maip.exceptions import (
    MAIPAuthError,
    MAIPConnectionError,
    MAIPNotFoundError,
    MAIPValidationError,
)
from delta_lake_maip.schemas import DeltaMergeReceipt, DeltaWriteReceipt

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BASE_URL = "https://test.maip.local/v1"


def _config() -> DeltaMAIPConfig:
    return DeltaMAIPConfig(
        api_url=BASE_URL,
        api_key="test-key",
        tenant_id="tenant-001",
        agent_id="agent-001",
        max_retries=1,
        timeout=5.0,
    )


def _sample_write_receipt() -> DeltaWriteReceipt:
    return DeltaWriteReceipt(
        table_path="/data/warehouse/events",
        table_name="events",
        version=5,
        operation="APPEND",
        num_files_added=3,
        num_files_removed=0,
        num_rows_affected=15000,
        partition_columns=["date"],
        schema_hash="abc123",
        commit_timestamp=1700000000000,
        agent_id="agent-001",
        tenant_id="tenant-001",
    )


def _sample_merge_receipt() -> DeltaMergeReceipt:
    return DeltaMergeReceipt(
        table_path="/data/warehouse/customers",
        table_name="customers",
        version=12,
        source_description="daily_ingestion_csv",
        condition="target.id = source.id",
        num_target_rows_inserted=500,
        num_target_rows_updated=200,
        num_target_rows_deleted=10,
        num_source_rows=710,
        commit_timestamp=1700000000000,
        agent_id="agent-001",
        tenant_id="tenant-001",
    )


RECEIPT_RESPONSE_JSON = {
    "receipt_id": "rcpt-delta-001",
    "status": "anchored",
    "metadata": {"file_path": "data/train.csv", "stage_name": "train", "run_id": "run-abc", "table_path": "/data/warehouse/events"},
    "chain_hash": "abc123def456",
    "log_index": 42,
    "issued_at": "2026-04-07T12:00:00",
}


# ---------------------------------------------------------------------------
# Tests: create_receipt (write)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_write_receipt_success() -> None:
    """A write receipt is created and the response is parsed correctly."""
    with respx.mock(base_url=BASE_URL) as router:
        router.post("/agent-receipts").mock(
            return_value=httpx.Response(200, json=RECEIPT_RESPONSE_JSON),
        )
        async with MAIPClient(_config()) as client:
            resp = await client.create_receipt(_sample_write_receipt())

    assert resp.receipt_id == "rcpt-delta-001"
    assert resp.status == "anchored"
    assert resp.chain_hash == "abc123def456"
    assert resp.log_index == 42


@pytest.mark.asyncio
async def test_create_merge_receipt_success() -> None:
    """A merge receipt is created and the response is parsed correctly."""
    with respx.mock(base_url=BASE_URL) as router:
        router.post("/agent-receipts").mock(
            return_value=httpx.Response(200, json=RECEIPT_RESPONSE_JSON),
        )
        async with MAIPClient(_config()) as client:
            resp = await client.create_receipt(_sample_merge_receipt())

    assert resp.receipt_id == "rcpt-delta-001"
    assert resp.status == "anchored"


@pytest.mark.asyncio
async def test_create_receipt_auth_error() -> None:
    """A 401 response raises MAIPAuthError."""
    with respx.mock(base_url=BASE_URL) as router:
        router.post("/agent-receipts").mock(
            return_value=httpx.Response(401, text="Unauthorized"),
        )
        async with MAIPClient(_config()) as client:
            with pytest.raises(MAIPAuthError, match="Authentication failed"):
                await client.create_receipt(_sample_write_receipt())


@pytest.mark.asyncio
async def test_create_receipt_validation_error() -> None:
    """A 422 response raises MAIPValidationError."""
    with respx.mock(base_url=BASE_URL) as router:
        router.post("/agent-receipts").mock(
            return_value=httpx.Response(422, text="Invalid payload"),
        )
        async with MAIPClient(_config()) as client:
            with pytest.raises(MAIPValidationError, match="Validation error"):
                await client.create_receipt(_sample_write_receipt())


@pytest.mark.asyncio
async def test_create_receipt_sends_correct_headers() -> None:
    """The client sends X-API-Key and User-Agent without a caller-controlled tenant headers."""
    captured_request: httpx.Request | None = None

    def _capture(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200, json=RECEIPT_RESPONSE_JSON)

    with respx.mock(base_url=BASE_URL) as router:
        router.post("/agent-receipts").mock(side_effect=_capture)
        async with MAIPClient(_config()) as client:
            await client.create_receipt(_sample_write_receipt())

    assert captured_request is not None
    assert captured_request.headers["X-API-Key"] == "test-key"
    assert "X-Tenant-ID" not in captured_request.headers
    assert captured_request.headers["User-Agent"].startswith("maip-ai-connectors/")


# ---------------------------------------------------------------------------
# Tests: get_receipt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_receipt_success() -> None:
    """A receipt can be retrieved by ID."""
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/agent-receipts/rcpt-delta-001").mock(
            return_value=httpx.Response(200, json=RECEIPT_RESPONSE_JSON),
        )
        async with MAIPClient(_config()) as client:
            resp = await client.get_receipt("rcpt-delta-001")

    assert resp.receipt_id == "rcpt-delta-001"


@pytest.mark.asyncio
async def test_get_receipt_not_found() -> None:
    """A 404 response raises MAIPNotFoundError."""
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
    """A receipt can be verified successfully."""
    verify_json = {
        "valid": True,
        "chain_verified": False,
        "signature_verified": True,
        "verdict": "VALID",
        "receipt_id": RECEIPT_RESPONSE_JSON["receipt_id"],
        "receipt": RECEIPT_RESPONSE_JSON,
    }
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/agent-receipts/verify/rcpt-delta-001").mock(
            return_value=httpx.Response(200, json=verify_json),
        )
        async with MAIPClient(_config()) as client:
            resp = await client.verify_receipt("rcpt-delta-001")

    assert resp.valid is True
    assert resp.chain_verified is False
    assert resp.signature_verified is True
    assert resp.receipt.receipt_id == "rcpt-delta-001"


@pytest.mark.asyncio
async def test_verify_receipt_invalid() -> None:
    """A receipt that fails verification returns valid=False."""
    verify_json = {
        "valid": False,
        "verdict": "INVALID",
        "receipt_id": RECEIPT_RESPONSE_JSON["receipt_id"],
        "chain_verified": False,
        "receipt": RECEIPT_RESPONSE_JSON,
    }
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/agent-receipts/verify/rcpt-delta-001").mock(
            return_value=httpx.Response(200, json=verify_json),
        )
        async with MAIPClient(_config()) as client:
            resp = await client.verify_receipt("rcpt-delta-001")

    assert resp.valid is False
    assert resp.chain_verified is False


# ---------------------------------------------------------------------------
# Tests: list_receipts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_receipts_success() -> None:
    """Receipts can be listed by table path (wrapped in object)."""
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/agent-receipts/agent/agent-001").mock(
            return_value=httpx.Response(
                200,
                json={"receipts": [RECEIPT_RESPONSE_JSON]},
            ),
        )
        async with MAIPClient(_config()) as client:
            receipts = await client.list_receipts("/data/warehouse/events")

    assert len(receipts) == 1
    assert receipts[0].receipt_id == "rcpt-delta-001"


@pytest.mark.asyncio
async def test_list_receipts_flat_array() -> None:
    """The client handles a bare list response."""
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/agent-receipts/agent/agent-001").mock(
            return_value=httpx.Response(200, json=[RECEIPT_RESPONSE_JSON]),
        )
        async with MAIPClient(_config()) as client:
            receipts = await client.list_receipts("/data/warehouse/events")

    assert len(receipts) == 1


@pytest.mark.asyncio
async def test_list_receipts_empty() -> None:
    """An empty list is returned when no receipts exist."""
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/agent-receipts/agent/agent-001").mock(
            return_value=httpx.Response(200, json={"receipts": []}),
        )
        async with MAIPClient(_config()) as client:
            receipts = await client.list_receipts("/data/warehouse/events")

    assert receipts == []


# ---------------------------------------------------------------------------
# Tests: retry logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_on_503() -> None:
    """The client retries on 503 and succeeds on the second attempt."""
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

    assert resp.receipt_id == "rcpt-delta-001"
    assert call_count == 2


@pytest.mark.asyncio
async def test_retry_on_429() -> None:
    """The client retries on 429 (rate limit) and succeeds."""
    cfg = _config()
    cfg.max_retries = 2
    call_count = 0

    def _side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            return httpx.Response(429, text="Too Many Requests")
        return httpx.Response(200, json=RECEIPT_RESPONSE_JSON)

    with respx.mock(base_url=BASE_URL) as router:
        router.get("/agent-receipts/retry-id").mock(side_effect=_side_effect)
        async with MAIPClient(cfg) as client:
            resp = await client.get_receipt("retry-id")

    assert resp.receipt_id == "rcpt-delta-001"
    assert call_count == 2


@pytest.mark.asyncio
async def test_connection_error_after_retries() -> None:
    """Transport errors exhaust retries and raise MAIPConnectionError."""
    cfg = _config()
    cfg.max_retries = 1

    with respx.mock(base_url=BASE_URL) as router:
        router.post("/agent-receipts").mock(side_effect=httpx.ConnectError("refused"))
        async with MAIPClient(cfg) as client:
            with pytest.raises(MAIPConnectionError):
                await client.create_receipt(_sample_write_receipt())


@pytest.mark.asyncio
async def test_client_close_idempotent() -> None:
    """Closing the client multiple times does not raise."""
    client = MAIPClient(_config())
    await client.close()
    await client.close()  # Should not raise

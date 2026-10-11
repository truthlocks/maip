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

from maip_ai_connectors.client import MAIPClient
from maip_ai_connectors.config import MAIPConfig
from maip_ai_connectors.exceptions import (
    MAIPAuthError,
    MAIPConnectionError,
    MAIPNotFoundError,
    MAIPValidationError,
)
from maip_ai_connectors.schemas import LLMCallReceipt

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BASE_URL = "https://test.maip.local/v1"


def _config() -> MAIPConfig:
    """Create a test configuration."""
    return MAIPConfig(
        api_url=BASE_URL,
        api_key="test-key",
        tenant_id="tenant-001",
        agent_id="agent-001",
        max_retries=1,
        timeout=5.0,
    )


def _sample_receipt() -> LLMCallReceipt:
    """Create a sample LLM call receipt for testing."""
    return LLMCallReceipt(
        model="gpt-4o",
        provider="openai",
        prompt_hash="abc123",
        completion_hash="def456",
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        estimated_cost_usd=0.00075,
        latency_ms=500,
        agent_id="agent-001",
        tenant_id="tenant-001",
    )


RECEIPT_RESPONSE_JSON = {
    "receipt_id": "rcpt-12345",
    "status": "anchored",
    "chain_hash": "abc123def456",
    "log_index": 42,
    "issued_at": "2026-04-07T12:00:00",
}


# ---------------------------------------------------------------------------
# Tests: create_receipt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_receipt_success() -> None:
    """Verify successful receipt creation returns parsed response."""
    with respx.mock(base_url=BASE_URL) as router:
        router.post("/agent-receipts").mock(
            return_value=httpx.Response(200, json=RECEIPT_RESPONSE_JSON),
        )
        async with MAIPClient(_config()) as client:
            resp = await client.create_receipt(_sample_receipt())

    assert resp.receipt_id == "rcpt-12345"
    assert resp.status == "anchored"
    assert resp.chain_hash == "abc123def456"
    assert resp.log_index == 42


@pytest.mark.asyncio
async def test_create_receipt_auth_error() -> None:
    """Verify 401 raises MAIPAuthError."""
    with respx.mock(base_url=BASE_URL) as router:
        router.post("/agent-receipts").mock(
            return_value=httpx.Response(401, text="Unauthorized"),
        )
        async with MAIPClient(_config()) as client:
            with pytest.raises(MAIPAuthError, match="Authentication failed"):
                await client.create_receipt(_sample_receipt())


@pytest.mark.asyncio
async def test_create_receipt_validation_error() -> None:
    """Verify 422 raises MAIPValidationError."""
    with respx.mock(base_url=BASE_URL) as router:
        router.post("/agent-receipts").mock(
            return_value=httpx.Response(422, text="Invalid payload"),
        )
        async with MAIPClient(_config()) as client:
            with pytest.raises(MAIPValidationError, match="Validation error"):
                await client.create_receipt(_sample_receipt())


# ---------------------------------------------------------------------------
# Tests: get_receipt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_receipt_success() -> None:
    """Verify successful receipt retrieval."""
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/agent-receipts/rcpt-12345").mock(
            return_value=httpx.Response(200, json=RECEIPT_RESPONSE_JSON),
        )
        async with MAIPClient(_config()) as client:
            resp = await client.get_receipt("rcpt-12345")

    assert resp.receipt_id == "rcpt-12345"


@pytest.mark.asyncio
async def test_get_receipt_not_found() -> None:
    """Verify 404 raises MAIPNotFoundError."""
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
    """Verify successful receipt verification."""
    verify_json = {
        "valid": True,
        "chain_verified": False,
        "verdict": "VALID", "receipt_id": "rcpt-12345", "signature_verified": True,
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


# ---------------------------------------------------------------------------
# Tests: list_receipts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_receipts_success() -> None:
    """Verify listing receipts with filters."""
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/agent-receipts/agent/agent-001").mock(
            return_value=httpx.Response(
                200,
                json={"receipts": [RECEIPT_RESPONSE_JSON]},
            ),
        )
        async with MAIPClient(_config()) as client:
            receipts = await client.list_receipts(agent_id="agent-001")

    assert len(receipts) == 1
    assert receipts[0].receipt_id == "rcpt-12345"


@pytest.mark.asyncio
async def test_list_receipts_flat_array() -> None:
    """Verify the client handles a bare list response."""
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/agent-receipts/agent/agent-001").mock(
            return_value=httpx.Response(200, json=[RECEIPT_RESPONSE_JSON]),
        )
        async with MAIPClient(_config()) as client:
            receipts = await client.list_receipts()

    assert len(receipts) == 1


# ---------------------------------------------------------------------------
# Tests: retry logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_on_503() -> None:
    """Verify retries on transient 503 errors."""
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
        router.get("/agent-receipts/rcpt-12345").mock(side_effect=_side_effect)
        async with MAIPClient(cfg) as client:
            resp = await client.get_receipt("rcpt-12345")

    assert resp.receipt_id == "rcpt-12345"
    assert call_count == 2


@pytest.mark.asyncio
async def test_connection_error_after_retries() -> None:
    """Verify MAIPConnectionError raised after all retries exhausted."""
    cfg = _config()
    cfg.max_retries = 1

    with respx.mock(base_url=BASE_URL) as router:
        router.post("/agent-receipts").mock(side_effect=httpx.ConnectError("refused"))
        async with MAIPClient(cfg) as client:
            with pytest.raises(MAIPConnectionError):
                await client.create_receipt(_sample_receipt())

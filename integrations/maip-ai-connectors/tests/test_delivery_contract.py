import asyncio
import json
import httpx
import pytest
import respx

from maip_ai_connectors.client import MAIPClient
from maip_ai_connectors.config import MAIPConfig
from maip_ai_connectors.exceptions import MAIPError
from maip_ai_connectors.schemas import LLMCallReceipt, ReceiptVerifyResponse

BASE = "https://sandbox-api.truthlocks.com/v1"
RESULT = {"receipt_id": "maip-receipt:qa", "status": "valid", "created_at": "2026-10-11T12:00:00Z", "signature": "example", "signing_envelope": {"version": "2"}}

def payload():
    return LLMCallReceipt(model="fixture", provider="fixture", agent_id="maip:qa", prompt_hash="abc", completion_hash="def")

def config(**kwargs):
    return MAIPConfig(api_key="tl_test_fixture", agent_id="maip:qa", max_retries=0, **kwargs)

def test_sync_delivery_is_not_silently_skipped():
    with respx.mock as router:
        def handler(request):
            body = json.loads(request.content)
            assert body["receipt_type"] == "action"
            assert body["metadata"]["receipt_type"] == "llm_call_receipt"
            assert body["agent_id"] == "maip:qa"
            assert body["inputs_hash"] == "abc"
            assert request.headers["X-API-Key"] == "tl_test_fixture"
            assert "X-Tenant-ID" not in request.headers
            return httpx.Response(201, json=RESULT)
        route = router.post(BASE + "/agent-receipts").mock(side_effect=handler)
        client = MAIPClient(config())
        result = client.submit_receipt_background(payload())
        assert result.receipt_id == RESULT["receipt_id"]
        assert result.created_at is not None
        assert len(client.submitted_receipts) == 1 and route.call_count == 1

@pytest.mark.asyncio
async def test_background_close_waits_and_reports_delivery_failure():
    with respx.mock as router:
        route = router.post(BASE + "/agent-receipts").mock(return_value=httpx.Response(503))
        client = MAIPClient(config())
        client.submit_receipt_background(payload())
        with pytest.raises(MAIPError, match="not confirmed"):
            await client.close()
        assert route.call_count == 1

@pytest.mark.asyncio
async def test_write_not_replayed_even_when_read_retries_enabled():
    cfg = config()
    cfg.max_retries = 3
    with respx.mock as router:
        route = router.post(BASE + "/agent-receipts").mock(return_value=httpx.Response(503))
        async with MAIPClient(cfg) as client:
            with pytest.raises(MAIPError):
                await client.create_receipt(payload())
        assert route.call_count == 1

@pytest.mark.asyncio
async def test_redirect_does_not_forward_credentials():
    with respx.mock as router:
        router.get(BASE + "/agent-receipts/qa").mock(return_value=httpx.Response(302, headers={"location": "https://untrusted.invalid/"}))
        async with MAIPClient(config()) as client:
            with pytest.raises(MAIPError):
                await client.get_receipt("qa")

def test_unsubstantiated_valid_response_rejected():
    with pytest.raises(ValueError):
        ReceiptVerifyResponse(valid=True, verdict="VALID", receipt_id="qa")

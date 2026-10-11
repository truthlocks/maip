import asyncio
import httpx
import pytest
import respx
from langchain_core.runnables import RunnableLambda
from maip_ai_connectors.langchain import MAIPRunnableWrapper
from maip_ai_connectors.config import MAIPConfig
from maip_ai_connectors.providers.openai import MAIPOpenAIWrapper
from unittest.mock import MagicMock

@pytest.mark.asyncio
async def test_real_langchain_async_events_are_delivered_before_close():
    config = MAIPConfig(api_key='tl_test_fixture', agent_id='maip:qa')
    wrapper = MAIPRunnableWrapper(RunnableLambda(lambda x: x.upper()), config=config)
    with respx.mock as router:
        route = router.post('https://sandbox-api.truthlocks.com/v1/agent-receipts').mock(
            return_value=httpx.Response(201, json={'receipt_id': 'maip-receipt:qa', 'status': 'valid'}))
        assert await wrapper.ainvoke('hello') == 'HELLO'
        await wrapper.aclose()
        assert route.call_count >= 1
        assert wrapper.get_submitted_receipts()[0].receipt_id == 'maip-receipt:qa'

def test_stream_rejected_before_provider_request():
    provider = MagicMock()
    wrapper = MAIPOpenAIWrapper(client=provider, config=MAIPConfig(auto_receipt=False))
    with pytest.raises(ValueError, match='Streaming'):
        wrapper.chat_completions_create(model='fixture', messages=[], stream=True)
    provider.chat.completions.create.assert_not_called()

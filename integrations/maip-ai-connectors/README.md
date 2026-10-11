# Truthlocks AI connectors integration

Build structured, hash-addressed evidence from AI connectors metadata for your application's audit workflow.

**Package:** `maip-ai-connectors` · **Python:** 3.9+ · **License:** Apache-2.0

[Developer documentation](https://docs.truthlocks.com) · [Console](https://console.truthlocks.com)

## Install

```sh
python -m pip install maip-ai-connectors
```

Use a virtual environment and lock compatible framework versions with your application.
The local example below needs no hosted credentials and makes no external requests.

## Quickstart: create local evidence

```python
from maip_ai_connectors.config import MAIPConfig
from maip_ai_connectors.receipts import build_llm_call_receipt, hash_receipt_payload

receipt = build_llm_call_receipt(
    model="demo-model", provider="example", prompt="Hello", completion="Hello back",
    input_tokens=1, output_tokens=2, latency_ms=10,
    config=MAIPConfig(auto_receipt=False),
)
assert receipt.payload_hash == hash_receipt_payload(receipt)
print(receipt.model_dump_json(indent=2))
```

## Connect real data

Pass the actual request/response content and usage values recorded by your application. No model is called in this example. Install provider-specific extras only for integrations you use, such as maip-ai-connectors[anthropic] or maip-ai-connectors[langchain].

## Available interfaces

Receipt builders cover LLM calls, embeddings, agent actions and chains. Integration modules cover OpenAI, Anthropic, Bedrock, LangChain, CrewAI, AutoGen and LlamaIndex. Each wrapper captures its supported methods and callback events; it cannot observe unrelated calls.

## Configuration

| Setting | Meaning |
| --- | --- |
| `auto_receipt=False` | Disable automatic hosted submission in integration hooks. |
| `agent_id` | Registered agent in the authenticated workspace, used for signing. |
| `tenant_id` | Workspace metadata; does not authorize API access. |
| `api_key`, `api_url` | Hosted transport configuration, separate from framework credentials. |
| `timeout` | HTTP timeout in seconds; default 30. |
| `verify_ssl` | TLS verification; keep enabled. |

## Evidence and delivery guarantees

The local result is a Pydantic model with a `payload_hash`. Save it using
`model_dump_json()` and retain the metadata needed to reproduce it. Recomputing the
hash checks consistency of that local representation; it does not validate a server
signature, establish a trusted identity, or confirm transparency-log inclusion.

Cost values use a bundled estimate table and may differ from provider invoices. Zero usage can trigger token estimation. A hash binds recorded data but does not prove a provider actually produced it.


## Submit and verify hosted evidence (1.1.0+)

Register a machine identity in your workspace before submission. Set `MAIP_AGENT_ID`
to its identifier and `MAIP_API_KEY` to a workspace API key with access to machine
identities and receipts. Provider keys are separate. A `tl_test_` key selects the
sandbox host unless `MAIP_API_URL` overrides it; production defaults to
`https://api.truthlocks.com/v1`. Do not use a tenant header as authentication.

This example submits the local `receipt` created above only when credentials are set:

```python
import asyncio
import os
from maip_ai_connectors.client import MAIPClient
from maip_ai_connectors.config import MAIPConfig

async def submit_and_verify(local_receipt):
    config = MAIPConfig(agent_id=os.environ["MAIP_AGENT_ID"],
                        api_key=os.environ["MAIP_API_KEY"])
    async with MAIPClient(config) as client:
        stored = await client.create_receipt(local_receipt)
        check = await client.verify_receipt(stored.receipt_id)
        if not check.valid or not check.signature_verified:
            raise RuntimeError(check.reason or check.verdict)
        print(stored.receipt_id, check.verdict)

if os.environ.get("MAIP_API_KEY") and os.environ.get("MAIP_AGENT_ID"):
    asyncio.run(submit_and_verify(receipt))
```

The server stores integration metadata in a signed MAIP action receipt. Its
`receipt_id` differs from the local `payload_hash`. Verification checks the signature
and current lifecycle state; it does **not** establish transparency-log inclusion.
Old receipts whose signing key was lost return `UNVERIFIABLE`.

For automatic hooks, enable `auto_receipt=True`. In synchronous code delivery is
confirmed before the hook returns. In asynchronous code, call `await wrapper.flush()`
and `await wrapper.aclose()` before shutdown; inspect `get_submitted_receipts()` for
server responses. These lifecycle methods apply to AI wrappers/callbacks; data
clients use their async context manager or `create_receipt_sync()` instead.
Read retries are bounded; writes are never automatically replayed. After a timeout,
check the agent's receipts before retrying. Listing returns up to the latest 100
receipts for one agent, with integration filters applied to that page.

## Troubleshooting

| Problem | Next step |
| --- | --- |
| Missing optional dependency | Install the framework/provider extra in the interpreter running your app. |
| Validation error | Supply the documented fields and types; do not substitute a whole response for one metadata object. |
| Hash changes | Compare serialized fields, including timestamps and identifiers. |
| Nothing appears in Console | Local builders do not submit records; configure a registered agent and await confirmed delivery. |

For support, share package and Python versions plus a sanitized example. Do not include
keys, customer data or full authentication headers. No automatic compliance certification
or fixed processing-latency guarantee is implied.

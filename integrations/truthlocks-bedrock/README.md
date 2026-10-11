# Truthlocks for Amazon Bedrock

Capture structured evidence about Amazon Bedrock operations in your Python application.
Inspect input/output hashes and execution metadata alongside the original result.

**Package:** `truthlocks-bedrock` · **Python:** 3.9+ · **License:** Apache-2.0

[Developer documentation](https://docs.truthlocks.com) · [Truthlocks Console](https://console.truthlocks.com)

## Install

```sh
python -m pip install truthlocks-bedrock
```

This package re-exports the Amazon Bedrock integration from `maip-ai-connectors` and installs
its corresponding optional dependencies. Keep compatible versions of the integration
and your provider/framework in your application's lockfile.

## Run a complete local example

This example creates local receipt data without calling a paid model or submitting
anything to Truthlocks. It deliberately sets `auto_receipt=False`.

```python
from truthlocks_bedrock import MAIPBedrockWrapper
from maip_ai_connectors.config import MAIPConfig

class DemoBedrock:
    def converse(self, **kwargs):
        return {"output": {"message": {"content": [{"text": "Hello"}]}},
                "usage": {"inputTokens": 1, "outputTokens": 1}}

wrapper = MAIPBedrockWrapper(client=DemoBedrock(), config=MAIPConfig(auto_receipt=False))
response, receipt = wrapper.converse(
    modelId="demo-model",
    messages=[{"role": "user", "content": [{"text": "Hello"}]}],
)
print(response["output"]["message"]["content"][0]["text"])
print(receipt.payload_hash)
```

## Connect your application

Replace `DemoBedrock()` with an authenticated `boto3` Bedrock Runtime client and use a model enabled in its AWS region. Only calls through the wrapper are captured. `invoke_model` parses model-specific JSON responses; streaming methods are not supported.

Provider credentials belong to the underlying provider client. A Truthlocks key does
not authenticate a model provider, and provider charges are separate.

## Understand the result

`payload_hash` is a hash of locally constructed receipt data. It is **not** a server
receipt ID, a signature, proof of transparency-log inclusion, or confirmation that
Truthlocks accepted the event. The local receipt has no `receipt_id` property.
Export its structured fields with `receipt.model_dump()` or `receipt.model_dump_json()`.
Hashing application-supplied data does not independently establish that an AI provider
performed an operation or that the output is correct.

## API and configuration

| Item | Purpose |
| --- | --- |
| `MAIPBedrockWrapper` | Public integration classes exported by this package. |
| `converse() and invoke_model()` | Supported entry points; see the example for the relevant class. |
| `MAIPConfig(auto_receipt=False)` | Collect local evidence without background HTTP submission. |
| `agent_id` | Registered agent in the authenticated workspace, used for signing. |
| `tenant_id` | Workspace metadata in the payload; it does not grant access. |

## Hosted receipt submission


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

| Symptom | Check |
| --- | --- |
| Import fails | Install this package in the Python environment running your app, including its optional framework dependencies. |
| Provider authentication fails | Configure credentials on the underlying provider client. |
| No local receipts | Execute a supported wrapper method or invoke an attached callback; construction alone records nothing. |
| `receipt_id` is missing | The returned object is local evidence; use `payload_hash` to inspect its digest. |
| No receipt arrives in Console | Local mode does not submit; configure a registered agent and await confirmed delivery. |

No fixed latency, automatic compliance certification, or universal event coverage is
promised. Measure overhead in your application and inspect the fields you retain.
For support, include the package version and a sanitized reproduction; exclude keys,
raw customer content and authentication tokens.

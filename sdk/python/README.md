# truthlocks-maip

Python SDK for the **MAIP (Machine Agent Identity Protocol)**.

## Installation

```bash
pip install truthlocks-maip
```

## Quick Start

```python
from truthlocks_maip import (
    MaipClient,
    CreateAgentRequest,
    CreateSessionRequest,
    OfferDelegationRequest,
    CheckGuardrailsRequest,
    Scope,
)

client = MaipClient(api_key="your-api-key")
# For self-hosted: MaipClient(api_key="...", base_url="https://maip.your-company.com")

# Register an agent
agent = client.register_agent(CreateAgentRequest(
    name="my-agent",
    scope=Scope(actions=["read", "write"], resources=["documents/*"]),
    public_key="base64-encoded-public-key",
))

# Create a session
session = client.create_session(CreateSessionRequest(
    agent_id=agent["id"],
    ttl_seconds=3600,
))

# Get trust score
trust = client.get_trust_score(agent["id"])
print(f"Trust level: {trust['level']}, score: {trust['score']}")

# Delegate trust
delegation = client.offer_delegation(OfferDelegationRequest(
    from_agent_id=agent["id"],
    to_agent_id="other-agent-id",
    scope=Scope(actions=["read"], resources=["documents/*"]),
    ttl_seconds=1800,
))

# Check guardrails
result = client.check_guardrails(CheckGuardrailsRequest(
    agent_id=agent["id"],
    action="write",
    resource_id="documents/report.pdf",
))

if result["allowed"]:
    pass  # Proceed with the action
```

## Offline Bundle Verification

Verify receipt bundles without network access:

```python
from truthlocks_maip import verify_bundle

result = verify_bundle(bundle)
if result.valid:
    print(f"Verified {result.receipt_count} receipts")
else:
    print("Bundle verification failed")
```

## API Reference

### `MaipClient`

| Method | Description |
|---|---|
| `register_agent(request)` | Register a new agent identity |
| `list_agents(status?, offset?, limit?)` | List agents with optional filters |
| `get_agent(agent_id)` | Get an agent by ID |
| `suspend_agent(agent_id)` | Suspend an active agent |
| `revoke_agent(agent_id)` | Permanently revoke an agent |
| `create_session(request)` | Create an authenticated session |
| `terminate_session(session_id)` | Terminate a session |
| `get_trust_score(agent_id)` | Get the current trust score |
| `compute_trust_score(request)` | Compute a fresh trust score |
| `offer_delegation(request)` | Offer trust delegation |
| `accept_delegation(delegation_id)` | Accept a delegation |
| `execute_orchestration(request)` | Execute multi-agent orchestration |
| `check_guardrails(request)` | Check guardrails before an action |

### Error Types

| Error | HTTP Status | Description |
|---|---|---|
| `MaipError` | any | Base error class |
| `UnauthorizedError` | 401 | Invalid or missing API key |
| `NotFoundError` | 404 | Resource not found |
| `LimitExceededError` | 429 | Rate limit or quota exceeded |
| `VerificationError` | n/a | Bundle/receipt verification failed |

## License

Apache-2.0

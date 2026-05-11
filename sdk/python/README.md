<p align="center">
  <a href="https://truthlocks.com">
    <img src="https://www.truthlocks.com/logo/logo-color-1.png" alt="Truthlocks" width="200" />
  </a>
</p>

<h1 align="center">Truthlock Python SDK</h1>

<p align="center">
  <strong>Official Python SDK for the Truthlocks Platform</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/truthlock/"><img src="https://img.shields.io/pypi/v/truthlock.svg?style=flat-square" alt="PyPI version" /></a>
  <a href="https://pypi.org/project/truthlock/"><img src="https://img.shields.io/pypi/dm/truthlock.svg?style=flat-square" alt="PyPI downloads" /></a>
  <a href="https://github.com/truthlocks/sdk-python/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square" alt="License" /></a>
  <a href="https://docs.truthlocks.com/sdk/python"><img src="https://img.shields.io/badge/docs-truthlocks.com-brightgreen.svg?style=flat-square" alt="Documentation" /></a>
</p>

<p align="center">
  <a href="https://docs.truthlocks.com/sdk/python">Documentation</a> &bull;
  <a href="https://docs.truthlocks.com/api-reference">API Reference</a> &bull;
  <a href="https://github.com/truthlocks/sdk-python/issues">Issues</a>
</p>

---

Pythonic client for the **Truthlocks** cryptographic trust infrastructure. Issue attestations, verify content authenticity, manage issuers and signing keys, and query the audit trail -- with both synchronous and async support.

## Installation

```bash
pip install truthlock
```

Requires **Python 3.10** or later.

## Quick Start

```python
from truthlock import TruthlockClient

client = TruthlockClient(
    base_url="https://api.truthlocks.com",
    api_key="tlk_live_...",
)

# Create an issuer
issuer = client.issuers.create(
    name="My Organization",
    legal_name="My Organization Inc.",
    display_name="My Org",
)
client.issuers.trust(issuer.id)

# Register a signing key
client.keys.register(
    issuer_id=issuer.id,
    kid="key-1",
    alg="ed25519",
    public_key_b64url="your-public-key",
)

# Mint an attestation
import base64
payload = base64.urlsafe_b64encode(b"Hello World").rstrip(b"=").decode()

attestation = client.attestations.mint(
    issuer_id=issuer.id,
    kid="key-1",
    alg="ed25519",
    payload_b64url=payload,
)

print(f"Attestation ID: {attestation.attestation_id}")

# Verify
result = client.verify.online(
    attestation_id=attestation.attestation_id,
    payload_b64url=payload,
)

if result.verdict == "VALID":
    print("Document verified successfully")
```

## Features

| Feature             | Description                                                 |
| ------------------- | ----------------------------------------------------------- |
| **Attestations**    | Mint, retrieve, list, and revoke cryptographic attestations |
| **Verification**    | Online and offline verification with full verdict details   |
| **Issuers**         | Create, update, trust, and manage issuer identities         |
| **Signing Keys**    | Register, rotate, and revoke Ed25519/ECDSA signing keys     |
| **Receipts**        | Issue, retrieve, and manage structured receipt types        |
| **Audit Trail**     | Query the tamper-evident audit log for any entity           |
| **Async Support**   | Full async/await API via `AsyncTruthlockClient`             |
| **Type Hints**      | Complete type annotations for IDE autocompletion            |
| **Auto-Retry**      | Automatic retries with exponential backoff                  |
| **Pydantic Models** | Response objects are Pydantic models with validation        |

## Async Support

```python
from truthlock import AsyncTruthlockClient

client = AsyncTruthlockClient(
    base_url="https://api.truthlocks.com",
    api_key="tlk_live_...",
)

async def main():
    attestation = await client.attestations.mint(...)
    result = await client.verify.online(
        attestation_id=attestation.attestation_id,
        payload_b64url=payload,
    )
```

## API Resources

### Attestations

```python
# Mint
att = client.attestations.mint(issuer_id=..., kid=..., alg=..., payload_b64url=...)

# Retrieve
att = client.attestations.get("att_abc123")

# List with pagination
items = client.attestations.list(limit=20, offset=0)

# Revoke
client.attestations.revoke("att_abc123", reason="Key compromised")
```

### Verification

```python
# Online (checks revocation, expiry, and signature)
result = client.verify.online(attestation_id="att_...", payload_b64url="...")

# Offline (signature + payload match only)
result = client.verify.offline(attestation_id="att_...", payload_b64url="...")
```

### Issuers & Keys

```python
# Create issuer
issuer = client.issuers.create(name="Acme Corp", legal_name="Acme Corp Inc.")

# Trust issuer
client.issuers.trust(issuer.id)

# Register key
client.keys.register(issuer.id, kid="primary-2026", alg="ed25519", public_key_b64url=...)

# Revoke key
client.keys.revoke(issuer.id, "primary-2025")
```

### Receipts

```python
# Issue
receipt = client.receipts.issue(
    receipt_type="purchase",
    issuer_id=issuer.id,
    payload={"amount": 99.99, "currency": "USD"},
)

# Retrieve
receipt = client.receipts.get(receipt.id)
```

## Error Handling

```python
from truthlock.exceptions import (
    TruthlockError,
    AuthenticationError,
    NotFoundError,
    RateLimitError,
)

try:
    client.attestations.get("invalid-id")
except AuthenticationError:
    print("Invalid or expired API key")
except NotFoundError:
    print("Attestation not found")
except RateLimitError as e:
    print(f"Rate limited. Retry after {e.retry_after}s")
except TruthlockError as e:
    print(f"API error {e.status}: {e.message}")
```

## Configuration

```python
client = TruthlockClient(
    base_url="https://api.truthlocks.com",  # required
    api_key="tlk_live_...",                  # required
    timeout=30.0,                            # request timeout (seconds)
    max_retries=3,                           # retry on transient errors
)
```

## Django Integration

```python
# settings.py
TRUTHLOCK_API_KEY = env("TRUTHLOCK_API_KEY")
TRUTHLOCK_BASE_URL = "https://api.truthlocks.com"

# views.py
from truthlock import TruthlockClient
from django.conf import settings

client = TruthlockClient(
    base_url=settings.TRUTHLOCK_BASE_URL,
    api_key=settings.TRUTHLOCK_API_KEY,
)
```

## FastAPI Integration

```python
from truthlock import AsyncTruthlockClient
from fastapi import FastAPI, Depends

app = FastAPI()

def get_truthlock():
    return AsyncTruthlockClient(
        base_url="https://api.truthlocks.com",
        api_key=os.environ["TRUTHLOCK_API_KEY"],
    )

@app.post("/attest")
async def create_attestation(client=Depends(get_truthlock)):
    return await client.attestations.mint(...)
```

## Documentation

- [SDK Guide](https://docs.truthlocks.com/sdk/python)
- [API Reference](https://docs.truthlocks.com/api-reference)
- [PyPI Package](https://pypi.org/project/truthlock/)
- [Examples](https://github.com/truthlocks/sdk-python/tree/main/examples)

## License

MIT -- see [LICENSE](https://github.com/truthlocks/sdk-python/blob/main/LICENSE) for details.

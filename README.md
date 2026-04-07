# MAIP — Machine Agent Identity Protocol

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

**MAIP** is an open standard for cryptographic identity, authorization, and trust scoring for AI agents and autonomous software systems.

## Problem

AI agents are proliferating across enterprise workflows, yet there is no standard way to:

- **Identify** which agent performed an action
- **Authorize** what an agent is allowed to do
- **Trust** that an agent is behaving within expected boundaries
- **Audit** the complete history of agent actions
- **Revoke** access instantly when behavior is anomalous

## Solution

MAIP provides a complete protocol for machine identity lifecycle management:

| Capability | Description |
|------------|-------------|
| **Agent Identity** | Ed25519/ES256 cryptographic keypairs with unique IDs (`maip-agent:<ulid>`) |
| **Scope-Based Authorization** | Fine-grained `resource:action` permission scopes |
| **Trust Scoring** | Continuous 0-100 behavioral trust evaluation with weighted factors |
| **Session Management** | Time-bounded, scope-narrowed execution contexts with IP allowlisting |
| **Cross-Tenant Delegation** | Bilateral offer/accept delegation chains across organizational boundaries |
| **Witness Network** | Decentralized peer attestation for trust verification |
| **Kill Switch** | Instant emergency revocation of all agent access |
| **AI Orchestration** | Multi-agent workflow execution with cost tracking and safety guardrails |

## Specification

- [Data Model](spec/data-model.md)
- [Trust Model](spec/trust-model.md)
- [Delegation Chain](spec/delegation-chain.md)
- [Receipt Format](spec/receipt-format.md)
- [AI Orchestration](spec/ai-orchestration.md)
- [Threat Model](spec/threat-model.md)
- [Pipeline Integration](spec/pipeline-integration.md)

## Reference Implementation

The reference implementation is available as part of the [Truthlocks](https://truthlocks.com) platform:

- **API Documentation**: [docs.truthlocks.com/guides/machine-identity](https://docs.truthlocks.com/guides/machine-identity)
- **SDKs**: JavaScript, Go, Python (coming soon)
- **Console**: [console.truthlocks.com](https://console.truthlocks.com)

## Quick Start

```bash
# Register an agent
curl -X POST https://api.truthlocks.com/v1/agents \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "name": "my-agent",
    "type": "autonomous",
    "scopes": ["receipts:write"]
  }'

# Create a session
curl -X POST https://api.truthlocks.com/v1/sessions \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "agent_id": "maip-agent:01JXXXX",
    "scopes": ["receipts:write"],
    "ttl_seconds": 3600
  }'

# Check trust score
curl https://api.truthlocks.com/v1/trust-scores/maip-agent:01JXXXX \
  -H "X-API-Key: $API_KEY"
```

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.

---

Built by [Truthlocks](https://truthlocks.com) — Cryptographic Trust for the AI Era.

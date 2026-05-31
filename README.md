# MAIP - Machine Agent Identity Protocol

Open standard for AI agent identity, trust, and accountability.

**Status: Merged into the main Truthlocks platform.**

## Install

```bash
# JavaScript/TypeScript
npm install @truthlocks/sdk

# Python
pip install truthlock

# Go
go get github.com/truthlocks/sdk-go
```

## Quick Start (Free - No Website Needed)

```bash
# Register from CLI
npx @truthlocks/protect register --email dev@example.com

# Or from Python
pip install truthlock
python -c "import asyncio; from truthlock import TruthlockClient; asyncio.run(TruthlockClient.register('dev@example.com'))"
```

## What is MAIP?

MAIP gives every AI agent a cryptographic identity with:
- **Kill switches** - Emergency revocation of rogue agents
- **Trust scores** - Real-time behavioral trust computation
- **Action receipts** - Tamper-proof audit trail of every AI operation
- **Delegation chains** - Verifiable authority transfer between agents
- **Guardrails** - Policy enforcement before agent actions execute

## 10 Signing Algorithms

Ed25519, ES256, ES384, ES512, RS256, RS384, RS512, PS256, PS384, PS512

## Documentation

- [MAIP Guide](https://docs.truthlocks.com/guides/machine-identity)
- [Agent Authorization](https://docs.truthlocks.com/guides/agent-authorization)
- [API Reference](https://docs.truthlocks.com/api-reference/machine-identity/agents/register)
- [Kill Switch](https://docs.truthlocks.com/api-reference/machine-identity/killswitch/kill)

## Specification

- [v1.0.0 Release](https://github.com/truthlocks/maip/releases/tag/v1.0.0)
- [Trust Model](https://docs.truthlocks.com/guides/trust-scores)
- [Delegation Chains](https://docs.truthlocks.com/guides/cross-tenant-delegation)

## License

Apache 2.0

# @truthlocks/maip

JavaScript/TypeScript SDK for the **MAIP (Machine Agent Identity Protocol)**.

## Installation

```bash
npm install @truthlocks/maip
```

## Quick Start

```typescript
import { MaipClient } from "@truthlocks/maip";

const client = new MaipClient({
  apiKey: "your-api-key",
  // For self-hosted deployments:
  // baseUrl: "https://maip.your-company.com",
});

// Register an agent
const agent = await client.registerAgent({
  name: "my-agent",
  scope: { actions: ["read", "write"], resources: ["documents/*"] },
  publicKey: "base64-encoded-public-key",
});

// Create a session
const session = await client.createSession({
  agentId: agent.id,
  ttlSeconds: 3600,
});

// Get trust score
const trust = await client.getTrustScore(agent.id);

// Delegate trust
const delegation = await client.offerDelegation({
  fromAgentId: agent.id,
  toAgentId: "other-agent-id",
  scope: { actions: ["read"], resources: ["documents/*"] },
  ttlSeconds: 1800,
});

// Check guardrails before acting
const guardrails = await client.checkGuardrails({
  agentId: agent.id,
  action: "write",
  resourceId: "documents/report.pdf",
});

if (guardrails.allowed) {
  // Proceed with the action
}
```

## Offline Bundle Verification

Verify receipt bundles without network access:

```typescript
import { verifyBundle } from "@truthlocks/maip";

const result = await verifyBundle(bundle);
if (result.valid) {
  console.log("Verified " + result.receiptCount + " receipts");
} else {
  console.error("Bundle verification failed");
}
```

## API Reference

### MaipClient

| Method | Description |
|---|---|
| `registerAgent(request)` | Register a new agent identity |
| `listAgents(options?)` | List agents with optional filters |
| `getAgent(agentId)` | Get an agent by ID |
| `suspendAgent(agentId)` | Suspend an active agent |
| `revokeAgent(agentId)` | Permanently revoke an agent |
| `createSession(request)` | Create an authenticated session |
| `terminateSession(sessionId)` | Terminate a session |
| `getTrustScore(agentId)` | Get the current trust score |
| `computeTrustScore(request)` | Compute a fresh trust score |
| `offerDelegation(request)` | Offer trust delegation |
| `acceptDelegation(delegationId)` | Accept a delegation |
| `executeOrchestration(request)` | Execute multi-agent orchestration |
| `checkGuardrails(request)` | Check guardrails before an action |

### Error Types

| Error | HTTP Status | Description |
|---|---|---|
| `MaipError` | any | Base error class |
| `UnauthorizedError` | 401 | Invalid or missing API key |
| `NotFoundError` | 404 | Resource not found |
| `LimitExceededError` | 429 | Rate limit or quota exceeded |
| `VerificationError` | n/a | Bundle/receipt verification failed |

## Self-Hosted Deployments

Point the client to your own MAIP-compatible server:

```typescript
const client = new MaipClient({
  apiKey: "your-api-key",
  baseUrl: "https://maip.internal.example.com",
  timeoutMs: 10_000,
});
```

## License

Apache-2.0

<p align="center">
  <a href="https://truthlocks.com">
    <img src="https://www.truthlocks.com/logo/logo-color-1.png" alt="Truthlocks" width="200" />
  </a>
</p>

<h1 align="center">@truthlock/sdk</h1>

<p align="center">
  <strong>Official TypeScript/JavaScript SDK for the Truthlocks Platform</strong>
</p>

<p align="center">
  <a href="https://www.npmjs.com/package/@truthlock/sdk"><img src="https://img.shields.io/npm/v/@truthlock/sdk.svg?style=flat-square" alt="npm version" /></a>
  <a href="https://www.npmjs.com/package/@truthlock/sdk"><img src="https://img.shields.io/npm/dm/@truthlock/sdk.svg?style=flat-square" alt="npm downloads" /></a>
  <a href="https://github.com/truthlocks/truthlock/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square" alt="License" /></a>
  <a href="https://docs.truthlocks.com/sdk/js"><img src="https://img.shields.io/badge/docs-truthlocks.com-brightgreen.svg?style=flat-square" alt="Documentation" /></a>
</p>

<p align="center">
  <a href="https://docs.truthlocks.com/sdk/js">Documentation</a> &bull;
  <a href="https://docs.truthlocks.com/api-reference">API Reference</a> &bull;
  <a href="https://github.com/truthlocks/truthlock/issues">Issues</a>
</p>

---

Full-featured TypeScript SDK for the **Truthlocks** cryptographic trust infrastructure. Issue attestations, verify content authenticity, manage signing keys, track audit trails, and evaluate risk -- with complete type safety, automatic retries, and idempotency built in.

## Installation

```bash
npm install @truthlock/sdk
```

```bash
yarn add @truthlock/sdk
```

```bash
pnpm add @truthlock/sdk
```

## Quick Start

```typescript
import { TruthlockClient, Algorithm, Verdict } from "@truthlock/sdk";

const client = new TruthlockClient({
  baseUrl: "https://api.truthlocks.com",
  auth: { type: "tenant", tenantId: "your-tenant-id" },
});

// Create an issuer
const issuer = await client.issuers.create({
  name: "My Org",
  legal_name: "My Organization Inc.",
  display_name: "My Org",
});

await client.issuers.trust(issuer.id);

// Register a signing key
await client.keys.register(issuer.id, {
  kid: "key-1",
  alg: Algorithm.Ed25519,
  public_key_b64url: "your-public-key",
});

// Mint an attestation
const attestation = await client.attestations.mint({
  issuer_id: issuer.id,
  kid: "key-1",
  alg: Algorithm.Ed25519,
  payload_b64url: Buffer.from("Hello World").toString("base64url"),
});

// Verify
const result = await client.verify.verifyOnline({
  attestation_id: attestation.attestation_id,
  payload_b64url: Buffer.from("Hello World").toString("base64url"),
});

if (result.verdict === Verdict.Valid) {
  console.log("Document verified successfully");
}
```

## Features

| Feature             | Description                                                    |
| ------------------- | -------------------------------------------------------------- |
| **Attestations**    | Mint, retrieve, list, and revoke cryptographic attestations    |
| **Verification**    | Online and offline verification with full verdict details      |
| **Issuers**         | Create, update, trust, and manage issuer identities            |
| **Signing Keys**    | Register, rotate, and revoke Ed25519/ECDSA signing keys        |
| **Receipts**        | Issue, retrieve, and manage structured receipt types           |
| **Risk Evaluation** | Ingest signals, evaluate risk, and manage fraud cases          |
| **Audit Trail**     | Query the tamper-evident audit log for any entity              |
| **Auto-Retry**      | Automatic retries with exponential backoff on transient errors |
| **Idempotency**     | Built-in idempotency key generation for safe retries           |
| **Dual Module**     | ESM and CommonJS support out of the box                        |

## API Resources

### Attestations

```typescript
// Mint an attestation
const att = await client.attestations.mint({ ... });

// Retrieve by ID
const fetched = await client.attestations.get(att.attestation_id);

// List with pagination
const list = await client.attestations.list({ limit: 20, offset: 0 });

// Revoke
await client.attestations.revoke(att.attestation_id, "Key compromised");
```

### Verification

```typescript
// Online verification (checks revocation, expiry, signature)
const result = await client.verify.verifyOnline({
  attestation_id: "att_...",
  payload_b64url: "...",
});

// Offline verification (signature + payload match only)
const offline = await client.verify.verifyOffline({ ... });
```

### Issuers & Keys

```typescript
// Create an issuer
const issuer = await client.issuers.create({ name: "Acme Corp", ... });

// Trust the issuer
await client.issuers.trust(issuer.id);

// Register a signing key
await client.keys.register(issuer.id, {
  kid: "primary-2026",
  alg: Algorithm.Ed25519,
  public_key_b64url: publicKeyB64,
});

// Rotate keys
await client.keys.revoke(issuer.id, "primary-2025");
```

### Receipts

```typescript
// Issue a receipt
const receipt = await client.receipts.issue({
  receipt_type: "purchase",
  issuer_id: issuer.id,
  payload: { amount: 99.99, currency: "USD" },
});

// Retrieve a receipt
const fetched = await client.receipts.get(receipt.id);

// Redact a receipt
await client.receipts.redact(receipt.id);
```

### Risk Evaluation

```typescript
import { RiskResource } from "@truthlock/sdk";

// Ingest a risk signal
await client.risk.ingestSignal({
  signal_source: "login-service",
  signal_type: "failed_login",
  subject_id: "user-123",
  risk_score: 65,
});

// Evaluate risk
const decision = await client.risk.evaluate({
  subject_id: "user-123",
  signal_type: "login",
  risk_score: 72,
});
```

### Audit Trail

```typescript
// Query audit events
const events = await client.audit.query({
  entity_type: "attestation",
  entity_id: att.attestation_id,
  limit: 50,
});
```

## Authentication

```typescript
// Tenant authentication
const client = new TruthlockClient({
  baseUrl: "https://api.truthlocks.com",
  auth: { type: "tenant", tenantId: "tnt_..." },
});

// API key authentication
const client = new TruthlockClient({
  baseUrl: "https://api.truthlocks.com",
  auth: { type: "apiKey", apiKey: "tlk_live_..." },
});
```

## Error Handling

```typescript
import { TruthlockError, ErrorCode } from "@truthlock/sdk";

try {
  await client.attestations.get("invalid-id");
} catch (err) {
  if (err instanceof TruthlockError) {
    console.error(`[${err.code}] ${err.message}`);
    // err.status  -- HTTP status code
    // err.code    -- Truthlocks error code
    // err.details -- Additional context
  }
}
```

## Requirements

- **Node.js** >= 18.0.0
- **TypeScript** >= 4.7.0 (optional -- full `.d.ts` definitions included)

## Documentation

- [SDK Guide](https://docs.truthlocks.com/sdk/js)
- [API Reference](https://docs.truthlocks.com/api-reference)
- [Quick Start Tutorial](https://docs.truthlocks.com/guides/onboarding)
- [Examples](https://github.com/truthlocks/truthlock/tree/main/examples)

## License

MIT -- see [LICENSE](https://github.com/truthlocks/truthlock/blob/main/LICENSE) for details.

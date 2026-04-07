# MAIP Receipt Format Specification

**Protocol**: Machine Agent Identity Protocol (MAIP)
**Version**: 1.0.0-draft
**Status**: Draft
**Date**: 2026-04-06
**Authors**: Truthlocks Inc.
**License**: Apache 2.0
**Companion**: MAIP_SPEC_DATA_MODEL.md

---

## Table of Contents

1. [Overview](#1-overview)
2. [Receipt Types](#2-receipt-types)
3. [Common Receipt Fields](#3-common-receipt-fields)
4. [Anti-Replay Mechanisms](#4-anti-replay-mechanisms)
5. [Receipt Chaining](#5-receipt-chaining)
6. [Type-Specific Payloads](#6-type-specific-payloads)
7. [Truth Claim Receipts](#7-truth-claim-receipts)
8. [Compliance Receipts](#8-compliance-receipts)
9. [Verification Algorithm](#9-verification-algorithm)
10. [Serialization and Canonicalization](#10-serialization-and-canonicalization)
11. [Conformance](#11-conformance)

---

## 1. Overview

This document defines the canonical receipt format for the Machine Agent Identity Protocol (MAIP). A **receipt** is a signed, tamper-evident record of an event in the MAIP system: an agent creation, a delegation, an action, a revocation, or a compliance check.

Every MAIP receipt is:

- **Signed**: Ed25519 (or ES256/RS256) signature over the JCS-canonicalized receipt body.
- **Anchored**: Recorded in the Truthlocks transparency log with a Merkle inclusion proof.
- **Chained**: Linked to the previous receipt by the same issuer, forming a tamper-evident sequence.
- **Schema-validated**: Payload conforms to a registered JSON Schema (draft 2020-12).
- **Tenant-isolated**: Scoped by RLS; receipts are only visible within the originating tenant.

### 1.1 Relationship to Truthlocks Primitives

MAIP receipts are implemented on top of the existing Truthlocks receipt infrastructure:

| MAIP Concept | Truthlocks Implementation |
|-------------|--------------------------|
| Receipt minting | `POST /v1/receipts` via Attestation Service |
| Receipt signing | `signing-service` gRPC `Sign()` with Ed25519/ES256/RS256 |
| Log anchoring | `transparency-log` gRPC `AppendEntry()` |
| Schema validation | `receipt_types` table + `validateReceiptPayload()` |
| Receipt revocation | `POST /v1/receipts/{id}/revoke` |
| Proof bundle | `GET /v1/receipts/{id}/proof-bundle` |
| Verification | `POST /v1/receipts/verify` |

The `CanonicalReceiptEnvelope` wraps all MAIP receipts:

```go
// From attestation-service/internal/service/receipts.go
type CanonicalReceiptEnvelope struct {
    SpecVersion    string          `json:"spec_version"`    // "receipt-v1"
    ReceiptType    string          `json:"receipt_type"`    // MAIP schema ID
    ReceiptVersion string          `json:"receipt_version"` // Schema version
    ReceiptID      string          `json:"receipt_id"`      // UUID
    TenantID       string          `json:"tenant_id"`       // UUID
    IssuerID       string          `json:"issuer_id"`       // UUID or maip agent ID
    IssuedAt       string          `json:"issued_at"`       // RFC 3339
    Subject        string          `json:"subject"`         // Subject identifier
    Payload        json.RawMessage `json:"payload"`         // Type-specific fields
    Metadata       json.RawMessage `json:"metadata"`        // Optional metadata
}
```

---

## 2. Receipt Types

MAIP defines nine receipt types. Each type has a dedicated `receipt_type` name registered in the schema registry and a type-specific payload structure.

| Receipt Type | `receipt_type` Value | Purpose | Default Expiry |
|-------------|---------------------|---------|---------------|
| Genesis Receipt | `maip_genesis` | Agent creation, includes genesis public key | None (permanent) |
| Delegation Receipt | `maip_delegation` | Authority delegation from parent to child | 1 year |
| Action Receipt | `maip_action` | Record of a discrete agent action | 24 hours |
| Dataset Attestation Receipt | `maip_dataset_attestation` | Dataset version signing with Merkle root | 1 year |
| Model Attestation Receipt | `maip_model_attestation` | Model version signing with weights hash | 1 year |
| Revocation Receipt | `maip_revocation` | Key, agent, or delegation revocation | None (permanent) |
| Approval Receipt | `maip_approval` | Human approval of an agent action | 24 hours |
| Compliance Receipt | `maip_compliance` | Regulatory compliance attestation | Per regulation |
| Truth Claim Receipt | `maip_truth_claim` | Multi-witness truth assertion | 1 year |

### 2.1 Type Hierarchy

```
maip_genesis (root of an agent's receipt chain)
    |
    +-- maip_delegation (grants authority to child agents)
    |       |
    |       +-- maip_delegation (sub-delegation, depth increases)
    |
    +-- maip_action (records agent behavior)
    |       |
    |       +-- maip_approval (human sign-off on action)
    |
    +-- maip_dataset_attestation (signs data)
    |
    +-- maip_model_attestation (signs models)
    |
    +-- maip_compliance (regulatory proof)
    |
    +-- maip_truth_claim (multi-witness consensus)
    |
    +-- maip_revocation (terminates any of the above)
```

---

## 3. Common Receipt Fields

All MAIP receipt types share a common envelope structure. The `payload` field contains type-specific data defined in Section 6.

### 3.1 Full Receipt Structure

```json
{
  "receipt_id": "rcpt_01HXYZ9K7PQRS4TUV0WX1YZ2AB",
  "receipt_type": "<maip_genesis | maip_delegation | maip_action | ...>",
  "schema_version": "1.0.0",
  "issuer_id": "<maip agent ID or human issuer UUID>",
  "subject_id": "<entity this receipt is about>",
  "subject_type": "agent | dataset | model | pipeline | document",
  "created_at": "2026-04-06T12:00:00Z",
  "expires_at": "2026-04-07T12:00:00Z",
  "audience": "<intended verifier domain | null>",
  "purpose": "<why this receipt was created>",
  "nonce": "<32-byte random value, base64url encoded>",

  "context": {
    "tenant_id": "<uuid>",
    "delegation_chain_hash": "<base64url SHA-256 of the serialized delegation chain>",
    "delegation_depth": 2,
    "scopes_used": ["inference", "data_read"]
  },

  "payload": {
    "<type-specific fields -- see Section 6>"
  },

  "previous_receipt_id": "<receipt_id of the prior receipt by this issuer | null>",
  "attestation_id": "<uuid of the Truthlocks attestation backing this receipt>",
  "transparency_log_entry": {
    "log_id": "<uuid>",
    "leaf_index": 42,
    "leaf_hash": "<base64url>"
  },

  "signature": {
    "alg": "Ed25519",
    "kid": "<key identifier>",
    "value": "<base64url Ed25519 signature over JCS-canonical JSON of all fields above>"
  }
}
```

### 3.2 Field Definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `receipt_id` | string | Yes | Unique receipt identifier. Format: `rcpt_<ulid>`. |
| `receipt_type` | string | Yes | One of the nine MAIP receipt types. |
| `schema_version` | string | Yes | Semantic version of the receipt schema. |
| `issuer_id` | string | Yes | MAIP agent ID (`maip:...`) or human issuer UUID. The entity that created and signed this receipt. |
| `subject_id` | string | Yes | The entity this receipt is about. May be an agent ID, dataset ID, model ID, or document hash. |
| `subject_type` | string | Yes | Type classifier for the subject: `agent`, `dataset`, `model`, `pipeline`, or `document`. |
| `created_at` | string | Yes | ISO 8601 UTC timestamp of receipt creation. |
| `expires_at` | string | No | ISO 8601 UTC timestamp after which this receipt is no longer valid. `null` for permanent receipts. |
| `audience` | string | No | Domain or identifier of the intended verifier. Restricts acceptance (see Section 4.2). |
| `purpose` | string | No | Declared use case for the receipt. Free-form string. Examples: `kyc_verification`, `model_training`, `audit_evidence`. |
| `nonce` | string | Yes | 32-byte cryptographically random value, base64url-encoded. Unique per receipt. |
| `context` | object | Yes | Delegation and scope context at receipt creation time. |
| `context.tenant_id` | string | Yes | UUID of the tenant. |
| `context.delegation_chain_hash` | string | Yes | SHA-256 hash of the full serialized delegation chain from the acting agent up to the root. |
| `context.delegation_depth` | integer | Yes | Depth of the acting agent in the delegation tree (0 = root). |
| `context.scopes_used` | array | Yes | Array of scope strings exercised by this receipt. Must be a subset of the agent's delegated scopes. |
| `payload` | object | Yes | Type-specific receipt data. Validated against the registered JSON Schema. |
| `previous_receipt_id` | string | No | Receipt ID of the immediately prior receipt issued by the same `issuer_id`. `null` for the first receipt. |
| `attestation_id` | string | Yes | UUID of the Truthlocks attestation that cryptographically backs this receipt. |
| `transparency_log_entry` | object | Yes | Transparency log coordinates for this receipt. |
| `transparency_log_entry.log_id` | string | Yes | UUID of the transparency log instance. |
| `transparency_log_entry.leaf_index` | integer | Yes | Leaf index in the Merkle tree. |
| `transparency_log_entry.leaf_hash` | string | Yes | Base64url-encoded leaf hash. |
| `signature` | object | Yes | Cryptographic signature over the receipt. |
| `signature.alg` | string | Yes | Signing algorithm: `Ed25519`, `ES256`, or `RS256`. |
| `signature.kid` | string | Yes | Key identifier of the signing key. |
| `signature.value` | string | Yes | Base64url-encoded signature bytes. |

### 3.3 Signature Computation

The signature covers all fields **except** the `signature` field itself:

```
1. Construct the receipt object with all fields except `signature`.
2. Serialize using JCS (RFC 8785) to produce canonical_bytes.
3. Sign: signature_bytes = Sign(private_key, canonical_bytes)
4. Encode: signature.value = base64url_no_pad(signature_bytes)
```

The verification counterpart:

```
1. Extract the `signature` field and remove it from the receipt object.
2. Serialize the remaining object using JCS to produce canonical_bytes.
3. Verify: Ed25519_Verify(public_key, canonical_bytes, decode(signature.value))
```

---

## 4. Anti-Replay Mechanisms

MAIP receipts incorporate six defense layers against replay, misuse, and tampering.

### 4.1 Nonce

Every receipt contains a `nonce` field: 32 bytes of cryptographically secure random data, base64url-encoded (43 characters).

**Requirements:**
- The nonce MUST be generated using a CSPRNG (e.g., `crypto/rand` in Go, `secrets.token_bytes` in Python).
- The nonce MUST be unique per receipt. Implementations MUST reject duplicate nonces within a sliding window of 24 hours for the same `issuer_id`.
- The nonce is included in the signed payload, so any modification invalidates the signature.

**Verification:**
```
IF seen_nonces[issuer_id] CONTAINS receipt.nonce
    AND receipt.created_at is within 24 hours of a prior receipt with the same nonce:
  REJECT with DUPLICATE_NONCE
```

### 4.2 Audience Restriction

The `audience` field restricts which verifier may accept a receipt.

**Semantics:**
- When `audience` is set, only a verifier whose domain matches the audience value SHOULD accept the receipt.
- Audience is a domain string (e.g., `verify.acme-corp.com`) or a structured identifier (e.g., `urn:maip:verifier:acme-corp`).
- A verifier receiving a receipt with a non-matching audience MUST return `AUDIENCE_MISMATCH`.
- When `audience` is `null`, the receipt is bearer-valid (any verifier may accept it).

**Use case:** An agent generates an inference receipt for a specific downstream consumer. Setting `audience: "ml-platform.customer.com"` ensures the receipt cannot be replayed to a different consumer.

### 4.3 Purpose Declaration

The `purpose` field declares the intended use of the receipt.

**Semantics:**
- Purpose is advisory and machine-readable. Verifiers MAY enforce purpose matching.
- Standard purpose values: `kyc_verification`, `model_training`, `audit_evidence`, `compliance_proof`, `data_access_log`, `inference_record`, `delegation_proof`.
- Custom purpose values SHOULD use a namespaced format: `custom:<tenant_hint>:<purpose_name>`.

### 4.4 Temporal Validity

The `expires_at` field sets a hard expiration boundary.

**Default expiry by receipt type:**

| Receipt Type | Default Expiry | Rationale |
|-------------|---------------|-----------|
| `maip_genesis` | None (permanent) | Agent identity is permanent until revoked |
| `maip_delegation` | 1 year | Delegations should be periodically renewed |
| `maip_action` | 24 hours | Action receipts are ephemeral evidence |
| `maip_dataset_attestation` | 1 year | Datasets may be re-attested with new versions |
| `maip_model_attestation` | 1 year | Models may be superseded |
| `maip_revocation` | None (permanent) | Revocations are permanent records |
| `maip_approval` | 24 hours | Approvals are time-sensitive |
| `maip_compliance` | Per regulation | Varies: 90 days (SOC2), 1 year (GDPR), etc. |
| `maip_truth_claim` | 1 year | Claims may need periodic re-attestation |

**Verification:**
```
IF receipt.expires_at IS NOT NULL AND receipt.expires_at < NOW():
  REJECT with EXPIRED
```

### 4.5 Delegation Chain Binding

The `context.delegation_chain_hash` field cryptographically binds the receipt to the specific delegation chain that was active when the receipt was created.

**Construction:**

```
chain_entries = [
  { parent_agent_id, child_agent_id, scopes, depth, delegation_attestation_id }
  for each delegation from acting agent up to root
]
chain_json = JCS_canonicalize(chain_entries)
delegation_chain_hash = SHA-256(chain_json)
```

**Verification:**

If the delegation chain changes after receipt creation (e.g., an intermediate delegation is revoked), the `delegation_chain_hash` will no longer match the current chain. This does not invalidate the receipt (it was valid at creation time) but signals that the authority context has changed.

```
IF delegation_chain_hash does not match recomputed chain:
  WARN with DELEGATION_CHAIN_STALE (receipt was valid at issuance but chain has since changed)
```

If any delegation in the chain was revoked **before** the receipt's `created_at`, the receipt is invalid:

```
IF any delegation in chain was revoked_at < receipt.created_at:
  REJECT with DELEGATION_REVOKED_AT_ISSUE
```

### 4.6 Receipt Chaining

The `previous_receipt_id` field creates a tamper-evident, append-only sequence per issuer. See Section 5 for full details.

---

## 5. Receipt Chaining

### 5.1 Chain Model

Each agent (identified by `issuer_id`) maintains an ordered, append-only chain of receipts. The chain is implemented via the `previous_receipt_id` field, which references the immediately preceding receipt by the same issuer.

```
[genesis_receipt] --> [delegation_receipt] --> [action_receipt_1] --> [action_receipt_2] --> ...
     (prev=null)         (prev=genesis)           (prev=deleg)          (prev=action_1)
```

### 5.2 Chain Rules

1. **First receipt**: The first receipt issued by an agent MUST have `previous_receipt_id = null`. This is always a `maip_genesis` receipt.

2. **Subsequent receipts**: Every subsequent receipt by the same issuer MUST set `previous_receipt_id` to the `receipt_id` of the immediately prior receipt.

3. **Chain integrity**: The chain forms a singly-linked list. A verifier can traverse from any receipt backward to the genesis receipt.

4. **Gap detection**: If a verifier discovers a gap in the chain (a receipt references a `previous_receipt_id` that itself references a `previous_receipt_id` that skips over known receipts), this indicates either a compromised agent or a network partition during receipt creation.

5. **Cross-type chaining**: The chain spans receipt types. An agent's chain may be: genesis -> delegation -> action -> action -> revocation. All are linked regardless of type.

### 5.3 Chain Verification

```
FUNCTION verify_chain(receipt):
  current = receipt
  seen = {}
  
  WHILE current.previous_receipt_id IS NOT NULL:
    IF current.receipt_id IN seen:
      RETURN CHAIN_CYCLE_DETECTED
    seen.add(current.receipt_id)
    
    previous = fetch_receipt(current.previous_receipt_id)
    IF previous IS NULL:
      RETURN CHAIN_BROKEN (missing receipt)
    IF previous.issuer_id != current.issuer_id:
      RETURN CHAIN_ISSUER_MISMATCH
    IF previous.created_at > current.created_at:
      RETURN CHAIN_TEMPORAL_VIOLATION
    
    current = previous
  
  -- Reached the genesis receipt (previous_receipt_id = null)
  IF current.receipt_type != "maip_genesis":
    RETURN CHAIN_MISSING_GENESIS
  
  RETURN CHAIN_VALID
```

### 5.4 Chain Queries

**"Show me everything this agent did, in order":**

```sql
WITH RECURSIVE chain AS (
    -- Start from the latest known receipt
    SELECT r.*, 0 AS chain_position
    FROM receipt_events r
    WHERE r.id = $1  -- latest receipt ID
    
    UNION ALL
    
    SELECT r.*, c.chain_position + 1
    FROM chain c
    JOIN receipt_events r ON r.id = (
        -- Extract previous_receipt_id from the payload
        c.payload_json->>'previous_receipt_id'
    )::uuid
)
SELECT * FROM chain ORDER BY chain_position DESC;
```

**"Find all action receipts by this agent in the last 24 hours":**

```sql
SELECT * FROM action_receipts
WHERE agent_id = $1
  AND tenant_id = $2
  AND created_at > NOW() - INTERVAL '24 hours'
ORDER BY created_at ASC;
```

---

## 6. Type-Specific Payloads

### 6.1 Genesis Receipt (`maip_genesis`)

Issued when a new MAIP agent is created. This is always the first receipt in an agent's chain.

**Payload:**

```json
{
  "schema_id": "maip_genesis",
  "schema_version": "1.0.0",
  "created_at": "2026-04-06T12:00:00Z",
  "issuer_id": "<human or org UUID that authorized this agent>",

  "agent_id": "maip:a1b2c3d4:01HXYZ9K7PQRS4TUV0WX1YZ2AB",
  "display_name": "Inference Agent - Production",
  "trust_level": "delegated",
  "genesis_public_key": "<base64url Ed25519 public key>",
  "genesis_key_algorithm": "Ed25519",
  "parent_agent_id": null,
  "capabilities": ["inference", "data_read", "model_load"],
  "max_delegation_depth": 3,
  "runtime_environment": {
    "platform": "aws-ecs",
    "region": "us-east-1",
    "image_hash": "<sha256 of container image>"
  }
}
```

**Constraints:**
- `genesis_public_key` MUST be a valid Ed25519 public key (32 bytes, base64url-encoded).
- `trust_level` MUST be one of: `system` (platform-managed agent), `delegated` (human-delegated), `ephemeral` (short-lived, auto-expires).
- `capabilities` MUST be a non-empty array. These define the maximum scope this agent can ever exercise or delegate.
- `max_delegation_depth` MUST be between 0 and 8 (inclusive). A value of 0 means the agent cannot delegate to sub-agents.

### 6.2 Delegation Receipt (`maip_delegation`)

Records authority delegation from a parent agent to a child agent.

**Payload:**

```json
{
  "schema_id": "maip_delegation",
  "schema_version": "1.0.0",
  "created_at": "2026-04-06T12:00:00Z",
  "issuer_id": "maip:a1b2c3d4:01HXYZ_PARENT",

  "parent_agent_id": "maip:a1b2c3d4:01HXYZ_PARENT",
  "child_agent_id": "maip:a1b2c3d4:01HXYZ_CHILD",
  "child_public_key": "<base64url Ed25519 public key of child>",
  "scopes": ["inference", "data_read"],
  "depth": 1,
  "max_depth": 2,
  "expires_at": "2027-04-06T12:00:00Z",
  "constraints": {
    "rate_limit": { "max_requests_per_hour": 1000 },
    "allowed_models": ["llm-summarizer-v3"],
    "time_window": {
      "start": "08:00:00Z",
      "end": "20:00:00Z"
    }
  },
  "revocable_by": ["maip:a1b2c3d4:01HXYZ_PARENT"]
}
```

**Constraints:**
- `scopes` MUST be a strict subset of (or equal to) the parent agent's scopes at the time of delegation.
- `depth` MUST equal `parent_depth + 1`.
- `depth` MUST NOT exceed `MAIP_MAX_DEPTH` (8).
- `depth` MUST NOT exceed the parent's `max_delegation_depth`.
- `max_depth` MUST NOT exceed `parent.max_delegation_depth - 1`.

**Scope subsetting rule:**

```
FUNCTION validate_delegation_scopes(parent_scopes, child_scopes):
  FOR EACH scope IN child_scopes:
    IF scope NOT IN parent_scopes:
      REJECT with SCOPE_ESCALATION
  RETURN OK
```

### 6.3 Action Receipt (`maip_action`)

Records a discrete action performed by an agent.

**Payload:**

```json
{
  "schema_id": "maip_action",
  "schema_version": "1.0.0",
  "created_at": "2026-04-06T12:05:00Z",
  "issuer_id": "maip:a1b2c3d4:01HXYZ_CHILD",

  "agent_id": "maip:a1b2c3d4:01HXYZ_CHILD",
  "action_type": "inference",
  "inputs_hash": "<base64url SHA-256 of input data>",
  "outputs_hash": "<base64url SHA-256 of output data>",
  "scopes_used": ["inference"],
  "delegation_chain_hash": "<base64url>",
  "duration_ms": 342,
  "status": "COMPLETE",
  "resource_accessed": {
    "type": "model",
    "id": "llm-summarizer-v3",
    "version": "3.2.1"
  },
  "error_code": null
}
```

**PENDING pattern:** For asynchronous operations, the initial receipt sets `outputs_hash = "PENDING"` and `status = "PENDING"`. On completion, a new receipt is minted with the final output hash and `status = "COMPLETE"` or `"FAILED"`. The original PENDING receipt is superseded via the Attestation Service's supersede operation.

### 6.4 Dataset Attestation Receipt (`maip_dataset_attestation`)

Signs a specific version of a dataset with its Merkle root.

**Payload:**

```json
{
  "schema_id": "maip_dataset_attestation",
  "schema_version": "1.0.0",
  "created_at": "2026-04-06T10:00:00Z",
  "issuer_id": "maip:a1b2c3d4:01HXYZ_DATA_AGENT",

  "dataset_id": "ds_customer_transactions_2026q1",
  "version": "1.0.0",
  "merkle_root": "<base64url>",
  "chunk_count": 4096,
  "chunk_size_bytes": 1048576,
  "total_size_bytes": 4294967296,
  "record_count": 1500000,
  "description": "Customer transaction dataset for Q1 2026",
  "lineage": {
    "source_dataset_ids": ["ds_raw_transactions_2026q1"],
    "transformation_receipt_id": "rcpt_01HXYZ..."
  }
}
```

### 6.5 Model Attestation Receipt (`maip_model_attestation`)

Signs a specific model version, binding weights to training data.

**Payload:**

```json
{
  "schema_id": "maip_model_attestation",
  "schema_version": "1.0.0",
  "created_at": "2026-04-06T08:00:00Z",
  "issuer_id": "maip:a1b2c3d4:01HXYZ_TRAINING_AGENT",

  "model_id": "llm-summarizer-v3",
  "model_version": "3.2.1",
  "weights_hash": "<base64url SHA-256 of model file>",
  "framework": "pytorch",
  "serialization_format": "safetensors",
  "training_dataset_attestation_id": "<uuid>",
  "metrics_hash": "<base64url SHA-256 of evaluation metrics JSON>",
  "evaluation_results": {
    "accuracy": 0.943,
    "f1_score": 0.921,
    "eval_dataset_size": 50000
  }
}
```

### 6.6 Revocation Receipt (`maip_revocation`)

Records the revocation of an agent, delegation, key, or prior receipt.

**Payload:**

```json
{
  "schema_id": "maip_revocation",
  "schema_version": "1.0.0",
  "created_at": "2026-04-06T14:00:00Z",
  "issuer_id": "<agent or human that initiated revocation>",

  "revocation_target_type": "agent | delegation | key | receipt",
  "revocation_target_id": "<ID of the entity being revoked>",
  "reason": "key_compromise | policy_violation | expired | administrative | other",
  "reason_detail": "Agent key material may have been exposed during incident INC-2026-0042",
  "effective_at": "2026-04-06T14:00:00Z",
  "cascade": true,
  "cascaded_revocations": [
    {
      "target_type": "delegation",
      "target_id": "<delegation_id>",
      "receipt_id": "<revocation receipt for this cascade target>"
    }
  ]
}
```

**Cascade semantics:** When an agent is revoked with `cascade: true`:
1. All delegations where the agent is the parent are revoked.
2. All delegations where the agent is the child are revoked.
3. All action receipts issued by the agent after the `effective_at` timestamp are marked invalid.
4. Each cascade target receives its own revocation receipt, linked via `cascaded_revocations`.

**Revocation is permanent:** Once a revocation receipt is minted and anchored in the transparency log, it cannot be undone. To restore an agent's authority, a new genesis receipt and delegation chain must be created.

### 6.7 Approval Receipt (`maip_approval`)

Records a human's explicit approval of an agent action. Used for human-in-the-loop workflows.

**Payload:**

```json
{
  "schema_id": "maip_approval",
  "schema_version": "1.0.0",
  "created_at": "2026-04-06T12:10:00Z",
  "issuer_id": "<human approver UUID>",

  "approved_receipt_id": "<receipt_id of the action being approved>",
  "approved_agent_id": "maip:a1b2c3d4:01HXYZ_CHILD",
  "approval_type": "pre_approval | post_approval | conditional",
  "decision": "approve | reject | escalate",
  "conditions": [
    "Only valid for transactions under $10,000",
    "Must be used within 24 hours"
  ],
  "approver_role": "compliance_officer",
  "approver_org": "Acme Corp Risk Management"
}
```

**Semantics:**
- `pre_approval`: Human approves before the agent acts. The agent's action receipt references this approval.
- `post_approval`: Human reviews and approves after the agent has already acted.
- `conditional`: Approval is granted subject to conditions. The agent MUST verify conditions are met.

---

## 7. Truth Claim Receipts

### 7.1 Overview

A truth claim receipt records a multi-witness assertion: multiple independent issuers attest to the same claim. This enables decentralized verification without requiring trust in a single authority.

**Use cases:**
- "3 independent auditors attest this document is genuine"
- "5 out of 7 validator nodes confirm this inference output is correct"
- "2 compliance officers sign off on this KYC result"

### 7.2 Payload Structure

```json
{
  "schema_id": "maip_truth_claim",
  "schema_version": "1.0.0",
  "created_at": "2026-04-06T16:00:00Z",
  "issuer_id": "<coordinating agent or human>",

  "claim_type": "document_authenticity | model_accuracy | data_integrity | custom",
  "claim_description": "The document with hash X is an authentic, unaltered version of the original.",
  "subject_hash": "<base64url SHA-256 of the claim subject>",

  "witness_receipts": [
    {
      "receipt_id": "rcpt_01HXYZ_WITNESS_1",
      "issuer_id": "maip:a1b2c3d4:01HXYZ_AUDITOR_1",
      "trust_level": "system",
      "trust_weight": 1.0,
      "attested_at": "2026-04-06T15:30:00Z"
    },
    {
      "receipt_id": "rcpt_01HXYZ_WITNESS_2",
      "issuer_id": "maip:f9e8d7c6:01HXYZ_AUDITOR_2",
      "trust_level": "delegated",
      "trust_weight": 0.8,
      "attested_at": "2026-04-06T15:45:00Z"
    },
    {
      "receipt_id": "rcpt_01HXYZ_WITNESS_3",
      "issuer_id": "maip:11223344:01HXYZ_AUDITOR_3",
      "trust_level": "delegated",
      "trust_weight": 0.8,
      "attested_at": "2026-04-06T15:55:00Z"
    }
  ],

  "consensus_threshold": 3,
  "consensus_score": 0.8667,
  "consensus_met": true,
  "consensus_algorithm": "weighted_majority"
}
```

### 7.3 Consensus Computation

**Weighted majority:**

```
total_weight = SUM(witness.trust_weight for witness in witness_receipts)
consensus_score = total_weight / (consensus_threshold * max_trust_weight)
```

Where `max_trust_weight` is 1.0 (the weight of a `system`-level agent).

**Trust weight assignment by trust level:**

| Trust Level | Default Weight | Description |
|------------|---------------|-------------|
| `system` | 1.0 | Platform-managed agents with hardware-backed keys |
| `delegated` | 0.8 | Human-delegated agents with standard key management |
| `ephemeral` | 0.5 | Short-lived agents, lower assurance |

**Consensus status:**

```
IF witness_count >= consensus_threshold AND consensus_score >= 0.5:
  status = "confirmed"
ELSE IF witness_count > 0:
  status = "pending"
ELSE:
  status = "pending"
```

### 7.4 Witness Validation

Each witness receipt referenced in `witness_receipts` MUST:

1. Be a valid, non-expired, non-revoked MAIP receipt.
2. Have been issued by a different `issuer_id` than any other witness (independence requirement).
3. Reference the same `subject_hash` as the truth claim.
4. Have been created before the truth claim receipt's `created_at`.

**Verification:**

```
FUNCTION verify_truth_claim(claim_receipt):
  IF claim_receipt.witness_receipts.length < claim_receipt.consensus_threshold:
    RETURN INSUFFICIENT_WITNESSES
  
  issuer_set = {}
  FOR EACH witness IN claim_receipt.witness_receipts:
    receipt = fetch_and_verify(witness.receipt_id)
    IF receipt IS NOT VALID:
      RETURN WITNESS_INVALID (witness.receipt_id)
    IF receipt.issuer_id IN issuer_set:
      RETURN DUPLICATE_WITNESS
    issuer_set.add(receipt.issuer_id)
    
    IF receipt.subject_hash != claim_receipt.subject_hash:
      RETURN WITNESS_SUBJECT_MISMATCH
  
  -- Recompute consensus score
  computed_score = compute_consensus(claim_receipt.witness_receipts)
  IF ABS(computed_score - claim_receipt.consensus_score) > 0.001:
    RETURN CONSENSUS_SCORE_MISMATCH
  
  RETURN VALID
```

---

## 8. Compliance Receipts

### 8.1 Overview

Compliance receipts provide cryptographic proof that a regulatory compliance check was performed, by whom, against which framework, and what the result was.

### 8.2 Payload Structure

```json
{
  "schema_id": "maip_compliance",
  "schema_version": "1.0.0",
  "created_at": "2026-04-06T09:00:00Z",
  "issuer_id": "<compliance agent or auditor ID>",

  "regulation": "GDPR | SOC2 | HIPAA | PCI-DSS | CCPA | AI-Act | ISO27001 | FATF | custom",
  "regulation_version": "2024",
  "compliance_type": "data_handling | access_control | retention | consent | model_governance | bias_audit",
  "subject_id": "<entity checked>",
  "subject_type": "agent | dataset | model | pipeline | organization",

  "result": "pass | fail | conditional_pass | not_applicable",
  "findings": [
    {
      "finding_id": "F001",
      "severity": "low | medium | high | critical",
      "description": "Data retention policy exceeds 30-day GDPR requirement for non-essential data",
      "remediation": "Reduce retention period for analytics data to 30 days",
      "status": "open | remediated | accepted_risk"
    }
  ],

  "evidence_hash": "<base64url SHA-256 of the compliance evidence bundle>",
  "evidence_description": "Automated scan of data retention policies across 47 data stores",

  "auditor_id": "maip:a1b2c3d4:01HXYZ_COMPLIANCE_AGENT",
  "auditor_name": "Automated Compliance Scanner v2.1",
  "auditor_certification": "SOC2 Type II certified",

  "valid_from": "2026-04-06T00:00:00Z",
  "valid_until": "2026-07-06T00:00:00Z",

  "previous_compliance_receipt_id": "<receipt_id of prior compliance check for same subject+regulation>",
  "remediation_deadline": "2026-05-06T00:00:00Z"
}
```

### 8.3 Regulation-Specific Fields

| Regulation | Additional Fields |
|-----------|-------------------|
| GDPR | `data_categories`, `legal_basis`, `dpia_required`, `cross_border_transfers` |
| SOC2 | `trust_criteria` (security, availability, processing integrity, confidentiality, privacy), `control_ids` |
| HIPAA | `phi_categories`, `safeguard_type` (administrative, physical, technical), `breach_risk_assessment` |
| AI-Act | `risk_category` (unacceptable, high, limited, minimal), `transparency_obligations`, `human_oversight_type` |
| PCI-DSS | `saq_type`, `scan_type` (ASV, internal), `requirement_ids` |

### 8.4 Compliance Chain

For ongoing compliance monitoring, each compliance receipt for the same `(subject_id, regulation)` pair references the prior compliance receipt via `previous_compliance_receipt_id`. This creates a compliance audit trail.

```
[compliance_check_Q1] --> [compliance_check_Q2] --> [compliance_check_Q3]
   result: pass             result: conditional       result: pass
                            findings: [F001]          findings: [] (F001 remediated)
```

---

## 9. Verification Algorithm

### 9.1 Overview

Receipt verification is an eight-step process. Each step may produce a terminal verdict or pass through to the next step. The algorithm is designed to be executable offline using only the receipt, the issuer's public key, and the transparency log checkpoint.

### 9.2 Verdict Codes

| Code | Meaning | Terminal? |
|------|---------|-----------|
| `VALID` | Receipt passed all verification checks | Yes |
| `EXPIRED` | Receipt has passed its `expires_at` time | Yes |
| `REVOKED` | The receipt, issuer, or delegation has been revoked | Yes |
| `INVALID_SIGNATURE` | Cryptographic signature verification failed | Yes |
| `SCHEMA_INVALID` | Payload does not conform to registered schema | Yes |
| `SCOPE_VIOLATION` | Action used scopes not granted by delegation chain | Yes |
| `CHAIN_BROKEN` | Receipt chain has a gap or missing link | Yes |
| `AUDIENCE_MISMATCH` | Receipt audience does not match verifier | Yes |
| `PURPOSE_MISMATCH` | Receipt purpose does not match verifier context | Soft (warning) |
| `DELEGATION_REVOKED_AT_ISSUE` | Delegation was revoked before receipt was created | Yes |
| `DELEGATION_CHAIN_STALE` | Delegation chain has changed since receipt creation | Soft (warning) |
| `KEY_COMPROMISED` | Signing key was marked compromised before or at issuance | Yes |
| `KEY_INACTIVE` | Signing key is not in active status | Yes |
| `KEY_EXPIRED` | Signing key was outside its validity window at issuance | Yes |
| `LOG_PROOF_INVALID` | Merkle inclusion proof does not verify | Yes |
| `DUPLICATE_NONCE` | Nonce has been seen before for this issuer | Yes |
| `INSUFFICIENT_WITNESSES` | Truth claim has fewer witnesses than threshold | Yes |
| `LINEAGE_INCOMPLETE` | Referenced lineage attestation is missing or revoked | Soft (warning) |

### 9.3 Verification Pseudocode

```
FUNCTION verify_receipt(receipt, verifier_context) -> Verdict:

  // ========================================================================
  // Step 1: Parse and validate schema
  // ========================================================================
  
  parsed = parse_json(receipt)
  IF parsed IS INVALID JSON:
    RETURN SCHEMA_INVALID("Receipt is not valid JSON")

  required_fields = [
    "receipt_id", "receipt_type", "schema_version", "issuer_id",
    "subject_id", "subject_type", "created_at", "nonce",
    "context", "payload", "attestation_id",
    "transparency_log_entry", "signature"
  ]
  
  FOR EACH field IN required_fields:
    IF field NOT IN parsed:
      RETURN SCHEMA_INVALID("Missing required field: " + field)

  schema = lookup_schema(parsed.receipt_type, parsed.schema_version)
  IF schema IS NULL:
    RETURN SCHEMA_INVALID("Unknown receipt type: " + parsed.receipt_type)
  
  IF NOT validate_payload_against_schema(parsed.payload, schema):
    RETURN SCHEMA_INVALID("Payload does not conform to schema")

  // ========================================================================
  // Step 2: Verify cryptographic signature
  // ========================================================================
  
  issuer_public_key = resolve_public_key(parsed.issuer_id, parsed.signature.kid)
  IF issuer_public_key IS NULL:
    RETURN KEY_INACTIVE("Could not resolve issuer public key")

  unsigned_receipt = remove_field(parsed, "signature")
  canonical_bytes = JCS_canonicalize(unsigned_receipt)
  signature_bytes = base64url_decode(parsed.signature.value)
  
  valid = crypto_verify(
    algorithm = parsed.signature.alg,
    public_key = issuer_public_key,
    message = canonical_bytes,
    signature = signature_bytes
  )
  
  IF NOT valid:
    RETURN INVALID_SIGNATURE("Cryptographic signature verification failed")

  // ========================================================================
  // Step 3: Check temporal validity
  // ========================================================================
  
  now = current_utc_time()
  
  IF parsed.expires_at IS NOT NULL:
    expires = parse_iso8601(parsed.expires_at)
    IF expires < now:
      RETURN EXPIRED("Receipt expired at " + parsed.expires_at)

  created = parse_iso8601(parsed.created_at)
  IF created > now + 5_MINUTES:  // Allow 5-minute clock skew
    RETURN SCHEMA_INVALID("Receipt created_at is in the future")

  // ========================================================================
  // Step 4: Verify delegation chain
  // ========================================================================
  
  IF parsed.context.delegation_depth > 0:
    chain = fetch_delegation_chain(parsed.issuer_id)
    
    IF chain IS NULL OR chain IS EMPTY:
      RETURN CHAIN_BROKEN("No delegation chain found for issuer")
    
    // Walk from acting agent up to root
    current_agent = parsed.issuer_id
    current_depth = parsed.context.delegation_depth
    
    WHILE current_depth > 0:
      delegation = find_delegation(child_agent_id = current_agent)
      
      IF delegation IS NULL:
        RETURN CHAIN_BROKEN("Missing delegation at depth " + current_depth)
      
      IF delegation.status == "revoked":
        IF delegation.revoked_at < parsed.created_at:
          RETURN DELEGATION_REVOKED_AT_ISSUE(
            "Delegation revoked before receipt creation"
          )
        ELSE:
          WARN DELEGATION_CHAIN_STALE(
            "Delegation revoked after receipt creation"
          )
      
      IF delegation.expires_at IS NOT NULL AND delegation.expires_at < parsed.created_at:
        RETURN EXPIRED("Delegation expired before receipt creation")
      
      // Verify scope subsetting
      FOR EACH scope IN parsed.context.scopes_used:
        IF scope NOT IN delegation.scopes:
          RETURN SCOPE_VIOLATION(
            "Scope '" + scope + "' not granted by delegation at depth " + current_depth
          )
      
      current_agent = delegation.parent_agent_id
      current_depth = current_depth - 1
    
    // Verify delegation chain hash matches
    recomputed_hash = compute_delegation_chain_hash(chain)
    IF recomputed_hash != parsed.context.delegation_chain_hash:
      WARN DELEGATION_CHAIN_STALE("Delegation chain hash mismatch")

  // ========================================================================
  // Step 5: Verify attestation exists and is not revoked
  // ========================================================================
  
  attestation = fetch_attestation(parsed.attestation_id)
  
  IF attestation IS NULL:
    RETURN REVOKED("Backing attestation not found")
  
  IF attestation.status == "REVOKED":
    RETURN REVOKED("Backing attestation has been revoked")
  
  IF attestation.status == "SUPERSEDED":
    // Not an error -- receipt remains valid, but newer version exists
    WARN("Attestation has been superseded by " + attestation.superseded_by)

  // ========================================================================
  // Step 6: Verify issuer key status
  // ========================================================================
  
  key_metadata = fetch_key_metadata(parsed.issuer_id, parsed.signature.kid)
  
  IF key_metadata IS NULL:
    RETURN KEY_INACTIVE("Signing key not found")
  
  IF key_metadata.status != "active" AND key_metadata.status != "ACTIVE":
    RETURN KEY_INACTIVE("Signing key status: " + key_metadata.status)
  
  IF key_metadata.compromised_at IS NOT NULL:
    IF key_metadata.compromised_at <= parsed.created_at:
      RETURN KEY_COMPROMISED(
        "Key compromised at " + key_metadata.compromised_at +
        " which is before or at receipt creation"
      )
  
  IF key_metadata.valid_from IS NOT NULL AND parsed.created_at < key_metadata.valid_from:
    RETURN KEY_EXPIRED("Key not yet valid at receipt creation time")
  
  IF key_metadata.valid_to IS NOT NULL AND parsed.created_at > key_metadata.valid_to:
    RETURN KEY_EXPIRED("Key expired before receipt creation time")

  // ========================================================================
  // Step 7: Verify transparency log inclusion proof
  // ========================================================================
  
  log_entry = parsed.transparency_log_entry
  
  proof = fetch_inclusion_proof(log_entry.log_id, parsed.attestation_id)
  
  IF proof IS NULL:
    RETURN LOG_PROOF_INVALID("No inclusion proof available")
  
  leaf_hash = calculate_leaf_hash(
    log_id = log_entry.log_id,
    attestation_id = parsed.attestation_id,
    event_type = "RECEIPT_ISSUE",
    payload_hash = attestation.payload_hash,
    issued_at_unix = parse_unix(parsed.created_at)
  )
  
  IF leaf_hash != base64url_decode(log_entry.leaf_hash):
    RETURN LOG_PROOF_INVALID("Leaf hash mismatch")
  
  checkpoint = fetch_checkpoint(log_entry.log_id)
  
  proof_valid = verify_inclusion_proof(
    root_hash = checkpoint.root_hash,
    leaf_hash = leaf_hash,
    index = log_entry.leaf_index,
    tree_size = checkpoint.tree_size,
    proof = proof.audit_path
  )
  
  IF NOT proof_valid:
    RETURN LOG_PROOF_INVALID("Merkle inclusion proof verification failed")

  // ========================================================================
  // Step 8: Check audience and purpose
  // ========================================================================
  
  IF parsed.audience IS NOT NULL:
    IF verifier_context.domain != parsed.audience:
      RETURN AUDIENCE_MISMATCH(
        "Receipt audience '" + parsed.audience +
        "' does not match verifier '" + verifier_context.domain + "'"
      )
  
  IF parsed.purpose IS NOT NULL AND verifier_context.expected_purpose IS NOT NULL:
    IF parsed.purpose != verifier_context.expected_purpose:
      WARN PURPOSE_MISMATCH(
        "Receipt purpose '" + parsed.purpose +
        "' does not match expected '" + verifier_context.expected_purpose + "'"
      )

  // ========================================================================
  // All checks passed
  // ========================================================================
  
  RETURN VALID
```

### 9.4 Offline Verification

For offline verification (using a bundle rather than live API calls), Steps 5-7 use data embedded in the bundle instead of fetching from servers:

| Step | Online Source | Offline Source (Bundle) |
|------|-------------|----------------------|
| Step 2 (public key) | Trust registry API | `bundle.issuer_key.public_key_b64url` |
| Step 5 (attestation) | Attestation service API | `bundle.receipt` (presence implies existence) |
| Step 6 (key metadata) | Trust registry API | `bundle.issuer_key` |
| Step 7 (inclusion proof) | Transparency log API | `bundle.transparency_log.inclusion_proof` + `bundle.transparency_log.checkpoint` |

The offline verifier MUST additionally verify the checkpoint signature:

```
checkpoint_valid = crypto_verify(
  algorithm = bundle.transparency_log.checkpoint.signature_alg,
  public_key = base64url_decode(bundle.transparency_log.checkpoint.signing_pubkey_b64url),
  message = construct_checkpoint_payload(
    tree_size = bundle.transparency_log.checkpoint.tree_size,
    root_hash = bundle.transparency_log.checkpoint.root_hash_b64url,
    issued_at = bundle.transparency_log.checkpoint.issued_at
  ),
  signature = base64url_decode(bundle.transparency_log.checkpoint.signature_b64url)
)

IF NOT checkpoint_valid:
  RETURN LOG_PROOF_INVALID("Checkpoint signature verification failed")
```

### 9.5 Exit Codes

For the `maip verify` CLI tool, verification verdicts map to process exit codes:

| Exit Code | Verdict |
|-----------|---------|
| 0 | `VALID` |
| 1 | `SCHEMA_INVALID` |
| 2 | `INVALID_SIGNATURE` |
| 3 | `KEY_COMPROMISED` or `KEY_INACTIVE` or `KEY_EXPIRED` |
| 4 | `REVOKED` |
| 5 | `EXPIRED` |
| 6 | `SCOPE_VIOLATION` |
| 7 | `CHAIN_BROKEN` or `DELEGATION_REVOKED_AT_ISSUE` |
| 8 | `LOG_PROOF_INVALID` |
| 9 | `AUDIENCE_MISMATCH` |
| 10 | `DUPLICATE_NONCE` or `INSUFFICIENT_WITNESSES` |

---

## 10. Serialization and Canonicalization

### 10.1 JSON Canonicalization

All MAIP receipts MUST use JSON Canonicalization Scheme (JCS, RFC 8785) when computing hashes or signatures. JCS guarantees deterministic serialization:

- Object keys sorted lexicographically by Unicode code point.
- No whitespace between tokens.
- Numbers represented without trailing zeros.
- Strings with minimal escape sequences.

**Implementation note**: The existing Truthlocks Attestation Service uses `json.Marshal` from Go's standard library, which produces lexicographically sorted keys. For cross-language compatibility, implementations MUST use a JCS-compliant library rather than relying on language-specific JSON serialization order.

### 10.2 Base64 Encoding

All binary data in MAIP receipts (hashes, signatures, public keys) MUST use base64url encoding without padding (RFC 4648 Section 5).

```
base64url_no_pad(bytes) = base64url(bytes).rstrip('=')
```

### 10.3 Timestamp Format

All timestamps MUST be ISO 8601 format with UTC timezone, seconds precision:

```
2026-04-06T12:00:00Z
```

Millisecond precision is allowed but not required:

```
2026-04-06T12:00:00.123Z
```

### 10.4 Receipt ID Format

Receipt IDs use the format `rcpt_<ULID>`:

```
rcpt_01HXYZ9K7PQRS4TUV0WX1YZ2AB
```

The ULID provides time-ordered, globally unique identification with millisecond precision and is lexicographically sortable.

---

## 11. Conformance

### 11.1 Receipt Producer Requirements

A conforming receipt producer MUST:

1. Generate a unique `nonce` for every receipt using a CSPRNG.
2. Compute signatures over JCS-canonicalized receipt JSON.
3. Set `previous_receipt_id` to the issuer's prior receipt (or `null` for genesis).
4. Validate that `context.scopes_used` is a subset of the issuer's delegated scopes.
5. Include valid `transparency_log_entry` coordinates after anchoring.
6. Set `expires_at` according to the defaults in Section 4.4 unless explicitly overridden.
7. Validate the payload against the registered schema before signing.

### 11.2 Receipt Consumer Requirements

A conforming receipt consumer (verifier) MUST:

1. Execute all eight steps of the verification algorithm (Section 9.3).
2. Reject receipts with terminal verdict codes.
3. Surface soft warnings (`DELEGATION_CHAIN_STALE`, `PURPOSE_MISMATCH`, `LINEAGE_INCOMPLETE`) to the calling application.
4. Support both online and offline verification modes.
5. Enforce audience matching when the verifier has a configured domain identity.

### 11.3 Interoperability

MAIP receipts are designed for cross-platform interoperability:

- The receipt format is pure JSON, parseable by any language.
- Signatures use standard algorithms (Ed25519, ECDSA P-256, RSA PKCS#1 v1.5).
- Merkle proofs follow RFC 6962 semantics.
- The offline verification bundle is self-contained and requires no external dependencies beyond a cryptographic library.

Reference implementations will be provided in Go, JavaScript, and Python at `github.com/truthlocksinc/maip`.

---

*End of MAIP Receipt Format Specification v1.0.0-draft*

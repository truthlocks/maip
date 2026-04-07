# MAIP Specification: Delegation Chain Model

**Protocol**: Machine Agent Identity Protocol (MAIP)
**Version**: 1.0.0-draft
**Status**: PROPOSED
**Date**: 2026-04-06
**Authors**: Truthlocks Architecture Team
**Depends On**: MAIP Core Identity, Truthlocks Attestation Service, Transparency Log, Trust Registry

---

## Table of Contents

1. [Overview](#1-overview)
2. [Delegation Model](#2-delegation-model)
3. [Scope Narrowing Rule](#3-scope-narrowing-rule)
4. [Chain Verification Algorithm](#4-chain-verification-algorithm)
5. [Offline Verification Bundle (MaipBundle)](#5-offline-verification-bundle-maipbundle)
6. [Revocation Propagation](#6-revocation-propagation)
7. [Cross-Tenant Delegation](#7-cross-tenant-delegation)
8. [Emergency Kill Switch](#8-emergency-kill-switch)
9. [Constants and Configuration](#9-constants-and-configuration)
10. [Security Considerations](#10-security-considerations)

---

## 1. Overview

The MAIP delegation chain is the mechanism by which trust flows from a human or
organizational root of trust down through a hierarchy of machine agents. Each
delegation is a cryptographically signed attestation that grants a child agent
a narrowed subset of the parent's capabilities. The chain provides end-to-end
verifiability: any party can trace an agent's authority back to a trusted root
without contacting a central server.

### 1.1 Design Goals

- **Zero-trust by default**: Every agent action must be traceable to a human/org root.
- **Offline verifiable**: A self-contained bundle proves chain validity without network calls.
- **Least privilege**: Scopes narrow monotonically at every delegation level.
- **Revocable**: Any link in the chain can be revoked, cascading to all descendants.
- **Auditable**: Every delegation and revocation is anchored in the transparency log.

### 1.2 Agent ID Format

```
maip:<first8_of_tenant_uuid>:<ulid>

Examples:
  maip:a1b2c3d4:01HXYZ99ABCDEF1234567890   (agent within tenant a1b2c3d4)
  maip:f9e8d7c6:01HXYZ99ZYXWVU0987654321   (agent within tenant f9e8d7c6)
```

- `first8_of_tenant_uuid`: The first 8 hex characters of the tenant's UUID, providing namespace isolation and quick visual identification.
- `ulid`: A Universally Unique Lexicographically Sortable Identifier, providing time-ordered uniqueness.

---

## 2. Delegation Model

### 2.1 Delegation Hierarchy

```
Depth 0   [ Human / Organization ]          ← Root of Trust (in Trust Registry)
               │
               │  DelegationAttestation (signed by root)
               ▼
Depth 1   [ Agent A ]                       ← First-level agent
               │
               │  DelegationAttestation (signed by Agent A)
               ▼
Depth 2   [ Agent B ]                       ← Sub-agent
               │
               │  DelegationAttestation (signed by Agent B)
               ▼
Depth 3   [ Agent C ]                       ← Sub-sub-agent
               │
              ...
               │
               ▼
Depth 8   [ Agent H ]                       ← Maximum depth (MAIP_MAX_DEPTH)
```

### 2.2 DelegationAttestation Schema

Each delegation is recorded as a signed attestation with the following structure:

```json
{
  "type": "DelegationAttestation",
  "version": "1.0.0",
  "delegation_id": "att_01HXYZ...",
  "parent_agent_id": "maip:a1b2c3d4:01HXYZ...",
  "child_agent_id": "maip:a1b2c3d4:01HXYZ...",
  "child_public_key": "<base64-encoded Ed25519 public key>",
  "depth": 2,
  "scopes": [
    "attestation:mint",
    "dataset:read",
    "model:deploy"
  ],
  "constraints": {
    "max_sub_delegations": 3,
    "allowed_environments": ["production", "staging"],
    "rate_limit_per_hour": 1000,
    "ip_allowlist": ["10.0.0.0/8"]
  },
  "not_before": "2026-04-06T00:00:00Z",
  "expires_at": "2026-07-06T00:00:00Z",
  "issued_at": "2026-04-06T12:00:00Z",
  "transparency_log_index": 48291,
  "signature": "<base64-encoded signature by parent's private key>",
  "signature_algorithm": "Ed25519"
}
```

### 2.3 Rules

| Rule | Description |
|------|-------------|
| **R-DEL-001** | Every delegation MUST be signed by the parent's private key. |
| **R-DEL-002** | The `depth` field MUST equal `parent.depth + 1`. |
| **R-DEL-003** | `depth` MUST NOT exceed `MAIP_MAX_DEPTH` (8). |
| **R-DEL-004** | Every delegation MUST be anchored in the transparency log before the child agent can act. |
| **R-DEL-005** | The `child_public_key` MUST be unique across all active delegations within a tenant. |
| **R-DEL-006** | `expires_at` MUST NOT exceed `parent.expires_at`. A child cannot outlive its parent delegation. |
| **R-DEL-007** | `not_before` MUST be >= `parent.not_before`. |
| **R-DEL-008** | The `constraints` object is optional but, when present, MUST be a subset of or equal to the parent's constraints. |

### 2.4 Delegation Lifecycle

```
  ┌─────────┐     anchor in      ┌──────────┐     child acts     ┌──────────┐
  │ CREATED │ ──── log ────────► │  ACTIVE  │ ────────────────► │  ACTIVE  │
  └─────────┘                    └──────────┘                    └──────────┘
                                      │                               │
                          expires or  │                   revoked by  │
                          revoked     │                   parent      │
                                      ▼                               ▼
                                 ┌──────────┐                    ┌──────────┐
                                 │ EXPIRED  │                    │ REVOKED  │
                                 └──────────┘                    └──────────┘
```

---

## 3. Scope Narrowing Rule

### 3.1 Formal Definition

For any delegation from parent P to child C:

```
child.scopes  ⊆  parent.scopes
```

This invariant holds at every level in the chain. A child can never possess a
scope that its parent does not possess. Scopes narrow monotonically from root
to leaf.

### 3.2 Scope Format

Scopes use a `resource:action` format:

```
<resource>:<action>

Examples:
  attestation:mint        Grant: create new attestations
  attestation:read        Grant: read attestation data
  attestation:revoke      Grant: revoke attestations
  dataset:read            Grant: read dataset records
  dataset:write           Grant: write/update datasets
  model:deploy            Grant: deploy models to inference
  model:train             Grant: initiate model training
  pipeline:execute        Grant: trigger pipeline runs
  receipt:create          Grant: create action receipts
  receipt:read            Grant: read receipts
  admin:manage_agents     Grant: create/revoke child agents
  identity:verify         Grant: verify identities
  *:*                     Grant: all scopes (root only)
```

### 3.3 Predefined Scope Categories

| Category | Actions | Description |
|----------|---------|-------------|
| `identity` | `create`, `read`, `verify`, `revoke` | Agent identity management |
| `attestation` | `mint`, `read`, `revoke`, `verify` | Attestation lifecycle |
| `dataset` | `read`, `write`, `delete`, `attest` | Dataset operations |
| `model` | `train`, `deploy`, `evaluate`, `attest` | ML model lifecycle |
| `pipeline` | `execute`, `read`, `configure` | Pipeline orchestration |
| `receipt` | `create`, `read`, `verify` | Receipt management |
| `admin` | `manage_agents`, `manage_scopes`, `audit`, `kill_switch` | Administrative operations |

### 3.4 Wildcard Semantics

- `*:*` expands to ALL scopes in ALL categories. Only a root issuer (depth=0) can hold `*:*`.
- `attestation:*` expands to all actions within the `attestation` category.
- `*:read` is NOT valid. Wildcards on the resource side are only permitted as `*:*`.

### 3.5 Scope Narrowing Examples

```
Root (depth=0): scopes = ["*:*"]
  │
  ├── Agent A (depth=1): scopes = ["attestation:mint", "attestation:read", "dataset:read"]
  │     │
  │     └── Agent B (depth=2): scopes = ["attestation:read", "dataset:read"]
  │           │
  │           └── Agent C (depth=3): scopes = ["dataset:read"]
  │                                                    ✓ Valid: monotonically narrowing
  │
  └── Agent D (depth=1): scopes = ["model:deploy", "model:train"]
        │
        └── Agent E (depth=2): scopes = ["model:deploy", "dataset:write"]
                                                       ✗ INVALID: "dataset:write" not in parent
```

### 3.6 Scope Validation Algorithm

```
function validateScopeNarrowing(parent_scopes, child_scopes):
    if parent_scopes contains "*:*":
        return VALID                          // Root can delegate anything

    for each scope in child_scopes:
        if scope not in parent_scopes:
            // Check category wildcard expansion
            category = scope.split(":")[0]
            if (category + ":*") not in parent_scopes:
                return SCOPE_VIOLATION(scope)

    return VALID
```

---

## 4. Chain Verification Algorithm

### 4.1 Inputs and Outputs

```
INPUTS:
  action_receipt   : The receipt to verify (contains agent_id, action, scopes_required)
  delegation_chain : Array of DelegationAttestation objects, ordered root → leaf

OUTPUT (enum):
  VALID              : Chain is complete, all signatures valid, scopes sufficient
  CHAIN_BROKEN       : A gap exists between consecutive delegations
  SCOPE_VIOLATION    : A child holds scopes not granted by parent, or leaf lacks required scopes
  REVOKED            : One or more delegations in the chain have been revoked
  EXPIRED            : One or more delegations have expired
  DEPTH_EXCEEDED     : Chain length exceeds MAIP_MAX_DEPTH (8)
  UNTRUSTED_ROOT     : The root issuer is not in the trust registry
```

### 4.2 Algorithm (Formal Steps)

```
function verifyDelegationChain(action_receipt, delegation_chain[]):

    // ─── Step 1: Verify chain contiguity ───
    for i = 0 to len(delegation_chain) - 2:
        current  = delegation_chain[i]
        next     = delegation_chain[i + 1]
        if current.child_agent_id != next.parent_agent_id:
            return CHAIN_BROKEN

    // Verify leaf agent matches the receipt's agent
    leaf = delegation_chain[len(delegation_chain) - 1]
    if leaf.child_agent_id != action_receipt.agent_id:
        return CHAIN_BROKEN

    // ─── Step 2: Verify root is trusted ───
    root = delegation_chain[0]
    if not trustRegistry.isTrustedIssuer(root.parent_agent_id):
        return UNTRUSTED_ROOT

    // ─── Step 3: Verify each delegation ───
    for i = 0 to len(delegation_chain) - 1:
        delegation = delegation_chain[i]

        // 3a: Verify cryptographic signature
        parent_pubkey = resolvePublicKey(delegation.parent_agent_id)
        if not verifySignature(delegation, parent_pubkey):
            return CHAIN_BROKEN

        // 3b: Check revocation status
        if revocationIndex.isRevoked(delegation.delegation_id):
            return REVOKED

        // 3c: Check temporal validity
        now = currentTimestamp()
        if now < delegation.not_before OR now > delegation.expires_at:
            return EXPIRED

        // 3d: Verify scope narrowing (except for root, which is depth=0)
        if i > 0:
            parent_delegation = delegation_chain[i - 1]
            if not isSubset(delegation.scopes, parent_delegation.scopes):
                return SCOPE_VIOLATION

        // 3e: Verify depth is correct
        expected_depth = i + 1
        if delegation.depth != expected_depth:
            return CHAIN_BROKEN

    // ─── Step 4: Verify leaf scopes cover required action scopes ───
    required_scopes = action_receipt.scopes_required
    leaf_scopes = delegation_chain[len(delegation_chain) - 1].scopes
    if not isSubset(required_scopes, leaf_scopes):
        return SCOPE_VIOLATION

    // ─── Step 5: Verify depth limit ───
    if len(delegation_chain) > MAIP_MAX_DEPTH:
        return DEPTH_EXCEEDED

    return VALID
```

### 4.3 Verification Complexity

| Step | Operation | Complexity |
|------|-----------|------------|
| Step 1 | Chain contiguity | O(n) where n = chain length |
| Step 2 | Trust registry lookup | O(1) amortized (cached) |
| Step 3a | Signature verification | O(n) Ed25519 verifications |
| Step 3b | Revocation check | O(n) lookups (bloom filter optimized) |
| Step 3c | Temporal check | O(n) timestamp comparisons |
| Step 3d | Scope subset check | O(n * s) where s = max scopes per level |
| Step 4 | Leaf scope check | O(s) |
| Step 5 | Depth check | O(1) |
| **Total** | | **O(n * s)** where n <= 8, s typically < 20 |

Worst-case wall-clock time with MAIP_MAX_DEPTH=8: under 5ms for online verification,
under 2ms for offline (all data local).

---

## 5. Offline Verification Bundle (MaipBundle)

### 5.1 Purpose

A MaipBundle is a self-contained package that allows any party to verify a
receipt's full delegation chain without making any network calls. This is
critical for air-gapped environments, regulatory audits, and cross-organization
trust verification.

### 5.2 Bundle Structure

```json
{
  "maip_bundle_version": "1.0.0",
  "created_at": "2026-04-06T14:30:00Z",
  "receipt": {
    "receipt_id": "rcpt_01HXYZ...",
    "type": "action_receipt",
    "agent_id": "maip:a1b2c3d4:01HXYZ...",
    "action": "model:deploy",
    "input_hash": "sha256:abcd1234...",
    "output_hash": "sha256:ef567890...",
    "scopes_required": ["model:deploy"],
    "timestamp": "2026-04-06T14:25:00Z",
    "signature": "<base64>"
  },
  "delegation_chain": [
    {
      "delegation_id": "att_01HXYZ...",
      "parent_agent_id": "maip:a1b2c3d4:ROOT",
      "child_agent_id": "maip:a1b2c3d4:01HXYZ_A...",
      "depth": 1,
      "scopes": ["model:deploy", "model:train", "attestation:mint"],
      "issued_at": "2026-01-01T00:00:00Z",
      "expires_at": "2027-01-01T00:00:00Z",
      "signature": "<base64>",
      "transparency_log_proof": {
        "log_index": 48291,
        "inclusion_proof": ["<hash1>", "<hash2>", "<hash3>"],
        "tree_root": "sha256:...",
        "tree_size": 102847
      }
    },
    {
      "delegation_id": "att_01HXYZ...",
      "parent_agent_id": "maip:a1b2c3d4:01HXYZ_A...",
      "child_agent_id": "maip:a1b2c3d4:01HXYZ_B...",
      "depth": 2,
      "scopes": ["model:deploy"],
      "issued_at": "2026-03-15T00:00:00Z",
      "expires_at": "2026-09-15T00:00:00Z",
      "signature": "<base64>",
      "transparency_log_proof": {
        "log_index": 51003,
        "inclusion_proof": ["<hash1>", "<hash2>"],
        "tree_root": "sha256:...",
        "tree_size": 108221
      }
    }
  ],
  "public_keys": [
    {
      "agent_id": "maip:a1b2c3d4:ROOT",
      "public_key": "<base64-encoded Ed25519 public key>",
      "key_attestation_id": "att_01HXYZ_KEY...",
      "key_attestation_signature": "<base64>",
      "key_transparency_proof": {
        "log_index": 10001,
        "inclusion_proof": ["<hash1>"],
        "tree_root": "sha256:...",
        "tree_size": 102847
      }
    },
    {
      "agent_id": "maip:a1b2c3d4:01HXYZ_A...",
      "public_key": "<base64-encoded Ed25519 public key>",
      "key_attestation_id": "att_01HXYZ_KEY2...",
      "key_attestation_signature": "<base64>",
      "key_transparency_proof": {
        "log_index": 48290,
        "inclusion_proof": ["<hash1>", "<hash2>"],
        "tree_root": "sha256:...",
        "tree_size": 102847
      }
    }
  ],
  "trust_registry_snapshot": {
    "snapshot_at": "2026-04-06T14:00:00Z",
    "trusted_issuers": [
      {
        "issuer_id": "maip:a1b2c3d4:ROOT",
        "trust_level": "high",
        "valid_from": "2025-01-01T00:00:00Z",
        "valid_until": "2027-01-01T00:00:00Z"
      }
    ],
    "snapshot_signature": "<base64, signed by trust registry operator>",
    "snapshot_transparency_proof": {
      "log_index": 52000,
      "inclusion_proof": ["<hash1>"],
      "tree_root": "sha256:...",
      "tree_size": 108500
    }
  }
}
```

### 5.3 Bundle Size

| Component | Typical Size |
|-----------|-------------|
| Receipt | 200-500 bytes |
| Each delegation (including proof) | 500-800 bytes |
| Each public key (including attestation) | 300-500 bytes |
| Trust registry snapshot | 500-1000 bytes |
| **Total (depth=2 chain)** | **~2-4 KB** |
| **Total (depth=8 chain, max)** | **~8-10 KB** |
| **Gzipped** | **~40-60% of raw** |

### 5.4 CLI Verification

```bash
# Verify a bundle (offline, no network calls)
maip verify bundle.json

# Exit codes:
#   0  = VALID
#   1  = CHAIN_BROKEN
#   2  = SCOPE_VIOLATION
#   3  = REVOKED
#   4  = EXPIRED
#   5  = DEPTH_EXCEEDED
#   6  = UNTRUSTED_ROOT
#   7  = INVALID_SIGNATURE
#   8  = MALFORMED_BUNDLE
#   9  = TRANSPARENCY_PROOF_INVALID
#  10  = KEY_ATTESTATION_INVALID

# Verbose output
maip verify --verbose bundle.json
# Output:
#   [PASS] Bundle format valid (v1.0.0)
#   [PASS] Chain contiguity verified (2 delegations)
#   [PASS] Root issuer maip:a1b2c3d4:ROOT trusted (trust_level=high)
#   [PASS] Delegation 1/2: signature valid, not revoked, not expired, scopes narrow
#   [PASS] Delegation 2/2: signature valid, not revoked, not expired, scopes narrow
#   [PASS] Leaf scopes cover required scopes: ["model:deploy"]
#   [PASS] Chain depth 2 <= max 8
#   [PASS] All transparency log proofs valid
#   [PASS] All key attestations valid
#   RESULT: VALID

# Generate a bundle from a receipt ID (online, fetches chain from services)
maip bundle create --receipt-id rcpt_01HXYZ... --output bundle.json

# Verify and pretty-print chain visualization
maip verify --visualize bundle.json
# Output:
#   ROOT maip:a1b2c3d4:ROOT [*:*]
#     └── maip:a1b2c3d4:01HXYZ_A [model:deploy, model:train, attestation:mint]
#           └── maip:a1b2c3d4:01HXYZ_B [model:deploy]  ← action agent
#   Receipt: model:deploy ✓
```

### 5.5 Bundle Freshness

Bundles are snapshots in time. They prove validity at `created_at`. For
ongoing trust, consumers should:

- Accept bundles created within a configurable freshness window (default: 24 hours).
- Re-fetch bundles for long-lived verifications.
- Check the trust registry snapshot timestamp against their own policy.

---

## 6. Revocation Propagation

### 6.1 Revocation Semantics

When a delegation is revoked, all descendant delegations are automatically
invalidated. This is the **cascading revocation** model.

```
Root
  └── Agent A [REVOKED at T=100]
        ├── Agent B [automatically invalid after T=100]
        │     └── Agent C [automatically invalid after T=100]
        └── Agent D [automatically invalid after T=100]
```

### 6.2 RevocationAttestation Schema

```json
{
  "type": "RevocationAttestation",
  "version": "1.0.0",
  "revocation_id": "rev_01HXYZ...",
  "target_delegation_id": "att_01HXYZ...",
  "target_agent_id": "maip:a1b2c3d4:01HXYZ...",
  "revoked_by": "maip:a1b2c3d4:01HXYZ_PARENT...",
  "reason": "policy_violation",
  "effective_from": "2026-04-06T15:00:00Z",
  "issued_at": "2026-04-06T15:00:00Z",
  "scope": "agent_and_descendants",
  "transparency_log_index": 52100,
  "signature": "<base64, signed by revoker's private key>"
}
```

### 6.3 Temporal Rules

| Scenario | Rule |
|----------|------|
| Normal revocation | `effective_from` = `issued_at`. Receipts created BEFORE this timestamp remain valid. Receipts created AFTER are invalid. |
| Key compromise (backdated) | `effective_from` < `issued_at`. The `compromised_at` field sets `effective_from` to the suspected compromise time. All receipts created AFTER `effective_from` are suspect and SHOULD be re-verified or flagged. |
| Pre-revocation receipts | Remain valid unless the revocation is due to key compromise with a `compromised_at` timestamp that precedes the receipt. |

### 6.4 Revocation Check Algorithm

```
function isRevoked(delegation_id, receipt_timestamp):

    revocation = revocationIndex.lookup(delegation_id)

    if revocation is null:
        return NOT_REVOKED

    if receipt_timestamp >= revocation.effective_from:
        return REVOKED

    // Receipt was created before revocation took effect
    if revocation.reason == "key_compromise":
        if receipt_timestamp >= revocation.compromised_at:
            return SUSPECT     // Requires manual review
        else:
            return NOT_REVOKED
    else:
        return NOT_REVOKED
```

### 6.5 Cascading Revocation Implementation

Revocation cascades are implemented lazily, not eagerly:

1. When a delegation is revoked, only the `RevocationAttestation` for that specific delegation is written.
2. During chain verification (Section 4), if ANY delegation in the chain is revoked, the entire chain fails with `REVOKED`.
3. There is no need to eagerly write revocation records for every descendant.
4. However, the revocation index MAY maintain a precomputed set of "revoked subtrees" for O(1) lookup performance.

### 6.6 Revocation Distribution

- **Push**: Revocations are published to a revocation event stream (Kafka topic / SNS topic). Verifiers that subscribe receive near-real-time updates.
- **Pull**: Verifiers poll the revocation index periodically (recommended interval: 60 seconds for online verification).
- **CRL (Certificate Revocation List)**: A periodic snapshot of all active revocations, signed by the trust registry. Updated every 15 minutes.
- **OCSP-like endpoint**: `GET /maip/v1/revocation/status/{delegation_id}` returns real-time status.

---

## 7. Cross-Tenant Delegation

### 7.1 Overview

Cross-tenant delegation allows an agent in Tenant A to delegate authority to an
agent in Tenant B. This requires explicit bilateral agreement.

```
Tenant A (maip:a1b2c3d4:...)          Tenant B (maip:f9e8d7c6:...)
┌─────────────────────────┐           ┌─────────────────────────┐
│  Root A                 │           │  Root B                 │
│    └── Agent A1         │           │    └── Agent B1         │
│          └── Agent A2 ──┼───────────┼──► Agent B2 (delegated) │
│                         │           │                         │
│  Trust Registry Entry:  │           │  Trust Registry Entry:  │
│  "trusts tenant B for   │           │  "trusts tenant A for   │
│   dataset:read"         │           │   dataset:read"         │
└─────────────────────────┘           └─────────────────────────┘
```

### 7.2 Requirements

| Requirement | Description |
|-------------|-------------|
| **CT-001** | Both tenants MUST have a `CrossTenantTrustAgreement` in the trust registry before any cross-tenant delegation can be created. |
| **CT-002** | The agreement specifies which scope categories are permitted across the boundary. |
| **CT-003** | Cross-tenant delegations carry a configurable trust score penalty (default: -20% of base trust score). |
| **CT-004** | Both tenants' audit logs record the delegation event. |
| **CT-005** | Either tenant can unilaterally revoke their side of the delegation. |
| **CT-006** | Cross-tenant delegations MUST NOT be further delegated across a third tenant boundary without explicit tri-lateral agreement. |

### 7.3 CrossTenantTrustAgreement Schema

```json
{
  "type": "CrossTenantTrustAgreement",
  "version": "1.0.0",
  "agreement_id": "cta_01HXYZ...",
  "tenant_a": "a1b2c3d4",
  "tenant_b": "f9e8d7c6",
  "permitted_scopes": ["dataset:read", "attestation:verify"],
  "trust_score_penalty": 0.20,
  "max_delegation_depth_across_boundary": 2,
  "established_at": "2026-04-01T00:00:00Z",
  "expires_at": "2027-04-01T00:00:00Z",
  "signed_by_a": "<base64>",
  "signed_by_b": "<base64>",
  "transparency_log_index": 50000
}
```

### 7.4 Cross-Tenant Chain Verification

The standard chain verification algorithm (Section 4) applies with these
additional checks at every tenant boundary crossing:

1. Verify a `CrossTenantTrustAgreement` exists and is active for the two tenants.
2. Verify the delegated scopes are within the agreement's `permitted_scopes`.
3. Verify the cross-boundary depth does not exceed `max_delegation_depth_across_boundary`.
4. Apply the `trust_score_penalty` to the final trust score.

---

## 8. Emergency Kill Switch

### 8.1 Purpose

The kill switch provides immediate, forceful revocation of an agent and
optionally all its descendants. It is designed for incident response scenarios
where speed is critical.

### 8.2 Kill Switch Triggers

| Trigger | Description |
|---------|-------------|
| `key_compromise` | Agent's private key is suspected or confirmed compromised. |
| `policy_violation` | Agent violated its granted scope or behavioral policy. |
| `anomaly_detected` | Automated monitoring detected anomalous agent behavior. |
| `manual_override` | Human operator manually triggered the kill switch. |

### 8.3 KillSwitchReceipt Schema

```json
{
  "type": "kill_switch_receipt",
  "version": "1.0.0",
  "kill_switch_id": "ks_01HXYZ...",
  "target_agent_id": "maip:a1b2c3d4:01HXYZ...",
  "triggered_by": "maip:a1b2c3d4:ADMIN_01HXYZ...",
  "reason": "key_compromise",
  "scope": "agent_and_descendants",
  "effective_from": "2026-04-05T10:00:00Z",
  "issued_at": "2026-04-06T16:00:00Z",
  "compromised_at": "2026-04-05T10:00:00Z",
  "affected_agent_count": 4,
  "affected_agent_ids": [
    "maip:a1b2c3d4:01HXYZ_TARGET...",
    "maip:a1b2c3d4:01HXYZ_CHILD1...",
    "maip:a1b2c3d4:01HXYZ_CHILD2...",
    "maip:a1b2c3d4:01HXYZ_GRANDCHILD1..."
  ],
  "notification_targets": [
    {"type": "webhook", "url": "https://soc.example.com/maip/alerts"},
    {"type": "siem", "integration": "splunk", "index": "maip_security"},
    {"type": "email", "address": "security@example.com"}
  ],
  "transparency_log_index": 52200,
  "signature": "<base64, signed by triggering authority>"
}
```

### 8.4 Kill Switch Scope Options

| Scope | Behavior |
|-------|----------|
| `agent_only` | Revoke only the target agent's delegation. Children are unaffected (they become orphaned and fail chain verification naturally). |
| `agent_and_descendants` | Revoke the target agent and ALL descendants recursively. This is the default and most common mode. |
| `full_chain` | Revoke every delegation in the chain from the target up to (but not including) the root. Used when the entire delegation path is suspect. |

### 8.5 Kill Switch Execution Flow

```
Trigger Event (e.g., anomaly detected)
    │
    ▼
┌──────────────────────────────────────────────┐
│ 1. Create KillSwitchReceipt                  │
│    - Enumerate affected agents (BFS from     │
│      target through delegation tree)         │
│    - Set effective_from (backdate if          │
│      key_compromise)                         │
│    - Sign with triggering authority's key     │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│ 2. Anchor in Transparency Log                │
│    - Write KillSwitchReceipt                 │
│    - Write RevocationAttestations for each   │
│      affected delegation (batch write)       │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│ 3. Update Revocation Index                   │
│    - Mark all affected delegations as        │
│      revoked with effective_from timestamp   │
│    - Invalidate any cached verification      │
│      results for affected agents             │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│ 4. Dispatch Notifications (parallel)         │
│    - Webhook to registered endpoints         │
│    - SIEM alert (Splunk, Datadog, etc.)      │
│    - Email to security contacts              │
│    - Push to revocation event stream         │
│    - Audit log entry for compliance          │
└──────────────────────────────────────────────┘
```

### 8.6 Kill Switch SLA

| Metric | Target |
|--------|--------|
| Time from trigger to revocation index update | < 500ms |
| Time from trigger to transparency log anchor | < 2 seconds |
| Time from trigger to webhook dispatch | < 5 seconds |
| Time from trigger to SIEM alert | < 10 seconds |

---

## 9. Constants and Configuration

| Constant | Value | Description |
|----------|-------|-------------|
| `MAIP_MAX_DEPTH` | 8 | Maximum delegation chain depth |
| `MAIP_DEFAULT_DELEGATION_TTL` | 90 days | Default delegation expiry |
| `MAIP_MAX_DELEGATION_TTL` | 365 days | Maximum delegation expiry |
| `MAIP_BUNDLE_FRESHNESS_WINDOW` | 24 hours | Default bundle freshness for consumers |
| `MAIP_REVOCATION_POLL_INTERVAL` | 60 seconds | Recommended revocation check interval |
| `MAIP_CRL_UPDATE_INTERVAL` | 15 minutes | Certificate revocation list refresh |
| `MAIP_CROSS_TENANT_TRUST_PENALTY` | 0.20 | Default trust score reduction for cross-tenant |
| `MAIP_SIGNATURE_ALGORITHM` | Ed25519 | Required signature algorithm |
| `MAIP_HASH_ALGORITHM` | SHA-256 | Required hash algorithm |

---

## 10. Security Considerations

### 10.1 Threat Model

| Threat | Mitigation |
|--------|------------|
| Stolen agent private key | Kill switch with backdated `compromised_at`; short delegation TTLs limit blast radius |
| Scope escalation attack | Scope narrowing enforced cryptographically; parent signs child's scope set |
| Delegation chain forgery | Every delegation anchored in append-only transparency log; Merkle proofs prevent tampering |
| Rogue root issuer | Trust registry is the single source of root trust; multi-party governance for root changes |
| Replay attack (old bundle) | Bundle freshness window; temporal validation in chain verification |
| Denial of service on revocation | Revocation index is replicated; CRL provides fallback; offline bundles degrade gracefully |

### 10.2 Key Rotation

- Agents SHOULD rotate keys on a schedule defined by organizational policy (recommended: every 90 days).
- Key rotation creates a new `DelegationAttestation` with the new public key and revokes the old delegation.
- The old key's delegation is revoked with `effective_from` = rotation timestamp (no backdating needed for planned rotation).
- All active child delegations must be re-issued under the new key.

### 10.3 Audit Requirements

- All delegation operations (create, revoke, kill switch) MUST be recorded in the transparency log.
- Audit queries MUST be able to reconstruct the full delegation tree for any point in time.
- Retention: delegation and revocation records MUST be retained for a minimum of 7 years (configurable per regulatory requirement).

---

*End of MAIP Delegation Chain Specification v1.0.0-draft*

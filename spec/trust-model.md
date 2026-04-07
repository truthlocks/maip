# MAIP Trust Model Specification

**Protocol**: Machine Agent Identity Protocol (MAIP)  
**Version**: 1.0.0-draft  
**Status**: Draft  
**Date**: 2026-04-06  
**Authors**: Truthlocks Inc.  
**Related**: [MAIP Threat Model](./MAIP_SPEC_THREAT_MODEL.md) | [MAIP Implementation Plan](./MAIP_PLAN.md)

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Trust Hierarchy](#2-trust-hierarchy)
3. [Trust Levels](#3-trust-levels)
4. [Trust Scoring Model](#4-trust-scoring-model)
5. [Trust Propagation Rules](#5-trust-propagation-rules)
6. [Trust Governance](#6-trust-governance)
7. [Multi-Witness Verification](#7-multi-witness-verification)
8. [Trust Anchors and Federation](#8-trust-anchors-and-federation)
9. [Protocol Constants](#9-protocol-constants)
10. [Data Structures](#10-data-structures)
11. [Conformance Requirements](#11-conformance-requirements)
12. [References](#12-references)

---

## 1. Introduction

### 1.1 Purpose

This document defines the trust model for the Machine Agent Identity Protocol (MAIP). It specifies how trust is established, measured, propagated, and governed across a hierarchy of human and machine identities. The trust model is the foundation upon which all MAIP security guarantees rest: without a rigorous, auditable model for "who trusts whom, and why," cryptographic signatures are meaningless.

### 1.2 Scope

This specification covers:

- The hierarchical trust model from platform root to leaf agents
- Quantitative trust scoring with composite factors
- Rules governing trust propagation through delegation chains
- Governance processes for trust elevation, demotion, and recovery
- Multi-witness verification and quorum requirements
- Trust anchor architecture and federation model

This specification does NOT cover:

- Wire-level protocol formats (see MAIP Protocol Specification)
- Specific cryptographic algorithm implementations (see MAIP Cryptographic Profile)
- Threat analysis and attack mitigations (see [MAIP Threat Model](./MAIP_SPEC_THREAT_MODEL.md))

### 1.3 Relationship to Truthlocks Platform

MAIP is an open protocol. Truthlocks operates the reference production implementation, analogous to how Let's Encrypt operates ACME. The trust model defined here is protocol-level and implementation-agnostic. Where the specification references Truthlocks-specific infrastructure (trust-registry, attestation-service, signing-service, transparency-log), these are examples of conforming implementations, not protocol requirements.

### 1.4 Terminology

| Term | Definition |
|------|-----------|
| **Agent** | An autonomous or semi-autonomous software entity that acts on behalf of a human or organization |
| **Agent ID** | A MAIP-format identifier: `maip:<first8_of_tenant_uuid>:<ulid>` |
| **Attestation** | A cryptographically signed statement binding a subject to a set of claims |
| **Delegation** | The act of granting a subset of one's authority to another identity |
| **Delegation Chain** | The ordered sequence of delegations from root to a leaf agent |
| **Issuer** | An identity registered in the trust registry that can produce signed attestations |
| **Receipt** | A signed, tamper-evident record of an action taken by an agent |
| **Trust Level** | A discrete tier (L0-L5) representing the verification status and authority class of an identity |
| **Trust Score** | A numeric value (0-100) representing composite trustworthiness |
| **Trust Registry** | The authoritative store of issuer identities, keys, policies, and trust relationships |
| **Transparency Log** | An append-only, Merkle-anchored log providing tamper evidence for all protocol operations |

### 1.5 Notational Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119.

---

## 2. Trust Hierarchy

### 2.1 Overview

MAIP defines a five-level trust hierarchy. Each level represents a class of identity with distinct verification requirements, authority bounds, and trust properties. The hierarchy is strict: trust flows downward through explicit delegation, never upward through assertion.

```
+----------------------------------------------------------+
|                    L5: Platform Root                      |
|          Truthlocks infrastructure (immutable)            |
+----------------------------------------------------------+
                          |
            Bilateral trust agreements
                          |
+----------------------------------------------------------+
|              L4: Verified Organization                    |
|        KYB-verified, multi-signer governance              |
+----------------------------------------------------------+
                          |
            Employment / authorization proof
                          |
+----------------------------------------------------------+
|              L3: Verified Individual                      |
|        KYC-verified, single signer                        |
+----------------------------------------------------------+
                          |
            DelegationAttestation (depth=0)
                          |
+----------------------------------------------------------+
|              L2: Authenticated Agent                      |
|        Delegated from L3+, scoped capabilities            |
+----------------------------------------------------------+
                          |
            DelegationAttestation (depth=1..7)
                          |
+----------------------------------------------------------+
|              L2: Sub-Agent (depth 1-7)                    |
|        Further delegated, narrower scope                  |
+----------------------------------------------------------+

L1: Self-Asserted  (no verification, limited capabilities)
L0: Anonymous      (no identity, read-only)
```

### 2.2 Root of Trust

The Platform Root (L5) is the ultimate trust anchor in the MAIP ecosystem. It has the following properties:

- **Immutability**: The root signing keys are generated in a multi-party key ceremony and stored in hardware security modules (HSMs). The public keys are published in the transparency log at genesis.
- **Non-delegation**: The root identity does not delegate to agents. It signs only platform-level attestations: organization onboarding, trust policy updates, and transparency log checkpoints.
- **Transparency**: Every action by the root identity is logged in the transparency log with Merkle inclusion proofs. The root cannot act silently.
- **Governance**: Root key operations require M-of-N multi-party authorization (see Section 6).

### 2.3 Organization Level (L4)

Organizations are legal entities verified through Know Your Business (KYB) processes. An L4 identity represents a tenant in the Truthlocks trust-registry.

- **Registration**: An organization registers by providing legal entity documentation. The platform root issues a `TenantOnboardingAttestation` upon verification.
- **Multi-Signer**: Organizations MUST designate at least two authorized signers. Policy changes require approval from a quorum of designated signers.
- **Tenant Isolation**: Each organization operates in an isolated tenant context. Row-level security (RLS) in the trust-registry enforces that organizations can only manage their own issuers, keys, and policies.
- **Agent Namespace**: All agents created under an organization share the tenant prefix: `maip:<first8_of_tenant_uuid>:*`.

### 2.4 Individual Level (L3)

Individuals are human operators verified through Know Your Customer (KYC) processes. An L3 identity is bound to a natural person within an organization.

- **Registration**: An individual registers by providing government-issued identity documentation. The organization (L4) issues a `HumanOperatorAttestation` upon verification.
- **Single Signer**: Each individual controls exactly one signing key pair. Key rotation follows the standard lifecycle (see Section 4.3).
- **Delegation Authority**: L3 identities are the highest level that can delegate to agents. This is a critical design decision: agents always trace back to a verified human.
- **Accountability**: Every agent action is ultimately attributable to the L3 individual who initiated the delegation chain.

### 2.5 Agent Level (L2)

Agents are machine identities delegated from verified humans (L3) or other agents (L2). Agent IDs follow the format `maip:<first8_of_tenant_uuid>:<ulid>`.

- **Registration**: An agent is registered by its parent (L3 or L2) via a `DelegationAttestation`. The agent's genesis key is published in the transparency log.
- **Scoped Authority**: An agent's capabilities are a strict subset of its parent's capabilities. Scopes are defined at delegation time and cannot be widened.
- **Delegation Depth**: Agents can delegate to sub-agents up to `MAIP_MAX_DEPTH = 8` total hops from the L3 root. Each hop reduces trust (see Section 5).
- **Key Lifecycle**: Agent keys are managed through the signing-service. Agents register as issuers in the trust-registry, with their keys tracked in `issuer_keys`.

### 2.6 Self-Asserted Level (L1)

Self-asserted identities have registered with the platform but have not completed any verification process.

- **Capabilities**: L1 identities can create attestations, but these carry minimal trust weight. They cannot delegate to agents.
- **Use Cases**: Development/testing environments, open-source contributors, community members who want provenance tracking without full verification.
- **Upgrade Path**: L1 identities can elevate to L3 by completing KYC verification (see Section 6.1).

### 2.7 Anonymous Level (L0)

Anonymous identities have no registered identity in the MAIP ecosystem.

- **Capabilities**: Read-only access to public transparency log data and public verification endpoints.
- **Trust**: Zero trust. No attestations or receipts can originate from L0.
- **Use Cases**: Public verification of receipts and inclusion proofs without authentication.

---

## 3. Trust Levels

### 3.1 Trust Level Definitions

| Level | Name | Verification | Trust Score Range | Max Delegation Depth | Key Requirements |
|-------|------|-------------|-------------------|---------------------|-----------------|
| L5 | Platform Root | Multi-party key ceremony, HSM-backed | 100 (fixed) | 0 (no delegation) | HSM-stored, M-of-N ceremony |
| L4 | Verified Organization | KYB verification, legal entity docs | 80-100 | 0 (delegates through L3 members) | Multi-signer, rotation policy |
| L3 | Verified Individual | KYC verification, government ID | 60-79 | 8 (to agents) | Single key pair, rotation policy |
| L2 | Authenticated Agent | DelegationAttestation from L3+ | 0-79 (computed) | 8 minus current depth | Managed by signing-service |
| L1 | Self-Asserted | Email verification only | 0-20 | 0 (no delegation) | Self-managed key pair |
| L0 | Anonymous | None | 0 (fixed) | 0 | None |

### 3.2 Trust Level Properties

Each trust level carries a set of boolean properties that define what the identity can and cannot do:

| Property | L5 | L4 | L3 | L2 | L1 | L0 |
|----------|----|----|----|----|----|----|
| Create attestations | Yes (platform-level) | Yes (org-level) | Yes | Yes (scoped) | Yes (low trust) | No |
| Delegate to agents | No | No (through L3 members) | Yes | Yes (within depth limit) | No | No |
| Manage trust policies | Yes | Yes (own tenant) | No | No | No | No |
| Revoke identities | Yes (any) | Yes (own tenant) | Yes (own delegates) | Yes (own sub-agents) | No | No |
| Verify receipts | Yes | Yes | Yes | Yes | Yes | Yes (public only) |
| Register receipt types | Yes | Yes (own tenant) | No | No | No | No |
| Access transparency log | Yes | Yes | Yes | Yes | Yes | Yes (public subset) |
| Multi-witness eligible | Yes | Yes | Yes | Yes | No | No |

### 3.3 Trust Level Transitions

Trust levels are not static. Identities can be elevated or demoted through governed processes:

```
L0 ──(register)──> L1 ──(KYC verify)──> L3 ──(org onboard)──> L4
                                           |
                                           └──(delegate)──> L2 ──(sub-delegate)──> L2
                                                                    (depth + 1)

Demotion (automatic):
L4/L3 ──(policy violation)──> L1 (pending review)
L2 ──(parent revoked)──> REVOKED (immediate, cascading)
L2 ──(anomaly detected)──> SUSPENDED (pending investigation)
```

**Elevation** always requires human approval and evidence (see Section 6.1).  
**Demotion** is automatic upon policy violation or anomaly detection (see Section 6.2).  
**Revocation** is immediate and cascading: revoking a parent revokes all descendants (see Section 5.4).

---

## 4. Trust Scoring Model

### 4.1 Overview

The MAIP trust score is a composite numeric value in the range [0, 100] that quantifies the trustworthiness of an identity at a given point in time. Trust scores are not static ratings; they are dynamically computed from multiple weighted factors and can change as conditions evolve.

Trust scores serve two purposes:

1. **Authorization decisions**: Verifiers use trust scores to determine whether to accept an attestation for a given context. A verifier MAY set a minimum trust threshold (e.g., "accept only receipts from issuers with trust score >= 60").
2. **Risk signaling**: Trust scores integrate with the Anti-Fraud Identity Firewall's risk scoring pipeline. A declining trust score triggers investigation.

### 4.2 Composite Score Calculation

The trust score for an identity `i` at time `t` is computed as:

```
TrustScore(i, t) = clamp(0, 100,
    W_rep  * ReputationScore(i, t)
  + W_key  * KeyHealthScore(i, t)
  + W_del  * DelegationDepthScore(i)
  + W_ver  * VerificationHistoryScore(i, t)
  + W_wit  * MultiWitnessScore(i, t)
  - W_ano  * AnomalyPenalty(i, t)
)
```

Where `clamp(min, max, value)` restricts the result to the range `[min, max]`.

### 4.3 Factor Definitions

#### 4.3.1 Reputation Score (Weight: W_rep = 0.25)

Measures the historical reliability of an issuer's attestations.

```
ReputationScore(i, t) = (valid_attestations - revoked_attestations) / total_attestations * 100
```

| Condition | Score Range |
|-----------|------------|
| >= 99% valid over 1000+ attestations | 90-100 |
| >= 95% valid over 100+ attestations | 70-89 |
| >= 90% valid over 10+ attestations | 50-69 |
| < 90% valid or < 10 attestations | 0-49 |

**Decay**: Reputation decays if an issuer is inactive for more than `REPUTATION_DECAY_PERIOD` (default: 90 days). The decay rate is 1 point per week of inactivity, floored at 50% of peak reputation.

**Recovery**: Reputation recovers through continued issuance of valid attestations. Recovery rate is capped at 2 points per week to prevent rapid trust rebuilding after compromise.

#### 4.3.2 Key Health Score (Weight: W_key = 0.20)

Measures compliance with key lifecycle policies.

| Factor | Score Contribution |
|--------|-------------------|
| Key age within rotation policy | +40 |
| Key stored in HSM/KMS (not software) | +25 |
| Key has never been flagged as compromised | +20 |
| Key rotation completed on schedule | +15 |

**Penalties**:
- Key age exceeds 80% of rotation period: -10
- Key age exceeds rotation period (overdue): -30
- Key flagged with prior compromise history (even if rotated): -15
- Software-only key storage: -10

The key health score maps directly to fields in the trust-registry's `issuer_keys` table: `valid_from`, `valid_to`, `compromised_at`, `revoked_at`, and `rotated_from`.

#### 4.3.3 Delegation Depth Score (Weight: W_del = 0.20)

Trust decays with each delegation hop. Deeper agents are further from human oversight and carry higher risk.

```
DelegationDepthScore(i) = max(0, 100 - (depth * DEPTH_DECAY_FACTOR))
```

Where `DEPTH_DECAY_FACTOR` defaults to 12 points per hop.

| Depth | Score | Interpretation |
|-------|-------|---------------|
| 0 (L3 human) | 100 | Direct human identity |
| 1 (direct agent) | 88 | One hop from human |
| 2 | 76 | Two hops |
| 3 | 64 | Three hops |
| 4 | 52 | Four hops |
| 5 | 40 | Five hops |
| 6 | 28 | Six hops |
| 7 | 16 | Seven hops |
| 8 (max) | 4 | Maximum depth, minimal trust |

#### 4.3.4 Verification History Score (Weight: W_ver = 0.15)

Measures how frequently an identity's attestations are verified by third parties and how often those verifications succeed.

```
VerificationHistoryScore(i, t) = (successful_verifications / total_verifications) * activity_factor * 100
```

Where `activity_factor` is:

| Verification Activity | Factor |
|----------------------|--------|
| >= 100 verifications in past 30 days | 1.0 |
| 10-99 verifications in past 30 days | 0.8 |
| 1-9 verifications in past 30 days | 0.6 |
| 0 verifications in past 30 days | 0.3 |

A high pass rate with high activity indicates an identity whose attestations are both widely used and consistently valid.

#### 4.3.5 Multi-Witness Score (Weight: W_wit = 0.10)

Measures how frequently an identity's claims are corroborated by independent witnesses (see Section 7).

```
MultiWitnessScore(i, t) = (co_signed_attestations / total_attestations) * witness_diversity * 100
```

Where `witness_diversity` is the number of unique co-signing issuers divided by the quorum requirement for the identity's trust level.

#### 4.3.6 Anomaly Penalty (Weight: W_ano = 0.10)

Penalties applied when the Anti-Fraud Identity Firewall flags suspicious activity. Penalties are additive and decay over time.

| Anomaly Type | Penalty | Decay Rate |
|-------------|---------|-----------|
| Unusual signing volume spike (>3 sigma) | -15 | 1 point/day |
| Signing from unrecognized IP/environment | -10 | 2 points/day |
| Failed verification rate spike | -20 | 1 point/day |
| Deepfake detection flag on linked identity | -30 | Manual review required |
| Associated with revoked/compromised peer | -10 | 5 points/day after peer remediated |
| Scope violation attempt | -25 | 1 point/day |

### 4.4 Trust Score Ceilings

Trust scores are bounded by trust level ceilings. No factor combination can push a score above the level ceiling:

| Trust Level | Maximum Trust Score |
|-------------|-------------------|
| L5 | 100 |
| L4 | 100 |
| L3 | 79 |
| L2 | min(parent_score - DEPTH_DECAY, 79) |
| L1 | 20 |
| L0 | 0 |

### 4.5 Trust Score Refresh

Trust scores MUST be recomputed:

1. On every verification request (real-time path)
2. On any key lifecycle event (rotation, revocation, compromise)
3. On delegation chain changes (new delegation, revocation)
4. On anomaly detection events
5. Periodically via batch job (default: every 6 hours) to apply decay functions

Implementations MAY cache trust scores with a TTL no greater than `TRUST_SCORE_CACHE_TTL` (default: 300 seconds, 5 minutes).

---

## 5. Trust Propagation Rules

### 5.1 Fundamental Invariants

The following invariants MUST hold at all times in a conforming MAIP implementation:

**Invariant 1 (Downward Trust Bound)**: A child identity's trust score MUST NOT exceed its parent's trust score at the time of delegation.

```
TrustScore(child) <= TrustScore(parent_at_delegation_time)
```

**Invariant 2 (Scope Narrowing)**: A child identity's capability scope MUST be a subset of its parent's scope.

```
Scopes(child) subset_of Scopes(parent)
```

**Invariant 3 (Depth Limit)**: No delegation chain MAY exceed `MAIP_MAX_DEPTH` (8) hops from the L3 root.

```
depth(agent) <= MAIP_MAX_DEPTH
```

**Invariant 4 (Human Root)**: Every valid delegation chain MUST terminate at a verified human identity (L3 or above).

```
root(delegation_chain) is L3 or L4 or L5
```

### 5.2 Trust Decay Through Delegation

When identity `P` (parent) delegates to identity `C` (child) at depth `d`:

```
max_trust(C) = min(
    TrustScore(P) - DEPTH_DECAY,
    scope_max_trust(C.scopes)
)
```

Where:
- `DEPTH_DECAY` is configurable per tenant, default 10 points per hop
- `scope_max_trust(scopes)` is the maximum trust allowed for the granted scope set

**Example**: A human operator (L3) with trust score 75 delegates to an agent (depth=1):

```
max_trust(agent) = min(75 - 10, 79) = 65
```

That agent delegates to a sub-agent (depth=2):

```
max_trust(sub_agent) = min(65 - 10, 79) = 55
```

### 5.3 Scope Propagation

Scopes are string identifiers following a hierarchical namespace:

```
<domain>:<resource>:<action>

Examples:
  attestation:receipt:create
  attestation:receipt:revoke
  dataset:training:attest
  dataset:training:read
  agent:delegate:create
  agent:identity:read
```

**Scope narrowing rules**:

1. A child MUST NOT receive a scope the parent does not hold.
2. A child MAY receive a narrower version of a parent's scope (e.g., parent has `dataset:*:*`, child receives `dataset:training:read`).
3. Wildcard scopes (`*`) are permitted only at L3 and L4. Agents (L2) MUST have explicitly enumerated scopes.
4. The scope `agent:delegate:create` is required to create sub-agents. Omitting this scope from a delegation prevents further delegation.

**Scope validation** occurs at:
- Delegation time: the attestation-service validates that the requested scopes are a subset of the parent's scopes.
- Action time: the machine-identity-service validates that the agent holds the required scope for the requested action.

### 5.4 Revocation Propagation

Revocation is MAIP's most critical trust operation. It MUST be immediate and cascading.

#### 5.4.1 Revocation Triggers

| Trigger | Source | Cascade |
|---------|--------|---------|
| Human operator revokes agent | Trust registry API | All descendants of revoked agent |
| Key compromise detected | `issuer_keys.compromised_at` set | All attestations signed after compromise time |
| Organization offboarded | Platform root action | All L3 and L2 identities under tenant |
| Anomaly auto-revocation | Anti-Fraud Firewall (risk_score > threshold) | Configurable: suspend-only or full cascade |
| Delegation expiry | TTL on DelegationAttestation | Agent and all descendants |
| Manual governance action | Dispute resolution (Section 6.3) | Case-specific |

#### 5.4.2 Cascade Algorithm

When identity `I` is revoked at time `T`:

```
REVOKE(I, T):
  1. Set I.status = REVOKED, I.revoked_at = T in trust-registry
  2. Set I.key.revoked_at = T in issuer_keys
  3. Publish RevocationAttestation to transparency log
  4. For each child C where C.parent = I:
       REVOKE(C, T)
  5. Emit revocation event to audit-service
  6. Notify downstream verifiers via webhook (if configured)
```

**Blast radius analysis**: Before executing a cascade revocation, the implementation SHOULD compute and log the blast radius:

```json
{
  "revocation_root": "maip:a1b2c3d4:01HXYZ...",
  "cascade_depth": 3,
  "affected_agents": 12,
  "affected_receipts": 1847,
  "affected_datasets": 3,
  "estimated_downstream_impact": "HIGH"
}
```

#### 5.4.3 Revocation Verification

Verifiers MUST check revocation status as part of every verification:

1. Check `issuer_keys.revoked_at` for the signing key
2. Check `issuer_keys.compromised_at` — if the receipt was signed AFTER `compromised_at`, the receipt is INVALID
3. Walk the delegation chain upward; if any ancestor is revoked, the receipt is INVALID
4. Check the transparency log for `RevocationAttestation` covering the issuer or key

### 5.5 Cross-Tenant Delegation

By default, delegation is scoped to a single tenant. Cross-tenant delegation requires explicit bilateral trust agreements.

#### 5.5.1 Trust Agreement Structure

```json
{
  "type": "CrossTenantTrustAgreement",
  "version": "1.0",
  "tenant_a": "<uuid>",
  "tenant_b": "<uuid>",
  "direction": "bilateral",
  "allowed_scopes": ["dataset:training:read", "attestation:receipt:verify"],
  "max_delegation_depth": 2,
  "trust_ceiling": 50,
  "effective_from": "2026-04-06T00:00:00Z",
  "expires_at": "2027-04-06T00:00:00Z",
  "signed_by_a": "<signature>",
  "signed_by_b": "<signature>"
}
```

#### 5.5.2 Cross-Tenant Rules

1. Both tenants MUST sign the trust agreement. One-sided trust is not permitted.
2. Cross-tenant delegations MUST have a `trust_ceiling` no higher than 50 (configurable at platform level).
3. Cross-tenant delegation depth counts against `MAIP_MAX_DEPTH` from the original human root, not from the cross-tenant boundary.
4. Either tenant MAY unilaterally revoke the trust agreement. Revocation takes effect immediately and cascades to all cross-tenant delegations.
5. Cross-tenant trust agreements are published in the transparency log for auditability.

---

## 6. Trust Governance

### 6.1 Trust Elevation

Trust elevation is the process of moving an identity to a higher trust level. Elevation always requires human approval and verifiable evidence.

#### 6.1.1 Elevation Requirements

| Transition | Required Evidence | Approver | Transparency Log Entry |
|-----------|-------------------|----------|----------------------|
| L0 to L1 | Email verification | Automated | `SelfAssertionAttestation` |
| L1 to L3 | Government-issued ID, liveness check, address proof | Organization admin (L4) | `KYCVerificationAttestation` |
| L3 to L4 (org creation) | Articles of incorporation, business registration, authorized signatory proof | Platform root (L5) | `KYBVerificationAttestation` |

#### 6.1.2 Elevation Process

```
1. Requester submits elevation request with evidence documents
2. Evidence is stored in encrypted evidence store (never in transparency log)
3. Evidence hash is computed: SHA-256(canonical(evidence))
4. Designated approver reviews evidence
5. If approved:
   a. Approver signs ElevationAttestation containing evidence hash
   b. ElevationAttestation is anchored in transparency log
   c. Trust level is updated in trust-registry
   d. Trust score is recomputed
6. If denied:
   a. DenialAttestation is recorded with reason code
   b. Requester may appeal after ELEVATION_COOLDOWN (default: 30 days)
```

#### 6.1.3 Anti-Gaming Controls

- Elevation requests are rate-limited: at most 1 request per `ELEVATION_COOLDOWN` period.
- Evidence documents are checked against the deepfake detection pipeline (Anti-Fraud Identity Firewall integration).
- Multiple failed elevation attempts trigger a manual review flag on the identity.

### 6.2 Trust Demotion

Trust demotion is the automatic reduction of an identity's trust level upon policy violation or anomaly detection. Unlike elevation, demotion does not require human approval (it is automatic) but MUST be auditable and appealable.

#### 6.2.1 Automatic Demotion Triggers

| Trigger | Demotion Action | Severity |
|---------|----------------|----------|
| Key compromise confirmed | Immediate revocation of identity and cascade (Section 5.4) | CRITICAL |
| Anomaly score exceeds `ANOMALY_SUSPEND_THRESHOLD` (default: 70) | Suspend identity, pending investigation | HIGH |
| Failed verification rate > 20% over 100+ checks | Reduce trust score ceiling by 20 points | MEDIUM |
| Key rotation overdue by > 2x policy period | Reduce trust score ceiling by 10 points | MEDIUM |
| Scope violation detected (attempted action outside granted scopes) | Log warning, reduce trust score by 25 | HIGH |
| Issuer reputation drops below 50 | Flag for review, reduce trust score ceiling | LOW |

#### 6.2.2 Demotion Process

```
1. Demotion trigger fires (automated detection or manual report)
2. System computes new trust ceiling for the identity
3. DemotionAttestation is created with:
   - Trigger type and evidence
   - Old trust level/ceiling
   - New trust level/ceiling
   - Timestamp
4. DemotionAttestation is anchored in transparency log
5. Trust score is recomputed with new ceiling
6. If demotion includes suspension:
   a. All pending operations by the identity are halted
   b. All sub-agents are suspended (not revoked, pending investigation)
7. Identity holder is notified with reason and appeal instructions
```

### 6.3 Dispute Resolution

When an identity disputes a demotion, anomaly flag, or revocation, MAIP provides a structured resolution process.

#### 6.3.1 Dispute Process

```
Phase 1: Automated Review (0-24 hours)
  - System re-evaluates evidence that triggered the demotion
  - If evidence is ambiguous, escalate to Phase 2
  - If evidence is clear, uphold demotion with explanation

Phase 2: Multi-Witness Review (24-72 hours)
  - 3 independent reviewers evaluate the dispute
  - Reviewers must be from different organizations (no conflict of interest)
  - Majority decision (2 of 3) determines outcome
  - All reviewer decisions are recorded in transparency log

Phase 3: Governance Board (72 hours - 14 days)
  - Escalation to MAIP Governance Board (platform-level)
  - Board reviews full evidence chain
  - Board decision is final and recorded as a GovernanceAttestation
```

#### 6.3.2 Dispute Outcomes

| Outcome | Action |
|---------|--------|
| Demotion upheld | No change; identity may pursue trust recovery (Section 6.4) |
| Demotion overturned | Trust level and score restored; apology attestation issued |
| Partial reversal | Trust level restored but with enhanced monitoring for 90 days |
| Escalation | Forwarded to governance board for complex cases |

### 6.4 Trust Recovery

After a compromise or demotion, an identity can recover trust through a structured process.

#### 6.4.1 Recovery Requirements

| Recovery Scenario | Requirements | Timeline |
|------------------|-------------|----------|
| Key compromise (single key) | New key ceremony, re-verification, 30-day probation | 30-60 days |
| Anomaly-triggered suspension | Investigation clearance, enhanced monitoring | 7-30 days |
| Reputation decline | Sustained valid attestation history (>95% valid for 90 days) | 90+ days |
| Organization offboarding reversal | Re-KYB, new trust agreement, platform approval | 30-90 days |

#### 6.4.2 Recovery Process

```
1. Identity holder initiates recovery request
2. Complete re-verification at the required trust level (same evidence as elevation)
3. New signing key is generated (old key remains revoked forever)
4. RecoveryAttestation is issued with:
   - Link to original compromise/demotion attestation
   - New key fingerprint
   - Recovery conditions (monitoring period, trust ceiling cap)
5. Trust score starts at 50% of the identity's pre-incident score
6. Trust score cap increases linearly over the monitoring period
7. Full trust restoration upon successful completion of monitoring period
```

---

## 7. Multi-Witness Verification

### 7.1 Purpose

Multi-witness verification allows multiple independent issuers to co-sign the same claim, producing a composite attestation with higher trust than any single issuer could provide. This is MAIP's primary defense against malicious issuers and colluding parties (see [Threat Model, Section 2: T1, T3](./MAIP_SPEC_THREAT_MODEL.md#2-threat-actors)).

### 7.2 Witness Model

A **witness** is any L2+ identity that independently verifies a claim and adds their signature to a multi-witness attestation.

```json
{
  "type": "MultiWitnessAttestation",
  "version": "1.0",
  "claim": {
    "subject": "dataset:training-set-v3",
    "claim_type": "integrity",
    "claim_value": "SHA-256:a1b2c3d4..."
  },
  "witnesses": [
    {
      "issuer_id": "maip:a1b2c3d4:01HX...",
      "trust_level": "L3",
      "trust_score": 72,
      "signature": "<ed25519_signature>",
      "signed_at": "2026-04-06T10:00:00Z",
      "verification_method": "independent_hash_computation"
    },
    {
      "issuer_id": "maip:e5f6g7h8:01HY...",
      "trust_level": "L2",
      "trust_score": 65,
      "signature": "<ed25519_signature>",
      "signed_at": "2026-04-06T10:05:00Z",
      "verification_method": "independent_hash_computation"
    },
    {
      "issuer_id": "maip:i9j0k1l2:01HZ...",
      "trust_level": "L3",
      "trust_score": 70,
      "signature": "<ed25519_signature>",
      "signed_at": "2026-04-06T10:10:00Z",
      "verification_method": "independent_hash_computation"
    }
  ],
  "quorum": {
    "required": 2,
    "achieved": 3,
    "policy": "majority"
  },
  "composite_trust_score": 82,
  "transparency_log_index": 184729
}
```

### 7.3 Quorum Requirements

Different trust operations require different quorum sizes:

| Operation | Minimum Witnesses | Quorum Policy | Diversity Requirement |
|-----------|------------------|---------------|----------------------|
| Standard attestation | 1 | Single signer | None |
| High-value attestation (trust score > 70 required) | 2 | Majority | Different organizations |
| Critical attestation (trust score > 85 required) | 3 | Supermajority (2/3) | Different organizations + different geographic regions |
| Platform-level operation | 5 | Supermajority (3/5) | Different organizations + multi-factor |
| Root key ceremony | M-of-N (N >= 7, M >= 5) | Threshold | Geographic distribution + independent custodians |

### 7.4 Diversity Requirements

To prevent collusion (see [Threat Model, Section 2: T3](./MAIP_SPEC_THREAT_MODEL.md#23-t3-colluding-issuers)), witnesses MUST satisfy diversity constraints:

1. **Organizational diversity**: At least `ceil(quorum / 2)` witnesses MUST be from different tenant IDs.
2. **Key diversity**: No two witnesses MAY share the same signing key or key derivation path.
3. **Temporal diversity**: Witness signatures MUST be collected within a `WITNESS_WINDOW` (default: 24 hours) but MUST NOT all occur within the same 60-second interval (to prevent automated rubber-stamping).
4. **Independence**: Witnesses MUST NOT be in the same delegation chain. A parent and its delegated agent cannot co-witness the same claim.

### 7.5 Composite Trust Score Calculation

The composite trust score for a multi-witness attestation is:

```
composite_trust = min(100, base_trust + witness_bonus)

Where:
  base_trust = max(witness_trust_scores)  -- strongest witness
  witness_bonus = sum(additional_witness_scores) * WITNESS_BONUS_FACTOR / num_witnesses

  WITNESS_BONUS_FACTOR = 0.3 (default)
```

**Example**: Three witnesses with trust scores [72, 65, 70]:

```
base_trust = 72
witness_bonus = (65 + 70) * 0.3 / 3 = 13.5
composite_trust = min(100, 72 + 13.5) = 85.5 -> 85 (floor)
```

A single L3 issuer with score 72 produces a trust-72 attestation. Three independent witnesses elevate this to trust-85, crossing the "critical attestation" threshold.

### 7.6 Witness Incentives

The protocol does not mandate economic incentives for witnesses, but implementations SHOULD track witness participation for reputation scoring (Section 4.3.5). Issuers who frequently serve as reliable witnesses build higher multi-witness scores, creating a positive feedback loop for ecosystem participation.

---

## 8. Trust Anchors and Federation

### 8.1 Trust Anchor Architecture

MAIP's trust anchor model is analogous to the PKI certificate authority hierarchy, adapted for machine identity:

| PKI Concept | MAIP Equivalent | Notes |
|-------------|----------------|-------|
| Root CA | Platform Root (L5) | Truthlocks operates the reference root |
| Intermediate CA | Verified Organization (L4) | Each tenant is an intermediate authority |
| End-entity certificate | Agent Identity (L2) | Machine identities issued by organizations |
| Certificate chain | Delegation chain | Ordered list of DelegationAttestations |
| CRL / OCSP | Revocation propagation + transparency log | Real-time revocation checking |
| CT log | Transparency log | Merkle-anchored, append-only audit trail |

### 8.2 Root Trust Anchor Properties

The MAIP root trust anchor MUST have the following properties:

1. **Public key transparency**: Root public keys are published in the transparency log at genesis and are independently verifiable.
2. **Key ceremony auditability**: Root key generation follows a documented, witnessed ceremony with M-of-N threshold signing (N >= 7, M >= 5).
3. **Operational separation**: Root key operations are physically separated from production operations. Root keys are stored in HSMs in geographically distributed facilities.
4. **Rotation schedule**: Root keys rotate on a fixed schedule (default: 5 years) with a 1-year overlap period for graceful migration.
5. **Revocation plan**: A documented procedure exists for emergency root key revocation, including a pre-published "next root" public key.

### 8.3 Federation Model

MAIP supports federation, where multiple independent MAIP-compliant registries can establish mutual trust. This enables interoperability without centralization.

#### 8.3.1 Federation Topology

```
+------------------+        Federation Agreement        +------------------+
| MAIP Registry A  |<=================================>| MAIP Registry B  |
| (e.g., Truthlocks)|    Signed by both roots          | (e.g., Partner)  |
|   L5 Root A      |    Published in both logs          |   L5 Root B      |
|   L4 Tenants...  |    Scope-limited                   |   L4 Tenants...  |
+------------------+                                    +------------------+
         |                                                       |
    Agents under A                                         Agents under B
    can verify receipts                                   can verify receipts
    from B (within                                        from A (within
    agreed scopes)                                        agreed scopes)
```

#### 8.3.2 Federation Requirements

1. **Bilateral root signing**: Both registries MUST sign a `FederationAgreement` attestation, published in both transparency logs.
2. **Scope limitation**: Federation agreements MUST specify which attestation types and scopes are accepted across the boundary.
3. **Trust ceiling**: Cross-federation trust scores are capped at `FEDERATION_TRUST_CEILING` (default: 60). Even a trust-100 identity in Registry A is treated as trust-60 by verifiers in Registry B.
4. **Independent verification**: Verifiers MUST validate the full delegation chain against the originating registry's transparency log, not the local registry.
5. **Revocation relay**: Revocation events MUST be relayed between federated registries within `FEDERATION_REVOCATION_RELAY_MAX` (default: 60 seconds).

#### 8.3.3 Federation Governance

- Federation agreements require approval from both registries' governance boards.
- Either registry MAY unilaterally withdraw from federation with a `FEDERATION_WITHDRAWAL_NOTICE` period (default: 30 days).
- Emergency withdrawal (e.g., partner compromise) is immediate but MUST be documented in the transparency log with evidence.

### 8.4 Offline Verification and Trust Anchors

MAIP supports offline verification via self-contained bundles (see MAIP Protocol Specification). For offline verification, the trust anchor is embedded in the bundle:

```json
{
  "trust_anchor": {
    "registry": "truthlocks",
    "root_public_key": "<ed25519_public_key>",
    "root_key_id": "maip-root-2026",
    "transparency_log_checkpoint": {
      "tree_size": 2847291,
      "root_hash": "SHA-256:...",
      "timestamp": "2026-04-06T00:00:00Z",
      "signature": "<ed25519_signature_by_root>"
    }
  }
}
```

Offline verifiers MUST:

1. Validate the trust anchor's root public key against a pinned or pre-distributed key set.
2. Verify the transparency log checkpoint signature.
3. Verify the inclusion proof for every attestation in the bundle against the checkpoint.
4. Verify the delegation chain from the signing agent back to an L3+ identity.
5. Check that no `RevocationAttestation` in the bundle covers any identity in the chain.

---

## 9. Protocol Constants

The following constants are defined at the protocol level. Implementations MAY allow tenant-level overrides where noted.

| Constant | Default Value | Tenant Override | Description |
|----------|--------------|----------------|-------------|
| `MAIP_MAX_DEPTH` | 8 | No | Maximum delegation chain depth from L3 root |
| `DEPTH_DECAY` | 10 | Yes (min: 5, max: 20) | Trust score reduction per delegation hop |
| `DEPTH_DECAY_FACTOR` | 12 | Yes (min: 8, max: 20) | Points deducted per hop in DelegationDepthScore |
| `TRUST_SCORE_CACHE_TTL` | 300s | Yes (max: 600s) | Maximum cache duration for trust scores |
| `REPUTATION_DECAY_PERIOD` | 90 days | Yes (min: 30d, max: 365d) | Inactivity period before reputation decay |
| `WITNESS_WINDOW` | 24 hours | Yes (min: 1h, max: 72h) | Maximum time span for collecting multi-witness signatures |
| `WITNESS_BONUS_FACTOR` | 0.3 | No | Multiplier for additional witness trust contribution |
| `ANOMALY_SUSPEND_THRESHOLD` | 70 | Yes (min: 50, max: 90) | Anomaly score triggering automatic suspension |
| `ELEVATION_COOLDOWN` | 30 days | No | Minimum wait between elevation requests |
| `FEDERATION_TRUST_CEILING` | 60 | No | Maximum trust score for cross-federation identities |
| `FEDERATION_REVOCATION_RELAY_MAX` | 60s | No | Maximum delay for cross-federation revocation relay |
| `FEDERATION_WITHDRAWAL_NOTICE` | 30 days | No | Notice period for non-emergency federation withdrawal |
| `ROOT_KEY_ROTATION_PERIOD` | 5 years | No | Root key rotation schedule |
| `ROOT_KEY_OVERLAP_PERIOD` | 1 year | No | Overlap period during root key rotation |

---

## 10. Data Structures

### 10.1 Trust Level Enum

```
enum TrustLevel {
  L0 = 0  // Anonymous
  L1 = 1  // Self-Asserted
  L2 = 2  // Authenticated Agent
  L3 = 3  // Verified Individual
  L4 = 4  // Verified Organization
  L5 = 5  // Platform Root
}
```

### 10.2 Trust Score Record

```json
{
  "identity_id": "maip:a1b2c3d4:01HXYZ...",
  "trust_level": "L2",
  "trust_score": 65,
  "score_components": {
    "reputation": 18.0,
    "key_health": 17.0,
    "delegation_depth": 15.2,
    "verification_history": 9.0,
    "multi_witness": 7.0,
    "anomaly_penalty": -1.2
  },
  "trust_ceiling": 76,
  "delegation_depth": 1,
  "computed_at": "2026-04-06T12:00:00Z",
  "valid_until": "2026-04-06T12:05:00Z",
  "parent_id": "maip:a1b2c3d4:operator-abc",
  "tenant_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

### 10.3 Delegation Attestation

```json
{
  "type": "DelegationAttestation",
  "version": "1.0",
  "issuer_id": "maip:a1b2c3d4:operator-abc",
  "subject_id": "maip:a1b2c3d4:01HXYZ...",
  "delegation_depth": 1,
  "scopes": [
    "attestation:receipt:create",
    "dataset:training:attest",
    "dataset:training:read"
  ],
  "constraints": {
    "max_sub_delegations": 3,
    "allowed_receipt_types": ["inference_receipt", "dataset_attestation"],
    "rate_limit": "1000/hour",
    "ip_allowlist": ["10.0.0.0/8"],
    "time_bound": {
      "not_before": "2026-04-06T00:00:00Z",
      "not_after": "2026-07-06T00:00:00Z"
    }
  },
  "parent_trust_score_at_delegation": 72,
  "signed_at": "2026-04-06T10:00:00Z",
  "signature": "<ed25519_signature>",
  "transparency_log_index": 184700
}
```

### 10.4 Revocation Attestation

```json
{
  "type": "RevocationAttestation",
  "version": "1.0",
  "issuer_id": "maip:a1b2c3d4:operator-abc",
  "subject_id": "maip:a1b2c3d4:01HXYZ...",
  "reason": "key_compromise",
  "reason_detail": "Signing key exposed in CI logs",
  "effective_at": "2026-04-06T14:30:00Z",
  "cascade": true,
  "affected_descendants": 12,
  "affected_receipts_after": "2026-04-05T00:00:00Z",
  "signed_at": "2026-04-06T14:30:05Z",
  "signature": "<ed25519_signature>",
  "transparency_log_index": 184750
}
```

### 10.5 Cross-Tenant Trust Agreement

See Section 5.5.1 for the full structure.

### 10.6 Federation Agreement

```json
{
  "type": "FederationAgreement",
  "version": "1.0",
  "registry_a": {
    "name": "truthlocks",
    "root_key_id": "maip-root-2026",
    "root_public_key": "<ed25519_public_key>"
  },
  "registry_b": {
    "name": "partner-registry",
    "root_key_id": "partner-root-2026",
    "root_public_key": "<ed25519_public_key>"
  },
  "allowed_attestation_types": ["dataset_attestation", "inference_receipt"],
  "trust_ceiling": 60,
  "effective_from": "2026-04-06T00:00:00Z",
  "expires_at": "2027-04-06T00:00:00Z",
  "withdrawal_notice_days": 30,
  "signed_by_a": "<ed25519_signature>",
  "signed_by_b": "<ed25519_signature>",
  "transparency_log_index_a": 184800,
  "transparency_log_index_b": 92400
}
```

---

## 11. Conformance Requirements

### 11.1 Conformance Levels

MAIP defines three conformance levels:

| Level | Name | Requirements |
|-------|------|-------------|
| Core | Basic MAIP | Trust levels L0-L3, single-tenant, single-signer, delegation depth <= 4 |
| Standard | Full MAIP | All trust levels, multi-tenant, multi-witness, full delegation depth, revocation cascade |
| Federation | Federated MAIP | Standard + cross-registry federation |

### 11.2 Core Conformance Requirements

A Core-conformant implementation MUST:

1. Implement trust levels L0, L1, L2, and L3.
2. Enforce `Scopes(child) subset_of Scopes(parent)` for all delegations.
3. Enforce `MAIP_MAX_DEPTH` limit on delegation chains.
4. Compute trust scores using at minimum the ReputationScore, KeyHealthScore, and DelegationDepthScore factors.
5. Implement cascading revocation (Section 5.4).
6. Anchor all delegations and revocations in an append-only log with Merkle inclusion proofs.
7. Support offline verification via self-contained bundles.

### 11.3 Standard Conformance Requirements

A Standard-conformant implementation MUST satisfy all Core requirements and additionally:

1. Implement trust levels L4 and L5.
2. Implement the full composite trust score model (all six factors, Section 4).
3. Support multi-witness verification with diversity requirements (Section 7).
4. Support cross-tenant trust agreements (Section 5.5).
5. Implement trust governance: elevation, demotion, dispute resolution, and recovery (Section 6).
6. Integrate with anomaly detection for automatic trust score adjustment.

### 11.4 Federation Conformance Requirements

A Federation-conformant implementation MUST satisfy all Standard requirements and additionally:

1. Support bilateral federation agreements (Section 8.3).
2. Implement cross-federation trust ceiling enforcement.
3. Implement revocation relay within `FEDERATION_REVOCATION_RELAY_MAX`.
4. Support independent verification against the originating registry's transparency log.

---

## 12. References

### Normative References

- **RFC 2119**: Key words for use in RFCs to Indicate Requirement Levels
- **RFC 8785**: JSON Canonicalization Scheme (JCS)
- **RFC 8032**: Edwards-Curve Digital Signature Algorithm (Ed25519)
- **RFC 6962**: Certificate Transparency (Merkle tree model reference)
- **MAIP Threat Model**: [MAIP_SPEC_THREAT_MODEL.md](./MAIP_SPEC_THREAT_MODEL.md)
- **MAIP Implementation Plan**: [MAIP_PLAN.md](./MAIP_PLAN.md)

### Informative References

- SPIFFE/SPIRE: Secure Production Identity Framework for Everyone
- W3C Verifiable Credentials Data Model 2.0
- W3C Decentralized Identifiers (DIDs) v1.0
- NIST SP 800-63: Digital Identity Guidelines
- Google Certificate Transparency (RFC 6962 implementation)
- Sigstore: Software supply chain transparency

### Truthlocks Platform References

- `services/trust-registry/` — Issuer management, `issuer_keys` table, RLS policies
- `services/attestation-service/` — Receipt minting, `receipt_types`, `receipt_events`
- `services/signing-service/` — Ed25519/KMS key lifecycle
- `services/transparency-log/` — Merkle-anchored append-only log
- `services/verification-service/` — Online/offline verification, risk scoring
- `services/audit-service/` — Tamper-evident event log

---

*End of MAIP Trust Model Specification v1.0.0-draft*

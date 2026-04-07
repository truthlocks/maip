# MAIP Protocol Specification: Threat Model

## MAIP-SPEC-THREAT-001 | Version 1.0 | Status: DRAFT

---

## 1. Overview

This document defines the threat model for the Machine Agent Identity Protocol (MAIP). It identifies threat actors, attack scenarios, security properties, cryptographic assumptions, failure modes, and mitigation strategies. The methodology combines STRIDE (Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege) with DREAD scoring (Damage, Reproducibility, Exploitability, Affected Users, Discoverability) on a 1-10 scale.

**Scope**: All MAIP protocol operations including agent registration, delegation, receipt creation, verification, revocation, and offline bundle verification. Covers both the open-source protocol and the Truthlocks hosted implementation.

**Out of scope**: Physical security of HSM devices, employee background checks, social engineering attacks on humans outside the protocol.

---

## 2. Threat Actors

| ID | Actor | Capabilities | Motivation | Access Level |
|----|-------|-------------|------------|-------------|
| **T1** | External Attacker | Network access, public APIs, no credentials, commodity tooling | Financial gain, disruption, reputation damage | External (unauthenticated) |
| **T2** | Compromised Agent | Valid MAIP identity, signed delegation chain, access to assigned scopes | Data exfiltration, scope escalation, unauthorized actions | Authenticated agent |
| **T3** | Malicious Insider | Org-level access, valid tenant credentials, knowledge of internal systems | Sabotage, data theft, fraud, competitive intelligence | Tenant administrator |
| **T4** | Compromised Issuer | Stolen signing keys, ability to mint attestations and receipts | False attestations, identity fraud, trust hierarchy poisoning | Issuer-level (trust-registry) |
| **T5** | Colluding Parties | Multiple actors coordinating across entities, shared information | Bypass multi-witness requirements, create false consensus | Multi-entity (cross-tenant) |
| **T6** | State-Level Adversary | Unlimited compute, legal compulsion, CA/infrastructure compromise | Surveillance, compelled disclosure, protocol subversion | Infrastructure-level |
| **T7** | Supply Chain Attacker | Compromised dependencies, malicious build tooling, CI/CD access | Backdoor insertion, key exfiltration, silent compromise | Build pipeline |

### 2.1 Threat Actor Profiles

**T1 — External Attacker**: Operates from the internet with no prior access. Uses automated scanning, API fuzzing, and known vulnerability exploitation. Cannot forge Ed25519 signatures but can attempt replay attacks, man-in-the-middle on unencrypted channels, and abuse of public verification endpoints.

**T2 — Compromised Agent**: A legitimate MAIP agent whose runtime has been compromised (e.g., container escape, dependency vulnerability). Possesses valid signing keys and delegation chain. Can sign receipts within its granted scopes but attempts to exceed those scopes or exfiltrate data.

**T3 — Malicious Insider**: A human with legitimate tenant-level access who abuses their position. Can create agents, issue delegations, and access audit logs. May attempt to create backdoor delegations, suppress audit evidence, or exfiltrate signing keys.

**T4 — Compromised Issuer**: An issuer in the trust-registry whose signing keys have been stolen. Can mint any attestation type that the issuer was authorized to create. The blast radius depends on the issuer's trust level and the number of agents delegated through it.

**T5 — Colluding Parties**: Two or more entities (potentially cross-tenant) coordinating to defeat multi-witness requirements. Can produce apparently independent attestations that are actually coordinated. Particularly dangerous for truth claims requiring independent verification.

**T6 — State-Level Adversary**: Can compel infrastructure providers (cloud, DNS, CA) to cooperate. May attempt to forge transparency log entries, compel key disclosure, or insert surveillance capabilities. Assumed to have unlimited computational resources but cannot break Ed25519 (128-bit security).

**T7 — Supply Chain Attacker**: Targets the software supply chain rather than the protocol directly. May compromise npm/Go module dependencies, CI/CD pipelines, or container images. Goal is to insert backdoors that exfiltrate keys or modify receipt generation logic.

---

## 3. Attack Scenarios

### A1: Replay of Valid Receipts in Wrong Context

**Description**: An attacker captures a valid, signed MAIP receipt and presents it to a different verifier or in a different context than originally intended.

**Preconditions**: Attacker has network access to observe or intercept receipts. Receipt lacks audience binding or has expired TTL.

**Attack Steps**:
1. Intercept a valid action receipt from Agent X to Verifier A
2. Present the same receipt to Verifier B as proof of action
3. Verifier B accepts the receipt because the signature is valid

**DREAD Score**: D=6, R=8, E=7, A=5, D=6 — **Total: 32/50 (HIGH)**

**Mitigations**:
- `audience` field binds receipt to intended verifier (REQUIRED for high-value receipts)
- `purpose` field constrains intended use
- `nonce` prevents exact replay (REQUIRED for financial/compliance receipts)
- `expires_at` limits temporal validity (default 24h for actions, 1y for attestations)
- Verifiers MUST check audience and reject mismatched receipts

**Detection**: Audit log correlation — same receipt_id presented to multiple verifiers triggers alert.

---

### A2: Scope Escalation via Delegation Chain Manipulation

**Description**: A compromised agent attempts to create or modify a delegation to grant itself scopes beyond what its parent delegated.

**Preconditions**: Agent has valid identity and at least one delegation. Agent's runtime is compromised.

**Attack Steps**:
1. Agent receives delegation with scopes `[data.read]`
2. Agent attempts to create sub-delegation with scopes `[data.read, data.write, admin.revoke]`
3. Sub-agent now has unauthorized capabilities

**DREAD Score**: D=8, R=4, E=3, A=7, D=4 — **Total: 26/50 (MEDIUM)**

**Mitigations**:
- Scope narrowing invariant: `child.scopes SUBSET_OF parent.scopes` — enforced by attestation-service at delegation creation time (server-side, not client-side)
- Delegation creation requires parent's signature — compromised child cannot forge parent's signature
- Verification algorithm re-checks scope subset at every chain level
- Anomaly detection: alerts on delegation creation attempts that fail scope validation

**Detection**: Failed delegation creation logged in audit trail. Repeated failures trigger investigation.

---

### A3: Key Compromise Blast Radius

**Description**: An agent's Ed25519 signing key is compromised. Attacker can sign receipts as the compromised agent.

**Preconditions**: Key extracted from agent runtime (memory dump, insecure storage, dependency vulnerability).

**Attack Steps**:
1. Extract agent signing key from compromised container
2. Sign arbitrary action receipts as the compromised agent
3. Receipts are anchored in transparency log, appearing legitimate
4. Attacker operates within the agent's delegated scopes

**DREAD Score**: D=9, R=7, E=5, A=8, D=5 — **Total: 34/50 (HIGH)**

**Mitigations**:
- **Blast radius containment**: Agent can only sign within its delegated scopes (scope confinement)
- **Key rotation**: Automatic key rotation on schedule (configurable, default 90 days)
- **`compromised_at` timestamp**: Once set in trust-registry, all receipts signed after this timestamp are INVALID
- **Cascade revocation**: Revoking the compromised agent revokes all sub-delegations
- **HSM-backed keys**: For high-value agents, keys stored in KMS/HSM (never in memory)
- **Short-lived sessions**: Agent session tokens expire (default 1h), limiting window of exploitation

**Detection**: Anomaly detection on agent behavior (sudden scope usage changes, geographic anomalies, volume spikes). Transparency log monitors for receipts from agents with unusual patterns.

---

### A4: Malicious Issuer Signing False Data

**Description**: A compromised or malicious issuer in the trust-registry creates false attestations — e.g., attesting that a training dataset is unaltered when it has been poisoned.

**Preconditions**: Issuer has valid signing keys and trust-registry entry. Issuer is authorized to create the attestation type.

**Attack Steps**:
1. Malicious issuer receives a dataset for attestation
2. Instead of verifying integrity, issuer signs a false dataset attestation
3. Downstream consumers trust the attestation based on issuer's trust level
4. Poisoned data enters ML pipeline with valid provenance

**DREAD Score**: D=9, R=6, E=4, A=9, D=3 — **Total: 31/50 (HIGH)**

**Mitigations**:
- **Multi-witness verification**: High-value attestations require N-of-M independent issuers
- **Trust scoring**: Issuer reputation tracks historical accuracy; false attestations reduce trust score over time
- **Independent verification**: Verifiers can request re-attestation from different issuer
- **Issuer audit**: Periodic audit of issuer attestation patterns (random sampling + verification)
- **Revocation**: False attestations can be superseded with correction receipts
- **Liability**: Issuers sign legal agreements; false attestations have contractual consequences

**Detection**: Statistical anomaly on issuer's attestation patterns. Cross-reference with other issuers' attestations of the same data.

---

### A5: Collusion to Bypass Multi-Witness

**Description**: Multiple issuers coordinate to produce apparently independent attestations that are actually pre-arranged, defeating the multi-witness trust requirement.

**Preconditions**: Two or more issuers willing to collude. Multi-witness is required (e.g., 3-of-5 threshold).

**Attack Steps**:
1. Colluding issuers agree to attest a false claim
2. Each issuer independently signs the same false attestation
3. System sees 3 independent witnesses and marks claim as high-trust
4. False claim propagated as verified truth

**DREAD Score**: D=9, R=3, E=2, A=9, D=2 — **Total: 25/50 (MEDIUM)**

**Mitigations**:
- **Witness independence requirement**: Witnesses must be from different trust domains (different organizations, different jurisdictions)
- **Witness diversity scoring**: Trust bonus reduced if witnesses share organizational affiliation
- **Temporal distribution**: Witnesses should attest at different times (simultaneous attestation is suspicious)
- **Witness selection**: For critical operations, platform selects witnesses randomly (issuers cannot self-select)
- **Collusion detection**: Graph analysis of witness co-occurrence patterns across attestations
- **Economic incentives**: Witnesses stake reputation; discovered collusion results in permanent trust revocation

**Detection**: Co-occurrence analysis — if the same set of witnesses always appear together, flag for review. Timestamp clustering analysis.

---

### A6: Receipt Chain Tampering

**Description**: Attacker attempts to insert, remove, or reorder receipts in a receipt chain (linked via `previous_receipt_id`).

**Preconditions**: Attacker has access to receipt storage or can intercept receipt delivery.

**Attack Steps**:
1. Remove an incriminating receipt from the chain
2. Re-link the previous receipt to the next one (requires forging a receipt)
3. Or: insert a fabricated receipt between two legitimate ones

**DREAD Score**: D=8, R=2, E=1, A=7, D=3 — **Total: 21/50 (MEDIUM)**

**Mitigations**:
- **Cryptographic chaining**: Each receipt's `previous_receipt_id` is included in the signed payload — changing it invalidates the signature
- **Transparency log anchoring**: Every receipt is anchored in the Merkle tree — removing a receipt creates a gap in the log
- **Fork detection**: Two receipts with the same `previous_receipt_id` = detected fork (immediate alert)
- **Offline bundles**: Include full chain for independent verification
- **Immutable storage**: Receipt storage is append-only; deletions require admin ceremony with audit trail

**Detection**: Chain verification during any receipt validation. Log consistency checks detect gaps or forks.

---

### A7: Transparency Log Equivocation (Split-View)

**Description**: The transparency log operator presents different views of the log to different verifiers — showing some receipts to one party and different receipts to another.

**Preconditions**: Compromised or malicious log operator. Multiple verifiers that don't cross-check.

**Attack Steps**:
1. Log operator maintains two versions of the Merkle tree
2. Presents tree A to Verifier 1 (includes receipt X)
3. Presents tree B to Verifier 2 (excludes receipt X)
4. Neither verifier detects the inconsistency alone

**DREAD Score**: D=9, R=3, E=2, A=9, D=2 — **Total: 25/50 (MEDIUM)**

**Mitigations**:
- **Signed Tree Heads (STH)**: Log publishes signed tree head at regular intervals
- **Gossip protocol**: Verifiers share STHs with each other; inconsistent STHs = detected equivocation
- **Monitor nodes**: Independent monitors continuously verify log consistency
- **Append-only proof**: Each new STH must be a strict extension of the previous one (verifiable via consistency proof)
- **Multiple logs**: Critical receipts can be anchored in multiple independent logs

**Detection**: STH gossip detects split views. Monitor nodes alert on consistency proof failures.

---

### A8: Agent Identity Theft

**Description**: Attacker steals an agent's complete identity (signing key + delegation chain) and impersonates the agent.

**Preconditions**: Access to agent's key material (insecure storage, memory dump, backup exposure).

**Attack Steps**:
1. Extract agent signing key and delegation chain from compromised system
2. Create a rogue agent instance with stolen identity
3. Sign actions as the legitimate agent
4. Actions appear legitimate to all verifiers

**DREAD Score**: D=9, R=6, E=5, A=7, D=5 — **Total: 32/50 (HIGH)**

**Mitigations**:
- **Key storage**: Keys in KMS/HSM, never in plaintext on disk
- **Key attestation**: Platform can verify key is stored in secure hardware (TPM attestation)
- **IP/network binding**: Optional — bind agent sessions to specific network ranges
- **Behavioral fingerprinting**: Detect anomalous behavior patterns (different request patterns, timing, geolocation)
- **Rapid revocation**: `compromised_at` timestamp immediately invalidates all post-compromise receipts
- **Re-keying**: New key generation ceremony after compromise; old key permanently revoked

**Detection**: Concurrent usage from different networks. Behavioral anomaly detection. User-reported suspicious activity.

---

### A9: Delegation Depth Bypass

**Description**: Attacker attempts to create delegation chains deeper than `MAIP_MAX_DEPTH = 8`.

**Preconditions**: Compromised agent at any level of the chain.

**Attack Steps**:
1. Agent at depth 7 creates a sub-delegation (depth 8 — the max)
2. Agent at depth 8 attempts to create another sub-delegation (depth 9)
3. If enforcement is client-side only, the bypass succeeds

**DREAD Score**: D=6, R=3, E=2, A=5, D=3 — **Total: 19/50 (LOW)**

**Mitigations**:
- **Server-side enforcement**: attestation-service rejects delegation creation when `depth >= MAIP_MAX_DEPTH`
- **Chain verification**: Every verification walks the chain and checks depth at each level
- **Depth included in signed payload**: Cannot be modified without invalidating the signature
- **Offline bundles**: Include depth verification in bundle validation

**Detection**: Rejected delegation attempts logged with full context. Pattern of depth-limit attempts triggers investigation.

---

### A10: Time-Based Attacks

**Description**: Attacker exploits clock skew between services or uses expired/not-yet-valid tokens.

**Preconditions**: Clock skew between signing and verification systems. Or: intercepted tokens with manipulated timestamps.

**Attack Steps**:
1. Capture a receipt that has expired (`expires_at` in the past)
2. Present it to a verifier whose clock is behind (still shows as valid)
3. Or: create a receipt with `iat` far in the future, making it appear "fresh" indefinitely

**DREAD Score**: D=5, R=6, E=5, A=4, D=5 — **Total: 25/50 (MEDIUM)**

**Mitigations**:
- **Clock tolerance**: 30-second tolerance for clock skew (`MAIP_CLOCK_TOLERANCE = 30s`)
- **NTP synchronization**: All services MUST synchronize to trusted NTP sources
- **Timestamp in signed payload**: Cannot be modified without invalidating signature
- **Future `iat` rejection**: Receipts with `iat > now + CLOCK_TOLERANCE` are rejected
- **Expired receipt rejection**: Receipts with `expires_at < now - CLOCK_TOLERANCE` are rejected
- **Transparency log timestamp**: Log server adds its own timestamp; deviation from receipt timestamp > tolerance triggers alert

**Detection**: Clock drift monitoring on all services. Timestamp deviation alerts between receipt `iat` and log anchor time.

---

### A11: Denial of Service Against Verification

**Description**: Attacker floods verification endpoints to prevent legitimate receipt verification, potentially allowing unauthorized actions to proceed unchecked.

**Preconditions**: Network access to verification endpoints. High request volume capability.

**Attack Steps**:
1. Flood `/api/v1/verify` with verification requests
2. Legitimate verifications time out or fail
3. Systems configured to "fail open" allow unverified actions
4. Or: systems "fail closed" halt all operations (business disruption)

**DREAD Score**: D=7, R=8, E=7, A=8, D=7 — **Total: 37/50 (HIGH)**

**Mitigations**:
- **Rate limiting**: Per-IP and per-tenant rate limits on verification endpoints
- **Offline verification**: MaipBundle enables verification without server calls
- **Fail-closed default**: Systems MUST fail closed (reject unverified actions)
- **CDN/WAF**: Verification endpoints behind CDN with DDoS protection
- **Cached verification**: Recently verified receipts cached (configurable TTL)
- **Geographic distribution**: Verification endpoints in multiple regions
- **Circuit breaker**: Automatic fallback to offline bundle verification during outages

**Detection**: Rate limit alerts. Latency spike monitoring. Automated scaling triggers.

---

### A12: Training Data Poisoning with Valid Attestations

**Description**: Attacker poisons training data while ensuring all attestations remain technically valid — the data has correct hashes but contains malicious content.

**Preconditions**: Access to inject data at any point in the ML pipeline. Valid agent identity for creating attestations.

**Attack Steps**:
1. Inject poisoned samples into training dataset
2. Create valid dataset attestation (hash of poisoned data matches)
3. Model trained on poisoned data produces biased/malicious outputs
4. All receipts in the pipeline are cryptographically valid

**DREAD Score**: D=9, R=5, E=4, A=9, D=3 — **Total: 30/50 (HIGH)**

**Mitigations**:
- **MAIP scope**: MAIP proves integrity (data hasn't changed since attestation), NOT correctness (data is truthful/accurate)
- **Truth claims**: Separate `truth.claim` receipts assert data quality (requires domain expertise)
- **Multi-source verification**: Cross-reference data against multiple independent sources
- **Data quality gates**: Automated checks (statistical distribution, anomaly detection) before attestation
- **Human review**: High-risk datasets require human sign-off (`approval_receipt`)
- **Lineage tracing**: Full provenance chain enables post-incident investigation

**Detection**: Model performance drift triggers lineage investigation. Statistical anomaly in data distribution.

---

### A13: Model Output Manipulation Before Receipt

**Description**: Attacker modifies model outputs after inference but before the action receipt is generated, so the receipt covers tampered outputs.

**Preconditions**: Compromised inference pipeline between model output and receipt generation.

**Attack Steps**:
1. Model produces legitimate output O
2. Attacker intercepts O and replaces with O' (modified)
3. Receipt generated with `outputs_hash = SHA-256(O')`
4. Receipt is technically valid but covers tampered data

**DREAD Score**: D=8, R=4, E=4, A=7, D=3 — **Total: 26/50 (MEDIUM)**

**Mitigations**:
- **Minimal gap**: Receipt generation should be as close to model output as possible (same process, same memory space)
- **MAIP middleware**: SDK generates receipt atomically with output capture (< 5ms overhead)
- **Trusted execution**: For high-value inference, use TEE (Trusted Execution Environment) to protect the output-to-receipt pipeline
- **Multi-witness**: Independent inference replicas produce separate receipts; divergence = detected tampering
- **Output verification**: Downstream consumers can re-run inference and compare hashes

**Detection**: Multi-witness disagreement. Reproducibility checks on sampled outputs.

---

### A14: Cross-Tenant Data Exfiltration via Delegation

**Description**: An agent with cross-tenant delegation uses its access to exfiltrate data from the target tenant.

**Preconditions**: Valid cross-tenant delegation between Tenant A and Tenant B. Compromised or malicious agent.

**Attack Steps**:
1. Agent in Tenant A has cross-tenant delegation to Tenant B with `data.read` scope
2. Agent reads sensitive data from Tenant B
3. Agent stores/transmits data outside of authorized channels
4. All actions produce valid receipts (technically within scope)

**DREAD Score**: D=8, R=5, E=4, A=6, D=4 — **Total: 27/50 (MEDIUM)**

**Mitigations**:
- **Strict cross-tenant limits**: Max depth 3 (vs. 8 for same-tenant); stricter scope requirements
- **Bilateral approval**: Both tenants must approve cross-tenant delegation
- **Data classification**: Cross-tenant agents can only access data explicitly marked for cross-tenant sharing
- **Audit visibility**: All cross-tenant actions visible in both tenants' audit logs
- **Volume limits**: Rate limiting on cross-tenant data access (configurable per delegation)
- **Time-bound**: Cross-tenant delegations have mandatory short TTL (max 24h, renewable)
- **Purpose binding**: Cross-tenant delegation requires explicit purpose declaration

**Detection**: Volume anomaly on cross-tenant data access. Unusual access patterns. Real-time audit stream to both tenant admins.

---

### A15: Kill-Switch Bypass or Unauthorized Revocation

**Description**: (a) Bypassing the kill switch to keep a revoked agent operating, or (b) Unauthorized triggering of kill switch to disable a legitimate agent.

**Preconditions**: (a) Compromised verification cache or offline-only verifier. (b) Unauthorized access to admin controls.

**Attack Steps (bypass)**:
1. Admin triggers kill switch on compromised agent
2. Agent operates in offline mode with cached delegation chain
3. Agent continues signing receipts (valid signatures but revoked identity)
4. Verifiers relying on cached state accept the receipts

**Attack Steps (unauthorized revocation)**:
1. Attacker gains admin-level access (or exploits admin API)
2. Triggers kill switch on legitimate high-value agent
3. All sub-delegations cascade-revoked — business disruption
4. Recovery requires new identity creation and re-delegation

**DREAD Score**: D=8, R=4, E=3, A=7, D=4 — **Total: 26/50 (MEDIUM)**

**Mitigations**:
- **Bundle freshness**: Offline bundles include `bundle_generated_at`; verifiers enforce max staleness (configurable, default 1h)
- **Revocation push**: Kill switch publishes to all known verifiers via webhook/event bus
- **Multi-admin approval**: Kill switch requires M-of-N admin approval for high-value agents
- **Kill switch receipt**: Every kill switch action produces a tamper-evident receipt (who, when, why)
- **No re-activation**: Killed identities are permanently revoked (prevents unauthorized reactivation)
- **Rate limiting**: Admin APIs rate-limited; anomalous revocation volume triggers alert
- **Separation of duties**: Kill switch and delegation creation require different admin roles

**Detection**: Kill switch audit trail. Anomalous revocation patterns. Alert on agent operating after revocation.

---

## 4. Security Properties

### 4.1 Non-Repudiation
**Definition**: An agent that signed a receipt cannot later deny having performed the action.

**Formal statement**: For any valid receipt R signed by agent A with key K, if `Verify(K_pub, R) = true` and K has not been reported compromised before R.timestamp, then A performed the action described in R.

**Implementation**: Ed25519 signatures over JCS-canonicalized payloads. Transparency log anchoring provides third-party proof of existence. Receipt includes agent_id, timestamp, and delegation chain hash.

### 4.2 Tamper Evidence
**Definition**: Any modification to a receipt after signing is detectable.

**Formal statement**: For any receipt R, if any byte of R is modified to produce R', then `Verify(K_pub, R') = false` with overwhelming probability (2^-128).

**Implementation**: Ed25519 signature covers the entire canonical receipt payload. Merkle inclusion proof ties the receipt to a specific tree state. Chain linkage (`previous_receipt_id`) detects insertion/deletion.

### 4.3 Historical Integrity
**Definition**: Receipts signed before a key compromise remain valid as historical records.

**Formal statement**: For receipt R signed at time T by key K, if `compromised_at(K) > T`, then R is valid. If `compromised_at(K) <= T`, then R is invalid.

**Implementation**: `compromised_at` timestamp in trust-registry. Verification algorithm checks: `receipt.timestamp < key.compromised_at OR key.compromised_at IS NULL`.

### 4.4 Scope Confinement
**Definition**: An agent cannot perform actions outside its delegated scopes.

**Formal statement**: For any action receipt R by agent A, `R.scopes SUBSET_OF delegation(A).scopes`. This is enforced at receipt creation (server-side) and re-verified at verification time.

**Implementation**: attestation-service validates scope subset at delegation creation and receipt creation. Verification algorithm re-checks at every chain level.

### 4.5 Delegation Monotonicity
**Definition**: Trust and scopes can only narrow (never expand) through the delegation chain.

**Formal statement**: For delegation chain D0 → D1 → ... → Dn: `D(i+1).scopes SUBSET_OF D(i).scopes` and `trust(D(i+1)) <= trust(D(i))` for all i.

**Implementation**: Enforced at every delegation creation. Trust score decays: `trust *= 0.9^depth`. Scopes strictly narrow at each level.

---

## 5. Cryptographic Assumptions

| Primitive | Algorithm | Security Level | Usage |
|-----------|-----------|---------------|-------|
| Signatures | Ed25519 | 128-bit | Receipt signing, delegation signing |
| Hashing | SHA-256 | 128-bit | Content hashing, Merkle trees |
| Canonicalization | JCS (RFC 8785) | N/A | Deterministic serialization before signing |
| Merkle Trees | Binary hash tree | 128-bit | Transparency log inclusion proofs |
| Key Derivation | N/A | N/A | Keys generated directly (no KDF) |

**Assumptions**:
1. Ed25519 is existentially unforgeable under chosen-message attack (EU-CMA)
2. SHA-256 is collision-resistant and pre-image resistant
3. JCS produces deterministic, unique canonical forms for all valid JSON
4. The discrete logarithm problem on Curve25519 is intractable
5. All timestamps are UTC; clocks synchronized within 30 seconds via NTP
6. Random number generators used for key generation are cryptographically secure

**Non-assumptions** (MAIP does NOT rely on):
- Secrecy of receipt contents (receipts may be public)
- Availability of verification servers (offline verification via bundles)
- Honesty of any single issuer (multi-witness mitigates)
- Correctness of attested data (MAIP proves integrity, not truth)

---

## 6. Failure Modes

### F1: Signing Service Unavailability

**Symptoms**: Receipt creation requests fail. Agents cannot sign actions. Delegation creation blocked.

**Detection**: Health check failures on signing-service. Latency spike > 5s. Error rate > 1%.

**Containment**: Circuit breaker activates. Queued receipt requests buffered (max 1000, max 60s). No fallback to unsigned receipts — fail closed.

**Recovery**: Auto-restart via ECS health checks. If persistent: failover to standby signing-service. Key material in KMS survives service restart. Buffered requests processed on recovery.

**RTO**: 30 seconds (auto-restart), 5 minutes (failover). **RPO**: Zero (no data loss — requests buffered).

---

### F2: Transparency Log Inconsistency

**Symptoms**: Merkle proof verification failures. Inconsistent tree heads between monitors. Gap in leaf sequence.

**Detection**: Monitor nodes detect inconsistent STH. Verification failures spike. Log health check includes consistency proof.

**Containment**: CRITICAL — immediately halt all new receipt anchoring. Flag all receipts anchored during inconsistency window for re-verification.

**Recovery**: Root cause analysis required before resumption. If data corruption: restore from latest consistent snapshot + replay. If Byzantine fault: switch to backup log. Re-anchor flagged receipts in restored log.

**RTO**: Manual — requires human investigation. **RPO**: Latest consistent tree head.

---

### F3: Trust Registry Data Corruption

**Symptoms**: Incorrect trust levels returned. Issuer keys don't match. Agent identities missing or duplicated.

**Detection**: Integrity checks on trust-registry queries (signatures on registry entries). Cross-reference with transparency log anchors. Periodic full-table checksum.

**Containment**: Switch to read-only mode. Serve from last known good backup. Reject all new registrations/delegations until resolved.

**Recovery**: Restore from backup. Replay all registry changes from transparency log (log is the source of truth for all state transitions). Verify restored state against log.

**RTO**: 15 minutes (backup restore). **RPO**: Latest transparency log anchor.

---

### F4: Network Partition Between Services

**Symptoms**: Timeouts between internal services. Partial failures in receipt creation (e.g., signed but not anchored). Inconsistent state across services.

**Detection**: Service mesh health checks. Cross-service latency monitoring. Partition detection via gossip.

**Containment**: Each service operates independently within its capability. signing-service can still sign. transparency-log can still accept entries. Receipts created during partition are flagged as "pending anchoring."

**Recovery**: On partition heal: reconcile pending operations. Anchor un-anchored receipts. Verify consistency across all services. No receipts lost — only delayed anchoring.

**RTO**: Automatic on partition heal. **RPO**: Zero (operations buffered).

---

### F5: Clock Drift Exceeding Tolerance

**Symptoms**: Receipt timestamps inconsistent with transparency log timestamps. Verification failures due to expired/not-yet-valid receipts. Cross-service timestamp mismatches.

**Detection**: NTP monitoring on all hosts. Timestamp delta monitoring between services. Alert on drift > 15s (warning) or > 30s (critical).

**Containment**: Service with drifted clock taken out of rotation. NTP force-sync. Receipts created during drift window flagged for review.

**Recovery**: NTP resync. Review flagged receipts — those within drift window are valid (tolerance is 30s). Services re-added to rotation after clock verified.

**RTO**: 2 minutes (NTP resync). **RPO**: Zero (receipts valid within tolerance).

---

## 7. Mitigations Matrix

Threat Actor × Attack Scenario mapping. **L**=Likelihood, **I**=Impact, **M**=Primary Mitigation.

| Scenario | T1 External | T2 Compromised Agent | T3 Malicious Insider | T4 Compromised Issuer | T5 Colluding | T6 State-Level | T7 Supply Chain |
|----------|-------------|---------------------|---------------------|----------------------|-------------|---------------|----------------|
| **A1** Replay | L:H I:M — Audience binding | L:M I:M — Nonce + TTL | L:L I:M — Audit logs | L:L I:H — Multi-witness | L:L I:M — Purpose field | L:M I:H — Multi-log | L:L I:M — Signature check |
| **A2** Scope Escalation | L:L I:H — Auth required | L:H I:H — Server-side enforcement | L:M I:H — Separation of duties | L:L I:C — Trust revocation | L:L I:H — Chain verification | L:L I:H — Offline verification | L:M I:H — Code review |
| **A3** Key Compromise | L:M I:H — Key rotation | L:H I:H — HSM keys | L:M I:H — Access controls | L:M I:C — Multi-key ceremony | L:L I:C — Independent keys | L:H I:C — HSM + multi-party | L:H I:C — Supply chain security |
| **A4** False Attestation | L:L I:H — Auth required | L:M I:H — Scope limits | L:M I:C — Multi-witness | L:H I:C — Multi-witness + audit | L:H I:C — Witness diversity | L:M I:C — Foundation governance | L:M I:H — Code signing |
| **A5** Witness Collusion | L:L I:H — N/A (no access) | L:L I:H — Scope limits | L:M I:C — Diversity requirements | L:M I:C — Random selection | L:H I:C — Graph analysis | L:H I:C — Jurisdictional diversity | L:L I:H — N/A |
| **A6** Chain Tamper | L:M I:H — Crypto chaining | L:M I:H — Log anchoring | L:L I:H — Immutable storage | L:L I:H — Fork detection | L:L I:H — Multi-log | L:M I:H — Gossip protocol | L:M I:H — Integrity checks |
| **A7** Log Equivocation | L:L I:C — STH gossip | L:L I:C — Monitor nodes | L:M I:C — Separation of duties | L:L I:C — Multi-log | L:M I:C — Cross-org monitors | L:H I:C — Foundation-operated | L:L I:C — Code audit |
| **A8** Identity Theft | L:M I:H — Network auth | L:H I:H — Runtime protection | L:M I:H — Access controls | L:L I:C — Multi-factor | L:L I:H — Behavioral analysis | L:H I:C — HSM + attestation | L:H I:C — Dependency scanning |
| **A9** Depth Bypass | L:L I:M — API validation | L:M I:M — Server enforcement | L:L I:M — Code review | L:L I:M — Chain verification | L:L I:M — N/A | L:L I:M — Protocol spec | L:M I:M — Code integrity |
| **A10** Time Attack | L:M I:M — NTP + tolerance | L:M I:M — Log timestamps | L:L I:M — Monitoring | L:L I:M — STH timestamps | L:L I:M — Multi-log timestamps | L:M I:H — Multi-source time | L:L I:M — NTP hardening |
| **A11** DoS | L:H I:H — Rate limiting + CDN | L:M I:M — Scope-based quotas | L:L I:H — Internal limits | L:L I:M — N/A | L:L I:H — N/A | L:H I:H — Geographic distribution | L:L I:M — N/A |
| **A12** Data Poisoning | L:L I:C — Auth required | L:H I:C — Quality gates | L:H I:C — Human review | L:M I:C — Multi-witness | L:H I:C — Multi-source verify | L:M I:C — Audit + review | L:H I:C — Provenance chain |
| **A13** Output Tamper | L:L I:H — N/A (no access) | L:H I:H — Atomic receipt | L:M I:H — TEE | L:L I:H — Multi-witness | L:M I:H — Reproducibility | L:M I:H — TEE + multi-witness | L:H I:H — Code signing |
| **A14** Cross-Tenant Exfil | L:L I:H — Auth required | L:M I:H — Scope + volume limits | L:H I:C — Bilateral approval | L:L I:H — Scope confinement | L:H I:C — Audit + time-bound | L:M I:C — Data classification | L:L I:H — N/A |
| **A15** Kill-Switch Abuse | L:L I:H — Auth required | L:M I:H — Freshness checks | L:H I:H — Multi-admin approval | L:L I:H — Separation of duties | L:M I:H — M-of-N approval | L:M I:C — Foundation oversight | L:M I:H — Code integrity |

---

## 8. Anti-Replay Mechanisms

MAIP employs six layered anti-replay defenses:

### 8.1 Audience Binding
```json
"audience": "verifier.example.com"
```
Receipt is bound to a specific verifier. Verifiers MUST reject receipts not addressed to them. **Required** for: financial receipts, compliance attestations. **Optional** for: general action receipts.

### 8.2 Purpose Declaration
```json
"purpose": "kyc_document_verification"
```
Receipt tagged with intended use case. Prevents repurposing of receipts across different workflows. Verifiers SHOULD reject receipts with mismatched purpose.

### 8.3 Nonce Requirement
```json
"nonce": "a3f8b2c1d4e5f6071829304a5b6c7d8e"
```
32-byte random hex string. Prevents exact replay even if all other fields match. **Required** for: financial/compliance/high-value receipts. Nonce uniqueness enforced within 24h sliding window.

### 8.4 TTL / Expiry
```json
"expires_at": "2026-04-07T12:00:00Z"
```
All receipts SHOULD have an expiry. Defaults: action receipts = 24h, attestations = 1y, delegations = configurable (max 1y). Verifiers MUST reject expired receipts (with 30s clock tolerance).

### 8.5 Delegation Chain Hash Binding
```json
"delegation_chain_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
```
SHA-256 hash of the JCS-canonicalized delegation chain. Binds receipt to a specific authority path. If any delegation in the chain is modified or revoked, the hash no longer matches.

### 8.6 Receipt Chaining
```json
"previous_receipt_id": "01HWXYZ..."
```
Each receipt references its predecessor. Creates an append-only chain. Fork detection: two receipts with same `previous_receipt_id` = immediate alert. First receipt in chain has `previous_receipt_id: null`.

---

## 9. Compromise Recovery Procedures

### 9.1 Key Rotation Ceremony

**Trigger**: Suspected or confirmed key compromise. Scheduled rotation (every 90 days).

**Steps**:
1. Generate new Ed25519 keypair (in KMS/HSM)
2. Create key rotation attestation signed by OLD key (proves continuity)
3. Update trust-registry with new public key
4. Anchor key rotation in transparency log
5. If compromise: set `compromised_at` timestamp on old key
6. Propagate new key to all verification endpoints
7. Generate incident receipt documenting the rotation

**Timeline**: Emergency rotation < 15 minutes. Scheduled rotation < 1 hour.

### 9.2 Receipt Invalidation After Compromise

**Rule**: All receipts signed by the compromised key AFTER `compromised_at` are INVALID. Receipts signed BEFORE `compromised_at` remain VALID (historical integrity).

**Implementation**: Verification algorithm checks: `receipt.timestamp < key.compromised_at`. Trust-registry is authoritative for `compromised_at` values.

### 9.3 Cascade Revocation

**Process**:
1. Mark compromised agent/issuer in trust-registry
2. Enumerate all delegations rooted at the compromised entity
3. Mark all sub-delegations as revoked (cascade)
4. Publish revocation events to event bus
5. All verifiers notified via webhook
6. Offline bundles older than 1h considered stale (must re-fetch)

**Blast radius calculation**: `affected_entities = count(all descendants in delegation tree)`

### 9.4 Incident Receipt Generation

Every compromise event MUST produce a tamper-evident incident receipt:
```json
{
  "receipt_type": "agent.revocation",
  "payload": {
    "reason": "key_compromise",
    "compromised_entity_id": "maip:abc12345:01HWXYZ...",
    "compromised_at": "2026-04-06T14:30:00Z",
    "discovered_at": "2026-04-06T15:00:00Z",
    "affected_delegations": 42,
    "affected_receipts_post_compromise": 7,
    "incident_commander": "admin@example.com",
    "recovery_actions": ["key_rotation", "cascade_revocation", "re-delegation"]
  }
}
```

### 9.5 Post-Incident Audit

1. Identify all receipts signed between `compromised_at` and `discovered_at`
2. Flag these receipts as "signed during compromise window"
3. Notify all verifiers who accepted these receipts
4. Downstream consumers must re-verify or reject flagged receipts
5. Generate post-incident report with full timeline and blast radius
6. Update threat model if new attack vector discovered

---

## 10. STRIDE Analysis

### Component: signing-service

| Threat | Applicable | Mitigation |
|--------|-----------|-----------|
| **S**poofing | Yes — fake signing requests | mTLS between services, request authentication |
| **T**ampering | Yes — modified sign requests | Request signing, input validation |
| **R**epudiation | Yes — deny signing action | All sign operations logged with caller identity |
| **I**nformation Disclosure | Yes — key material exposure | Keys in KMS/HSM, never in memory longer than needed |
| **D**enial of Service | Yes — flood sign requests | Rate limiting, circuit breaker, queue management |
| **E**levation of Privilege | Yes — sign with wrong key | Key selection based on authenticated caller, scope validation |

### Component: attestation-service

| Threat | Applicable | Mitigation |
|--------|-----------|-----------|
| **S**poofing | Yes — fake attestation requests | JWT auth, tenant isolation via RLS |
| **T**ampering | Yes — modify attestation in transit | TLS + signed payloads |
| **R**epudiation | Yes — deny creating attestation | Audit trail + transparency log anchoring |
| **I**nformation Disclosure | Yes — attestation contents | RLS, tenant-scoped access, encryption at rest |
| **D**enial of Service | Yes — flood attestation creation | Rate limiting per tenant, queue management |
| **E**levation of Privilege | Yes — create attestation for other tenant | RLS enforcement, tenant_id from JWT (not request body) |

### Component: transparency-log

| Threat | Applicable | Mitigation |
|--------|-----------|-----------|
| **S**poofing | Yes — fake log entries | Only attestation-service can submit (mTLS) |
| **T**ampering | Yes — modify/delete entries | Append-only Merkle tree, STH signing |
| **R**epudiation | Yes — deny log entry | STH published and gossiped, monitor nodes |
| **I**nformation Disclosure | Low — log entries are semi-public | Access control on queries, tenant filtering |
| **D**enial of Service | Yes — flood submissions | Rate limiting, priority queue for critical entries |
| **E**levation of Privilege | Yes — bypass append-only constraint | Cryptographic enforcement (tree can only grow) |

### Component: trust-registry

| Threat | Applicable | Mitigation |
|--------|-----------|-----------|
| **S**poofing | Yes — fake registry updates | Admin authentication, multi-party approval for critical changes |
| **T**ampering | Yes — modify trust levels | All changes anchored in transparency log, audit trail |
| **R**epudiation | Yes — deny registry change | Full audit trail with admin identity |
| **I**nformation Disclosure | Yes — issuer metadata, trust scores | Tenant-scoped access, public keys are intentionally public |
| **D**enial of Service | Yes — flood lookups | Caching, CDN for public key distribution |
| **E**levation of Privilege | Yes — promote trust level without authorization | Multi-admin approval for trust level changes |

### Component: machine-identity-service

| Threat | Applicable | Mitigation |
|--------|-----------|-----------|
| **S**poofing | Yes — register fake agents | Tenant authentication, KYC/KYB for issuers |
| **T**ampering | Yes — modify agent metadata | Signed agent identities, transparency log anchoring |
| **R**epudiation | Yes — deny agent actions | Action receipts with cryptographic non-repudiation |
| **I**nformation Disclosure | Yes — agent capabilities, delegation chains | RLS, tenant-scoped access |
| **D**enial of Service | Yes — mass agent registration | Rate limiting, billing entitlements |
| **E**levation of Privilege | Yes — scope escalation via delegation | Server-side scope validation, chain verification |

---

## 11. Compliance Alignment

### SOC 2 Type II
| Trust Service Criteria | MAIP Coverage |
|----------------------|--------------|
| CC6.1 — Logical access controls | Agent scopes, delegation chains, scope confinement |
| CC6.2 — Access authentication | Ed25519 signatures, delegation chain verification |
| CC6.3 — Access authorization | Capability-based scopes, server-side enforcement |
| CC7.1 — System monitoring | Transparency log, audit trail, anomaly detection |
| CC7.2 — Incident management | Kill switch, cascade revocation, incident receipts |
| CC8.1 — Change management | Schema versioning, workflow versioning, delegation immutability |

### ISO 27001
| Control | MAIP Coverage |
|---------|--------------|
| A.9.1 — Access control policy | Scope-based access control via delegation |
| A.9.2 — User access management | Agent identity lifecycle, registration, revocation |
| A.10.1 — Cryptographic controls | Ed25519, SHA-256, JCS canonicalization |
| A.12.4 — Logging and monitoring | Transparency log, audit trail, receipt chaining |
| A.16.1 — Incident management | Kill switch, compromise recovery procedures |
| A.18.1 — Compliance with legal requirements | Compliance receipts, regulatory attestations |

### NIST 800-53
| Control Family | MAIP Coverage |
|---------------|--------------|
| AC — Access Control | Delegation chains, scope confinement, least privilege |
| AU — Audit and Accountability | Receipt chaining, transparency log, non-repudiation |
| IA — Identification and Authentication | Agent identity, Ed25519 key binding |
| SC — System and Communications Protection | TLS, signed payloads, JCS canonicalization |
| SI — System and Information Integrity | Tamper evidence, Merkle proofs, hash verification |
| IR — Incident Response | Kill switch, cascade revocation, incident receipts |

### GDPR Article 32
| Requirement | MAIP Coverage |
|-------------|--------------|
| Pseudonymization and encryption | Agent IDs are pseudonymous (ULID, not PII). Payloads hashed (no plaintext PII in receipts) |
| Confidentiality and integrity | Scope confinement, tamper-evident receipts |
| Availability and resilience | Offline verification bundles, geographic distribution |
| Regular testing and assessment | Threat model, STRIDE analysis, compliance receipts |

---

## 12. Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-04-06 | Truthlocks Security | Initial threat model |

---

*MAIP-SPEC-THREAT-001 | Apache 2.0 | github.com/truthlocksinc/maip*

# MAIP — Machine Agent Identity Protocol

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![CI](https://github.com/truthlocks/maip/actions/workflows/ci.yml/badge.svg)](https://github.com/truthlocks/maip/actions/workflows/ci.yml)

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

This repository includes a portable Go reference implementation of the MAIP protocol core. The library has zero proprietary dependencies — only the Go standard library, `crypto/ed25519`, and `github.com/oklog/ulid/v2`.

### Package: `github.com/truthlocks/maip/reference`

| File | Description |
|------|-------------|
| `agent.go` | Agent identity, Ed25519 key generation, ULID-based IDs, registry |
| `scope.go` | Scope model (`resource:action`), scope checking, built-in scopes |
| `session.go` | Session creation with TTL, scope narrowing, IP allowlist |
| `receipt.go` | Action receipt creation, Ed25519 signing, receipt chain verification |
| `trust.go` | Trust score computation (0.0-1.0 scale with weighted factors) |
| `delegation.go` | Cross-tenant delegation, depth limiting (max 3), scope intersection |
| `bundle.go` | Proof bundle creation and offline verification |
| `witness.go` | Witness request, attestation, consensus computation |

### Quick Start (Go Library)

```go
import maip "github.com/truthlocks/maip/reference"

// Register an agent
agent, _ := maip.NewAgentWithTenant("my-agent", maip.AgentTypeAutonomous,
    []string{"dataset:read", "receipt:create"}, "a1b2c3d4")

// Create a scoped session
session, _ := maip.CreateSession(agent,
    maip.WithSessionTTL(30*time.Minute),
    maip.WithSessionScopes([]string{"dataset:read"}),
    maip.WithIPAllowlist([]string{"10.0.0.0/8"}))

// Create a signed receipt
receipt, _ := maip.NewReceipt(maip.ReceiptTypeAction, agent,
    "ds_01HXYZ", "dataset", payload, "")

// Verify the receipt
err := maip.VerifyReceipt(receipt, agent.PublicKey)

// Compute trust score
score, _ := maip.ComputeTrustScore(agent.ID, maip.TrustFactors{
    BehavioralCompliance: 0.92,
    ScopeAdherence:       1.0,
    AnomalyScore:         0.85,
    PeerAttestations:     0.60,
    SessionHygiene:       0.95,
})
```

## MAIP Verifier CLI

A standalone CLI tool for offline verification of MAIP proof bundles.

### Install

```bash
go install github.com/truthlocks/maip/verifier@latest
```

Or build from source:

```bash
make build
# Binary at ./bin/maip-verifier
```

### Usage

```bash
# Verify a proof bundle (offline, no network calls)
maip-verifier verify bundle.json

# Print bundle metadata and contents
maip-verifier inspect bundle.json

# Print version
maip-verifier version
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Valid — bundle verified successfully |
| 1 | Expired — receipt or delegation has expired |
| 2 | Revoked — a delegation in the chain was revoked |
| 3 | Scope violation — agent used scopes not granted |
| 4 | Chain broken — delegation chain has gaps |
| 5 | Signature invalid — cryptographic signature check failed |
| 6 | Key mismatch — public key not found or doesn't match |
| 10 | Unknown error — parse failure or other error |

## Examples

### Register an Agent

```bash
cd examples/register-agent
go run .
```

Creates an agent, opens a scoped session, issues a signed receipt, and computes a trust score.

### Verify a Bundle

```bash
cd examples/verify-bundle
go run .
```

Creates a delegation chain, issues a receipt, assembles a proof bundle, and verifies it offline.

## Development

### Prerequisites

- Go 1.22+

### Build & Test

```bash
# Run all tests
make test

# Build the verifier CLI
make build

# Run linting
make lint

# Format code
make fmt

# Build release binaries for all platforms
make release
```

### Project Structure

```
maip/
  spec/             MAIP protocol specifications
  reference/        Go reference implementation (library)
  verifier/         MAIP Verifier CLI tool
  examples/
    register-agent/ Agent registration example
    verify-bundle/  Bundle verification example
  .github/
    workflows/
      ci.yml        CI pipeline (test + lint + build)
  Makefile          Build automation
```

## Truthlocks Platform

The production implementation is available as part of the [Truthlocks](https://truthlocks.com) platform:

- **API Documentation**: [docs.truthlocks.com/guides/machine-identity](https://docs.truthlocks.com/guides/machine-identity)
- **SDKs**: JavaScript, Go, Python (coming soon)
- **Console**: [console.truthlocks.com](https://console.truthlocks.com)

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.

---

Built by [Truthlocks](https://truthlocks.com) — Cryptographic Trust for the AI Era.

<p align="center">
  <a href="https://truthlocks.com">
    <img src="https://www.truthlocks.com/logo/logo-color-1.png" alt="Truthlocks" width="200" />
  </a>
</p>

<h1 align="center">Truthlock Go SDK</h1>

<p align="center">
  <strong>Official Go SDK for the Truthlocks Platform</strong>
</p>

<p align="center">
  <a href="https://pkg.go.dev/github.com/truthlocks/sdk-go"><img src="https://pkg.go.dev/badge/github.com/truthlocks/sdk-go.svg" alt="Go Reference" /></a>
  <a href="https://goreportcard.com/report/github.com/truthlocks/sdk-go"><img src="https://goreportcard.com/badge/github.com/truthlocks/sdk-go" alt="Go Report Card" /></a>
  <a href="https://github.com/truthlocks/sdk-go/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square" alt="License" /></a>
  <a href="https://docs.truthlocks.com/sdk/go"><img src="https://img.shields.io/badge/docs-truthlocks.com-brightgreen.svg?style=flat-square" alt="Documentation" /></a>
</p>

<p align="center">
  <a href="https://docs.truthlocks.com/sdk/go">Documentation</a> &bull;
  <a href="https://docs.truthlocks.com/api-reference">API Reference</a> &bull;
  <a href="https://github.com/truthlocks/sdk-go/issues">Issues</a>
</p>

---

Idiomatic Go client for the **Truthlocks** cryptographic trust infrastructure. Issue attestations, verify content authenticity, manage issuers and signing keys, and query the audit trail with a clean, context-aware API.

## Installation

```bash
go get github.com/truthlocks/sdk-go@latest
```

Requires **Go 1.22** or later.

## Quick Start

```go
package main

import (
    "context"
    "encoding/base64"
    "fmt"
    "log"

    truthlock "github.com/truthlocks/sdk-go"
)

func main() {
    client := truthlock.NewClient(truthlock.Config{
        BaseURL:  "https://api.truthlocks.com",
        TenantID: "your-tenant-id",
    })

    ctx := context.Background()

    // Create an issuer
    issuer, err := client.Issuers.Create(ctx, &truthlock.CreateIssuerRequest{
        Name:        "My Organization",
        LegalName:   "My Organization Inc.",
        DisplayName: "My Org",
    })
    if err != nil {
        log.Fatal(err)
    }

    // Trust the issuer
    if err := client.Issuers.Trust(ctx, issuer.ID); err != nil {
        log.Fatal(err)
    }

    // Register a signing key
    if err := client.Keys.Register(ctx, issuer.ID, &truthlock.RegisterKeyRequest{
        KID:            "key-1",
        Alg:            truthlock.AlgEd25519,
        PublicKeyB64URL: "your-public-key-base64url",
    }); err != nil {
        log.Fatal(err)
    }

    // Mint an attestation
    payload := base64.RawURLEncoding.EncodeToString([]byte("Hello World"))
    attestation, err := client.Attestations.Mint(ctx, &truthlock.MintRequest{
        IssuerID:      issuer.ID,
        KID:           "key-1",
        Alg:           truthlock.AlgEd25519,
        PayloadB64URL: payload,
    })
    if err != nil {
        log.Fatal(err)
    }

    fmt.Println("Attestation ID:", attestation.AttestationID)

    // Verify
    result, err := client.Verify.Online(ctx, &truthlock.VerifyRequest{
        AttestationID: attestation.AttestationID,
        PayloadB64URL: payload,
    })
    if err != nil {
        log.Fatal(err)
    }

    if result.Verdict == truthlock.VerdictValid {
        fmt.Println("Document verified successfully")
    }
}
```

## Features

| Feature           | Description                                                         |
| ----------------- | ------------------------------------------------------------------- |
| **Attestations**  | Mint, retrieve, list, and revoke cryptographic attestations         |
| **Verification**  | Online and offline verification with full verdict details           |
| **Issuers**       | Create, update, trust, and manage issuer identities                 |
| **Signing Keys**  | Register, rotate, and revoke Ed25519/ECDSA signing keys             |
| **Receipts**      | Issue, retrieve, and manage structured receipt types                |
| **Audit Trail**   | Query the tamper-evident audit log for any entity                   |
| **Context-aware** | All methods accept `context.Context` for cancellation and deadlines |
| **Error types**   | Structured error types with HTTP status codes and error codes       |

## API Resources

### Attestations

```go
// Mint
att, err := client.Attestations.Mint(ctx, &truthlock.MintRequest{...})

// Retrieve
att, err := client.Attestations.Get(ctx, "att_abc123")

// List
list, err := client.Attestations.List(ctx, &truthlock.ListParams{Limit: 20})

// Revoke
err := client.Attestations.Revoke(ctx, "att_abc123", "Key compromised")
```

### Verification

```go
// Online (checks revocation, expiry, and signature)
result, err := client.Verify.Online(ctx, &truthlock.VerifyRequest{...})

// Offline (signature + payload match only)
result, err := client.Verify.Offline(ctx, &truthlock.VerifyRequest{...})
```

### Issuers & Keys

```go
// Create issuer
issuer, err := client.Issuers.Create(ctx, &truthlock.CreateIssuerRequest{...})

// Register signing key
err := client.Keys.Register(ctx, issuerID, &truthlock.RegisterKeyRequest{...})

// Revoke key
err := client.Keys.Revoke(ctx, issuerID, "key-1")
```

## Error Handling

```go
result, err := client.Attestations.Get(ctx, "invalid-id")
if err != nil {
    var apiErr *truthlock.APIError
    if errors.As(err, &apiErr) {
        fmt.Printf("API error %d: %s (code: %s)\n",
            apiErr.Status, apiErr.Message, apiErr.Code)
    }
}
```

## Configuration

```go
client := truthlock.NewClient(truthlock.Config{
    BaseURL:    "https://api.truthlocks.com", // required
    TenantID:   "tnt_...",                     // tenant auth
    APIKey:     "tlk_live_...",                // or API key auth
    Timeout:    30 * time.Second,              // request timeout
    MaxRetries: 3,                             // retry on transient errors
    HTTPClient: &http.Client{},               // custom HTTP client
})
```

## Documentation

- [SDK Guide](https://docs.truthlocks.com/sdk/go)
- [API Reference](https://docs.truthlocks.com/api-reference)
- [pkg.go.dev Reference](https://pkg.go.dev/github.com/truthlocks/sdk-go)
- [Examples](https://github.com/truthlocks/sdk-go/tree/main/examples)

## License

MIT -- see [LICENSE](https://github.com/truthlocks/sdk-go/blob/main/LICENSE) for details.

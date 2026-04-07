# MAIP Go SDK

Go SDK for the **MAIP (Machine Agent Identity Protocol)**.

## Installation

```bash
go get github.com/truthlocks/maip/sdk/go
```

## Quick Start

```go
package main

import (
	"context"
	"fmt"
	"log"

	maip "github.com/truthlocks/maip/sdk/go"
)

func main() {
	client := maip.NewClient("your-api-key")
	// For self-hosted: maip.NewClient("...", maip.WithBaseURL("https://maip.your-company.com"))

	ctx := context.Background()

	// Register an agent
	agent, err := client.RegisterAgent(ctx, maip.CreateAgentRequest{
		Name:      "my-agent",
		Scope:     maip.Scope{Actions: []string{"read", "write"}, Resources: []string{"documents/*"}},
		PublicKey: "base64-encoded-public-key",
	})
	if err != nil {
		log.Fatal(err)
	}

	// Create a session
	ttl := 3600
	session, err := client.CreateSession(ctx, maip.CreateSessionRequest{
		AgentID:    agent.ID,
		TTLSeconds: &ttl,
	})
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("Session: %s\n", session.ID)

	// Get trust score
	trust, err := client.GetTrustScore(ctx, agent.ID)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("Trust level: %s, score: %.2f\n", trust.Level, trust.Score)

	// Check guardrails
	result, err := client.CheckGuardrails(ctx, maip.CheckGuardrailsRequest{
		AgentID:    agent.ID,
		Action:     "write",
		ResourceID: "documents/report.pdf",
	})
	if err != nil {
		log.Fatal(err)
	}
	if result.Allowed {
		fmt.Println("Action allowed")
	}
}
```

## Offline Bundle Verification

```go
result, err := maip.VerifyBundle(bundle)
if err != nil {
    log.Fatal(err)
}
if result.Valid {
    fmt.Printf("Verified %d receipts\n", result.ReceiptCount)
}
```

## API Reference

### `Client` Methods

| Method | Description |
|---|---|
| `RegisterAgent(ctx, req)` | Register a new agent identity |
| `ListAgents(ctx, opts)` | List agents with optional filters |
| `GetAgent(ctx, agentID)` | Get an agent by ID |
| `SuspendAgent(ctx, agentID)` | Suspend an active agent |
| `RevokeAgent(ctx, agentID)` | Permanently revoke an agent |
| `CreateSession(ctx, req)` | Create an authenticated session |
| `TerminateSession(ctx, sessionID)` | Terminate a session |
| `GetTrustScore(ctx, agentID)` | Get the current trust score |
| `ComputeTrustScore(ctx, req)` | Compute a fresh trust score |
| `OfferDelegation(ctx, req)` | Offer trust delegation |
| `AcceptDelegation(ctx, delegationID)` | Accept a delegation |
| `ExecuteOrchestration(ctx, req)` | Execute multi-agent orchestration |
| `CheckGuardrails(ctx, req)` | Check guardrails before an action |

### Client Options

| Option | Description |
|---|---|
| `WithBaseURL(url)` | Set custom base URL for self-hosted deployments |
| `WithTimeout(duration)` | Set HTTP request timeout |
| `WithHTTPClient(client)` | Use a custom `*http.Client` |

### Error Types

| Error | HTTP Status | Description |
|---|---|---|
| `*MaipError` | any | Base error type |
| `*UnauthorizedError` | 401 | Invalid or missing API key |
| `*NotFoundError` | 404 | Resource not found |
| `*LimitExceededError` | 429 | Rate limit or quota exceeded |
| `*VerificationError` | n/a | Bundle/receipt verification failed |

## License

Apache-2.0

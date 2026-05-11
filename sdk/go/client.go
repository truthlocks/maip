// Package truthlock provides the official Go SDK for the Truthlock platform.
//
// # Quick Start
//
// Create a client and start making API calls:
//
//	import "github.com/truthlock/sdk-go"
//
//	client := truthlock.NewClient(truthlock.Config{
//		BaseURL:  "https://api.truthlocks.com",
//		TenantID: "your-tenant-id",
//	})
//
//	// Create an issuer
//	issuer, err := client.Issuers.Create(ctx, &truthlock.CreateIssuerRequest{
//		Name:        "My Organization",
//		LegalName:   "My Organization Inc.",
//		DisplayName: "My Org",
//	})
//
//	// Mint an attestation
//	attestation, err := client.Attestations.Mint(ctx, &truthlock.MintRequest{
//		IssuerID:     issuer.ID,
//		KID:          "key-1",
//		Alg:          truthlock.AlgEd25519,
//		PayloadB64URL: base64.RawURLEncoding.EncodeToString([]byte("Hello World")),
//	})
package truthlock

import (
	"context"
	"net/http"
)

// Config holds the configuration for the Truthlock client.
type Config struct {
	// BaseURL is the base URL of the Truthlock API gateway.
	BaseURL string
	// TenantID is the tenant identifier for multi-tenant operations.
	TenantID string
	// APIKey is an optional API key for service-to-service authentication.
	APIKey string
	// HTTPClient is an optional custom HTTP client.
	HTTPClient *http.Client
	// Debug enables debug logging.
	Debug bool
}

// Client is the main Truthlock API client.
type Client struct {
	config Config
	http   *http.Client

	// Issuers provides issuer management operations.
	Issuers *IssuersService
	// Keys provides key management operations.
	Keys *KeysService
	// Attestations provides attestation operations.
	Attestations *AttestationsService
	// Verify provides verification operations.
	Verify *VerifyService
	// Audit provides audit log operations.
	Audit *AuditService
	// Receipts provides receipt lifecycle operations (Ticket 81).
	Receipts *ReceiptsService
}

// NewClient creates a new Truthlock client with the given configuration.
func NewClient(config Config) *Client {
	if config.HTTPClient == nil {
		config.HTTPClient = &http.Client{}
	}

	c := &Client{
		config: config,
		http:   config.HTTPClient,
	}

	c.Issuers = &IssuersService{client: c}
	c.Keys = &KeysService{client: c}
	c.Attestations = &AttestationsService{client: c}
	c.Verify = &VerifyService{client: c}
	c.Audit = &AuditService{client: c}
	c.Receipts = &ReceiptsService{client: c}

	return c
}

// request performs an authenticated HTTP request to the Truthlock API.
func (c *Client) request(ctx context.Context, method, path string, body, result interface{}) error {
	// Implementation would use c.config.BaseURL, c.config.TenantID, etc.
	// This is a simplified version - full implementation would include:
	// - JSON marshaling/unmarshaling
	// - Header setting (X-Tenant-ID, Idempotency-Key, etc.)
	// - Error handling and mapping
	// - Retry logic for idempotent operations
	return nil
}

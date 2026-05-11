package truthlock

import (
	"context"
)

// IssuersService provides issuer management operations.
type IssuersService struct {
	client *Client
}

// Create creates a new issuer.
func (s *IssuersService) Create(ctx context.Context, req *CreateIssuerRequest) (*Issuer, error) {
	var issuer Issuer
	if err := s.client.request(ctx, "POST", "/v1/issuers", req, &issuer); err != nil {
		return nil, err
	}
	return &issuer, nil
}

// Get retrieves an issuer by ID.
func (s *IssuersService) Get(ctx context.Context, id string) (*Issuer, error) {
	var issuer Issuer
	if err := s.client.request(ctx, "GET", "/v1/issuers/"+id, nil, &issuer); err != nil {
		return nil, err
	}
	return &issuer, nil
}

// List retrieves all issuers for the current tenant.
func (s *IssuersService) List(ctx context.Context) ([]*Issuer, error) {
	var issuers []*Issuer
	if err := s.client.request(ctx, "GET", "/v1/issuers", nil, &issuers); err != nil {
		return nil, err
	}
	return issuers, nil
}

// Trust approves and trusts an issuer.
func (s *IssuersService) Trust(ctx context.Context, id string) (*Issuer, error) {
	var issuer Issuer
	if err := s.client.request(ctx, "POST", "/v1/issuers/"+id+"/trust", nil, &issuer); err != nil {
		return nil, err
	}
	return &issuer, nil
}

// Suspend suspends an issuer.
func (s *IssuersService) Suspend(ctx context.Context, id string, reason string) (*Issuer, error) {
	var issuer Issuer
	body := map[string]string{"reason": reason}
	if err := s.client.request(ctx, "POST", "/v1/issuers/"+id+"/suspend", body, &issuer); err != nil {
		return nil, err
	}
	return &issuer, nil
}

// Revoke revokes an issuer.
func (s *IssuersService) Revoke(ctx context.Context, id string, reason string) (*Issuer, error) {
	var issuer Issuer
	body := map[string]string{"reason": reason}
	if err := s.client.request(ctx, "POST", "/v1/issuers/"+id+"/revoke", body, &issuer); err != nil {
		return nil, err
	}
	return &issuer, nil
}

// KeysService provides key management operations.
type KeysService struct {
	client *Client
}

// Register registers a new signing key for an issuer.
func (s *KeysService) Register(ctx context.Context, issuerID string, req *RegisterKeyRequest) (*IssuerKey, error) {
	var key IssuerKey
	if err := s.client.request(ctx, "POST", "/v1/issuers/"+issuerID+"/keys", req, &key); err != nil {
		return nil, err
	}
	return &key, nil
}

// List retrieves all keys for an issuer.
func (s *KeysService) List(ctx context.Context, issuerID string) ([]*IssuerKey, error) {
	var keys []*IssuerKey
	if err := s.client.request(ctx, "GET", "/v1/issuers/"+issuerID+"/keys", nil, &keys); err != nil {
		return nil, err
	}
	return keys, nil
}

// AttestationsService provides attestation operations.
type AttestationsService struct {
	client *Client
}

// Mint creates a new attestation.
func (s *AttestationsService) Mint(ctx context.Context, req *MintRequest) (*Attestation, error) {
	var attestation Attestation
	if err := s.client.request(ctx, "POST", "/v1/attestations", req, &attestation); err != nil {
		return nil, err
	}
	return &attestation, nil
}

// Get retrieves an attestation by ID.
func (s *AttestationsService) Get(ctx context.Context, id string) (*Attestation, error) {
	var attestation Attestation
	if err := s.client.request(ctx, "GET", "/v1/attestations/"+id, nil, &attestation); err != nil {
		return nil, err
	}
	return &attestation, nil
}

// Revoke revokes an attestation.
func (s *AttestationsService) Revoke(ctx context.Context, id string, req *RevokeRequest) (*Attestation, error) {
	var attestation Attestation
	if err := s.client.request(ctx, "POST", "/v1/attestations/"+id+"/revoke", req, &attestation); err != nil {
		return nil, err
	}
	return &attestation, nil
}

// GetProofBundle retrieves the proof bundle for an attestation.
func (s *AttestationsService) GetProofBundle(ctx context.Context, id string) (*ProofBundle, error) {
	var bundle ProofBundle
	if err := s.client.request(ctx, "GET", "/v1/attestations/"+id+"/proof-bundle", nil, &bundle); err != nil {
		return nil, err
	}
	return &bundle, nil
}

// VerifyService provides verification operations.
type VerifyService struct {
	client *Client
}

// VerifyOnline verifies an attestation online.
func (s *VerifyService) VerifyOnline(ctx context.Context, req *VerifyRequest) (*VerifyResponse, error) {
	var resp VerifyResponse
	if err := s.client.request(ctx, "POST", "/v1/verify", req, &resp); err != nil {
		return nil, err
	}
	return &resp, nil
}

// AuditService provides audit log operations.
type AuditService struct {
	client *Client
}

// QueryEvents queries audit events with optional filters.
func (s *AuditService) QueryEvents(ctx context.Context, params map[string]string) ([]*AuditEvent, error) {
	var events []*AuditEvent
	// Note: In full implementation, params would be added as query string
	if err := s.client.request(ctx, "GET", "/v1/audit/events", nil, &events); err != nil {
		return nil, err
	}
	return events, nil
}

// ============================================================================
// ReceiptsService — Ticket 81: Receipt Canonical Event Schema v2
// ============================================================================

// ReceiptsService provides receipt lifecycle operations.
type ReceiptsService struct {
	client *Client
}

// Mint creates a new cryptographically signed and transparency-log-anchored receipt.
func (s *ReceiptsService) Mint(ctx context.Context, req *MintReceiptRequest) (*ReceiptEvent, error) {
	var receipt ReceiptEvent
	if err := s.client.request(ctx, "POST", "/v1/receipts", req, &receipt); err != nil {
		return nil, err
	}
	return &receipt, nil
}

// Get retrieves a receipt event by ID.
func (s *ReceiptsService) Get(ctx context.Context, id string) (*ReceiptEvent, error) {
	var receipt ReceiptEvent
	if err := s.client.request(ctx, "GET", "/v1/receipts/"+id, nil, &receipt); err != nil {
		return nil, err
	}
	return &receipt, nil
}

// List retrieves receipt events with optional filters.
func (s *ReceiptsService) List(ctx context.Context, f *ListReceiptsFilter) (*ListReceiptsResponse, error) {
	path := "/v1/receipts"
	sep := "?"
	if f != nil {
		if f.ReceiptType != "" {
			path += sep + "receipt_type=" + f.ReceiptType
			sep = "&"
		}
		if f.IssuerID != "" {
			path += sep + "issuer_id=" + f.IssuerID
			sep = "&"
		}
		if f.Status != "" {
			path += sep + "status=" + string(f.Status)
			sep = "&"
		}
		if f.Limit > 0 {
			path += sep + "limit=" + itoa(f.Limit)
			sep = "&"
		}
		if f.Offset > 0 {
			path += sep + "offset=" + itoa(f.Offset)
		}
	}

	var resp ListReceiptsResponse
	if err := s.client.request(ctx, "GET", path, nil, &resp); err != nil {
		return nil, err
	}
	return &resp, nil
}

// Revoke revokes a receipt event and records a RECEIPT_REVOKE entry in the transparency log.
func (s *ReceiptsService) Revoke(ctx context.Context, id string, req *RevokeReceiptRequest) (*ReceiptEvent, error) {
	var receipt ReceiptEvent
	if req == nil {
		req = &RevokeReceiptRequest{}
	}
	if err := s.client.request(ctx, "POST", "/v1/receipts/"+id+"/revoke", req, &receipt); err != nil {
		return nil, err
	}
	return &receipt, nil
}

// ListTypes returns all active receipt type families available to the tenant.
func (s *ReceiptsService) ListTypes(ctx context.Context) (*ListReceiptTypesResponse, error) {
	var resp ListReceiptTypesResponse
	if err := s.client.request(ctx, "GET", "/v1/receipt-types", nil, &resp); err != nil {
		return nil, err
	}
	return &resp, nil
}

// GetType retrieves a specific receipt type by name.
// To pin a version use: "payment_receipt@1.0.0"
func (s *ReceiptsService) GetType(ctx context.Context, name string) (*ReceiptType, error) {
	var rt ReceiptType
	if err := s.client.request(ctx, "GET", "/v1/receipt-types/"+name, nil, &rt); err != nil {
		return nil, err
	}
	return &rt, nil
}

// CreateType creates a tenant-custom receipt type with a JSON Schema.
func (s *ReceiptsService) CreateType(ctx context.Context, req *CreateReceiptTypeRequest) (*ReceiptType, error) {
	var rt ReceiptType
	if err := s.client.request(ctx, "POST", "/v1/receipt-types", req, &rt); err != nil {
		return nil, err
	}
	return &rt, nil
}

// UpdateType deprecates or archives a tenant-custom receipt type.
func (s *ReceiptsService) UpdateType(ctx context.Context, name string, req *UpdateReceiptTypeRequest) error {
	return s.client.request(ctx, "PATCH", "/v1/receipt-types/"+name, req, nil)
}

// GetSigningPolicy returns the signing policy for a receipt type.
func (s *ReceiptsService) GetSigningPolicy(ctx context.Context, name string) (*SigningPolicy, error) {
	var sp SigningPolicy
	if err := s.client.request(ctx, "GET", "/v1/receipt-types/"+name+"/signing-policy", nil, &sp); err != nil {
		return nil, err
	}
	return &sp, nil
}

// SetSigningPolicy sets the signing policy for a receipt type.
func (s *ReceiptsService) SetSigningPolicy(ctx context.Context, name string, req *SetSigningPolicyRequest) (*SigningPolicy, error) {
	var sp SigningPolicy
	if err := s.client.request(ctx, "POST", "/v1/receipt-types/"+name+"/signing-policy", req, &sp); err != nil {
		return nil, err
	}
	return &sp, nil
}

// GetProofBundle retrieves the proof bundle for a receipt.
func (s *ReceiptsService) GetProofBundle(ctx context.Context, id string) (map[string]interface{}, error) {
	var bundle map[string]interface{}
	if err := s.client.request(ctx, "GET", "/v1/receipts/"+id+"/proof-bundle", nil, &bundle); err != nil {
		return nil, err
	}
	return bundle, nil
}

// Verify verifies a receipt by ID.
func (s *ReceiptsService) Verify(ctx context.Context, receiptID string) (*ReceiptVerifyResponse, error) {
	var resp ReceiptVerifyResponse
	body := map[string]string{"receipt_id": receiptID}
	if err := s.client.request(ctx, "POST", "/v1/receipts/verify", body, &resp); err != nil {
		return nil, err
	}
	return &resp, nil
}

// Search searches receipt events with full-text and faceted filtering.
func (s *ReceiptsService) Search(ctx context.Context, q *SearchReceiptsQuery) (*ListReceiptsResponse, error) {
	var resp ListReceiptsResponse
	if err := s.client.request(ctx, "POST", "/v1/receipts/search", q, &resp); err != nil {
		return nil, err
	}
	return &resp, nil
}

// Export queues a bulk export of receipts.
func (s *ReceiptsService) Export(ctx context.Context, req *CreateExportRequest) (*ReceiptExport, error) {
	var exp ReceiptExport
	if err := s.client.request(ctx, "POST", "/v1/receipts/export", req, &exp); err != nil {
		return nil, err
	}
	return &exp, nil
}

// GetExport retrieves the status and download URL of an export job.
func (s *ReceiptsService) GetExport(ctx context.Context, exportID string) (*ReceiptExport, error) {
	var exp ReceiptExport
	if err := s.client.request(ctx, "GET", "/v1/receipts/exports/"+exportID, nil, &exp); err != nil {
		return nil, err
	}
	return &exp, nil
}

// Redact removes PII from a receipt payload while preserving the cryptographic proof.
func (s *ReceiptsService) Redact(ctx context.Context, id string) (map[string]interface{}, error) {
	var resp map[string]interface{}
	if err := s.client.request(ctx, "POST", "/v1/receipts/"+id+"/redact", map[string]string{}, &resp); err != nil {
		return nil, err
	}
	return resp, nil
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	buf := make([]byte, 0, 10)
	for n > 0 {
		buf = append([]byte{byte('0' + n%10)}, buf...)
		n /= 10
	}
	return string(buf)
}

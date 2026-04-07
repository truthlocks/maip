// Copyright 2026 Truthlocks Inc.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package reference

import (
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"sort"
	"time"

	"github.com/oklog/ulid/v2"
)

// ReceiptType identifies the kind of MAIP receipt.
type ReceiptType string

const (
	ReceiptTypeGenesis    ReceiptType = "maip_genesis"
	ReceiptTypeDelegation ReceiptType = "maip_delegation"
	ReceiptTypeAction     ReceiptType = "maip_action"
	ReceiptTypeRevocation ReceiptType = "maip_revocation"
	ReceiptTypeDataset    ReceiptType = "maip_dataset_attestation"
	ReceiptTypeModel      ReceiptType = "maip_model_attestation"
	ReceiptTypeApproval   ReceiptType = "maip_approval"
	ReceiptTypeCompliance ReceiptType = "maip_compliance"
	ReceiptTypeTruthClaim ReceiptType = "maip_truth_claim"
)

// Receipt is a signed, tamper-evident record of an event in the MAIP system.
// Receipts form a chain per issuer, linked by PreviousReceiptID.
type Receipt struct {
	// ID is the unique receipt identifier in the format rcpt_<ulid>.
	ID string `json:"receipt_id"`

	// Type classifies the receipt.
	Type ReceiptType `json:"receipt_type"`

	// SchemaVersion is the semantic version of the receipt schema.
	SchemaVersion string `json:"schema_version"`

	// IssuerID is the MAIP agent ID or human issuer UUID that created this receipt.
	IssuerID string `json:"issuer_id"`

	// SubjectID is the entity this receipt is about.
	SubjectID string `json:"subject_id"`

	// SubjectType classifies the subject (agent, dataset, model, pipeline, document).
	SubjectType string `json:"subject_type"`

	// CreatedAt is when the receipt was created.
	CreatedAt time.Time `json:"created_at"`

	// ExpiresAt is when the receipt expires. Zero value means permanent.
	ExpiresAt time.Time `json:"expires_at,omitempty"`

	// Nonce is a 32-byte cryptographically random value for anti-replay.
	Nonce string `json:"nonce"`

	// Context holds delegation and scope context at receipt creation time.
	Context ReceiptContext `json:"context"`

	// Payload holds type-specific receipt data.
	Payload json.RawMessage `json:"payload"`

	// PreviousReceiptID links to the prior receipt by this issuer. Empty for first.
	PreviousReceiptID string `json:"previous_receipt_id,omitempty"`

	// Signature holds the Ed25519 signature over the receipt body.
	Signature ReceiptSignature `json:"signature"`
}

// ReceiptContext holds delegation and scope context at receipt creation time.
type ReceiptContext struct {
	TenantID             string   `json:"tenant_id"`
	DelegationChainHash  string   `json:"delegation_chain_hash"`
	DelegationDepth      int      `json:"delegation_depth"`
	ScopesUsed           []string `json:"scopes_used"`
}

// ReceiptSignature holds the cryptographic signature over the receipt.
type ReceiptSignature struct {
	Algorithm string `json:"alg"`
	KeyID     string `json:"kid"`
	Value     string `json:"value"`
}

// generateReceiptID produces a unique receipt ID in the format rcpt_<ulid>.
func generateReceiptID() string {
	entropy := ulid.Monotonic(rand.Reader, 0)
	id := ulid.MustNew(ulid.Timestamp(time.Now()), entropy)
	return fmt.Sprintf("rcpt_%s", id.String())
}

// generateNonce produces a 32-byte cryptographic nonce, base64url-encoded.
func generateNonce() (string, error) {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return "", fmt.Errorf("generating nonce: %w", err)
	}
	return base64.RawURLEncoding.EncodeToString(b), nil
}

// canonicalizeReceipt produces a deterministic JSON representation of the receipt
// for signing. It includes all fields except the signature itself.
// This uses sorted keys for determinism (simplified JCS).
func canonicalizeReceipt(r *Receipt) ([]byte, error) {
	// Create a copy without signature for canonical form
	type receiptForSigning struct {
		ID                string           `json:"receipt_id"`
		Type              ReceiptType      `json:"receipt_type"`
		SchemaVersion     string           `json:"schema_version"`
		IssuerID          string           `json:"issuer_id"`
		SubjectID         string           `json:"subject_id"`
		SubjectType       string           `json:"subject_type"`
		CreatedAt         time.Time        `json:"created_at"`
		ExpiresAt         time.Time        `json:"expires_at,omitempty"`
		Nonce             string           `json:"nonce"`
		Context           ReceiptContext   `json:"context"`
		Payload           json.RawMessage  `json:"payload"`
		PreviousReceiptID string           `json:"previous_receipt_id,omitempty"`
	}

	forSigning := receiptForSigning{
		ID:                r.ID,
		Type:              r.Type,
		SchemaVersion:     r.SchemaVersion,
		IssuerID:          r.IssuerID,
		SubjectID:         r.SubjectID,
		SubjectType:       r.SubjectType,
		CreatedAt:         r.CreatedAt,
		ExpiresAt:         r.ExpiresAt,
		Nonce:             r.Nonce,
		Context:           r.Context,
		Payload:           r.Payload,
		PreviousReceiptID: r.PreviousReceiptID,
	}

	// Marshal to JSON, then re-parse and re-serialize with sorted keys
	data, err := json.Marshal(forSigning)
	if err != nil {
		return nil, fmt.Errorf("marshaling receipt for signing: %w", err)
	}

	// Parse into a generic map and re-serialize with sorted keys
	var m map[string]interface{}
	if err := json.Unmarshal(data, &m); err != nil {
		return nil, fmt.Errorf("parsing receipt JSON: %w", err)
	}

	return canonicalJSON(m)
}

// canonicalJSON produces a deterministic JSON serialization with sorted keys.
func canonicalJSON(v interface{}) ([]byte, error) {
	switch val := v.(type) {
	case map[string]interface{}:
		keys := make([]string, 0, len(val))
		for k := range val {
			keys = append(keys, k)
		}
		sort.Strings(keys)

		result := []byte("{")
		for i, k := range keys {
			if i > 0 {
				result = append(result, ',')
			}
			keyJSON, err := json.Marshal(k)
			if err != nil {
				return nil, err
			}
			result = append(result, keyJSON...)
			result = append(result, ':')
			valJSON, err := canonicalJSON(val[k])
			if err != nil {
				return nil, err
			}
			result = append(result, valJSON...)
		}
		result = append(result, '}')
		return result, nil

	case []interface{}:
		result := []byte("[")
		for i, item := range val {
			if i > 0 {
				result = append(result, ',')
			}
			itemJSON, err := canonicalJSON(item)
			if err != nil {
				return nil, err
			}
			result = append(result, itemJSON...)
		}
		result = append(result, ']')
		return result, nil

	default:
		return json.Marshal(v)
	}
}

// ReceiptOption configures optional receipt parameters before signing.
type ReceiptOption func(*Receipt)

// WithScopesUsed sets the scopes exercised by this receipt.
func WithScopesUsed(scopes []string) ReceiptOption {
	return func(r *Receipt) {
		r.Context.ScopesUsed = scopes
	}
}

// WithDelegationChainHash sets the delegation chain hash on the receipt context.
func WithDelegationChainHash(hash string) ReceiptOption {
	return func(r *Receipt) {
		r.Context.DelegationChainHash = hash
	}
}

// WithReceiptExpiry overrides the default expiry time.
func WithReceiptExpiry(expiresAt time.Time) ReceiptOption {
	return func(r *Receipt) {
		r.ExpiresAt = expiresAt
	}
}

// NewReceipt creates a new signed receipt. Options are applied before signing
// so the signature covers all configured fields.
func NewReceipt(
	receiptType ReceiptType,
	agent *Agent,
	subjectID string,
	subjectType string,
	payload json.RawMessage,
	previousReceiptID string,
	opts ...ReceiptOption,
) (*Receipt, error) {
	if agent == nil {
		return nil, fmt.Errorf("agent must not be nil")
	}
	if agent.PrivateKey == nil {
		return nil, fmt.Errorf("agent %s has no private key for signing", agent.ID)
	}

	nonce, err := generateNonce()
	if err != nil {
		return nil, err
	}

	now := time.Now().UTC()
	receipt := &Receipt{
		ID:            generateReceiptID(),
		Type:          receiptType,
		SchemaVersion: "1.0.0",
		IssuerID:      agent.ID,
		SubjectID:     subjectID,
		SubjectType:   subjectType,
		CreatedAt:     now,
		Nonce:         nonce,
		Context: ReceiptContext{
			TenantID:            agent.TenantPrefix,
			DelegationChainHash: "", // Set by caller if applicable
			DelegationDepth:     agent.DelegationDepth,
			ScopesUsed:          []string{},
		},
		Payload:           payload,
		PreviousReceiptID: previousReceiptID,
	}

	// Set default expiry based on receipt type
	switch receiptType {
	case ReceiptTypeAction, ReceiptTypeApproval:
		receipt.ExpiresAt = now.Add(24 * time.Hour)
	case ReceiptTypeDelegation, ReceiptTypeDataset, ReceiptTypeModel, ReceiptTypeTruthClaim:
		receipt.ExpiresAt = now.Add(365 * 24 * time.Hour)
	// Genesis and Revocation are permanent (zero ExpiresAt)
	}

	// Apply options before signing
	for _, opt := range opts {
		opt(receipt)
	}

	// Sign the receipt
	if err := signReceipt(receipt, agent); err != nil {
		return nil, fmt.Errorf("signing receipt: %w", err)
	}

	return receipt, nil
}

// signReceipt computes and sets the Ed25519 signature on the receipt.
func signReceipt(receipt *Receipt, agent *Agent) error {
	canonical, err := canonicalizeReceipt(receipt)
	if err != nil {
		return err
	}

	sig := ed25519.Sign(agent.PrivateKey, canonical)

	receipt.Signature = ReceiptSignature{
		Algorithm: "Ed25519",
		KeyID:     agent.PublicKeyBase64,
		Value:     base64.RawURLEncoding.EncodeToString(sig),
	}

	return nil
}

// VerifyReceipt checks the Ed25519 signature on a receipt against the provided
// public key. Returns nil if valid, error describing the failure otherwise.
func VerifyReceipt(receipt *Receipt, publicKey ed25519.PublicKey) error {
	canonical, err := canonicalizeReceipt(receipt)
	if err != nil {
		return fmt.Errorf("canonicalizing receipt: %w", err)
	}

	sigBytes, err := base64.RawURLEncoding.DecodeString(receipt.Signature.Value)
	if err != nil {
		return fmt.Errorf("decoding signature: %w", err)
	}

	if !ed25519.Verify(publicKey, canonical, sigBytes) {
		return fmt.Errorf("signature verification failed for receipt %s", receipt.ID)
	}

	return nil
}

// ReceiptChain is an ordered sequence of receipts from the same issuer.
type ReceiptChain struct {
	Receipts []*Receipt
}

// Append adds a receipt to the chain, setting its PreviousReceiptID to the
// last receipt in the chain.
func (rc *ReceiptChain) Append(receipt *Receipt) {
	if len(rc.Receipts) > 0 {
		receipt.PreviousReceiptID = rc.Receipts[len(rc.Receipts)-1].ID
	}
	rc.Receipts = append(rc.Receipts, receipt)
}

// Verify checks the integrity of the receipt chain: each receipt's
// PreviousReceiptID must match the preceding receipt's ID, and all
// signatures must be valid.
func (rc *ReceiptChain) Verify(publicKey ed25519.PublicKey) error {
	for i, receipt := range rc.Receipts {
		// Verify chain linkage
		if i == 0 {
			if receipt.PreviousReceiptID != "" {
				return fmt.Errorf("first receipt in chain has non-empty previous_receipt_id")
			}
		} else {
			if receipt.PreviousReceiptID != rc.Receipts[i-1].ID {
				return fmt.Errorf("chain broken at index %d: expected previous %s, got %s",
					i, rc.Receipts[i-1].ID, receipt.PreviousReceiptID)
			}
		}

		// Verify signature
		if err := VerifyReceipt(receipt, publicKey); err != nil {
			return fmt.Errorf("receipt %d (%s): %w", i, receipt.ID, err)
		}
	}
	return nil
}

// ComputeChainHash computes the SHA-256 hash of the serialized receipt chain.
// This is used in the delegation_chain_hash field of receipt contexts.
func (rc *ReceiptChain) ComputeChainHash() (string, error) {
	data, err := json.Marshal(rc.Receipts)
	if err != nil {
		return "", fmt.Errorf("marshaling receipt chain: %w", err)
	}
	hash := sha256.Sum256(data)
	return base64.RawURLEncoding.EncodeToString(hash[:]), nil
}

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
	"encoding/base64"
	"encoding/json"
	"fmt"
	"time"
)

// BundleVersion is the current MAIP proof bundle format version.
const BundleVersion = "1.0.0"

// Bundle is a self-contained MAIP proof bundle that enables offline
// verification of a receipt and its complete delegation chain without
// any network calls.
type Bundle struct {
	// Version is the bundle format version.
	Version string `json:"maip_bundle_version"`

	// CreatedAt is when the bundle was assembled.
	CreatedAt time.Time `json:"created_at"`

	// Receipt is the action receipt being verified.
	Receipt *Receipt `json:"receipt"`

	// DelegationChain is the ordered sequence of delegations from root to the
	// receipt's issuing agent.
	DelegationChain []*Delegation `json:"delegation_chain"`

	// PublicKeys maps agent IDs to their base64url-encoded Ed25519 public keys.
	PublicKeys []BundlePublicKey `json:"public_keys"`

	// Metadata holds optional additional context.
	Metadata *BundleMetadata `json:"metadata,omitempty"`
}

// BundlePublicKey associates an agent ID with its public key material.
type BundlePublicKey struct {
	AgentID   string `json:"agent_id"`
	PublicKey string `json:"public_key"`
	Algorithm string `json:"algorithm"`
}

// BundleMetadata holds optional metadata about the bundle.
type BundleMetadata struct {
	// BundlerID identifies who created the bundle.
	BundlerID string `json:"bundler_id,omitempty"`
	// Purpose describes why the bundle was created.
	Purpose string `json:"purpose,omitempty"`
	// Notes holds free-form notes.
	Notes string `json:"notes,omitempty"`
}

// BundleVerificationResult holds the outcome of verifying a proof bundle.
type BundleVerificationResult struct {
	// Valid is true if the bundle passed all verification checks.
	Valid bool `json:"valid"`
	// Result is the chain verification outcome.
	Result ChainVerificationResult `json:"result"`
	// ReceiptValid is true if the receipt signature is valid.
	ReceiptValid bool `json:"receipt_valid"`
	// Error describes any verification failure.
	Error string `json:"error,omitempty"`
	// AgentID is the agent that issued the receipt.
	AgentID string `json:"agent_id"`
	// ReceiptID is the receipt that was verified.
	ReceiptID string `json:"receipt_id"`
	// ChainDepth is the delegation chain depth.
	ChainDepth int `json:"chain_depth"`
}

// NewBundle creates a new proof bundle from a receipt, its delegation chain,
// and the public keys needed for offline verification.
func NewBundle(
	receipt *Receipt,
	delegations []*Delegation,
	keys []BundlePublicKey,
	metadata *BundleMetadata,
) *Bundle {
	return &Bundle{
		Version:         BundleVersion,
		CreatedAt:       time.Now().UTC(),
		Receipt:         receipt,
		DelegationChain: delegations,
		PublicKeys:      keys,
		Metadata:        metadata,
	}
}

// MarshalJSON serializes the bundle to JSON.
func (b *Bundle) MarshalJSON() ([]byte, error) {
	type bundleAlias Bundle
	return json.MarshalIndent((*bundleAlias)(b), "", "  ")
}

// VerifyBundle performs offline verification of a proof bundle. It:
//  1. Resolves public keys from the bundle's key list
//  2. Verifies the delegation chain (contiguity, signatures, scopes, temporal validity)
//  3. Verifies the receipt signature
//  4. Checks that the receipt's scopes are covered by the leaf delegation
//
// Returns a BundleVerificationResult describing the outcome.
func VerifyBundle(b *Bundle) *BundleVerificationResult {
	result := &BundleVerificationResult{
		AgentID:    b.Receipt.IssuerID,
		ReceiptID:  b.Receipt.ID,
		ChainDepth: len(b.DelegationChain),
	}

	// Build a key map from bundle
	keyMap := make(map[string]ed25519.PublicKey)
	for _, bpk := range b.PublicKeys {
		keyBytes, err := base64.RawURLEncoding.DecodeString(bpk.PublicKey)
		if err != nil {
			result.Result = ChainKeyMismatch
			result.Error = fmt.Sprintf("invalid public key for agent %s: %v", bpk.AgentID, err)
			return result
		}
		keyMap[bpk.AgentID] = ed25519.PublicKey(keyBytes)
	}

	// Verify delegation chain
	if len(b.DelegationChain) > 0 {
		chainEntries := make([]DelegationChainEntry, len(b.DelegationChain))
		for i, d := range b.DelegationChain {
			parentKey, ok := keyMap[d.ParentAgentID]
			if !ok {
				result.Result = ChainKeyMismatch
				result.Error = fmt.Sprintf("missing public key for parent agent %s at chain index %d", d.ParentAgentID, i)
				return result
			}
			chainEntries[i] = DelegationChainEntry{
				Delegation:      d,
				ParentPublicKey: parentKey,
			}
		}

		chainResult, err := VerifyChain(chainEntries)
		if chainResult != ChainValid {
			result.Result = chainResult
			if err != nil {
				result.Error = err.Error()
			}
			return result
		}

		// Check that receipt issuer matches the leaf agent in the chain
		leafDelegation := b.DelegationChain[len(b.DelegationChain)-1]
		if b.Receipt.IssuerID != leafDelegation.ChildAgentID {
			result.Result = ChainBroken
			result.Error = fmt.Sprintf("receipt issuer %s does not match leaf agent %s",
				b.Receipt.IssuerID, leafDelegation.ChildAgentID)
			return result
		}

		// Check receipt scopes against leaf delegation scopes
		if len(b.Receipt.Context.ScopesUsed) > 0 {
			if err := ValidateScopeNarrowing(leafDelegation.Scopes, b.Receipt.Context.ScopesUsed); err != nil {
				result.Result = ChainScopeViolation
				result.Error = fmt.Sprintf("receipt scope violation: %v", err)
				return result
			}
		}
	}

	// Verify receipt signature
	receiptKey, ok := keyMap[b.Receipt.IssuerID]
	if !ok {
		result.Result = ChainKeyMismatch
		result.Error = fmt.Sprintf("missing public key for receipt issuer %s", b.Receipt.IssuerID)
		return result
	}

	if err := VerifyReceipt(b.Receipt, receiptKey); err != nil {
		result.Result = ChainVerificationResult("signature_invalid")
		result.Error = err.Error()
		return result
	}

	// Check receipt temporal validity
	now := time.Now().UTC()
	if !b.Receipt.ExpiresAt.IsZero() && now.After(b.Receipt.ExpiresAt) {
		result.Result = ChainExpired
		result.Error = fmt.Sprintf("receipt %s expired at %s", b.Receipt.ID, b.Receipt.ExpiresAt)
		return result
	}

	result.Valid = true
	result.ReceiptValid = true
	result.Result = ChainValid
	return result
}

// ParseBundle deserializes a JSON proof bundle.
func ParseBundle(data []byte) (*Bundle, error) {
	var b Bundle
	if err := json.Unmarshal(data, &b); err != nil {
		return nil, fmt.Errorf("parsing bundle: %w", err)
	}
	return &b, nil
}

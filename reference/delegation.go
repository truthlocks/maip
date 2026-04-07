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
	"encoding/base64"
	"encoding/json"
	"fmt"
	"time"

	"github.com/oklog/ulid/v2"
)

// MaxDelegationDepth is the maximum number of hops from the root allowed
// in a MAIP delegation chain (MAIP_MAX_DEPTH).
const MaxDelegationDepth = 3

// DelegationStatus represents the lifecycle state of a delegation.
type DelegationStatus string

const (
	DelegationStatusActive  DelegationStatus = "active"
	DelegationStatusExpired DelegationStatus = "expired"
	DelegationStatusRevoked DelegationStatus = "revoked"
)

// Delegation represents a DelegationAttestation in the MAIP protocol.
// It records the transfer of a narrowed set of scopes from a parent to a child agent.
type Delegation struct {
	// ID is the unique delegation identifier.
	ID string `json:"delegation_id"`

	// ParentAgentID is the MAIP ID of the delegating agent.
	ParentAgentID string `json:"parent_agent_id"`

	// ChildAgentID is the MAIP ID of the delegatee agent.
	ChildAgentID string `json:"child_agent_id"`

	// ChildPublicKey is the base64url-encoded Ed25519 public key of the child.
	ChildPublicKey string `json:"child_public_key"`

	// Depth is the delegation depth (parent.depth + 1).
	Depth int `json:"depth"`

	// Scopes is the set of scopes delegated to the child. Must be a subset
	// of the parent's scopes.
	Scopes []string `json:"scopes"`

	// Constraints holds optional operational constraints on the delegation.
	Constraints *DelegationConstraints `json:"constraints,omitempty"`

	// NotBefore is the earliest time the delegation is valid.
	NotBefore time.Time `json:"not_before"`

	// ExpiresAt is the time the delegation expires.
	ExpiresAt time.Time `json:"expires_at"`

	// IssuedAt is the time the delegation was created.
	IssuedAt time.Time `json:"issued_at"`

	// Signature is the base64url-encoded Ed25519 signature by the parent.
	Signature string `json:"signature"`

	// SignatureAlgorithm identifies the signing algorithm.
	SignatureAlgorithm string `json:"signature_algorithm"`

	// Status tracks the delegation lifecycle.
	Status DelegationStatus `json:"status"`

	// CrossTenant indicates whether this is a cross-tenant delegation.
	CrossTenant bool `json:"cross_tenant,omitempty"`

	// SourceTenant is the originating tenant for cross-tenant delegations.
	SourceTenant string `json:"source_tenant,omitempty"`

	// TargetTenant is the receiving tenant for cross-tenant delegations.
	TargetTenant string `json:"target_tenant,omitempty"`
}

// DelegationConstraints holds optional operational limits on a delegation.
type DelegationConstraints struct {
	MaxSubDelegations   int      `json:"max_sub_delegations,omitempty"`
	AllowedEnvironments []string `json:"allowed_environments,omitempty"`
	RateLimitPerHour    int      `json:"rate_limit_per_hour,omitempty"`
	IPAllowlist         []string `json:"ip_allowlist,omitempty"`
}

// DelegationOffer represents a cross-tenant delegation offer that must be
// accepted by the target tenant before becoming active.
type DelegationOffer struct {
	// OfferID is the unique identifier for this offer.
	OfferID string `json:"offer_id"`

	// Delegation contains the proposed delegation terms.
	Delegation *Delegation `json:"delegation"`

	// OfferedAt is when the offer was created.
	OfferedAt time.Time `json:"offered_at"`

	// ExpiresAt is when the offer expires if not accepted.
	ExpiresAt time.Time `json:"expires_at"`

	// Accepted tracks whether the offer has been accepted.
	Accepted bool `json:"accepted"`

	// AcceptedAt is when the offer was accepted.
	AcceptedAt time.Time `json:"accepted_at,omitempty"`
}

// generateDelegationID creates a unique delegation ID.
func generateDelegationID() string {
	entropy := ulid.Monotonic(rand.Reader, 0)
	id := ulid.MustNew(ulid.Timestamp(time.Now()), entropy)
	return fmt.Sprintf("del_%s", id.String())
}

// CreateDelegation creates a new delegation from parent to child agent.
// It enforces depth limiting, scope narrowing, and temporal constraints.
func CreateDelegation(
	parent *Agent,
	child *Agent,
	scopes []string,
	ttl time.Duration,
	constraints *DelegationConstraints,
) (*Delegation, error) {
	if parent == nil || child == nil {
		return nil, fmt.Errorf("parent and child agents must not be nil")
	}
	if parent.PrivateKey == nil {
		return nil, fmt.Errorf("parent agent %s has no private key for signing", parent.ID)
	}

	// Enforce depth limit
	childDepth := parent.DelegationDepth + 1
	if childDepth > MaxDelegationDepth {
		return nil, fmt.Errorf("delegation depth %d exceeds maximum %d", childDepth, MaxDelegationDepth)
	}

	// Enforce scope narrowing
	if err := ValidateScopeNarrowing(parent.Scopes, scopes); err != nil {
		return nil, fmt.Errorf("scope narrowing violation: %w", err)
	}

	now := time.Now().UTC()
	delegation := &Delegation{
		ID:                 generateDelegationID(),
		ParentAgentID:      parent.ID,
		ChildAgentID:       child.ID,
		ChildPublicKey:     child.PublicKeyBase64,
		Depth:              childDepth,
		Scopes:             scopes,
		Constraints:        constraints,
		NotBefore:          now,
		ExpiresAt:          now.Add(ttl),
		IssuedAt:           now,
		SignatureAlgorithm: "Ed25519",
		Status:             DelegationStatusActive,
	}

	// Sign the delegation
	if err := signDelegation(delegation, parent.PrivateKey); err != nil {
		return nil, fmt.Errorf("signing delegation: %w", err)
	}

	// Update child agent metadata
	child.DelegationDepth = childDepth
	child.Scopes = scopes

	return delegation, nil
}

// CreateCrossTenantDelegation creates a delegation offer for cross-tenant
// delegation. The offer must be accepted by the target tenant's agent.
func CreateCrossTenantDelegation(
	parent *Agent,
	child *Agent,
	scopes []string,
	ttl time.Duration,
	sourceTenant string,
	targetTenant string,
) (*DelegationOffer, error) {
	delegation, err := CreateDelegation(parent, child, scopes, ttl, nil)
	if err != nil {
		return nil, err
	}

	delegation.CrossTenant = true
	delegation.SourceTenant = sourceTenant
	delegation.TargetTenant = targetTenant

	// Re-sign with cross-tenant fields included
	if err := signDelegation(delegation, parent.PrivateKey); err != nil {
		return nil, fmt.Errorf("re-signing cross-tenant delegation: %w", err)
	}

	offer := &DelegationOffer{
		OfferID:    fmt.Sprintf("offer_%s", delegation.ID),
		Delegation: delegation,
		OfferedAt:  time.Now().UTC(),
		ExpiresAt:  time.Now().UTC().Add(24 * time.Hour), // 24h offer window
		Accepted:   false,
	}

	return offer, nil
}

// AcceptDelegationOffer accepts a cross-tenant delegation offer. The accepting
// agent's public key must match the child_public_key in the delegation.
func AcceptDelegationOffer(offer *DelegationOffer, acceptingAgent *Agent) error {
	if offer == nil {
		return fmt.Errorf("offer must not be nil")
	}
	if offer.Accepted {
		return fmt.Errorf("offer %s has already been accepted", offer.OfferID)
	}
	if time.Now().UTC().After(offer.ExpiresAt) {
		return fmt.Errorf("offer %s has expired", offer.OfferID)
	}
	if acceptingAgent.PublicKeyBase64 != offer.Delegation.ChildPublicKey {
		return fmt.Errorf("accepting agent's public key does not match delegation child key")
	}

	offer.Accepted = true
	offer.AcceptedAt = time.Now().UTC()

	// Update the accepting agent's delegation metadata
	acceptingAgent.DelegationDepth = offer.Delegation.Depth
	acceptingAgent.Scopes = offer.Delegation.Scopes

	return nil
}

// signDelegation computes the Ed25519 signature over the delegation's canonical form.
func signDelegation(d *Delegation, privateKey ed25519.PrivateKey) error {
	canonical, err := canonicalizeDelegation(d)
	if err != nil {
		return err
	}

	sig := ed25519.Sign(privateKey, canonical)
	d.Signature = base64.RawURLEncoding.EncodeToString(sig)
	return nil
}

// VerifyDelegation checks the Ed25519 signature on a delegation against
// the parent's public key.
func VerifyDelegation(d *Delegation, parentPublicKey ed25519.PublicKey) error {
	sigBytes, err := base64.RawURLEncoding.DecodeString(d.Signature)
	if err != nil {
		return fmt.Errorf("decoding signature: %w", err)
	}

	canonical, err := canonicalizeDelegation(d)
	if err != nil {
		return fmt.Errorf("canonicalizing delegation: %w", err)
	}

	if !ed25519.Verify(parentPublicKey, canonical, sigBytes) {
		return fmt.Errorf("delegation signature verification failed for %s", d.ID)
	}

	return nil
}

// canonicalizeDelegation produces a deterministic JSON representation for signing.
func canonicalizeDelegation(d *Delegation) ([]byte, error) {
	type delegationForSigning struct {
		ID             string                `json:"delegation_id"`
		ParentAgentID  string                `json:"parent_agent_id"`
		ChildAgentID   string                `json:"child_agent_id"`
		ChildPublicKey string                `json:"child_public_key"`
		Depth          int                   `json:"depth"`
		Scopes         []string              `json:"scopes"`
		Constraints    *DelegationConstraints `json:"constraints,omitempty"`
		NotBefore      time.Time             `json:"not_before"`
		ExpiresAt      time.Time             `json:"expires_at"`
		IssuedAt       time.Time             `json:"issued_at"`
		CrossTenant    bool                  `json:"cross_tenant,omitempty"`
		SourceTenant   string                `json:"source_tenant,omitempty"`
		TargetTenant   string                `json:"target_tenant,omitempty"`
	}

	forSigning := delegationForSigning{
		ID:             d.ID,
		ParentAgentID:  d.ParentAgentID,
		ChildAgentID:   d.ChildAgentID,
		ChildPublicKey: d.ChildPublicKey,
		Depth:          d.Depth,
		Scopes:         d.Scopes,
		Constraints:    d.Constraints,
		NotBefore:      d.NotBefore,
		ExpiresAt:      d.ExpiresAt,
		IssuedAt:       d.IssuedAt,
		CrossTenant:    d.CrossTenant,
		SourceTenant:   d.SourceTenant,
		TargetTenant:   d.TargetTenant,
	}

	data, err := json.Marshal(forSigning)
	if err != nil {
		return nil, fmt.Errorf("marshaling delegation for signing: %w", err)
	}

	var m map[string]interface{}
	if err := json.Unmarshal(data, &m); err != nil {
		return nil, err
	}
	return canonicalJSON(m)
}

// VerifyDelegationChain verifies an entire delegation chain from root to leaf.
// It checks contiguity, signatures, scope narrowing, depth limits, temporal
// validity, and revocation status.
type ChainVerificationResult string

const (
	ChainValid          ChainVerificationResult = "valid"
	ChainBroken         ChainVerificationResult = "chain_broken"
	ChainScopeViolation ChainVerificationResult = "scope_violation"
	ChainRevoked        ChainVerificationResult = "revoked"
	ChainExpired        ChainVerificationResult = "expired"
	ChainDepthExceeded  ChainVerificationResult = "depth_exceeded"
	ChainKeyMismatch    ChainVerificationResult = "key_mismatch"
)

// DelegationChainEntry pairs a delegation with the parent's public key
// needed for verification.
type DelegationChainEntry struct {
	Delegation      *Delegation
	ParentPublicKey ed25519.PublicKey
}

// VerifyChain verifies a delegation chain from root to leaf. The chain is
// an ordered slice of DelegationChainEntry values, from the first delegation
// (root -> first child) to the last (penultimate -> leaf).
func VerifyChain(chain []DelegationChainEntry) (ChainVerificationResult, error) {
	if len(chain) == 0 {
		return ChainValid, nil
	}

	now := time.Now().UTC()

	for i, entry := range chain {
		d := entry.Delegation

		// Check depth
		expectedDepth := i + 1
		if d.Depth != expectedDepth {
			return ChainBroken, fmt.Errorf("delegation %d: expected depth %d, got %d", i, expectedDepth, d.Depth)
		}
		if d.Depth > MaxDelegationDepth {
			return ChainDepthExceeded, fmt.Errorf("delegation %d: depth %d exceeds max %d", i, d.Depth, MaxDelegationDepth)
		}

		// Check contiguity
		if i > 0 {
			prev := chain[i-1].Delegation
			if d.ParentAgentID != prev.ChildAgentID {
				return ChainBroken, fmt.Errorf("chain broken at index %d: parent %s != previous child %s",
					i, d.ParentAgentID, prev.ChildAgentID)
			}
		}

		// Check temporal validity
		if now.Before(d.NotBefore) || now.After(d.ExpiresAt) {
			return ChainExpired, fmt.Errorf("delegation %d (%s) is not temporally valid", i, d.ID)
		}

		// Check revocation
		if d.Status == DelegationStatusRevoked {
			return ChainRevoked, fmt.Errorf("delegation %d (%s) has been revoked", i, d.ID)
		}

		// Verify signature
		if err := VerifyDelegation(d, entry.ParentPublicKey); err != nil {
			return ChainKeyMismatch, fmt.Errorf("delegation %d: %w", i, err)
		}

		// Check scope narrowing (except first delegation which inherits from root)
		if i > 0 {
			if err := ValidateScopeNarrowing(chain[i-1].Delegation.Scopes, d.Scopes); err != nil {
				return ChainScopeViolation, fmt.Errorf("delegation %d: %w", i, err)
			}
		}
	}

	return ChainValid, nil
}

// RevokeDelegation marks a delegation as revoked. In a production system,
// this would also cascade to all child delegations.
func RevokeDelegation(d *Delegation) {
	d.Status = DelegationStatusRevoked
}

// IntersectScopes returns the intersection of two scope lists, used for
// computing the effective scopes when accepting cross-tenant delegations.
func IntersectScopes(a, b []string) ([]string, error) {
	setA, err := NewScopeSet(a)
	if err != nil {
		return nil, err
	}
	setB, err := NewScopeSet(b)
	if err != nil {
		return nil, err
	}

	result := setA.Intersect(setB)
	return result.Strings(), nil
}

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
	"crypto/sha256"
	"encoding/base64"
	"fmt"
	"time"
)

// WitnessRequest represents a request for an agent to witness (co-sign) a claim.
type WitnessRequest struct {
	// RequestID is the unique identifier for this witness request.
	RequestID string `json:"request_id"`

	// ClaimHash is the SHA-256 hash of the claim being witnessed, base64url-encoded.
	ClaimHash string `json:"claim_hash"`

	// ClaimType describes what kind of claim is being witnessed
	// (e.g., "integrity", "provenance", "compliance").
	ClaimType string `json:"claim_type"`

	// SubjectID identifies the entity the claim is about.
	SubjectID string `json:"subject_id"`

	// RequestedBy is the agent ID that initiated the witness request.
	RequestedBy string `json:"requested_by"`

	// RequestedAt is when the request was created.
	RequestedAt time.Time `json:"requested_at"`

	// ExpiresAt is the deadline for providing witness attestations.
	ExpiresAt time.Time `json:"expires_at"`

	// RequiredWitnesses is the minimum number of witnesses needed for quorum.
	RequiredWitnesses int `json:"required_witnesses"`
}

// WitnessAttestation is a single witness's signed attestation of a claim.
type WitnessAttestation struct {
	// WitnessID is the MAIP agent ID of the witnessing agent.
	WitnessID string `json:"witness_id"`

	// ClaimHash is the hash of the claim being attested.
	ClaimHash string `json:"claim_hash"`

	// VerificationMethod describes how the witness independently verified the claim.
	VerificationMethod string `json:"verification_method"`

	// TrustScore is the witness's trust score at the time of attestation.
	TrustScore float64 `json:"trust_score"`

	// SignedAt is when the attestation was created.
	SignedAt time.Time `json:"signed_at"`

	// Signature is the base64url-encoded Ed25519 signature over the attestation.
	Signature string `json:"signature"`
}

// MultiWitnessResult holds the outcome of a multi-witness verification.
type MultiWitnessResult struct {
	// ClaimHash is the claim that was witnessed.
	ClaimHash string `json:"claim_hash"`

	// Attestations is the list of witness attestations collected.
	Attestations []WitnessAttestation `json:"attestations"`

	// QuorumRequired is the minimum number of witnesses needed.
	QuorumRequired int `json:"quorum_required"`

	// QuorumAchieved is the actual number of valid attestations.
	QuorumAchieved int `json:"quorum_achieved"`

	// QuorumMet is true if enough witnesses attested to the claim.
	QuorumMet bool `json:"quorum_met"`

	// CompositeTrustScore is the weighted average trust score of the witnesses.
	CompositeTrustScore float64 `json:"composite_trust_score"`

	// DiversityScore measures organizational diversity of witnesses (0.0-1.0).
	DiversityScore float64 `json:"diversity_score"`
}

// DefaultWitnessWindow is the default time window for collecting witness
// attestations (24 hours per MAIP spec).
const DefaultWitnessWindow = 24 * time.Hour

// NewWitnessRequest creates a new request for witnesses to attest a claim.
func NewWitnessRequest(
	requestID string,
	claimData []byte,
	claimType string,
	subjectID string,
	requestedBy string,
	requiredWitnesses int,
) *WitnessRequest {
	hash := sha256.Sum256(claimData)
	return &WitnessRequest{
		RequestID:         requestID,
		ClaimHash:         base64.RawURLEncoding.EncodeToString(hash[:]),
		ClaimType:         claimType,
		SubjectID:         subjectID,
		RequestedBy:       requestedBy,
		RequestedAt:       time.Now().UTC(),
		ExpiresAt:         time.Now().UTC().Add(DefaultWitnessWindow),
		RequiredWitnesses: requiredWitnesses,
	}
}

// CreateWitnessAttestation creates a signed witness attestation for a claim.
// The witness must independently verify the claim before attesting.
func CreateWitnessAttestation(
	witness *Agent,
	claimHash string,
	verificationMethod string,
	trustScore float64,
) (*WitnessAttestation, error) {
	if witness == nil {
		return nil, fmt.Errorf("witness agent must not be nil")
	}
	if witness.PrivateKey == nil {
		return nil, fmt.Errorf("witness agent %s has no private key", witness.ID)
	}

	attestation := &WitnessAttestation{
		WitnessID:          witness.ID,
		ClaimHash:          claimHash,
		VerificationMethod: verificationMethod,
		TrustScore:         trustScore,
		SignedAt:            time.Now().UTC(),
	}

	// Sign the attestation
	sigData := fmt.Sprintf("%s|%s|%s|%f|%s",
		attestation.WitnessID,
		attestation.ClaimHash,
		attestation.VerificationMethod,
		attestation.TrustScore,
		attestation.SignedAt.Format(time.RFC3339Nano),
	)

	sig := ed25519.Sign(witness.PrivateKey, []byte(sigData))
	attestation.Signature = base64.RawURLEncoding.EncodeToString(sig)

	return attestation, nil
}

// VerifyWitnessAttestation checks the signature on a witness attestation.
func VerifyWitnessAttestation(attestation *WitnessAttestation, witnessPublicKey ed25519.PublicKey) error {
	sigData := fmt.Sprintf("%s|%s|%s|%f|%s",
		attestation.WitnessID,
		attestation.ClaimHash,
		attestation.VerificationMethod,
		attestation.TrustScore,
		attestation.SignedAt.Format(time.RFC3339Nano),
	)

	sigBytes, err := base64.RawURLEncoding.DecodeString(attestation.Signature)
	if err != nil {
		return fmt.Errorf("decoding witness signature: %w", err)
	}

	if !ed25519.Verify(witnessPublicKey, []byte(sigData), sigBytes) {
		return fmt.Errorf("witness attestation signature verification failed for %s", attestation.WitnessID)
	}

	return nil
}

// ComputeConsensus evaluates a set of witness attestations against a request
// and determines if quorum is met. It computes the composite trust score
// as a weighted average of attesting witnesses' trust scores.
func ComputeConsensus(
	request *WitnessRequest,
	attestations []WitnessAttestation,
	witnessKeys map[string]ed25519.PublicKey,
) (*MultiWitnessResult, error) {
	result := &MultiWitnessResult{
		ClaimHash:      request.ClaimHash,
		QuorumRequired: request.RequiredWitnesses,
	}

	var validAttestations []WitnessAttestation
	var totalTrustScore float64
	uniqueTenants := make(map[string]bool)

	for _, att := range attestations {
		// Verify the attestation matches the request
		if att.ClaimHash != request.ClaimHash {
			continue
		}

		// Verify the attestation was within the witness window
		if att.SignedAt.After(request.ExpiresAt) {
			continue
		}

		// Verify signature if key is available
		if key, ok := witnessKeys[att.WitnessID]; ok {
			if err := VerifyWitnessAttestation(&att, key); err != nil {
				continue // Skip invalid attestations
			}
		}

		validAttestations = append(validAttestations, att)
		totalTrustScore += att.TrustScore

		// Extract tenant from agent ID for diversity scoring
		tenant := extractTenant(att.WitnessID)
		if tenant != "" {
			uniqueTenants[tenant] = true
		}
	}

	result.Attestations = validAttestations
	result.QuorumAchieved = len(validAttestations)
	result.QuorumMet = result.QuorumAchieved >= result.QuorumRequired

	if len(validAttestations) > 0 {
		result.CompositeTrustScore = totalTrustScore / float64(len(validAttestations))
	}

	// Compute diversity score
	if result.QuorumRequired > 0 && len(uniqueTenants) > 0 {
		result.DiversityScore = float64(len(uniqueTenants)) / float64(result.QuorumRequired)
		if result.DiversityScore > 1.0 {
			result.DiversityScore = 1.0
		}
	}

	return result, nil
}

// extractTenant extracts the tenant prefix from a MAIP agent ID.
// For IDs in format "maip:<tenant>:<ulid>", returns the tenant prefix.
// For IDs in format "maip-agent:<ulid>", returns empty string.
func extractTenant(agentID string) string {
	// maip:a1b2c3d4:01HXYZ...
	if len(agentID) > 5 && agentID[:5] == "maip:" {
		rest := agentID[5:]
		for i, c := range rest {
			if c == ':' {
				return rest[:i]
			}
		}
	}
	return ""
}

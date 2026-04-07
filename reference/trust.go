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
	"fmt"
	"math"
)

// TrustScore represents a computed trust score on the 0.0 to 1.0 scale.
// The score is composed of weighted factors that evaluate different aspects
// of an agent's trustworthiness.
type TrustScore struct {
	// Overall is the composite trust score in [0.0, 1.0].
	Overall float64 `json:"overall"`

	// Factors contains the individual factor scores before weighting.
	Factors TrustFactors `json:"factors"`

	// AgentID identifies the agent this score belongs to.
	AgentID string `json:"agent_id"`
}

// TrustFactors holds the individual factor scores (each in [0.0, 1.0])
// that compose the overall trust score.
//
// Weight distribution per MAIP reference implementation:
//   - BehavioralCompliance: 35%
//   - ScopeAdherence:       25%
//   - AnomalyScore:         20%
//   - PeerAttestations:     10%
//   - SessionHygiene:       10%
type TrustFactors struct {
	// BehavioralCompliance measures how well the agent follows expected
	// behavioral patterns (action frequency, type distribution, timing).
	// Weight: 0.35
	BehavioralCompliance float64 `json:"behavioral_compliance"`

	// ScopeAdherence measures whether the agent stays within its granted
	// scopes without attempted violations.
	// Weight: 0.25
	ScopeAdherence float64 `json:"scope_adherence"`

	// AnomalyScore is an inverse anomaly indicator. A value of 1.0 means
	// no anomalies detected; 0.0 means severe anomalies. This is subtracted
	// (inverted) in the final computation so higher anomaly = lower trust.
	// Weight: 0.20
	AnomalyScore float64 `json:"anomaly_score"`

	// PeerAttestations measures how frequently other agents/witnesses have
	// co-signed or attested to this agent's actions.
	// Weight: 0.10
	PeerAttestations float64 `json:"peer_attestations"`

	// SessionHygiene measures session management quality: short TTLs, proper
	// scope narrowing, IP restriction usage, clean session termination.
	// Weight: 0.10
	SessionHygiene float64 `json:"session_hygiene"`
}

// Trust factor weights sum to 1.0.
const (
	WeightBehavioralCompliance = 0.35
	WeightScopeAdherence       = 0.25
	WeightAnomalyScore         = 0.20
	WeightPeerAttestations     = 0.10
	WeightSessionHygiene       = 0.10
)

// ComputeTrustScore calculates the composite trust score from individual factors.
// Each factor must be in [0.0, 1.0]. The result is clamped to [0.0, 1.0].
func ComputeTrustScore(agentID string, factors TrustFactors) (*TrustScore, error) {
	// Validate factor ranges
	if err := validateFactor("behavioral_compliance", factors.BehavioralCompliance); err != nil {
		return nil, err
	}
	if err := validateFactor("scope_adherence", factors.ScopeAdherence); err != nil {
		return nil, err
	}
	if err := validateFactor("anomaly_score", factors.AnomalyScore); err != nil {
		return nil, err
	}
	if err := validateFactor("peer_attestations", factors.PeerAttestations); err != nil {
		return nil, err
	}
	if err := validateFactor("session_hygiene", factors.SessionHygiene); err != nil {
		return nil, err
	}

	overall := WeightBehavioralCompliance*factors.BehavioralCompliance +
		WeightScopeAdherence*factors.ScopeAdherence +
		WeightAnomalyScore*factors.AnomalyScore +
		WeightPeerAttestations*factors.PeerAttestations +
		WeightSessionHygiene*factors.SessionHygiene

	// Clamp to [0.0, 1.0]
	overall = clamp(overall, 0.0, 1.0)

	return &TrustScore{
		Overall: overall,
		Factors: factors,
		AgentID: agentID,
	}, nil
}

// TrustLevel returns a qualitative trust level based on the overall score.
//
//	>= 0.8  -> "high"
//	>= 0.5  -> "medium"
//	>= 0.2  -> "low"
//	<  0.2  -> "untrusted"
func (ts *TrustScore) TrustLevel() string {
	switch {
	case ts.Overall >= 0.8:
		return "high"
	case ts.Overall >= 0.5:
		return "medium"
	case ts.Overall >= 0.2:
		return "low"
	default:
		return "untrusted"
	}
}

// MeetsThreshold checks if the trust score meets the given minimum threshold.
func (ts *TrustScore) MeetsThreshold(threshold float64) bool {
	return ts.Overall >= threshold
}

// ApplyDepthDecay reduces the trust score based on delegation depth.
// Each hop reduces the score by depthDecayFactor (default 0.12 per hop,
// equivalent to 12 points on a 0-100 scale per the MAIP spec).
func (ts *TrustScore) ApplyDepthDecay(depth int, depthDecayFactor float64) {
	if depth <= 0 {
		return
	}
	decay := float64(depth) * depthDecayFactor
	ts.Overall = clamp(ts.Overall-decay, 0.0, 1.0)
}

// DefaultDepthDecayFactor is the default trust decay per delegation hop
// (12 points on 0-100 scale = 0.12 on 0-1 scale).
const DefaultDepthDecayFactor = 0.12

// validateFactor checks that a factor value is within [0.0, 1.0].
func validateFactor(name string, value float64) error {
	if math.IsNaN(value) || math.IsInf(value, 0) {
		return fmt.Errorf("trust factor %s must be a finite number, got %v", name, value)
	}
	if value < 0.0 || value > 1.0 {
		return fmt.Errorf("trust factor %s must be in [0.0, 1.0], got %f", name, value)
	}
	return nil
}

// clamp restricts a value to the range [min, max].
func clamp(value, min, max float64) float64 {
	if value < min {
		return min
	}
	if value > max {
		return max
	}
	return value
}

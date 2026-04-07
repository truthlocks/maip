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

// Package reference provides a portable Go reference implementation of the
// Machine Agent Identity Protocol (MAIP). It implements agent identity,
// scoped authorization, session management, receipt signing, trust scoring,
// cross-tenant delegation, proof bundles, and multi-witness attestation.
//
// This package has zero external dependencies beyond the Go standard library,
// crypto/ed25519, and github.com/oklog/ulid/v2 for ULID generation.
package reference

import (
	"crypto/ed25519"
	"crypto/rand"
	"encoding/base64"
	"fmt"
	"io"
	"strings"
	"sync"
	"time"

	"github.com/oklog/ulid/v2"
)

// AgentType classifies the operational mode of an agent.
type AgentType string

const (
	// AgentTypeAutonomous represents a fully autonomous agent.
	AgentTypeAutonomous AgentType = "autonomous"
	// AgentTypeSemiAutonomous represents an agent requiring periodic human approval.
	AgentTypeSemiAutonomous AgentType = "semi_autonomous"
	// AgentTypeSupervisedOnly represents an agent that must have human approval for every action.
	AgentTypeSupervisedOnly AgentType = "supervised_only"
)

// Agent represents a MAIP agent identity with Ed25519 cryptographic keys.
// Agent IDs follow the format: maip-agent:<ulid>
type Agent struct {
	// ID is the globally unique agent identifier in the format maip-agent:<ulid>.
	ID string `json:"id"`

	// Name is a human-readable name for the agent.
	Name string `json:"name"`

	// Type classifies the agent's operational mode.
	Type AgentType `json:"type"`

	// Scopes lists the resource:action permissions granted to this agent.
	Scopes []string `json:"scopes"`

	// PublicKey is the Ed25519 public key for this agent.
	PublicKey ed25519.PublicKey `json:"-"`

	// PrivateKey is the Ed25519 private key for this agent.
	// It is never serialized to JSON.
	PrivateKey ed25519.PrivateKey `json:"-"`

	// PublicKeyBase64 is the base64url-encoded public key for serialization.
	PublicKeyBase64 string `json:"public_key"`

	// CreatedAt is the time the agent was registered.
	CreatedAt time.Time `json:"created_at"`

	// TenantPrefix is the first 8 hex characters of the tenant UUID.
	// Used in the full maip:<tenant>:<ulid> format when tenant context is known.
	TenantPrefix string `json:"tenant_prefix,omitempty"`

	// DelegationDepth tracks how many hops from the root this agent sits.
	DelegationDepth int `json:"delegation_depth"`
}

// AgentRegistry provides thread-safe registration and lookup of MAIP agents.
type AgentRegistry struct {
	mu     sync.RWMutex
	agents map[string]*Agent
}

// NewAgentRegistry creates a new empty agent registry.
func NewAgentRegistry() *AgentRegistry {
	return &AgentRegistry{
		agents: make(map[string]*Agent),
	}
}

// GenerateAgentID produces a new MAIP agent ID in the format maip-agent:<ulid>.
func GenerateAgentID() (string, error) {
	entropy := ulid.Monotonic(rand.Reader, 0)
	id := ulid.MustNew(ulid.Timestamp(time.Now()), entropy)
	return fmt.Sprintf("maip-agent:%s", id.String()), nil
}

// GenerateAgentIDWithTenant produces a MAIP agent ID in the format
// maip:<tenant_prefix>:<ulid> where tenant_prefix is the first 8 hex
// characters of the tenant UUID.
func GenerateAgentIDWithTenant(tenantPrefix string) (string, error) {
	if len(tenantPrefix) != 8 {
		return "", fmt.Errorf("tenant prefix must be exactly 8 hex characters, got %d", len(tenantPrefix))
	}
	for _, c := range tenantPrefix {
		if !((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F')) {
			return "", fmt.Errorf("tenant prefix must be hex characters, got '%c'", c)
		}
	}
	entropy := ulid.Monotonic(rand.Reader, 0)
	id := ulid.MustNew(ulid.Timestamp(time.Now()), entropy)
	return fmt.Sprintf("maip:%s:%s", strings.ToLower(tenantPrefix), id.String()), nil
}

// GenerateKeyPair creates a new Ed25519 key pair suitable for MAIP agent signing.
func GenerateKeyPair() (ed25519.PublicKey, ed25519.PrivateKey, error) {
	return ed25519.GenerateKey(rand.Reader)
}

// GenerateKeyPairFromReader creates a new Ed25519 key pair from a provided
// entropy source. This is useful for deterministic testing.
func GenerateKeyPairFromReader(reader io.Reader) (ed25519.PublicKey, ed25519.PrivateKey, error) {
	return ed25519.GenerateKey(reader)
}

// NewAgent creates and registers a new MAIP agent with freshly generated
// Ed25519 keys and a ULID-based identifier.
func NewAgent(name string, agentType AgentType, scopes []string) (*Agent, error) {
	id, err := GenerateAgentID()
	if err != nil {
		return nil, fmt.Errorf("generating agent ID: %w", err)
	}

	pub, priv, err := GenerateKeyPair()
	if err != nil {
		return nil, fmt.Errorf("generating key pair: %w", err)
	}

	agent := &Agent{
		ID:              id,
		Name:            name,
		Type:            agentType,
		Scopes:          scopes,
		PublicKey:        pub,
		PrivateKey:       priv,
		PublicKeyBase64:  base64.RawURLEncoding.EncodeToString(pub),
		CreatedAt:        time.Now().UTC(),
		DelegationDepth: 0,
	}

	return agent, nil
}

// NewAgentWithTenant creates a new MAIP agent with a tenant-scoped ID in the
// format maip:<tenant_prefix>:<ulid>.
func NewAgentWithTenant(name string, agentType AgentType, scopes []string, tenantPrefix string) (*Agent, error) {
	id, err := GenerateAgentIDWithTenant(tenantPrefix)
	if err != nil {
		return nil, fmt.Errorf("generating tenant agent ID: %w", err)
	}

	pub, priv, err := GenerateKeyPair()
	if err != nil {
		return nil, fmt.Errorf("generating key pair: %w", err)
	}

	agent := &Agent{
		ID:              id,
		Name:            name,
		Type:            agentType,
		Scopes:          scopes,
		PublicKey:        pub,
		PrivateKey:       priv,
		PublicKeyBase64:  base64.RawURLEncoding.EncodeToString(pub),
		CreatedAt:        time.Now().UTC(),
		TenantPrefix:    strings.ToLower(tenantPrefix),
		DelegationDepth: 0,
	}

	return agent, nil
}

// Register adds an agent to the registry. Returns an error if an agent
// with the same ID is already registered.
func (r *AgentRegistry) Register(agent *Agent) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	if _, exists := r.agents[agent.ID]; exists {
		return fmt.Errorf("agent already registered: %s", agent.ID)
	}

	r.agents[agent.ID] = agent
	return nil
}

// Lookup retrieves an agent by ID. Returns nil if not found.
func (r *AgentRegistry) Lookup(id string) *Agent {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.agents[id]
}

// Deregister removes an agent from the registry.
func (r *AgentRegistry) Deregister(id string) bool {
	r.mu.Lock()
	defer r.mu.Unlock()

	if _, exists := r.agents[id]; !exists {
		return false
	}
	delete(r.agents, id)
	return true
}

// List returns all registered agent IDs.
func (r *AgentRegistry) List() []string {
	r.mu.RLock()
	defer r.mu.RUnlock()

	ids := make([]string, 0, len(r.agents))
	for id := range r.agents {
		ids = append(ids, id)
	}
	return ids
}

// Sign signs the given message with the agent's private key using Ed25519.
func (a *Agent) Sign(message []byte) ([]byte, error) {
	if a.PrivateKey == nil {
		return nil, fmt.Errorf("agent %s has no private key", a.ID)
	}
	return ed25519.Sign(a.PrivateKey, message), nil
}

// Verify checks an Ed25519 signature against the agent's public key.
func (a *Agent) Verify(message, signature []byte) bool {
	if a.PublicKey == nil {
		return false
	}
	return ed25519.Verify(a.PublicKey, message, signature)
}

// HasScope checks whether the agent possesses the given scope.
func (a *Agent) HasScope(scope string) bool {
	for _, s := range a.Scopes {
		if s == scope || s == "*:*" {
			return true
		}
		// Check category wildcard: e.g., "attestation:*" matches "attestation:mint"
		parts := strings.SplitN(scope, ":", 2)
		sParts := strings.SplitN(s, ":", 2)
		if len(parts) == 2 && len(sParts) == 2 {
			if sParts[0] == parts[0] && sParts[1] == "*" {
				return true
			}
		}
	}
	return false
}

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
	"crypto/rand"
	"encoding/base64"
	"fmt"
	"net"
	"time"
)

// SessionStatus represents the lifecycle state of a session.
type SessionStatus string

const (
	// SessionStatusActive indicates the session is active and usable.
	SessionStatusActive SessionStatus = "active"
	// SessionStatusExpired indicates the session has passed its TTL.
	SessionStatusExpired SessionStatus = "expired"
	// SessionStatusRevoked indicates the session was explicitly terminated.
	SessionStatusRevoked SessionStatus = "revoked"
)

// Session represents a time-bounded, scope-narrowed execution context for a
// MAIP agent. Sessions enforce temporal limits, scope narrowing, and optional
// IP allowlisting.
type Session struct {
	// ID is a unique session identifier.
	ID string `json:"id"`

	// AgentID is the MAIP agent ID that owns this session.
	AgentID string `json:"agent_id"`

	// Token is a cryptographic bearer token for this session.
	// Generated from 32 bytes of crypto/rand entropy, base64url-encoded.
	Token string `json:"token"`

	// Scopes is the narrowed set of scopes for this session.
	// Must be a subset of the agent's scopes.
	Scopes []string `json:"scopes"`

	// CreatedAt is when the session was created.
	CreatedAt time.Time `json:"created_at"`

	// ExpiresAt is the absolute expiration time.
	ExpiresAt time.Time `json:"expires_at"`

	// IPAllowlist restricts session usage to specific IP addresses or CIDR ranges.
	// An empty list means no IP restriction.
	IPAllowlist []string `json:"ip_allowlist,omitempty"`

	// Status is the current session state.
	Status SessionStatus `json:"status"`

	// parsedNets caches parsed CIDR networks for IP checking.
	parsedNets []*net.IPNet
}

// DefaultSessionTTL is the default session time-to-live (1 hour).
const DefaultSessionTTL = time.Hour

// MaxSessionTTL is the maximum session time-to-live (24 hours).
const MaxSessionTTL = 24 * time.Hour

// SessionOption configures optional session parameters.
type SessionOption func(*Session) error

// WithSessionTTL sets the session time-to-live. Must not exceed MaxSessionTTL.
func WithSessionTTL(ttl time.Duration) SessionOption {
	return func(s *Session) error {
		if ttl <= 0 {
			return fmt.Errorf("session TTL must be positive, got %v", ttl)
		}
		if ttl > MaxSessionTTL {
			return fmt.Errorf("session TTL %v exceeds maximum %v", ttl, MaxSessionTTL)
		}
		s.ExpiresAt = s.CreatedAt.Add(ttl)
		return nil
	}
}

// WithSessionScopes narrows the session scopes. Each scope must be present
// in the agent's scopes (scope narrowing rule).
func WithSessionScopes(scopes []string) SessionOption {
	return func(s *Session) error {
		s.Scopes = scopes
		return nil
	}
}

// WithIPAllowlist restricts the session to the given IP addresses or CIDR ranges.
func WithIPAllowlist(cidrs []string) SessionOption {
	return func(s *Session) error {
		nets := make([]*net.IPNet, 0, len(cidrs))
		for _, cidr := range cidrs {
			_, ipNet, err := net.ParseCIDR(cidr)
			if err != nil {
				// Try as a plain IP address
				ip := net.ParseIP(cidr)
				if ip == nil {
					return fmt.Errorf("invalid IP/CIDR %q: %w", cidr, err)
				}
				mask := net.CIDRMask(128, 128)
				if ip.To4() != nil {
					mask = net.CIDRMask(32, 32)
				}
				ipNet = &net.IPNet{IP: ip, Mask: mask}
			}
			nets = append(nets, ipNet)
		}
		s.IPAllowlist = cidrs
		s.parsedNets = nets
		return nil
	}
}

// generateSessionToken produces a cryptographically random session token.
func generateSessionToken() (string, error) {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return "", fmt.Errorf("generating session token: %w", err)
	}
	return base64.RawURLEncoding.EncodeToString(b), nil
}

// generateSessionID produces a unique session ID.
func generateSessionID() (string, error) {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		return "", fmt.Errorf("generating session ID: %w", err)
	}
	return fmt.Sprintf("sess_%s", base64.RawURLEncoding.EncodeToString(b)), nil
}

// CreateSession creates a new session for the given agent with optional
// configuration. The session's scopes must be a subset of the agent's scopes.
func CreateSession(agent *Agent, opts ...SessionOption) (*Session, error) {
	if agent == nil {
		return nil, fmt.Errorf("agent must not be nil")
	}

	id, err := generateSessionID()
	if err != nil {
		return nil, err
	}

	token, err := generateSessionToken()
	if err != nil {
		return nil, err
	}

	now := time.Now().UTC()
	session := &Session{
		ID:        id,
		AgentID:   agent.ID,
		Token:     token,
		Scopes:    agent.Scopes, // default: inherit all agent scopes
		CreatedAt: now,
		ExpiresAt: now.Add(DefaultSessionTTL),
		Status:    SessionStatusActive,
	}

	for _, opt := range opts {
		if err := opt(session); err != nil {
			return nil, fmt.Errorf("applying session option: %w", err)
		}
	}

	// Validate scope narrowing: session scopes must be subset of agent scopes
	if err := ValidateScopeNarrowing(agent.Scopes, session.Scopes); err != nil {
		return nil, fmt.Errorf("session scope narrowing violation: %w", err)
	}

	return session, nil
}

// IsActive returns true if the session is active and not expired.
func (s *Session) IsActive() bool {
	if s.Status != SessionStatusActive {
		return false
	}
	return time.Now().UTC().Before(s.ExpiresAt)
}

// IsExpired returns true if the session has passed its expiration time.
func (s *Session) IsExpired() bool {
	return time.Now().UTC().After(s.ExpiresAt)
}

// Revoke terminates the session immediately.
func (s *Session) Revoke() {
	s.Status = SessionStatusRevoked
}

// CheckIP verifies that the given IP address is allowed by the session's
// IP allowlist. If no allowlist is configured, all IPs are allowed.
func (s *Session) CheckIP(ipStr string) bool {
	if len(s.parsedNets) == 0 {
		return true
	}

	ip := net.ParseIP(ipStr)
	if ip == nil {
		return false
	}

	for _, ipNet := range s.parsedNets {
		if ipNet.Contains(ip) {
			return true
		}
	}
	return false
}

// HasScope checks whether the session grants the given scope.
func (s *Session) HasScope(scope string) bool {
	ss, err := NewScopeSet(s.Scopes)
	if err != nil {
		return false
	}
	return ss.ContainsString(scope)
}

// RemainingTTL returns the time remaining before the session expires.
// Returns zero if the session is already expired.
func (s *Session) RemainingTTL() time.Duration {
	remaining := time.Until(s.ExpiresAt)
	if remaining < 0 {
		return 0
	}
	return remaining
}

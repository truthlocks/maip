// Copyright 2026 Truthlocks Inc.
// Licensed under the Apache License, Version 2.0

package maip

// Scope defines the permissions and boundaries for an agent.
type Scope struct {
	Actions     []string          `json:"actions"`
	Resources   []string          `json:"resources"`
	Constraints map[string]string `json:"constraints,omitempty"`
}

// AgentStatus represents the lifecycle state of an agent.
type AgentStatus string

const (
	AgentStatusActive    AgentStatus = "active"
	AgentStatusSuspended AgentStatus = "suspended"
	AgentStatusRevoked   AgentStatus = "revoked"
)

// Agent represents a registered machine agent identity.
type Agent struct {
	ID        string            `json:"id"`
	Name      string            `json:"name"`
	Status    AgentStatus       `json:"status"`
	Scope     Scope             `json:"scope"`
	PublicKey string            `json:"publicKey"`
	Metadata  map[string]string `json:"metadata"`
	CreatedAt string            `json:"createdAt"`
	UpdatedAt string            `json:"updatedAt"`
}

// SessionStatus represents the lifecycle state of a session.
type SessionStatus string

const (
	SessionStatusActive     SessionStatus = "active"
	SessionStatusTerminated SessionStatus = "terminated"
	SessionStatusExpired    SessionStatus = "expired"
)

// Session represents an authenticated agent session.
type Session struct {
	ID        string        `json:"id"`
	AgentID   string        `json:"agentId"`
	Status    SessionStatus `json:"status"`
	Scope     Scope         `json:"scope"`
	ExpiresAt string        `json:"expiresAt"`
	CreatedAt string        `json:"createdAt"`
}

// TrustLevel represents the computed trust tier.
type TrustLevel string

const (
	TrustLevelCritical TrustLevel = "critical"
	TrustLevelLow      TrustLevel = "low"
	TrustLevelMedium   TrustLevel = "medium"
	TrustLevelHigh     TrustLevel = "high"
	TrustLevelVerified TrustLevel = "verified"
)

// TrustFactor is a single factor contributing to a trust score.
type TrustFactor struct {
	Name        string  `json:"name"`
	Weight      float64 `json:"weight"`
	Value       float64 `json:"value"`
	Description string  `json:"description"`
}

// TrustScore represents the computed trust level for an agent.
type TrustScore struct {
	AgentID    string        `json:"agentId"`
	Score      float64       `json:"score"`
	Level      TrustLevel    `json:"level"`
	Factors    []TrustFactor `json:"factors"`
	ComputedAt string        `json:"computedAt"`
}

// DelegationStatus represents the lifecycle state of a delegation.
type DelegationStatus string

const (
	DelegationStatusOffered  DelegationStatus = "offered"
	DelegationStatusAccepted DelegationStatus = "accepted"
	DelegationStatusRejected DelegationStatus = "rejected"
	DelegationStatusRevoked  DelegationStatus = "revoked"
	DelegationStatusExpired  DelegationStatus = "expired"
)

// Delegation represents a trust delegation from one agent to another.
type Delegation struct {
	ID          string           `json:"id"`
	FromAgentID string           `json:"fromAgentId"`
	ToAgentID   string           `json:"toAgentId"`
	Scope       Scope            `json:"scope"`
	Status      DelegationStatus `json:"status"`
	ExpiresAt   string           `json:"expiresAt"`
	CreatedAt   string           `json:"createdAt"`
}

// OrchestrationStatus represents the lifecycle state of an orchestration.
type OrchestrationStatus string

const (
	OrchestrationStatusPending   OrchestrationStatus = "pending"
	OrchestrationStatusRunning   OrchestrationStatus = "running"
	OrchestrationStatusCompleted OrchestrationStatus = "completed"
	OrchestrationStatusFailed    OrchestrationStatus = "failed"
	OrchestrationStatusCancelled OrchestrationStatus = "cancelled"
)

// Orchestration represents a multi-agent orchestration session.
type Orchestration struct {
	ID                  string              `json:"id"`
	CoordinatorAgentID  string              `json:"coordinatorAgentId"`
	ParticipantAgentIDs []string            `json:"participantAgentIds"`
	Status              OrchestrationStatus `json:"status"`
	Scope               Scope               `json:"scope"`
	Result              map[string]any      `json:"result,omitempty"`
	CreatedAt           string              `json:"createdAt"`
	CompletedAt         *string             `json:"completedAt,omitempty"`
}

// Receipt is a cryptographic proof of an action taken by an agent.
type Receipt struct {
	ID         string            `json:"id"`
	AgentID    string            `json:"agentId"`
	SessionID  string            `json:"sessionId"`
	Action     string            `json:"action"`
	ResourceID string            `json:"resourceId"`
	Timestamp  string            `json:"timestamp"`
	Signature  string            `json:"signature"`
	Metadata   map[string]string `json:"metadata"`
}

// Bundle is a collection of receipts that can be verified offline.
type Bundle struct {
	ID        string    `json:"id"`
	Receipts  []Receipt `json:"receipts"`
	RootHash  string    `json:"rootHash"`
	Signature string    `json:"signature"`
	CreatedAt string    `json:"createdAt"`
}

// ViolationSeverity represents the severity of a guardrail violation.
type ViolationSeverity string

const (
	ViolationSeverityInfo     ViolationSeverity = "info"
	ViolationSeverityWarning  ViolationSeverity = "warning"
	ViolationSeverityError    ViolationSeverity = "error"
	ViolationSeverityCritical ViolationSeverity = "critical"
)

// GuardrailViolation represents a guardrail rule violation.
type GuardrailViolation struct {
	Rule     string            `json:"rule"`
	Severity ViolationSeverity `json:"severity"`
	Message  string            `json:"message"`
}

// GuardrailResult represents the outcome of a guardrails check.
type GuardrailResult struct {
	Allowed    bool                 `json:"allowed"`
	Violations []GuardrailViolation `json:"violations"`
	CheckedAt  string               `json:"checkedAt"`
}

// ListResponse is a paginated list response.
type ListResponse[T any] struct {
	Items  []T `json:"items"`
	Total  int `json:"total"`
	Offset int `json:"offset"`
	Limit  int `json:"limit"`
}

// --- Request types ---

// CreateAgentRequest contains options for creating an agent.
type CreateAgentRequest struct {
	Name      string            `json:"name"`
	Scope     Scope             `json:"scope"`
	PublicKey string            `json:"publicKey"`
	Metadata  map[string]string `json:"metadata,omitempty"`
}

// CreateSessionRequest contains options for creating a session.
type CreateSessionRequest struct {
	AgentID    string `json:"agentId"`
	Scope      *Scope `json:"scope,omitempty"`
	TTLSeconds *int   `json:"ttlSeconds,omitempty"`
}

// ComputeTrustScoreRequest contains options for computing a trust score.
type ComputeTrustScoreRequest struct {
	AgentID string           `json:"agentId"`
	Factors []map[string]any `json:"factors,omitempty"`
}

// OfferDelegationRequest contains options for offering a delegation.
type OfferDelegationRequest struct {
	FromAgentID string `json:"fromAgentId"`
	ToAgentID   string `json:"toAgentId"`
	Scope       Scope  `json:"scope"`
	TTLSeconds  *int   `json:"ttlSeconds,omitempty"`
}

// ExecuteOrchestrationRequest contains options for executing an orchestration.
type ExecuteOrchestrationRequest struct {
	CoordinatorAgentID  string         `json:"coordinatorAgentId"`
	ParticipantAgentIDs []string       `json:"participantAgentIds"`
	Scope               Scope          `json:"scope"`
	Parameters          map[string]any `json:"parameters,omitempty"`
}

// CheckGuardrailsRequest contains options for checking guardrails.
type CheckGuardrailsRequest struct {
	AgentID    string         `json:"agentId"`
	Action     string         `json:"action"`
	ResourceID string         `json:"resourceId"`
	Context    map[string]any `json:"context,omitempty"`
}

// ListAgentsOptions contains options for listing agents.
type ListAgentsOptions struct {
	Status *AgentStatus
	Offset *int
	Limit  *int
}

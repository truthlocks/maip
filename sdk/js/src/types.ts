// Copyright 2026 Truthlocks Inc.
// Licensed under the Apache License, Version 2.0

/** Scope defines the permissions and boundaries for an agent. */
export interface Scope {
  /** Allowed actions (e.g., "read", "write", "execute"). */
  actions: string[];
  /** Resource patterns the scope applies to. */
  resources: string[];
  /** Optional constraints (key-value metadata). */
  constraints?: Record<string, string>;
}

/** Agent represents a registered machine agent identity. */
export interface Agent {
  id: string;
  name: string;
  status: AgentStatus;
  scope: Scope;
  publicKey: string;
  metadata: Record<string, string>;
  createdAt: string;
  updatedAt: string;
}

export type AgentStatus = "active" | "suspended" | "revoked";

/** Session represents an authenticated agent session. */
export interface Session {
  id: string;
  agentId: string;
  status: SessionStatus;
  scope: Scope;
  expiresAt: string;
  createdAt: string;
}

export type SessionStatus = "active" | "terminated" | "expired";

/** TrustScore represents the computed trust level for an agent. */
export interface TrustScore {
  agentId: string;
  score: number;
  level: TrustLevel;
  factors: TrustFactor[];
  computedAt: string;
}

export type TrustLevel = "critical" | "low" | "medium" | "high" | "verified";

export interface TrustFactor {
  name: string;
  weight: number;
  value: number;
  description: string;
}

/** Delegation represents a trust delegation from one agent to another. */
export interface Delegation {
  id: string;
  fromAgentId: string;
  toAgentId: string;
  scope: Scope;
  status: DelegationStatus;
  expiresAt: string;
  createdAt: string;
}

export type DelegationStatus = "offered" | "accepted" | "rejected" | "revoked" | "expired";

/** Orchestration represents a multi-agent orchestration session. */
export interface Orchestration {
  id: string;
  coordinatorAgentId: string;
  participantAgentIds: string[];
  status: OrchestrationStatus;
  scope: Scope;
  result?: Record<string, unknown>;
  createdAt: string;
  completedAt?: string;
}

export type OrchestrationStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

/** Receipt is a cryptographic proof of an action taken by an agent. */
export interface Receipt {
  id: string;
  agentId: string;
  sessionId: string;
  action: string;
  resourceId: string;
  timestamp: string;
  signature: string;
  metadata: Record<string, string>;
}

/** Bundle is a collection of receipts that can be verified offline. */
export interface Bundle {
  id: string;
  receipts: Receipt[];
  rootHash: string;
  signature: string;
  createdAt: string;
}

/** GuardrailResult represents the outcome of a guardrails check. */
export interface GuardrailResult {
  allowed: boolean;
  violations: GuardrailViolation[];
  checkedAt: string;
}

export interface GuardrailViolation {
  rule: string;
  severity: "info" | "warning" | "error" | "critical";
  message: string;
}

/** Options for creating an agent. */
export interface CreateAgentRequest {
  name: string;
  scope: Scope;
  publicKey: string;
  metadata?: Record<string, string>;
}

/** Options for creating a session. */
export interface CreateSessionRequest {
  agentId: string;
  scope?: Scope;
  ttlSeconds?: number;
}

/** Options for computing a trust score. */
export interface ComputeTrustScoreRequest {
  agentId: string;
  factors?: Partial<TrustFactor>[];
}

/** Options for offering a delegation. */
export interface OfferDelegationRequest {
  fromAgentId: string;
  toAgentId: string;
  scope: Scope;
  ttlSeconds?: number;
}

/** Options for executing an orchestration. */
export interface ExecuteOrchestrationRequest {
  coordinatorAgentId: string;
  participantAgentIds: string[];
  scope: Scope;
  parameters?: Record<string, unknown>;
}

/** Options for checking guardrails. */
export interface CheckGuardrailsRequest {
  agentId: string;
  action: string;
  resourceId: string;
  context?: Record<string, unknown>;
}

/** Paginated list response. */
export interface ListResponse<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}

/** Options for listing agents. */
export interface ListAgentsOptions {
  status?: AgentStatus;
  offset?: number;
  limit?: number;
}

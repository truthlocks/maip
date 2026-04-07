# Copyright 2026 Truthlocks Inc.
# Licensed under the Apache License, Version 2.0

"""Data types for the MAIP SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, Optional, TypeVar

T = TypeVar("T")


class AgentStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class SessionStatus(str, Enum):
    ACTIVE = "active"
    TERMINATED = "terminated"
    EXPIRED = "expired"


class TrustLevel(str, Enum):
    CRITICAL = "critical"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERIFIED = "verified"


class DelegationStatus(str, Enum):
    OFFERED = "offered"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REVOKED = "revoked"
    EXPIRED = "expired"


class OrchestrationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ViolationSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True)
class Scope:
    """Permissions and boundaries for an agent."""
    actions: list[str]
    resources: list[str]
    constraints: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Agent:
    """A registered machine agent identity."""
    id: str
    name: str
    status: AgentStatus
    scope: Scope
    public_key: str
    metadata: dict[str, str]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class Session:
    """An authenticated agent session."""
    id: str
    agent_id: str
    status: SessionStatus
    scope: Scope
    expires_at: str
    created_at: str


@dataclass(frozen=True)
class TrustFactor:
    """A single factor contributing to a trust score."""
    name: str
    weight: float
    value: float
    description: str


@dataclass(frozen=True)
class TrustScore:
    """Computed trust level for an agent."""
    agent_id: str
    score: float
    level: TrustLevel
    factors: list[TrustFactor]
    computed_at: str


@dataclass(frozen=True)
class Delegation:
    """Trust delegation from one agent to another."""
    id: str
    from_agent_id: str
    to_agent_id: str
    scope: Scope
    status: DelegationStatus
    expires_at: str
    created_at: str


@dataclass(frozen=True)
class Orchestration:
    """A multi-agent orchestration session."""
    id: str
    coordinator_agent_id: str
    participant_agent_ids: list[str]
    status: OrchestrationStatus
    scope: Scope
    created_at: str
    result: Optional[dict[str, Any]] = None
    completed_at: Optional[str] = None


@dataclass(frozen=True)
class Receipt:
    """Cryptographic proof of an action taken by an agent."""
    id: str
    agent_id: str
    session_id: str
    action: str
    resource_id: str
    timestamp: str
    signature: str
    metadata: dict[str, str]


@dataclass(frozen=True)
class Bundle:
    """Collection of receipts that can be verified offline."""
    id: str
    receipts: list[Receipt]
    root_hash: str
    signature: str
    created_at: str


@dataclass(frozen=True)
class GuardrailViolation:
    """A guardrail rule violation."""
    rule: str
    severity: ViolationSeverity
    message: str


@dataclass(frozen=True)
class GuardrailResult:
    """Outcome of a guardrails check."""
    allowed: bool
    violations: list[GuardrailViolation]
    checked_at: str


@dataclass(frozen=True)
class ListResponse(Generic[T]):
    """Paginated list response."""
    items: list[T]
    total: int
    offset: int
    limit: int


@dataclass(frozen=True)
class CreateAgentRequest:
    """Options for creating an agent."""
    name: str
    scope: Scope
    public_key: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CreateSessionRequest:
    """Options for creating a session."""
    agent_id: str
    scope: Optional[Scope] = None
    ttl_seconds: Optional[int] = None


@dataclass(frozen=True)
class ComputeTrustScoreRequest:
    """Options for computing a trust score."""
    agent_id: str
    factors: Optional[list[dict[str, Any]]] = None


@dataclass(frozen=True)
class OfferDelegationRequest:
    """Options for offering a delegation."""
    from_agent_id: str
    to_agent_id: str
    scope: Scope
    ttl_seconds: Optional[int] = None


@dataclass(frozen=True)
class ExecuteOrchestrationRequest:
    """Options for executing an orchestration."""
    coordinator_agent_id: str
    participant_agent_ids: list[str]
    scope: Scope
    parameters: Optional[dict[str, Any]] = None


@dataclass(frozen=True)
class CheckGuardrailsRequest:
    """Options for checking guardrails."""
    agent_id: str
    action: str
    resource_id: str
    context: Optional[dict[str, Any]] = None

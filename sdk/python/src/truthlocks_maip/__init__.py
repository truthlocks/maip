# Copyright 2026 Truthlocks Inc.
# Licensed under the Apache License, Version 2.0

"""Python SDK for the MAIP (Machine Agent Identity Protocol)."""

from truthlocks_maip.client import MaipClient
from truthlocks_maip.errors import (
    LimitExceededError,
    MaipError,
    NotFoundError,
    UnauthorizedError,
    VerificationError,
)
from truthlocks_maip.types import (
    Agent,
    AgentStatus,
    Bundle,
    CheckGuardrailsRequest,
    ComputeTrustScoreRequest,
    CreateAgentRequest,
    CreateSessionRequest,
    Delegation,
    DelegationStatus,
    ExecuteOrchestrationRequest,
    GuardrailResult,
    GuardrailViolation,
    ListResponse,
    OfferDelegationRequest,
    Orchestration,
    OrchestrationStatus,
    Receipt,
    Scope,
    Session,
    SessionStatus,
    TrustFactor,
    TrustLevel,
    TrustScore,
)
from truthlocks_maip.verify import verify_bundle, verify_receipt_hash

__all__ = [
    "MaipClient",
    "MaipError",
    "LimitExceededError",
    "UnauthorizedError",
    "NotFoundError",
    "VerificationError",
    "Agent",
    "AgentStatus",
    "Bundle",
    "CheckGuardrailsRequest",
    "ComputeTrustScoreRequest",
    "CreateAgentRequest",
    "CreateSessionRequest",
    "Delegation",
    "DelegationStatus",
    "ExecuteOrchestrationRequest",
    "GuardrailResult",
    "GuardrailViolation",
    "ListResponse",
    "OfferDelegationRequest",
    "Orchestration",
    "OrchestrationStatus",
    "Receipt",
    "Scope",
    "Session",
    "SessionStatus",
    "TrustFactor",
    "TrustLevel",
    "TrustScore",
    "verify_bundle",
    "verify_receipt_hash",
]

__version__ = "0.1.0"

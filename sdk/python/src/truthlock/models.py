"""Truthlock SDK data models and enums."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Algorithm(str, Enum):
    ED25519 = "Ed25519"
    ES256 = "ES256"
    RS256 = "RS256"


class Verdict(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    REVOKED = "revoked"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


class AttestationStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


@dataclass
class Issuer:
    id: str
    name: str
    status: str
    did: str | None = None
    tenant_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class IssuerKey:
    kid: str
    issuer_id: str
    alg: str
    public_key: str
    status: str
    created_at: str | None = None


@dataclass
class Attestation:
    attestation_id: str
    issuer_id: str
    kid: str
    alg: str
    status: str
    payload_hash: str | None = None
    created_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class VerifyResult:
    verdict: Verdict
    attestation_id: str
    issuer_id: str | None = None
    issued_at: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProofBundle:
    header: dict[str, Any] = field(default_factory=dict)
    attestation: dict[str, Any] = field(default_factory=dict)
    proofs: list[dict[str, Any]] = field(default_factory=list)
    issuer_certificate: dict[str, Any] = field(default_factory=dict)
    bundle_signature: dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Receipt Types (Ticket 81: Receipt Canonical Event Schema v2)
# ============================================================================


class ReceiptStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"


class RetentionPolicy(str, Enum):
    STANDARD = "standard"
    EXTENDED = "extended"
    PERMANENT = "permanent"


@dataclass
class ReceiptSignature:
    alg: str
    kid: str
    value: str


@dataclass
class ReceiptLog:
    log_id: str
    leaf_index: int
    leaf_hash: str


@dataclass
class ReceiptEvent:
    receipt_id: str
    receipt_type: str
    receipt_version: str
    status: str
    issued_at: str
    tenant_id: str
    issuer_id: str
    payload_hash: str
    signature: dict[str, Any] = field(default_factory=dict)
    log: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReceiptType:
    id: str
    name: str
    display_name: str
    version: str
    status: str
    schema: dict[str, Any] = field(default_factory=dict)
    description: str | None = None
    created_at: str | None = None


@dataclass
class MintReceiptRequest:
    issuer_id: str
    kid: str
    alg: str
    receipt_type: str
    subject: str
    payload: dict[str, Any]
    receipt_version: str = "1.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)
    retention_policy: str = RetentionPolicy.STANDARD


@dataclass
class ListReceiptsFilter:
    receipt_type: str | None = None
    issuer_id: str | None = None
    status: str | None = None
    limit: int = 20
    offset: int = 0

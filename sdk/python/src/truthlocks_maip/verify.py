# Copyright 2026 Truthlocks Inc.
# Licensed under the Apache License, Version 2.0

"""Offline bundle and receipt verification.

All functions in this module are pure and make no network calls.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from truthlocks_maip.errors import VerificationError
from truthlocks_maip.types import Bundle, Receipt


def _sha256_hex(data: str) -> str:
    """Compute SHA-256 hex digest of a string."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _hash_receipt(receipt: Receipt) -> str:
    """Compute the canonical hash of a receipt for Merkle tree inclusion."""
    canonical = json.dumps(
        {
            "action": receipt.action,
            "agentId": receipt.agent_id,
            "id": receipt.id,
            "metadata": receipt.metadata,
            "resourceId": receipt.resource_id,
            "sessionId": receipt.session_id,
            "signature": receipt.signature,
            "timestamp": receipt.timestamp,
        },
        sort_keys=False,
        separators=(",", ":"),
    )
    return _sha256_hex(canonical)


def _compute_merkle_root(leaf_hashes: list[str]) -> str:
    """Compute the Merkle root from an ordered list of leaf hashes."""
    if not leaf_hashes:
        return _sha256_hex("")
    if len(leaf_hashes) == 1:
        return leaf_hashes[0]

    level = list(leaf_hashes)
    while len(level) > 1:
        next_level: list[str] = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i + 1] if i + 1 < len(level) else left
            next_level.append(_sha256_hex(left + right))
        level = next_level
    return level[0]


@dataclass(frozen=True)
class VerifyBundleResult:
    """Result of a bundle verification."""
    valid: bool
    computed_root_hash: str
    declared_root_hash: str
    receipt_count: int
    receipt_hashes: list[str]


def verify_bundle(bundle: Bundle) -> VerifyBundleResult:
    """Verify a receipt bundle offline.

    Checks that the Merkle root hash matches the receipts in the bundle.
    Does NOT verify cryptographic signatures against agent public keys
    (that requires network access to retrieve keys).

    Pure function: no network calls are made.

    Args:
        bundle: The bundle to verify.

    Returns:
        The verification result.

    Raises:
        VerificationError: If the bundle structure is invalid.
    """
    if not bundle.receipts or not isinstance(bundle.receipts, list):
        raise VerificationError("Bundle has no receipts list")
    if not bundle.root_hash:
        raise VerificationError("Bundle has no root_hash")

    receipt_hashes: list[str] = []
    for receipt in bundle.receipts:
        if not receipt.id or not receipt.agent_id or not receipt.timestamp:
            raise VerificationError(
                f"Receipt is missing required fields: {receipt}"
            )
        receipt_hashes.append(_hash_receipt(receipt))

    computed_root_hash = _compute_merkle_root(receipt_hashes)

    return VerifyBundleResult(
        valid=computed_root_hash == bundle.root_hash,
        computed_root_hash=computed_root_hash,
        declared_root_hash=bundle.root_hash,
        receipt_count=len(bundle.receipts),
        receipt_hashes=receipt_hashes,
    )


def verify_receipt_hash(receipt: Receipt, expected_hash: str) -> bool:
    """Verify a single receipt hash against an expected value.

    Useful for spot-checking individual receipts from a bundle.

    Args:
        receipt: The receipt to hash.
        expected_hash: The expected SHA-256 hex hash.

    Returns:
        True if the computed hash matches the expected hash.
    """
    computed = _hash_receipt(receipt)
    return computed == expected_hash

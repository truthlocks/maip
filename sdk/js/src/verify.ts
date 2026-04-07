// Copyright 2026 Truthlocks Inc.
// Licensed under the Apache License, Version 2.0

import type { Bundle, Receipt } from "./types.js";
import { VerificationError } from "./errors.js";

/**
 * Compute a SHA-256 hex digest of the given data using the Web Crypto API.
 * Works in Node.js 18+ and modern browsers.
 */
async function sha256Hex(data: string): Promise<string> {
  const encoder = new TextEncoder();
  const buffer = await crypto.subtle.digest("SHA-256", encoder.encode(data));
  return Array.from(new Uint8Array(buffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * Compute the canonical hash of a receipt for inclusion in the Merkle tree.
 * The canonical form is the JSON-serialized receipt fields in deterministic order.
 */
async function hashReceipt(receipt: Receipt): Promise<string> {
  const canonical = JSON.stringify({
    action: receipt.action,
    agentId: receipt.agentId,
    id: receipt.id,
    metadata: receipt.metadata,
    resourceId: receipt.resourceId,
    sessionId: receipt.sessionId,
    signature: receipt.signature,
    timestamp: receipt.timestamp,
  });
  return sha256Hex(canonical);
}

/**
 * Compute the Merkle root hash from an ordered list of leaf hashes.
 */
async function computeMerkleRoot(leafHashes: string[]): Promise<string> {
  if (leafHashes.length === 0) {
    return sha256Hex("");
  }
  if (leafHashes.length === 1) {
    return leafHashes[0]!;
  }

  let level = [...leafHashes];
  while (level.length > 1) {
    const next: string[] = [];
    for (let i = 0; i < level.length; i += 2) {
      const left = level[i]!;
      const right = i + 1 < level.length ? level[i + 1]! : left;
      next.push(await sha256Hex(left + right));
    }
    level = next;
  }
  return level[0]!;
}

/**
 * Result of a bundle verification.
 */
export interface VerifyBundleResult {
  /** Whether the bundle's Merkle root matches the computed root. */
  valid: boolean;
  /** The computed Merkle root hash. */
  computedRootHash: string;
  /** The declared root hash from the bundle. */
  declaredRootHash: string;
  /** Number of receipts verified. */
  receiptCount: number;
  /** Per-receipt hashes in order. */
  receiptHashes: string[];
}

/**
 * Verify a receipt bundle offline. This checks that the Merkle root hash
 * matches the receipts in the bundle. It does NOT verify cryptographic
 * signatures against agent public keys (that requires network access to
 * retrieve keys).
 *
 * Pure function: no network calls are made.
 *
 * @param bundle - The bundle to verify.
 * @returns The verification result.
 * @throws {VerificationError} If the bundle structure is invalid.
 */
export async function verifyBundle(bundle: Bundle): Promise<VerifyBundleResult> {
  if (!bundle.receipts || !Array.isArray(bundle.receipts)) {
    throw new VerificationError("Bundle has no receipts array");
  }
  if (!bundle.rootHash) {
    throw new VerificationError("Bundle has no rootHash");
  }

  const receiptHashes: string[] = [];
  for (const receipt of bundle.receipts) {
    if (!receipt.id || !receipt.agentId || !receipt.timestamp) {
      throw new VerificationError(
        `Receipt is missing required fields: ${JSON.stringify(receipt)}`
      );
    }
    receiptHashes.push(await hashReceipt(receipt));
  }

  const computedRootHash = await computeMerkleRoot(receiptHashes);

  return {
    valid: computedRootHash === bundle.rootHash,
    computedRootHash,
    declaredRootHash: bundle.rootHash,
    receiptCount: bundle.receipts.length,
    receiptHashes,
  };
}

/**
 * Verify a single receipt's hash against an expected value.
 * Useful for spot-checking individual receipts from a bundle.
 *
 * @param receipt - The receipt to hash.
 * @param expectedHash - The expected SHA-256 hex hash.
 * @returns True if the computed hash matches the expected hash.
 */
export async function verifyReceiptHash(
  receipt: Receipt,
  expectedHash: string
): Promise<boolean> {
  const computed = await hashReceipt(receipt);
  return computed === expectedHash;
}

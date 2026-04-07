// Copyright 2026 Truthlocks Inc.
// Licensed under the Apache License, Version 2.0

package maip

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
)

// VerifyBundleResult holds the result of a bundle verification.
type VerifyBundleResult struct {
	// Valid is true if the computed Merkle root matches the declared root.
	Valid bool
	// ComputedRootHash is the Merkle root computed from the receipts.
	ComputedRootHash string
	// DeclaredRootHash is the root hash declared in the bundle.
	DeclaredRootHash string
	// ReceiptCount is the number of receipts in the bundle.
	ReceiptCount int
	// ReceiptHashes contains per-receipt hashes in order.
	ReceiptHashes []string
}

// sha256Hex computes the SHA-256 hex digest of a string.
func sha256Hex(data string) string {
	h := sha256.Sum256([]byte(data))
	return fmt.Sprintf("%x", h)
}

// canonicalReceipt is the deterministic JSON structure for receipt hashing.
type canonicalReceipt struct {
	Action     string            `json:"action"`
	AgentID    string            `json:"agentId"`
	ID         string            `json:"id"`
	Metadata   map[string]string `json:"metadata"`
	ResourceID string            `json:"resourceId"`
	SessionID  string            `json:"sessionId"`
	Signature  string            `json:"signature"`
	Timestamp  string            `json:"timestamp"`
}

// hashReceipt computes the canonical hash of a receipt.
func hashReceipt(r Receipt) (string, error) {
	canonical := canonicalReceipt{
		Action:     r.Action,
		AgentID:    r.AgentID,
		ID:         r.ID,
		Metadata:   r.Metadata,
		ResourceID: r.ResourceID,
		SessionID:  r.SessionID,
		Signature:  r.Signature,
		Timestamp:  r.Timestamp,
	}
	data, err := json.Marshal(canonical)
	if err != nil {
		return "", fmt.Errorf("failed to marshal receipt: %w", err)
	}
	return sha256Hex(string(data)), nil
}

// computeMerkleRoot computes the Merkle root from an ordered list of leaf hashes.
func computeMerkleRoot(leafHashes []string) string {
	if len(leafHashes) == 0 {
		return sha256Hex("")
	}
	if len(leafHashes) == 1 {
		return leafHashes[0]
	}

	level := make([]string, len(leafHashes))
	copy(level, leafHashes)

	for len(level) > 1 {
		var next []string
		for i := 0; i < len(level); i += 2 {
			left := level[i]
			right := left
			if i+1 < len(level) {
				right = level[i+1]
			}
			next = append(next, sha256Hex(left+right))
		}
		level = next
	}
	return level[0]
}

// VerifyBundle verifies a receipt bundle offline. It checks that the Merkle
// root hash matches the receipts in the bundle. It does NOT verify
// cryptographic signatures against agent public keys (that requires network
// access to retrieve keys).
//
// This is a pure function: no network calls are made.
func VerifyBundle(bundle Bundle) (*VerifyBundleResult, error) {
	if len(bundle.Receipts) == 0 {
		return nil, NewVerificationError("bundle has no receipts")
	}
	if bundle.RootHash == "" {
		return nil, NewVerificationError("bundle has no root hash")
	}

	receiptHashes := make([]string, 0, len(bundle.Receipts))
	for _, receipt := range bundle.Receipts {
		if receipt.ID == "" || receipt.AgentID == "" || receipt.Timestamp == "" {
			return nil, NewVerificationError(
				fmt.Sprintf("receipt is missing required fields: %+v", receipt),
			)
		}
		h, err := hashReceipt(receipt)
		if err != nil {
			return nil, NewVerificationError(
				fmt.Sprintf("failed to hash receipt %s: %v", receipt.ID, err),
			)
		}
		receiptHashes = append(receiptHashes, h)
	}

	computedRoot := computeMerkleRoot(receiptHashes)

	return &VerifyBundleResult{
		Valid:            computedRoot == bundle.RootHash,
		ComputedRootHash: computedRoot,
		DeclaredRootHash: bundle.RootHash,
		ReceiptCount:     len(bundle.Receipts),
		ReceiptHashes:    receiptHashes,
	}, nil
}

// VerifyReceiptHash verifies a single receipt's hash against an expected value.
// Useful for spot-checking individual receipts from a bundle.
func VerifyReceiptHash(receipt Receipt, expectedHash string) (bool, error) {
	computed, err := hashReceipt(receipt)
	if err != nil {
		return false, err
	}
	return computed == expectedHash, nil
}

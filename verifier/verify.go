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

package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"

	maip "github.com/truthlocks/maip"
)

// Exit codes per MAIP verifier specification.
const (
	ExitValid            = 0
	ExitExpired          = 1
	ExitRevoked          = 2
	ExitScopeViolation   = 3
	ExitChainBroken      = 4
	ExitSignatureInvalid = 5
	ExitKeyMismatch      = 6
	ExitUnknownError     = 10
)

// runVerify reads a bundle file and performs offline verification.
// Returns the appropriate exit code.
func runVerify(path string) int {
	data, err := os.ReadFile(path)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error reading bundle: %v\n", err)
		return ExitUnknownError
	}

	bundle, err := maip.ParseBundle(data)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error parsing bundle: %v\n", err)
		return ExitUnknownError
	}

	result := maip.VerifyBundle(bundle)

	if result.Valid {
		fmt.Printf("VALID\n")
		fmt.Printf("  Receipt:     %s\n", result.ReceiptID)
		fmt.Printf("  Agent:       %s\n", result.AgentID)
		fmt.Printf("  Chain depth: %d\n", result.ChainDepth)
		return ExitValid
	}

	fmt.Fprintf(os.Stderr, "INVALID: %s\n", result.Result)
	if result.Error != "" {
		fmt.Fprintf(os.Stderr, "  Detail: %s\n", result.Error)
	}
	fmt.Fprintf(os.Stderr, "  Receipt: %s\n", result.ReceiptID)
	fmt.Fprintf(os.Stderr, "  Agent:   %s\n", result.AgentID)

	return resultToExitCode(result.Result)
}

// runInspect reads a bundle file and prints its metadata.
func runInspect(path string) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return fmt.Errorf("reading bundle: %w", err)
	}

	bundle, err := maip.ParseBundle(data)
	if err != nil {
		return fmt.Errorf("parsing bundle: %w", err)
	}

	fmt.Printf("MAIP Proof Bundle\n")
	fmt.Printf("=================\n")
	fmt.Printf("  Version:      %s\n", bundle.Version)
	fmt.Printf("  Created:      %s\n", bundle.CreatedAt.Format(time.RFC3339))
	fmt.Printf("\n")

	fmt.Printf("Receipt\n")
	fmt.Printf("-------\n")
	fmt.Printf("  ID:           %s\n", bundle.Receipt.ID)
	fmt.Printf("  Type:         %s\n", bundle.Receipt.Type)
	fmt.Printf("  Issuer:       %s\n", bundle.Receipt.IssuerID)
	fmt.Printf("  Subject:      %s\n", bundle.Receipt.SubjectID)
	fmt.Printf("  Subject Type: %s\n", bundle.Receipt.SubjectType)
	fmt.Printf("  Created:      %s\n", bundle.Receipt.CreatedAt.Format(time.RFC3339))
	if !bundle.Receipt.ExpiresAt.IsZero() {
		fmt.Printf("  Expires:      %s\n", bundle.Receipt.ExpiresAt.Format(time.RFC3339))
	} else {
		fmt.Printf("  Expires:      never\n")
	}
	fmt.Printf("  Schema:       %s\n", bundle.Receipt.SchemaVersion)
	fmt.Printf("  Scopes Used:  %s\n", formatScopes(bundle.Receipt.Context.ScopesUsed))
	fmt.Printf("  Depth:        %d\n", bundle.Receipt.Context.DelegationDepth)
	fmt.Printf("\n")

	fmt.Printf("Delegation Chain (%d entries)\n", len(bundle.DelegationChain))
	fmt.Printf("----------------------------\n")
	for i, d := range bundle.DelegationChain {
		fmt.Printf("  [%d] %s\n", i, d.ID)
		fmt.Printf("      Parent: %s\n", d.ParentAgentID)
		fmt.Printf("      Child:  %s\n", d.ChildAgentID)
		fmt.Printf("      Depth:  %d\n", d.Depth)
		fmt.Printf("      Scopes: %s\n", formatScopes(d.Scopes))
		fmt.Printf("      Valid:  %s to %s\n",
			d.NotBefore.Format(time.RFC3339),
			d.ExpiresAt.Format(time.RFC3339))
		fmt.Printf("      Status: %s\n", d.Status)
		if d.CrossTenant {
			fmt.Printf("      Cross-Tenant: %s -> %s\n", d.SourceTenant, d.TargetTenant)
		}
		fmt.Printf("\n")
	}

	fmt.Printf("Public Keys (%d entries)\n", len(bundle.PublicKeys))
	fmt.Printf("-----------------------\n")
	for _, k := range bundle.PublicKeys {
		fmt.Printf("  %s (%s)\n", k.AgentID, k.Algorithm)
		// Show truncated key for readability
		keyDisplay := k.PublicKey
		if len(keyDisplay) > 20 {
			keyDisplay = keyDisplay[:20] + "..."
		}
		fmt.Printf("    Key: %s\n", keyDisplay)
	}

	if bundle.Metadata != nil {
		fmt.Printf("\nMetadata\n")
		fmt.Printf("--------\n")
		if bundle.Metadata.BundlerID != "" {
			fmt.Printf("  Bundler: %s\n", bundle.Metadata.BundlerID)
		}
		if bundle.Metadata.Purpose != "" {
			fmt.Printf("  Purpose: %s\n", bundle.Metadata.Purpose)
		}
		if bundle.Metadata.Notes != "" {
			fmt.Printf("  Notes:   %s\n", bundle.Metadata.Notes)
		}
	}

	// Also run verification and show result
	fmt.Printf("\nVerification\n")
	fmt.Printf("------------\n")
	vResult := maip.VerifyBundle(bundle)
	if vResult.Valid {
		fmt.Printf("  Status: VALID\n")
	} else {
		fmt.Printf("  Status: INVALID (%s)\n", vResult.Result)
		if vResult.Error != "" {
			fmt.Printf("  Detail: %s\n", vResult.Error)
		}
	}

	// Print raw payload
	if len(bundle.Receipt.Payload) > 0 {
		fmt.Printf("\nPayload\n")
		fmt.Printf("-------\n")
		var prettyPayload json.RawMessage
		if err := json.Unmarshal(bundle.Receipt.Payload, &prettyPayload); err == nil {
			pretty, _ := json.MarshalIndent(prettyPayload, "  ", "  ")
			fmt.Printf("  %s\n", string(pretty))
		}
	}

	return nil
}

// formatScopes formats a scope list for display.
func formatScopes(scopes []string) string {
	if len(scopes) == 0 {
		return "(none)"
	}
	return strings.Join(scopes, ", ")
}

// resultToExitCode maps a ChainVerificationResult to the appropriate exit code.
func resultToExitCode(result maip.ChainVerificationResult) int {
	switch result {
	case maip.ChainValid:
		return ExitValid
	case maip.ChainExpired:
		return ExitExpired
	case maip.ChainRevoked:
		return ExitRevoked
	case maip.ChainScopeViolation:
		return ExitScopeViolation
	case maip.ChainBroken:
		return ExitChainBroken
	case maip.ChainKeyMismatch:
		return ExitKeyMismatch
	case maip.ChainVerificationResult("signature_invalid"):
		return ExitSignatureInvalid
	default:
		return ExitUnknownError
	}
}

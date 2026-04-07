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

// Example verify-bundle demonstrates how to create a proof bundle and verify
// it offline. This shows the complete flow: agent creation, delegation,
// receipt signing, bundle assembly, and offline verification.
package main

import (
	"encoding/json"
	"fmt"
	"log"
	"time"

	maip "github.com/truthlocks/maip"
)

func main() {
	fmt.Println("MAIP Reference Implementation - Bundle Verification Example")
	fmt.Println("============================================================")
	fmt.Println()

	// 1. Create a root agent (representing a verified human/org)
	root, err := maip.NewAgentWithTenant(
		"org-root",
		maip.AgentTypeAutonomous,
		[]string{"*:*"}, // root has all scopes
		"a1b2c3d4",
	)
	if err != nil {
		log.Fatalf("Failed to create root agent: %v", err)
	}
	fmt.Printf("Root agent: %s\n", root.ID)

	// 2. Create a child agent
	child, err := maip.NewAgentWithTenant(
		"model-deployer",
		maip.AgentTypeAutonomous,
		[]string{"model:deploy", "model:evaluate", "receipt:create"},
		"a1b2c3d4",
	)
	if err != nil {
		log.Fatalf("Failed to create child agent: %v", err)
	}
	fmt.Printf("Child agent: %s\n", child.ID)

	// 3. Create delegation from root to child
	delegation, err := maip.CreateDelegation(
		root,
		child,
		[]string{"model:deploy", "model:evaluate", "receipt:create"},
		90*24*time.Hour, // 90 days
		&maip.DelegationConstraints{
			MaxSubDelegations:   2,
			AllowedEnvironments: []string{"production", "staging"},
			RateLimitPerHour:    500,
		},
	)
	if err != nil {
		log.Fatalf("Failed to create delegation: %v", err)
	}
	fmt.Printf("Delegation: %s (depth=%d)\n", delegation.ID, delegation.Depth)
	fmt.Println()

	// 4. Child agent creates an action receipt
	payload, _ := json.Marshal(map[string]interface{}{
		"action":        "model:deploy",
		"model_id":      "llm-summarizer-v3",
		"model_version": "3.2.1",
		"environment":   "production",
		"instance_count": 3,
	})

	receipt, err := maip.NewReceipt(
		maip.ReceiptTypeAction,
		child,
		"llm-summarizer-v3",
		"model",
		payload,
		"",
		maip.WithScopesUsed([]string{"model:deploy"}),
	)
	if err != nil {
		log.Fatalf("Failed to create receipt: %v", err)
	}
	fmt.Printf("Receipt: %s\n", receipt.ID)

	// 5. Assemble a proof bundle
	bundle := maip.NewBundle(
		receipt,
		[]*maip.Delegation{delegation},
		[]maip.BundlePublicKey{
			{
				AgentID:   root.ID,
				PublicKey:  root.PublicKeyBase64,
				Algorithm: "Ed25519",
			},
			{
				AgentID:   child.ID,
				PublicKey:  child.PublicKeyBase64,
				Algorithm: "Ed25519",
			},
		},
		&maip.BundleMetadata{
			BundlerID: root.ID,
			Purpose:   "deployment audit evidence",
			Notes:     "Model deployment to production cluster",
		},
	)

	// Serialize to JSON
	bundleJSON, err := json.MarshalIndent(bundle, "", "  ")
	if err != nil {
		log.Fatalf("Failed to serialize bundle: %v", err)
	}
	fmt.Printf("\nBundle JSON (%d bytes):\n", len(bundleJSON))
	// Print first 500 chars for brevity
	preview := string(bundleJSON)
	if len(preview) > 500 {
		preview = preview[:500] + "\n  ... (truncated)"
	}
	fmt.Println(preview)
	fmt.Println()

	// 6. Verify the bundle offline
	fmt.Println("Verifying bundle offline...")
	result := maip.VerifyBundle(bundle)

	fmt.Printf("\nVerification Result:\n")
	fmt.Printf("  Valid:        %v\n", result.Valid)
	fmt.Printf("  Result:       %s\n", result.Result)
	fmt.Printf("  Receipt OK:   %v\n", result.ReceiptValid)
	fmt.Printf("  Agent:        %s\n", result.AgentID)
	fmt.Printf("  Receipt:      %s\n", result.ReceiptID)
	fmt.Printf("  Chain Depth:  %d\n", result.ChainDepth)
	if result.Error != "" {
		fmt.Printf("  Error:        %s\n", result.Error)
	}

	// 7. Also parse the JSON back and re-verify (round-trip test)
	fmt.Println("\nRound-trip verification (parse JSON -> verify)...")
	parsed, err := maip.ParseBundle(bundleJSON)
	if err != nil {
		log.Fatalf("Failed to parse bundle: %v", err)
	}
	rtResult := maip.VerifyBundle(parsed)
	fmt.Printf("  Round-trip valid: %v\n", rtResult.Valid)
}

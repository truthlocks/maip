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

// Example register-agent demonstrates how to register a MAIP agent, create
// a scoped session, and issue a signed action receipt.
package main

import (
	"encoding/json"
	"fmt"
	"log"
	"time"

	maip "github.com/truthlocks/maip"
)

func main() {
	fmt.Println("MAIP Reference Implementation - Agent Registration Example")
	fmt.Println("===========================================================")
	fmt.Println()

	// 1. Create an agent registry
	registry := maip.NewAgentRegistry()

	// 2. Register a new agent with scopes
	agent, err := maip.NewAgentWithTenant(
		"data-processor",
		maip.AgentTypeAutonomous,
		[]string{"dataset:read", "dataset:write", "receipt:create"},
		"a1b2c3d4",
	)
	if err != nil {
		log.Fatalf("Failed to create agent: %v", err)
	}

	if err := registry.Register(agent); err != nil {
		log.Fatalf("Failed to register agent: %v", err)
	}

	fmt.Printf("Agent registered:\n")
	fmt.Printf("  ID:     %s\n", agent.ID)
	fmt.Printf("  Name:   %s\n", agent.Name)
	fmt.Printf("  Type:   %s\n", agent.Type)
	fmt.Printf("  Scopes: %v\n", agent.Scopes)
	fmt.Printf("  Key:    %s\n", agent.PublicKeyBase64)
	fmt.Println()

	// 3. Create a session with narrowed scopes and TTL
	session, err := maip.CreateSession(agent,
		maip.WithSessionTTL(30*time.Minute),
		maip.WithSessionScopes([]string{"dataset:read", "receipt:create"}),
		maip.WithIPAllowlist([]string{"10.0.0.0/8"}),
	)
	if err != nil {
		log.Fatalf("Failed to create session: %v", err)
	}

	fmt.Printf("Session created:\n")
	fmt.Printf("  ID:       %s\n", session.ID)
	fmt.Printf("  Agent:    %s\n", session.AgentID)
	fmt.Printf("  Scopes:   %v\n", session.Scopes)
	fmt.Printf("  Expires:  %s\n", session.ExpiresAt.Format(time.RFC3339))
	fmt.Printf("  IP Allow: %v\n", session.IPAllowlist)
	fmt.Printf("  Active:   %v\n", session.IsActive())
	fmt.Printf("  TTL:      %s\n", session.RemainingTTL().Round(time.Second))
	fmt.Println()

	// 4. Check session capabilities
	fmt.Printf("Session scope checks:\n")
	fmt.Printf("  dataset:read   = %v\n", session.HasScope("dataset:read"))
	fmt.Printf("  dataset:write  = %v (narrowed out)\n", session.HasScope("dataset:write"))
	fmt.Printf("  receipt:create = %v\n", session.HasScope("receipt:create"))
	fmt.Println()

	// 5. Create a signed action receipt
	payload, _ := json.Marshal(map[string]interface{}{
		"action":      "dataset:read",
		"dataset_id":  "ds_01HXYZ9K7P",
		"records_read": 1500,
		"duration_ms": 42,
	})

	receipt, err := maip.NewReceipt(
		maip.ReceiptTypeAction,
		agent,
		"ds_01HXYZ9K7P",
		"dataset",
		payload,
		"", // first receipt in chain
	)
	if err != nil {
		log.Fatalf("Failed to create receipt: %v", err)
	}

	fmt.Printf("Action receipt created:\n")
	fmt.Printf("  ID:      %s\n", receipt.ID)
	fmt.Printf("  Type:    %s\n", receipt.Type)
	fmt.Printf("  Issuer:  %s\n", receipt.IssuerID)
	fmt.Printf("  Subject: %s\n", receipt.SubjectID)
	fmt.Printf("  Signed:  alg=%s kid=%s\n", receipt.Signature.Algorithm, receipt.Signature.KeyID[:20]+"...")
	fmt.Println()

	// 6. Verify the receipt
	if err := maip.VerifyReceipt(receipt, agent.PublicKey); err != nil {
		log.Fatalf("Receipt verification failed: %v", err)
	}
	fmt.Println("Receipt signature: VERIFIED")
	fmt.Println()

	// 7. Compute a trust score
	score, err := maip.ComputeTrustScore(agent.ID, maip.TrustFactors{
		BehavioralCompliance: 0.92,
		ScopeAdherence:       1.0,
		AnomalyScore:         0.85,
		PeerAttestations:     0.60,
		SessionHygiene:       0.95,
	})
	if err != nil {
		log.Fatalf("Failed to compute trust score: %v", err)
	}

	fmt.Printf("Trust score:\n")
	fmt.Printf("  Overall: %.3f\n", score.Overall)
	fmt.Printf("  Level:   %s\n", score.TrustLevel())
	fmt.Printf("  Factors:\n")
	fmt.Printf("    Behavioral Compliance: %.2f (weight: 35%%)\n", score.Factors.BehavioralCompliance)
	fmt.Printf("    Scope Adherence:       %.2f (weight: 25%%)\n", score.Factors.ScopeAdherence)
	fmt.Printf("    Anomaly Score:         %.2f (weight: 20%%)\n", score.Factors.AnomalyScore)
	fmt.Printf("    Peer Attestations:     %.2f (weight: 10%%)\n", score.Factors.PeerAttestations)
	fmt.Printf("    Session Hygiene:       %.2f (weight: 10%%)\n", score.Factors.SessionHygiene)
}

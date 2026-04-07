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

package reference

import (
	"fmt"
	"strings"
)

// Scope represents a MAIP authorization scope in the resource:action format.
type Scope struct {
	// Resource is the target resource category (e.g., "attestation", "model").
	Resource string `json:"resource"`
	// Action is the permitted operation (e.g., "mint", "read", "deploy").
	Action string `json:"action"`
}

// Built-in scope constants for common MAIP operations.
var (
	// Identity scopes
	ScopeIdentityCreate = Scope{Resource: "identity", Action: "create"}
	ScopeIdentityRead   = Scope{Resource: "identity", Action: "read"}
	ScopeIdentityVerify = Scope{Resource: "identity", Action: "verify"}
	ScopeIdentityRevoke = Scope{Resource: "identity", Action: "revoke"}

	// Attestation scopes
	ScopeAttestationMint   = Scope{Resource: "attestation", Action: "mint"}
	ScopeAttestationRead   = Scope{Resource: "attestation", Action: "read"}
	ScopeAttestationRevoke = Scope{Resource: "attestation", Action: "revoke"}
	ScopeAttestationVerify = Scope{Resource: "attestation", Action: "verify"}

	// Dataset scopes
	ScopeDatasetRead   = Scope{Resource: "dataset", Action: "read"}
	ScopeDatasetWrite  = Scope{Resource: "dataset", Action: "write"}
	ScopeDatasetDelete = Scope{Resource: "dataset", Action: "delete"}
	ScopeDatasetAttest = Scope{Resource: "dataset", Action: "attest"}

	// Model scopes
	ScopeModelTrain    = Scope{Resource: "model", Action: "train"}
	ScopeModelDeploy   = Scope{Resource: "model", Action: "deploy"}
	ScopeModelEvaluate = Scope{Resource: "model", Action: "evaluate"}
	ScopeModelAttest   = Scope{Resource: "model", Action: "attest"}

	// Pipeline scopes
	ScopePipelineExecute   = Scope{Resource: "pipeline", Action: "execute"}
	ScopePipelineRead      = Scope{Resource: "pipeline", Action: "read"}
	ScopePipelineConfigure = Scope{Resource: "pipeline", Action: "configure"}

	// Receipt scopes
	ScopeReceiptCreate = Scope{Resource: "receipt", Action: "create"}
	ScopeReceiptRead   = Scope{Resource: "receipt", Action: "read"}
	ScopeReceiptVerify = Scope{Resource: "receipt", Action: "verify"}

	// Admin scopes
	ScopeAdminManageAgents = Scope{Resource: "admin", Action: "manage_agents"}
	ScopeAdminManageScopes = Scope{Resource: "admin", Action: "manage_scopes"}
	ScopeAdminAudit        = Scope{Resource: "admin", Action: "audit"}
	ScopeAdminKillSwitch   = Scope{Resource: "admin", Action: "kill_switch"}

	// Wildcard scope - only valid for root issuers (depth 0)
	ScopeWildcard = Scope{Resource: "*", Action: "*"}
)

// ParseScope parses a scope string in the format "resource:action" into a Scope.
func ParseScope(s string) (Scope, error) {
	parts := strings.SplitN(s, ":", 2)
	if len(parts) != 2 {
		return Scope{}, fmt.Errorf("invalid scope format %q: must be resource:action", s)
	}
	resource := strings.TrimSpace(parts[0])
	action := strings.TrimSpace(parts[1])
	if resource == "" || action == "" {
		return Scope{}, fmt.Errorf("invalid scope format %q: resource and action must not be empty", s)
	}
	return Scope{Resource: resource, Action: action}, nil
}

// String returns the scope in resource:action format.
func (s Scope) String() string {
	return s.Resource + ":" + s.Action
}

// IsWildcard returns true if this is the universal wildcard scope (*:*).
func (s Scope) IsWildcard() bool {
	return s.Resource == "*" && s.Action == "*"
}

// IsCategoryWildcard returns true if this is a category wildcard (e.g., attestation:*).
func (s Scope) IsCategoryWildcard() bool {
	return s.Action == "*" && s.Resource != "*"
}

// Matches returns true if this scope grants access for the target scope.
// A wildcard scope (*:*) matches everything. A category wildcard (resource:*)
// matches any action within that resource.
func (s Scope) Matches(target Scope) bool {
	if s.IsWildcard() {
		return true
	}
	if s.Resource == target.Resource {
		if s.Action == "*" || s.Action == target.Action {
			return true
		}
	}
	return false
}

// ScopeSet is an ordered collection of scopes with set operations.
type ScopeSet struct {
	scopes []Scope
}

// NewScopeSet creates a ScopeSet from a list of scope strings.
func NewScopeSet(scopeStrings []string) (*ScopeSet, error) {
	scopes := make([]Scope, 0, len(scopeStrings))
	for _, s := range scopeStrings {
		scope, err := ParseScope(s)
		if err != nil {
			return nil, err
		}
		scopes = append(scopes, scope)
	}
	return &ScopeSet{scopes: scopes}, nil
}

// NewScopeSetFromScopes creates a ScopeSet from a list of Scope values.
func NewScopeSetFromScopes(scopes []Scope) *ScopeSet {
	return &ScopeSet{scopes: scopes}
}

// Contains checks whether this set grants the given scope.
func (ss *ScopeSet) Contains(target Scope) bool {
	for _, s := range ss.scopes {
		if s.Matches(target) {
			return true
		}
	}
	return false
}

// ContainsString checks whether this set grants the given scope string.
func (ss *ScopeSet) ContainsString(target string) bool {
	t, err := ParseScope(target)
	if err != nil {
		return false
	}
	return ss.Contains(t)
}

// IsSubsetOf checks whether every scope in this set is granted by the parent set.
// This implements the MAIP scope narrowing rule: child.scopes <= parent.scopes.
func (ss *ScopeSet) IsSubsetOf(parent *ScopeSet) bool {
	for _, child := range ss.scopes {
		if !parent.Contains(child) {
			return false
		}
	}
	return true
}

// Intersect returns a new ScopeSet containing only scopes that are in both sets.
// For non-wildcard scopes this is an exact match. Wildcard scopes in either set
// expand to cover matching scopes from the other.
func (ss *ScopeSet) Intersect(other *ScopeSet) *ScopeSet {
	var result []Scope
	for _, s := range ss.scopes {
		if other.Contains(s) {
			result = append(result, s)
		}
	}
	return &ScopeSet{scopes: result}
}

// Strings returns the scopes as a slice of resource:action strings.
func (ss *ScopeSet) Strings() []string {
	out := make([]string, len(ss.scopes))
	for i, s := range ss.scopes {
		out[i] = s.String()
	}
	return out
}

// Len returns the number of scopes in the set.
func (ss *ScopeSet) Len() int {
	return len(ss.scopes)
}

// ValidateScopeNarrowing checks that childScopes is a valid narrowing of
// parentScopes per the MAIP delegation chain specification. Returns an error
// describing the violation if the narrowing is invalid.
func ValidateScopeNarrowing(parentScopes, childScopes []string) error {
	parent, err := NewScopeSet(parentScopes)
	if err != nil {
		return fmt.Errorf("invalid parent scopes: %w", err)
	}
	child, err := NewScopeSet(childScopes)
	if err != nil {
		return fmt.Errorf("invalid child scopes: %w", err)
	}

	for _, cs := range child.scopes {
		if !parent.Contains(cs) {
			return fmt.Errorf("scope violation: child scope %q not granted by parent", cs.String())
		}
	}
	return nil
}

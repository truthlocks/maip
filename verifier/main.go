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

// Command maip-verifier is a standalone CLI tool for offline verification of
// MAIP proof bundles. It reads a self-contained JSON bundle and verifies the
// complete delegation chain, receipt signatures, scope compliance, and temporal
// validity without any network calls.
//
// Usage:
//
//	maip-verifier verify  <bundle.json>   Verify a proof bundle (offline)
//	maip-verifier inspect <bundle.json>   Print bundle metadata
//	maip-verifier version                 Print version
//
// Exit codes:
//
//	0  = valid
//	1  = expired
//	2  = revoked
//	3  = scope_violation
//	4  = chain_broken
//	5  = signature_invalid
//	6  = key_mismatch
//	10 = unknown_error
package main

import (
	"fmt"
	"os"
)

// Version is set at build time via ldflags.
var Version = "dev"

func main() {
	if len(os.Args) < 2 {
		printUsage()
		os.Exit(10)
	}

	switch os.Args[1] {
	case "verify":
		if len(os.Args) < 3 {
			fmt.Fprintf(os.Stderr, "Error: verify requires a bundle file path\n")
			printUsage()
			os.Exit(10)
		}
		exitCode := runVerify(os.Args[2])
		os.Exit(exitCode)

	case "inspect":
		if len(os.Args) < 3 {
			fmt.Fprintf(os.Stderr, "Error: inspect requires a bundle file path\n")
			printUsage()
			os.Exit(10)
		}
		if err := runInspect(os.Args[2]); err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(10)
		}

	case "version":
		fmt.Printf("maip-verifier %s\n", Version)

	case "-h", "--help", "help":
		printUsage()

	default:
		fmt.Fprintf(os.Stderr, "Unknown command: %s\n", os.Args[1])
		printUsage()
		os.Exit(10)
	}
}

func printUsage() {
	fmt.Fprintf(os.Stderr, `MAIP Verifier - Offline proof bundle verification

Usage:
  maip-verifier verify  <bundle.json>   Verify a proof bundle (offline)
  maip-verifier inspect <bundle.json>   Print bundle metadata
  maip-verifier version                 Print version
  maip-verifier help                    Show this help

Exit codes:
  0  = valid
  1  = expired
  2  = revoked
  3  = scope_violation
  4  = chain_broken
  5  = signature_invalid
  6  = key_mismatch
  10 = unknown_error
`)
}

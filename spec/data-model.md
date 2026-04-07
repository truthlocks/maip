# MAIP Data Model Specification

**Protocol**: Machine Agent Identity Protocol (MAIP)
**Version**: 1.0.0-draft
**Status**: Draft
**Date**: 2026-04-06
**Authors**: Truthlocks Inc.
**License**: Apache 2.0

---

## Table of Contents

1. [Overview](#1-overview)
2. [What Gets Signed](#2-what-gets-signed)
3. [Schema System](#3-schema-system)
4. [Database Schema](#4-database-schema)
5. [Payload Size Strategy](#5-payload-size-strategy)
6. [Data Lineage Tracking](#6-data-lineage-tracking)
7. [Conformance](#7-conformance)

---

## 1. Overview

This document defines the canonical data model for the Machine Agent Identity Protocol (MAIP). It specifies what artifacts are signed, how schemas are defined and versioned, the relational storage model, size constraints, and lineage tracking semantics.

MAIP builds on Truthlocks production primitives:

- **Attestation Service**: Mint, revoke, and supersede attestations with SHA-256 payload hashing, Ed25519/ES256/RS256 signing, and idempotent operations.
- **Signing Service**: Ed25519, ECDSA P-256, and RSA-3072+ key lifecycle with KMS provider support.
- **Transparency Log**: Merkle tree with RFC 6962 inclusion proofs, domain-separated leaf hashing (`0x00` prefix for leaves, `0x01` for internal nodes), and protobuf-canonical leaf payloads.
- **Receipt System**: Typed, versioned receipt events with JSON Schema validation, RLS-isolated storage, and transparency log anchoring.

### 1.1 Notation

- All hashes use SHA-256 unless otherwise stated.
- All signatures use Ed25519 unless the issuer key specifies ES256 or RS256.
- All timestamps are ISO 8601 with UTC timezone.
- All identifiers use UUID v7 (time-ordered) or ULID where noted.
- JSON canonicalization follows RFC 8785 (JCS).
- Base64 encoding uses URL-safe encoding without padding (RFC 4648 Section 5).

### 1.2 Agent ID Format

```
maip:<first8_of_tenant_uuid>:<ulid>
```

Examples:
```
maip:a1b2c3d4:01HXYZ9K7PQRS4TUV0WX1YZ2AB
maip:f9e8d7c6:01HXYZ9K7PQRS4TUV0WX1YZ2CD
```

The `first8_of_tenant_uuid` segment provides a human-readable tenant hint without exposing the full tenant UUID. The ULID suffix provides time-ordered, globally unique identification with millisecond precision.

---

## 2. What Gets Signed

MAIP defines eight artifact types. For each, this section specifies the exact signed payload construction, the signing strategy, and the maximum permitted size of the raw artifact.

### 2.1 Artifact Signing Table

| Artifact | Signed Payload | Strategy | Max Size |
|----------|---------------|----------|----------|
| Raw files (images, docs) | SHA-256 of file content bytes | Hash-only (file never leaves client) | Unlimited |
| Metadata (labels, annotations) | SHA-256 of JCS-canonicalized metadata JSON | Full metadata embedded in receipt | 64 KB |
| Model outputs (inference) | SHA-256 of: `input_hash \|\| model_id \|\| model_version \|\| output_hash` | Hash chain | N/A |
| Embeddings | SHA-256 of: `tensor_bytes \|\| model_id \|\| model_version` | Reference hash | N/A |
| Training datasets | Merkle root of dataset chunks (configurable chunk size) | Merkle tree | Unlimited |
| Pipeline state (DAG) | SHA-256 of: `dag_definition \|\| run_id \|\| parameters_hash` | Signed manifest | 256 KB |
| Model weights | SHA-256 of serialized model file bytes | Hash-only | Unlimited |
| Feature vectors | SHA-256 of: `feature_name \|\| version \|\| value_hash` | Reference hash | N/A |

### 2.2 Raw Files

Raw files (images, documents, PDFs, audio, video) are never transmitted to MAIP infrastructure. The client computes the SHA-256 hash locally and submits only the hash for attestation.

**Signed payload construction:**
```
payload_hash = SHA-256(file_content_bytes)
```

**Attestation payload:**
```json
{
  "artifact_type": "raw_file",
  "file_hash": "<base64url of SHA-256>",
  "file_name": "report-2026-Q1.pdf",
  "file_size_bytes": 2458901,
  "content_type": "application/pdf",
  "hash_algorithm": "SHA-256"
}
```

**Rationale**: Files may be arbitrarily large (multi-gigabyte model checkpoints, video datasets). Transmitting only the hash keeps MAIP operations O(1) in network cost regardless of file size, and ensures no data ever leaves the client's control boundary unless explicitly shared.

### 2.3 Metadata

Metadata objects (labels, annotations, tags, classification results) are small enough to embed directly in the receipt payload. The signed hash uses JSON Canonicalization Scheme (JCS, RFC 8785) to ensure deterministic serialization.

**Signed payload construction:**
```
canonical_json = JCS_canonicalize(metadata_object)
payload_hash   = SHA-256(canonical_json)
```

**Attestation payload:**
```json
{
  "artifact_type": "metadata",
  "metadata_hash": "<base64url of SHA-256>",
  "metadata": {
    "classification": "confidential",
    "department": "research",
    "project_id": "proj_01HXYZ"
  },
  "hash_algorithm": "SHA-256",
  "canonicalization": "JCS-RFC8785"
}
```

**Size constraint**: The `metadata` field MUST NOT exceed 64 KB when serialized as UTF-8 JSON. Implementations MUST reject metadata payloads exceeding this limit with a `PAYLOAD_TOO_LARGE` error.

### 2.4 Model Outputs (Inference)

Inference results are signed using a hash chain that cryptographically binds the output to the specific model version and input that produced it. This enables downstream consumers to verify provenance without accessing the model or input data directly.

**Signed payload construction:**
```
input_hash   = SHA-256(input_data_bytes)
output_hash  = SHA-256(output_data_bytes)
payload_hash = SHA-256(input_hash || model_id || model_version || output_hash)
```

Where `||` denotes byte concatenation with each component UTF-8 encoded. String fields (`model_id`, `model_version`) are encoded as their raw UTF-8 byte representation.

**Attestation payload:**
```json
{
  "artifact_type": "model_output",
  "input_hash": "<base64url>",
  "output_hash": "<base64url>",
  "model_id": "llm-summarizer-v3",
  "model_version": "3.2.1",
  "chain_hash": "<base64url of combined hash>",
  "inference_timestamp": "2026-04-06T12:00:00Z",
  "latency_ms": 342
}
```

### 2.5 Embeddings

Embedding vectors are signed by hashing the raw tensor bytes concatenated with the model that produced them. This proves a specific model version generated a specific embedding.

**Signed payload construction:**
```
payload_hash = SHA-256(tensor_bytes || model_id || model_version)
```

Where `tensor_bytes` is the raw binary representation of the embedding vector (IEEE 754 float32 or float64, little-endian byte order).

**Attestation payload:**
```json
{
  "artifact_type": "embedding",
  "tensor_hash": "<base64url>",
  "model_id": "text-embedding-ada-002",
  "model_version": "2.0.0",
  "dimensions": 1536,
  "dtype": "float32",
  "byte_order": "little-endian"
}
```

### 2.6 Training Datasets

Datasets are signed using a Merkle tree over configurable-size chunks. This allows proof-of-inclusion for any individual record without downloading the entire dataset.

**Signed payload construction:**
```
chunks[]     = split(dataset_bytes, chunk_size)  // default chunk_size = 1 MB
leaf_hashes[] = [SHA-256(0x00 || chunk) for chunk in chunks]
merkle_root  = compute_merkle_root(leaf_hashes)
```

The Merkle tree uses domain-separated hashing consistent with the Truthlocks transparency log:
- Leaf hash: `SHA-256(0x00 || chunk_bytes)`
- Internal node: `SHA-256(0x01 || left_child_hash || right_child_hash)`

**Attestation payload:**
```json
{
  "artifact_type": "training_dataset",
  "dataset_id": "ds_01HXYZ9K7P",
  "merkle_root": "<base64url>",
  "chunk_count": 4096,
  "chunk_size_bytes": 1048576,
  "total_size_bytes": 4294967296,
  "record_count": 1500000,
  "hash_algorithm": "SHA-256",
  "tree_algorithm": "RFC6962-compatible"
}
```

### 2.7 Pipeline State (DAG)

Pipeline definitions capture the computational graph (DAG), run parameters, and execution identity. The signed manifest binds a specific run to its configuration.

**Signed payload construction:**
```
dag_bytes        = JCS_canonicalize(dag_definition)
params_hash      = SHA-256(JCS_canonicalize(parameters))
payload_hash     = SHA-256(dag_bytes || run_id || params_hash)
```

**Size constraint**: The DAG definition MUST NOT exceed 256 KB when serialized as UTF-8 JSON.

**Attestation payload:**
```json
{
  "artifact_type": "pipeline_state",
  "pipeline_id": "pipe_01HXYZ",
  "run_id": "run_01HXYZ9K7P",
  "dag_hash": "<base64url>",
  "parameters_hash": "<base64url>",
  "manifest_hash": "<base64url of combined>",
  "stage_count": 7,
  "input_attestation_ids": ["att_...", "att_..."],
  "output_attestation_ids": ["att_...", "att_..."]
}
```

### 2.8 Model Weights

Model weight files are treated identically to raw files: only the hash is transmitted. The attestation records the model identity, version, and training lineage.

**Signed payload construction:**
```
payload_hash = SHA-256(serialized_model_file_bytes)
```

**Attestation payload:**
```json
{
  "artifact_type": "model_weights",
  "model_id": "llm-summarizer-v3",
  "model_version": "3.2.1",
  "weights_hash": "<base64url>",
  "framework": "pytorch",
  "serialization_format": "safetensors",
  "file_size_bytes": 13000000000,
  "training_dataset_attestation_id": "att_...",
  "metrics_hash": "<base64url of evaluation metrics JSON>"
}
```

### 2.9 Feature Vectors

Feature vectors are individual named features with version tracking. The reference hash binds a feature name and version to its computed value.

**Signed payload construction:**
```
value_hash   = SHA-256(feature_value_bytes)
payload_hash = SHA-256(feature_name || version || value_hash)
```

**Attestation payload:**
```json
{
  "artifact_type": "feature_vector",
  "feature_name": "user_purchase_frequency_30d",
  "version": "2.1.0",
  "value_hash": "<base64url>",
  "feature_hash": "<base64url of combined>",
  "dtype": "float64",
  "source_dataset_attestation_id": "att_..."
}
```

---

## 3. Schema System

### 3.1 Schema Definition Format

All MAIP schemas are defined using JSON Schema draft 2020-12. Schemas are stored in the `receipt_types` table (existing Truthlocks infrastructure) and validated at mint time.

**Base meta-schema requirements**: Every MAIP schema document MUST include:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://maip.truthlocks.com/schemas/<schema_id>/<version>",
  "type": "object",
  "required": ["schema_id", "schema_version", "created_at", "issuer_id"],
  "properties": {
    "schema_id": {
      "type": "string",
      "description": "Unique identifier for this schema family"
    },
    "schema_version": {
      "type": "string",
      "pattern": "^\\d+\\.\\d+\\.\\d+$",
      "description": "Semantic version of this schema"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "description": "ISO 8601 timestamp of record creation"
    },
    "issuer_id": {
      "type": "string",
      "description": "MAIP agent ID or human issuer ID"
    }
  }
}
```

### 3.2 Required Fields

All schemas MUST declare the following four fields as required:

| Field | Type | Description |
|-------|------|-------------|
| `schema_id` | string | Unique schema family identifier (e.g., `agent_identity`, `delegation`) |
| `schema_version` | string | Semantic version (`MAJOR.MINOR.PATCH`) |
| `created_at` | string (date-time) | ISO 8601 UTC timestamp |
| `issuer_id` | string | MAIP agent ID (`maip:...`) or human issuer UUID |

### 3.3 Schema Registry

The schema registry is implemented via the existing `receipt_types` table in the Attestation Service database.

**Registration**: Schemas are registered via `POST /v1/receipt-types` with the schema JSON in the `schema` field. Platform-defined schemas have `tenant_id = NULL` (globally available). Tenant-custom schemas have `tenant_id` set and are isolated by row-level security.

**Versioning**: Schemas are identified by the composite key `(name, version)`. The `name` field uses snake_case naming convention (e.g., `agent_identity`, `model_attestation`).

**Discovery**: Schemas are discoverable via:
- `GET /v1/receipt-types` -- lists all active schemas visible to the requesting tenant
- `GET /v1/receipt-types/{name}` -- returns the latest version of a named schema
- `GET /v1/receipt-types/{name}@{version}` -- returns a specific version

**Status lifecycle**:
```
active --> deprecated --> archived
```

- `active`: Schema can be used to mint new receipts.
- `deprecated`: Existing receipts remain valid; new minting triggers a warning header (`X-Schema-Deprecated: true`) but is still allowed.
- `archived`: No new receipts can be minted against this schema version. Existing receipts remain valid and verifiable.

### 3.4 Built-in Schemas

MAIP defines seven built-in schemas. These are registered as platform-defined receipt types (`tenant_id = NULL`) and are available to all tenants without registration.

#### 3.4.1 `agent_identity`

Issued when an agent is created. Serves as the genesis record.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://maip.truthlocks.com/schemas/agent_identity/1.0.0",
  "type": "object",
  "required": [
    "schema_id", "schema_version", "created_at", "issuer_id",
    "agent_id", "display_name", "trust_level", "genesis_public_key"
  ],
  "properties": {
    "schema_id":          { "const": "agent_identity" },
    "schema_version":     { "const": "1.0.0" },
    "created_at":         { "type": "string", "format": "date-time" },
    "issuer_id":          { "type": "string" },
    "agent_id":           { "type": "string", "pattern": "^maip:[a-f0-9]{8}:[A-Z0-9]{26}$" },
    "display_name":       { "type": "string", "maxLength": 256 },
    "trust_level":        { "type": "string", "enum": ["system", "delegated", "ephemeral"] },
    "genesis_public_key": { "type": "string", "description": "Base64url-encoded Ed25519 public key" },
    "parent_agent_id":    { "type": ["string", "null"] },
    "capabilities":       { "type": "array", "items": { "type": "string" } },
    "max_delegation_depth": { "type": "integer", "minimum": 0, "maximum": 8 },
    "metadata":           { "type": "object" }
  },
  "additionalProperties": false
}
```

#### 3.4.2 `delegation`

Records authority delegation from a parent agent to a child agent.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://maip.truthlocks.com/schemas/delegation/1.0.0",
  "type": "object",
  "required": [
    "schema_id", "schema_version", "created_at", "issuer_id",
    "parent_agent_id", "child_agent_id", "scopes", "depth"
  ],
  "properties": {
    "schema_id":        { "const": "delegation" },
    "schema_version":   { "const": "1.0.0" },
    "created_at":       { "type": "string", "format": "date-time" },
    "issuer_id":        { "type": "string" },
    "parent_agent_id":  { "type": "string", "pattern": "^maip:[a-f0-9]{8}:" },
    "child_agent_id":   { "type": "string", "pattern": "^maip:[a-f0-9]{8}:" },
    "scopes":           {
      "type": "array",
      "items": { "type": "string" },
      "minItems": 1,
      "description": "Capability scopes granted. Must be a subset of parent's scopes."
    },
    "depth":            { "type": "integer", "minimum": 0, "maximum": 8 },
    "max_depth":        { "type": "integer", "minimum": 0, "maximum": 8 },
    "expires_at":       { "type": ["string", "null"], "format": "date-time" },
    "constraints":      {
      "type": "object",
      "description": "Additional constraints (rate limits, IP allowlists, time windows)"
    },
    "metadata":         { "type": "object" }
  },
  "additionalProperties": false
}
```

#### 3.4.3 `action_receipt`

Records a discrete agent action (inference call, data access, API invocation).

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://maip.truthlocks.com/schemas/action_receipt/1.0.0",
  "type": "object",
  "required": [
    "schema_id", "schema_version", "created_at", "issuer_id",
    "agent_id", "action_type", "inputs_hash", "outputs_hash"
  ],
  "properties": {
    "schema_id":              { "const": "action_receipt" },
    "schema_version":         { "const": "1.0.0" },
    "created_at":             { "type": "string", "format": "date-time" },
    "issuer_id":              { "type": "string" },
    "agent_id":               { "type": "string" },
    "action_type":            { "type": "string", "description": "e.g., inference, data_access, api_call, transformation" },
    "inputs_hash":            { "type": "string" },
    "outputs_hash":           { "type": "string", "description": "Set to 'PENDING' for async; superseded on completion" },
    "scopes_used":            { "type": "array", "items": { "type": "string" } },
    "delegation_chain_hash":  { "type": "string" },
    "previous_receipt_id":    { "type": ["string", "null"] },
    "duration_ms":            { "type": "integer" },
    "status":                 { "type": "string", "enum": ["PENDING", "COMPLETE", "FAILED"] },
    "error_code":             { "type": ["string", "null"] },
    "metadata":               { "type": "object" }
  },
  "additionalProperties": false
}
```

**PENDING receipt pattern**: When an agent begins an asynchronous operation, a receipt is minted with `outputs_hash = "PENDING"` and `status = "PENDING"`. When the operation completes, the original receipt is superseded by a new receipt containing the final `outputs_hash` and `status = "COMPLETE"` (or `"FAILED"`). The supersession is recorded via the Attestation Service's supersede operation, which atomically marks the original as `SUPERSEDED` and links to the completion receipt.

#### 3.4.4 `dataset_attestation`

Signs a versioned dataset using a Merkle root.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://maip.truthlocks.com/schemas/dataset_attestation/1.0.0",
  "type": "object",
  "required": [
    "schema_id", "schema_version", "created_at", "issuer_id",
    "dataset_id", "merkle_root", "chunk_count"
  ],
  "properties": {
    "schema_id":        { "const": "dataset_attestation" },
    "schema_version":   { "const": "1.0.0" },
    "created_at":       { "type": "string", "format": "date-time" },
    "issuer_id":        { "type": "string" },
    "dataset_id":       { "type": "string" },
    "merkle_root":      { "type": "string", "description": "Base64url Merkle root" },
    "chunk_count":      { "type": "integer", "minimum": 1 },
    "chunk_size_bytes": { "type": "integer" },
    "total_size_bytes": { "type": "integer" },
    "record_count":     { "type": "integer" },
    "version":          { "type": "string" },
    "description":      { "type": "string" },
    "lineage":          {
      "type": "object",
      "properties": {
        "source_dataset_ids":       { "type": "array", "items": { "type": "string" } },
        "transformation_receipt_id": { "type": "string" }
      }
    },
    "metadata":         { "type": "object" }
  },
  "additionalProperties": false
}
```

#### 3.4.5 `model_attestation`

Signs a specific model version, binding weights to training data.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://maip.truthlocks.com/schemas/model_attestation/1.0.0",
  "type": "object",
  "required": [
    "schema_id", "schema_version", "created_at", "issuer_id",
    "model_id", "model_version", "weights_hash"
  ],
  "properties": {
    "schema_id":                        { "const": "model_attestation" },
    "schema_version":                   { "const": "1.0.0" },
    "created_at":                       { "type": "string", "format": "date-time" },
    "issuer_id":                        { "type": "string" },
    "model_id":                         { "type": "string" },
    "model_version":                    { "type": "string" },
    "weights_hash":                     { "type": "string" },
    "framework":                        { "type": "string" },
    "serialization_format":             { "type": "string" },
    "training_dataset_attestation_id":  { "type": "string" },
    "metrics_hash":                     { "type": "string" },
    "evaluation_results":               { "type": "object" },
    "metadata":                         { "type": "object" }
  },
  "additionalProperties": false
}
```

#### 3.4.6 `inference_receipt`

Specialized action receipt for model inference, binding input/output to a model attestation.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://maip.truthlocks.com/schemas/inference_receipt/1.0.0",
  "type": "object",
  "required": [
    "schema_id", "schema_version", "created_at", "issuer_id",
    "agent_id", "model_attestation_id", "input_hash", "output_hash"
  ],
  "properties": {
    "schema_id":              { "const": "inference_receipt" },
    "schema_version":         { "const": "1.0.0" },
    "created_at":             { "type": "string", "format": "date-time" },
    "issuer_id":              { "type": "string" },
    "agent_id":               { "type": "string" },
    "model_attestation_id":   { "type": "string" },
    "model_id":               { "type": "string" },
    "model_version":          { "type": "string" },
    "input_hash":             { "type": "string" },
    "output_hash":            { "type": "string" },
    "chain_hash":             { "type": "string", "description": "SHA-256(input_hash || model_id || model_version || output_hash)" },
    "latency_ms":             { "type": "integer" },
    "token_count":            { "type": "object", "properties": { "input": { "type": "integer" }, "output": { "type": "integer" } } },
    "previous_receipt_id":    { "type": ["string", "null"] },
    "metadata":               { "type": "object" }
  },
  "additionalProperties": false
}
```

#### 3.4.7 `pipeline_manifest`

Records a pipeline execution, linking input and output attestations through a DAG.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://maip.truthlocks.com/schemas/pipeline_manifest/1.0.0",
  "type": "object",
  "required": [
    "schema_id", "schema_version", "created_at", "issuer_id",
    "pipeline_id", "dag_hash", "run_id"
  ],
  "properties": {
    "schema_id":                { "const": "pipeline_manifest" },
    "schema_version":           { "const": "1.0.0" },
    "created_at":               { "type": "string", "format": "date-time" },
    "issuer_id":                { "type": "string" },
    "pipeline_id":              { "type": "string" },
    "pipeline_version":         { "type": "string" },
    "dag_hash":                 { "type": "string" },
    "parameters_hash":          { "type": "string" },
    "run_id":                   { "type": "string" },
    "input_attestation_ids":    { "type": "array", "items": { "type": "string" } },
    "output_attestation_ids":   { "type": "array", "items": { "type": "string" } },
    "stage_count":              { "type": "integer" },
    "stages":                   {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["stage_id", "agent_id"],
        "properties": {
          "stage_id":       { "type": "string" },
          "agent_id":       { "type": "string" },
          "action_receipt_id": { "type": "string" },
          "status":         { "type": "string" }
        }
      }
    },
    "metadata":                 { "type": "object" }
  },
  "additionalProperties": false
}
```

### 3.5 Custom Schemas

Tenants may define custom schemas by registering new receipt types via the Attestation Service API.

**Constraints for custom schemas:**

1. The `name` field MUST use snake_case, contain only lowercase alphanumeric characters and underscores, and be between 3-128 characters.
2. Custom schema names MUST NOT collide with built-in schema names listed in Section 3.4.
3. Custom schemas MUST include the four required base fields (`schema_id`, `schema_version`, `created_at`, `issuer_id`).
4. The `schema_json` field MUST be valid JSON Schema draft 2020-12.
5. The `$id` field SHOULD follow the pattern `https://maip.truthlocks.com/schemas/{tenant_hint}/{name}/{version}`.

**Validation rules:**

- At mint time, the Attestation Service validates the receipt payload against the schema's `required` array and `properties` type constraints.
- Unknown properties are rejected if `additionalProperties: false` is set in the schema.
- Schema validation failures return HTTP 422 with a `PAYLOAD_SCHEMA_INVALID` error code and a list of missing or invalid fields.

**Backward compatibility requirements:**

- Custom schemas MUST follow semver for versioning.
- MINOR version bumps (e.g., 1.0.0 to 1.1.0) MUST be additive-only: new optional fields may be added, but no existing fields may be removed or have their types changed.
- MAJOR version bumps (e.g., 1.0.0 to 2.0.0) are required for: removing required fields, changing field types, changing field semantics, or renaming fields.
- Receipts minted against a schema version remain valid and verifiable regardless of subsequent schema changes.

### 3.6 Schema Versioning

**Version format**: Semantic versioning (`MAJOR.MINOR.PATCH`) per https://semver.org.

**Version resolution**: When a receipt type name is specified without a version (e.g., `action_receipt`), the system resolves to the latest `active` version.

**Evolution rules:**

| Change Type | Version Impact | Example |
|------------|---------------|---------|
| Add optional field | MINOR bump | 1.0.0 -> 1.1.0 |
| Add new enum value to existing field | MINOR bump | 1.1.0 -> 1.2.0 |
| Fix description/documentation only | PATCH bump | 1.2.0 -> 1.2.1 |
| Remove required field | MAJOR bump (new schema_id) | 1.x.y -> 2.0.0 |
| Change field type | MAJOR bump (new schema_id) | 1.x.y -> 2.0.0 |
| Rename field | MAJOR bump (new schema_id) | 1.x.y -> 2.0.0 |
| Narrow enum values | MAJOR bump (new schema_id) | 1.x.y -> 2.0.0 |

**Breaking change policy**: For MAIP built-in schemas, breaking changes MUST be introduced as a new `schema_id` rather than a version bump. For example, `action_receipt` v1 would be deprecated and `action_receipt_v2` registered, rather than bumping `action_receipt` to 2.0.0. This ensures that verifiers compiled against the v1 schema never encounter incompatible payloads.

---

## 4. Database Schema

### 4.1 Overview

MAIP extends the existing Truthlocks database with four core tables and three extension tables. All tables follow established patterns:

- UUID primary keys (v7 time-ordered where applicable)
- Row-Level Security (RLS) scoped to `app.tenant_id`
- Platform admin audit access via `app.platform_admin_mode`
- `created_at` / `updated_at` timestamps on every table
- JSONB for flexible structured data

### 4.2 Core Tables

#### 4.2.1 `agent_identities`

Stores the identity registry for all MAIP agents within a tenant.

```sql
CREATE TABLE agent_identities (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL,
    agent_id                TEXT NOT NULL,
        -- Format: maip:<first8_of_tenant_uuid>:<ulid>
        -- UNIQUE within the table
    display_name            TEXT NOT NULL,
    trust_level             TEXT NOT NULL DEFAULT 'delegated'
        CHECK (trust_level IN ('system', 'delegated', 'ephemeral')),
    parent_agent_id         TEXT,
        -- NULL for root agents (delegated directly by human/org)
    genesis_attestation_id  UUID NOT NULL,
        -- References the attestation minted at agent creation
    genesis_public_key      TEXT NOT NULL,
        -- Base64url-encoded Ed25519 public key
    status                  TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'suspended', 'revoked')),
    capabilities            JSONB NOT NULL DEFAULT '[]',
        -- Array of scope strings this agent was initially granted
    max_delegation_depth    INTEGER NOT NULL DEFAULT 3
        CHECK (max_delegation_depth >= 0 AND max_delegation_depth <= 8),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at              TIMESTAMPTZ,

    UNIQUE (agent_id),
    UNIQUE (tenant_id, agent_id)
);

-- Indexes
CREATE INDEX idx_agent_identities_tenant
    ON agent_identities(tenant_id);
CREATE INDEX idx_agent_identities_parent
    ON agent_identities(tenant_id, parent_agent_id)
    WHERE parent_agent_id IS NOT NULL;
CREATE INDEX idx_agent_identities_status
    ON agent_identities(tenant_id, status);
CREATE INDEX idx_agent_identities_genesis
    ON agent_identities(genesis_attestation_id);

-- RLS
ALTER TABLE agent_identities ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_identities FORCE ROW LEVEL SECURITY;
CREATE POLICY agent_identities_tenant_isolation ON agent_identities
    USING (
        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        OR current_setting('app.platform_admin_mode', true) = 'true'
    );
```

#### 4.2.2 `agent_delegations`

Tracks the authority delegation chain between agents.

```sql
CREATE TABLE agent_delegations (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                   UUID NOT NULL,
    parent_agent_id             TEXT NOT NULL,
        -- maip agent ID of the delegating agent
    child_agent_id              TEXT NOT NULL,
        -- maip agent ID of the receiving agent
    depth                       INTEGER NOT NULL
        CHECK (depth >= 0 AND depth <= 8),
    scopes                      JSONB NOT NULL,
        -- Array of scope strings. Must be subset of parent's scopes.
    max_depth                   INTEGER NOT NULL DEFAULT 3
        CHECK (max_depth >= 0 AND max_depth <= 8),
    expires_at                  TIMESTAMPTZ,
    constraints                 JSONB DEFAULT '{}',
        -- Rate limits, IP allowlists, time windows
    delegation_attestation_id   UUID NOT NULL,
        -- References the attestation backing this delegation
    status                      TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'expired', 'revoked')),
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at                  TIMESTAMPTZ,

    UNIQUE (tenant_id, parent_agent_id, child_agent_id)
);

-- Indexes
CREATE INDEX idx_agent_delegations_tenant
    ON agent_delegations(tenant_id);
CREATE INDEX idx_agent_delegations_parent
    ON agent_delegations(tenant_id, parent_agent_id);
CREATE INDEX idx_agent_delegations_child
    ON agent_delegations(tenant_id, child_agent_id);
CREATE INDEX idx_agent_delegations_active
    ON agent_delegations(tenant_id, status)
    WHERE status = 'active';

-- RLS
ALTER TABLE agent_delegations ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_delegations FORCE ROW LEVEL SECURITY;
CREATE POLICY agent_delegations_tenant_isolation ON agent_delegations
    USING (
        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        OR current_setting('app.platform_admin_mode', true) = 'true'
    );
```

#### 4.2.3 `action_receipts`

Records discrete actions taken by agents.

```sql
CREATE TABLE action_receipts (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL,
    agent_id                TEXT NOT NULL,
    action_type             TEXT NOT NULL,
        -- e.g., 'inference', 'data_access', 'api_call', 'transformation'
    inputs_hash             TEXT NOT NULL,
        -- Base64url SHA-256 of the action inputs
    outputs_hash            TEXT NOT NULL,
        -- Base64url SHA-256 of action outputs; 'PENDING' for async
    scopes_used             JSONB NOT NULL DEFAULT '[]',
        -- Array of scope strings exercised by this action
    delegation_chain_hash   TEXT NOT NULL,
        -- SHA-256 of the full delegation chain at action time
    attestation_id          UUID NOT NULL,
        -- References the attestation backing this receipt
    previous_receipt_id     UUID,
        -- Chain link to the prior receipt by this agent (NULL for first)
    status                  TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'COMPLETE', 'FAILED')),
    duration_ms             INTEGER,
    error_code              TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_action_receipts_tenant
    ON action_receipts(tenant_id);
CREATE INDEX idx_action_receipts_agent
    ON action_receipts(tenant_id, agent_id, created_at DESC);
CREATE INDEX idx_action_receipts_chain
    ON action_receipts(tenant_id, agent_id, previous_receipt_id);
CREATE INDEX idx_action_receipts_type
    ON action_receipts(tenant_id, action_type);
CREATE INDEX idx_action_receipts_attestation
    ON action_receipts(attestation_id);
CREATE INDEX idx_action_receipts_status
    ON action_receipts(tenant_id, status)
    WHERE status = 'PENDING';

-- RLS
ALTER TABLE action_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE action_receipts FORCE ROW LEVEL SECURITY;
CREATE POLICY action_receipts_tenant_isolation ON action_receipts
    USING (
        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        OR current_setting('app.platform_admin_mode', true) = 'true'
    );
```

#### 4.2.4 `dataset_attestations`

Records signed dataset versions with Merkle roots for inclusion proofs.

```sql
CREATE TABLE dataset_attestations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    agent_id            TEXT NOT NULL,
    dataset_id          TEXT NOT NULL,
    merkle_root         TEXT NOT NULL,
        -- Base64url Merkle root hash
    chunk_count         INTEGER NOT NULL CHECK (chunk_count > 0),
    chunk_size_bytes    INTEGER NOT NULL DEFAULT 1048576,
        -- Default 1 MB chunks
    total_size_bytes    BIGINT,
    record_count        BIGINT,
    schema_id           TEXT,
        -- Optional: schema family of records within the dataset
    attestation_id      UUID NOT NULL,
        -- References the attestation backing this record
    version             TEXT NOT NULL DEFAULT '1.0.0',
    superseded_by       UUID,
        -- Points to the newer dataset_attestation that replaces this one
    lineage             JSONB DEFAULT '{}',
        -- { source_dataset_ids: [...], transformation_receipt_id: "..." }
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (tenant_id, dataset_id, version)
);

-- Indexes
CREATE INDEX idx_dataset_attestations_tenant
    ON dataset_attestations(tenant_id);
CREATE INDEX idx_dataset_attestations_dataset
    ON dataset_attestations(tenant_id, dataset_id, version DESC);
CREATE INDEX idx_dataset_attestations_agent
    ON dataset_attestations(tenant_id, agent_id);
CREATE INDEX idx_dataset_attestations_attestation
    ON dataset_attestations(attestation_id);

-- RLS
ALTER TABLE dataset_attestations ENABLE ROW LEVEL SECURITY;
ALTER TABLE dataset_attestations FORCE ROW LEVEL SECURITY;
CREATE POLICY dataset_attestations_tenant_isolation ON dataset_attestations
    USING (
        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        OR current_setting('app.platform_admin_mode', true) = 'true'
    );
```

### 4.3 Extension Tables

#### 4.3.1 `model_attestations`

Records signed model versions, binding weights hashes to training data lineage.

```sql
CREATE TABLE model_attestations (
    id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                       UUID NOT NULL,
    agent_id                        TEXT NOT NULL,
    model_id                        TEXT NOT NULL,
    model_version                   TEXT NOT NULL,
    weights_hash                    TEXT NOT NULL,
        -- Base64url SHA-256 of serialized model file
    framework                       TEXT,
        -- e.g., 'pytorch', 'tensorflow', 'jax'
    serialization_format            TEXT,
        -- e.g., 'safetensors', 'onnx', 'pickle'
    training_dataset_attestation_id UUID,
        -- FK to dataset_attestations.id
    metrics_hash                    TEXT,
        -- Base64url SHA-256 of evaluation metrics JSON
    evaluation_results              JSONB DEFAULT '{}',
    attestation_id                  UUID NOT NULL,
    superseded_by                   UUID,
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (tenant_id, model_id, model_version)
);

-- Indexes
CREATE INDEX idx_model_attestations_tenant
    ON model_attestations(tenant_id);
CREATE INDEX idx_model_attestations_model
    ON model_attestations(tenant_id, model_id, model_version DESC);
CREATE INDEX idx_model_attestations_training
    ON model_attestations(training_dataset_attestation_id)
    WHERE training_dataset_attestation_id IS NOT NULL;
CREATE INDEX idx_model_attestations_attestation
    ON model_attestations(attestation_id);

-- RLS
ALTER TABLE model_attestations ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_attestations FORCE ROW LEVEL SECURITY;
CREATE POLICY model_attestations_tenant_isolation ON model_attestations
    USING (
        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        OR current_setting('app.platform_admin_mode', true) = 'true'
    );
```

#### 4.3.2 `pipeline_manifests`

Records pipeline execution manifests linking stages, inputs, and outputs.

```sql
CREATE TABLE pipeline_manifests (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL,
    agent_id                TEXT NOT NULL,
    pipeline_id             TEXT NOT NULL,
    pipeline_version        TEXT,
    dag_hash                TEXT NOT NULL,
        -- Base64url SHA-256 of JCS-canonicalized DAG definition
    parameters_hash         TEXT NOT NULL,
        -- Base64url SHA-256 of JCS-canonicalized parameters
    input_attestation_ids   UUID[] NOT NULL DEFAULT '{}',
        -- Array of attestation IDs for pipeline inputs
    output_attestation_ids  UUID[] NOT NULL DEFAULT '{}',
        -- Array of attestation IDs for pipeline outputs
    run_id                  TEXT NOT NULL,
    stage_count             INTEGER,
    stages                  JSONB DEFAULT '[]',
        -- Array of { stage_id, agent_id, action_receipt_id, status }
    attestation_id          UUID NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (tenant_id, pipeline_id, run_id)
);

-- Indexes
CREATE INDEX idx_pipeline_manifests_tenant
    ON pipeline_manifests(tenant_id);
CREATE INDEX idx_pipeline_manifests_pipeline
    ON pipeline_manifests(tenant_id, pipeline_id);
CREATE INDEX idx_pipeline_manifests_run
    ON pipeline_manifests(run_id);
CREATE INDEX idx_pipeline_manifests_attestation
    ON pipeline_manifests(attestation_id);

-- RLS
ALTER TABLE pipeline_manifests ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_manifests FORCE ROW LEVEL SECURITY;
CREATE POLICY pipeline_manifests_tenant_isolation ON pipeline_manifests
    USING (
        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        OR current_setting('app.platform_admin_mode', true) = 'true'
    );
```

#### 4.3.3 `truth_claims`

Records multi-witness truth assertions where multiple issuers attest to the same claim.

```sql
CREATE TABLE truth_claims (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    claim_type          TEXT NOT NULL,
        -- e.g., 'document_authenticity', 'model_accuracy', 'data_integrity'
    subject_hash        TEXT NOT NULL,
        -- Base64url SHA-256 of the claim subject
    subject_description TEXT,
    attestation_ids     UUID[] NOT NULL DEFAULT '{}',
        -- Array of attestation IDs from contributing witnesses
    witness_count       INTEGER NOT NULL DEFAULT 0,
    consensus_threshold INTEGER NOT NULL DEFAULT 1,
        -- Minimum witnesses required for claim validity
    consensus_score     NUMERIC(5,4) NOT NULL DEFAULT 0.0,
        -- Weighted score based on witness trust levels (0.0 to 1.0)
    status              TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'confirmed', 'disputed', 'expired')),
    expires_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_truth_claims_tenant
    ON truth_claims(tenant_id);
CREATE INDEX idx_truth_claims_subject
    ON truth_claims(tenant_id, subject_hash);
CREATE INDEX idx_truth_claims_type
    ON truth_claims(tenant_id, claim_type);
CREATE INDEX idx_truth_claims_status
    ON truth_claims(tenant_id, status)
    WHERE status IN ('pending', 'confirmed');

-- RLS
ALTER TABLE truth_claims ENABLE ROW LEVEL SECURITY;
ALTER TABLE truth_claims FORCE ROW LEVEL SECURITY;
CREATE POLICY truth_claims_tenant_isolation ON truth_claims
    USING (
        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        OR current_setting('app.platform_admin_mode', true) = 'true'
    );
```

### 4.4 Cross-Table References

The following diagram shows how MAIP tables reference each other and the existing Truthlocks tables:

```
                          Existing Truthlocks
                    ┌──────────────────────────────┐
                    │  attestations                 │
                    │  (attestation-service)        │
                    │  ─────────────────            │
                    │  attestation_id (PK)          │
                    │  tenant_id                    │
                    │  issuer_id                    │
                    │  payload_hash                 │
                    │  signature                    │
                    │  log_id                       │
                    └──────────┬───────────────────┘
                               │
           ┌───────────────────┼───────────────────────┐
           │                   │                        │
           ▼                   ▼                        ▼
  ┌──────────────┐  ┌───────────────────┐  ┌──────────────────┐
  │ agent_       │  │ agent_            │  │ action_          │
  │ identities   │  │ delegations       │  │ receipts         │
  │              │  │                   │  │                  │
  │ genesis_     │  │ delegation_       │  │ attestation_id ──┤──► attestations
  │ attestation  │  │ attestation_id ───┤──► attestations     │
  │ _id ─────────┤──► attestations      │  │ agent_id ────────┤──► agent_identities
  │              │  │ parent_agent_id ──┤──► agent_identities │  │ previous_receipt │
  │              │  │ child_agent_id ───┤──► agent_identities │  │ _id ─────────────┤──► action_receipts
  └──────────────┘  └───────────────────┘  └──────────────────┘
                                                    │
                                                    │
  ┌──────────────────┐  ┌───────────────────┐  ┌───┴──────────────┐
  │ dataset_         │  │ model_            │  │ pipeline_        │
  │ attestations     │  │ attestations      │  │ manifests        │
  │                  │  │                   │  │                  │
  │ attestation_id ──┤  │ training_dataset_ │  │ input/output_    │
  │                  │  │ attestation_id ───┤──► dataset_         │  attestation_ids │
  │                  │  │ attestation_id ───┤  │ attestations     │  ──► attestations│
  └──────────────────┘  └───────────────────┘  └──────────────────┘
                                │
                                │
                    ┌───────────┴──────────┐
                    │ truth_claims         │
                    │                      │
                    │ attestation_ids[] ───┤──► attestations
                    └──────────────────────┘
```

### 4.5 RLS and Audit Access

All MAIP tables enforce two-tier access:

1. **Tenant isolation**: Standard operations are scoped to `app.tenant_id`. Agents, delegations, receipts, and attestations are only visible to the tenant that owns them.

2. **Platform admin audit**: When `app.platform_admin_mode = 'true'` is set in the session, platform administrators can read across tenants for audit, compliance investigation, and support purposes. This mode is only activatable by service accounts with the `platform_admin` role.

**Audit trail**: All mutations to MAIP tables emit audit events via the existing `audit.Client` (see Attestation Service implementation). Audit events include:
- `AGENT_CREATED`, `AGENT_SUSPENDED`, `AGENT_REVOKED`
- `DELEGATION_CREATED`, `DELEGATION_REVOKED`
- `ACTION_RECEIPT_CREATED`, `ACTION_RECEIPT_COMPLETED`, `ACTION_RECEIPT_FAILED`
- `DATASET_ATTESTED`, `MODEL_ATTESTED`, `PIPELINE_RECORDED`
- `TRUTH_CLAIM_CREATED`, `TRUTH_CLAIM_CONFIRMED`, `TRUTH_CLAIM_DISPUTED`

---

## 5. Payload Size Strategy

### 5.1 Design Principle

MAIP attestations and receipts contain **hashes and metadata only** -- never raw content. This is a non-negotiable architectural constraint that ensures:

- O(1) storage cost per attestation regardless of artifact size
- No data residency concerns (file content stays with the client)
- Constant-time verification (hash comparison, not content inspection)
- Privacy by design (content is never exposed to the attestation infrastructure)

### 5.2 Receipt Size Budgets

| Component | Typical Size | Maximum Size |
|-----------|-------------|-------------|
| Receipt envelope (canonical JSON) | 500 bytes - 4 KB | 64 KB |
| Metadata field | 0 - 8 KB | 64 KB |
| Full receipt event row (DB) | 1 - 8 KB | 128 KB |
| Proof bundle (receipt + attestation + delegation chain + inclusion proof) | 4 - 32 KB | 256 KB |

### 5.3 Large Dataset Strategy

For datasets that exceed practical single-hash size (i.e., where individual record verification is needed):

**Merkle tree construction:**

1. Split the dataset into chunks of configurable size (default: 1 MB, minimum: 1 KB, maximum: 64 MB).
2. Compute leaf hashes: `leaf_hash = SHA-256(0x00 || chunk_bytes)`
3. Build the tree bottom-up: `node_hash = SHA-256(0x01 || left || right)`
4. The Merkle root is stored in the `dataset_attestations.merkle_root` column.

**Proof-of-inclusion for a single record:**

To prove that a specific record exists within an attested dataset:

1. Identify which chunk contains the record (by byte offset or record index).
2. Provide the chunk bytes and the Merkle audit path (array of sibling hashes from leaf to root).
3. The verifier recomputes the leaf hash, walks the audit path, and checks that the result equals the attested Merkle root.

```
Verification:
  Given: chunk_bytes, chunk_index, audit_path[], attested_merkle_root

  1. leaf_hash = SHA-256(0x00 || chunk_bytes)
  2. current = leaf_hash
  3. for each (sibling, direction) in audit_path:
       if direction == LEFT:
         current = SHA-256(0x01 || sibling || current)
       else:
         current = SHA-256(0x01 || current || sibling)
  4. assert current == attested_merkle_root
```

This is consistent with the existing `merkle.VerifyInclusionProof` implementation in the Truthlocks transparency log.

**Configurable chunk size**: The chunk size is stored in the `dataset_attestations.chunk_size_bytes` column and is immutable for a given dataset version. Changing chunk size requires minting a new dataset attestation (new version).

### 5.4 Offline Verification Bundle Format

A complete offline verification bundle contains everything needed to verify a receipt without calling any server.

```json
{
  "bundle_id": "<uuid>",
  "bundle_version": "maip-bundle-v1",
  "generated_at": "<ISO 8601>",

  "receipt": {
    "receipt_id": "<uuid>",
    "receipt_type": "<schema_id>",
    "receipt_version": "<schema_version>",
    "status": "active",
    "issued_at": "<ISO 8601>",
    "issuer_id": "<maip agent ID or uuid>",
    "payload_hash": "<base64url>",
    "canonical_payload": { },
    "signature": {
      "alg": "Ed25519",
      "kid": "<key ID>",
      "value": "<base64url signature>"
    }
  },

  "delegation_chain": [
    {
      "depth": 0,
      "parent_agent_id": "<maip:...>",
      "child_agent_id": "<maip:...>",
      "scopes": ["inference", "data_read"],
      "delegation_attestation_id": "<uuid>",
      "delegation_signature": {
        "alg": "Ed25519",
        "kid": "<key ID>",
        "value": "<base64url>"
      }
    }
  ],

  "issuer_key": {
    "kid": "<key ID>",
    "alg": "Ed25519",
    "public_key_b64url": "<base64url Ed25519 public key>",
    "status": "active",
    "valid_from": "<ISO 8601>",
    "valid_to": "<ISO 8601 | null>",
    "compromised_at": null
  },

  "transparency_log": {
    "log_id": "<uuid>",
    "checkpoint": {
      "tree_size": 42,
      "root_hash_b64url": "<base64url>",
      "issued_at": "<ISO 8601>",
      "signature_b64url": "<base64url>",
      "signing_pubkey_b64url": "<base64url>",
      "signature_alg": "Ed25519"
    },
    "inclusion_proof": {
      "leaf_index": 7,
      "leaf_hash_b64url": "<base64url>",
      "audit_path_b64url": ["<base64url>", "<base64url>", "..."],
      "hash_alg": "SHA-256"
    }
  },

  "bundle_hash_b64url": "<base64url SHA-256 of bundle>"
}
```

This format extends the existing Truthlocks proof bundle (see `HandleGetReceiptProofBundle`) with delegation chain data.

---

## 6. Data Lineage Tracking

### 6.1 Lineage Model

MAIP lineage is a directed acyclic graph (DAG) of attestation references. Each node in the graph is an attestation (agent identity, delegation, action receipt, dataset attestation, model attestation, or pipeline manifest). Edges represent derivation relationships.

```
                    ┌─────────────────┐
                    │ Raw Source Data  │
                    │ (file attestation)│
                    └────────┬────────┘
                             │ dataset_attestation
                             │ (lineage.source_dataset_ids)
                             ▼
                    ┌─────────────────┐
                    │ Training Dataset │
                    │ (Merkle root)    │
                    └────────┬────────┘
                             │ model_attestation
                             │ (training_dataset_attestation_id)
                             ▼
                    ┌─────────────────┐
                    │ Model Weights    │
                    │ (weights_hash)   │
                    └────────┬────────┘
                             │ inference_receipt
                             │ (model_attestation_id)
                             ▼
                    ┌─────────────────┐
                    │ Model Output     │
                    │ (inference result)│
                    └─────────────────┘
```

### 6.2 Lineage References

Each MAIP record type maintains references to its provenance:

| Record Type | Lineage Field | References |
|------------|---------------|------------|
| `dataset_attestations` | `lineage.source_dataset_ids` | Array of parent dataset IDs |
| `dataset_attestations` | `lineage.transformation_receipt_id` | Action receipt for the transform |
| `model_attestations` | `training_dataset_attestation_id` | Dataset used for training |
| `action_receipts` | `inputs_hash` | Hash of all inputs (binds to source) |
| `inference_receipt` (schema) | `model_attestation_id` | Specific model version used |
| `pipeline_manifests` | `input_attestation_ids` | Array of input attestation IDs |
| `pipeline_manifests` | `output_attestation_ids` | Array of output attestation IDs |
| `pipeline_manifests` | `stages[].action_receipt_id` | Per-stage action receipts |

### 6.3 Lineage Query Patterns

**Forward lineage** ("What was this data used for?"):

Given a `dataset_attestation_id`, find all downstream consumers:

```sql
-- Find all models trained on this dataset
SELECT * FROM model_attestations
WHERE training_dataset_attestation_id = $1;

-- Find all pipelines that used this dataset as input
SELECT * FROM pipeline_manifests
WHERE $1 = ANY(input_attestation_ids);
```

**Reverse lineage** ("What went into this model output?"):

Given an `action_receipt_id` for an inference result, trace back to the raw source:

```
Step 1: action_receipt -> attestation_id -> get receipt payload
Step 2: payload.model_attestation_id -> model_attestations row
Step 3: model_attestations.training_dataset_attestation_id -> dataset_attestations row
Step 4: dataset_attestations.lineage.source_dataset_ids -> parent datasets
Step 5: Recurse until source datasets have no parents (leaf sources)
```

**Full provenance query** ("Show me everything"):

```sql
-- Recursive CTE to walk the lineage graph
WITH RECURSIVE lineage AS (
    -- Base case: the target action receipt
    SELECT
        ar.attestation_id AS node_id,
        'action_receipt' AS node_type,
        0 AS depth
    FROM action_receipts ar
    WHERE ar.id = $1

    UNION ALL

    -- Model attestation referenced by inference receipt payload
    SELECT
        ma.attestation_id,
        'model_attestation',
        l.depth + 1
    FROM lineage l
    JOIN model_attestations ma ON ma.attestation_id = l.node_id
    WHERE l.node_type = 'action_receipt'

    UNION ALL

    -- Training dataset referenced by model
    SELECT
        da.attestation_id,
        'dataset_attestation',
        l.depth + 1
    FROM lineage l
    JOIN model_attestations ma ON ma.attestation_id = l.node_id
    JOIN dataset_attestations da ON da.id = ma.training_dataset_attestation_id
    WHERE l.node_type = 'model_attestation'
)
SELECT * FROM lineage ORDER BY depth;
```

### 6.4 Lineage Integrity

Lineage references are verified by checking that:

1. Each referenced attestation exists and is not revoked.
2. The chain of hashes is consistent (each attestation's payload_hash matches the content it claims to reference).
3. All attestations in the lineage belong to the same tenant (enforced by RLS).
4. Delegation scopes at each step in the chain are sufficient for the action type.

A broken lineage (missing or revoked intermediate attestation) does not invalidate the leaf attestation itself but is reported as a `LINEAGE_INCOMPLETE` warning during verification.

---

## 7. Conformance

### 7.1 Conformance Levels

| Level | Requirements |
|-------|-------------|
| **MAIP Core** | Agent identities, delegations (depth 0-8), action receipts, offline verification bundles, Ed25519 signatures |
| **MAIP Data** | Core + dataset attestations with Merkle proofs, model attestations, feature vectors |
| **MAIP Pipeline** | Data + pipeline manifests, stage-level receipts, lineage DAG queries |
| **MAIP Enterprise** | Pipeline + truth claims (multi-witness), compliance receipts, ES256/RS256 support, KMS provider integration |

### 7.2 Implementation Requirements

A conforming implementation MUST:

1. Generate agent IDs in the `maip:<tenant_hint>:<ulid>` format.
2. Use SHA-256 for all payload hashing.
3. Support Ed25519 signatures at minimum.
4. Enforce `MAIP_MAX_DEPTH = 8` for delegation chains.
5. Validate scope subsetting at each delegation level (child scopes must be a subset of parent scopes).
6. Anchor all attestations in a transparency log with RFC 6962-compatible Merkle inclusion proofs.
7. Support offline verification using the bundle format defined in Section 5.4.
8. Validate receipt payloads against registered JSON Schemas at mint time.
9. Enforce RLS or equivalent tenant isolation for all multi-tenant deployments.
10. Use JCS (RFC 8785) for JSON canonicalization before hashing.

### 7.3 Protocol Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `MAIP_MAX_DEPTH` | 8 | Maximum delegation chain depth |
| `MAIP_DEFAULT_CHUNK_SIZE` | 1,048,576 (1 MB) | Default Merkle tree chunk size |
| `MAIP_MIN_CHUNK_SIZE` | 1,024 (1 KB) | Minimum allowed chunk size |
| `MAIP_MAX_CHUNK_SIZE` | 67,108,864 (64 MB) | Maximum allowed chunk size |
| `MAIP_MAX_METADATA_SIZE` | 65,536 (64 KB) | Maximum metadata payload size |
| `MAIP_MAX_DAG_SIZE` | 262,144 (256 KB) | Maximum DAG definition size |
| `MAIP_MAX_BUNDLE_SIZE` | 262,144 (256 KB) | Maximum offline verification bundle size |
| `MAIP_SPEC_VERSION` | `receipt-v1` | Current spec version identifier |
| `MAIP_HASH_ALGORITHM` | `SHA-256` | Mandatory hash algorithm |
| `MAIP_LEAF_PREFIX` | `0x00` | Merkle tree leaf domain separator |
| `MAIP_NODE_PREFIX` | `0x01` | Merkle tree internal node domain separator |

---

*End of MAIP Data Model Specification v1.0.0-draft*

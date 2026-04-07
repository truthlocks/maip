# MAIP Specification: ML/Data Pipeline Integration

**Protocol**: Machine Agent Identity Protocol (MAIP)
**Version**: 1.0.0-draft
**Status**: PROPOSED
**Date**: 2026-04-06
**Authors**: Truthlocks Architecture Team
**Depends On**: MAIP Core Identity, MAIP Delegation Chain, Truthlocks Attestation Service, Transparency Log

---

## Table of Contents

1. [Overview](#1-overview)
2. [Pipeline Insertion Points](#2-pipeline-insertion-points)
3. [MLflow Integration](#3-mlflow-integration)
4. [DVC (Data Version Control) Integration](#4-dvc-data-version-control-integration)
5. [Delta Lake / Data Lake Integration](#5-delta-lake--data-lake-integration)
6. [Kafka / PubSub Streaming](#6-kafka--pubsub-streaming)
7. [Feature Store Integration](#7-feature-store-integration)
8. [Inference Pipeline Middleware](#8-inference-pipeline-middleware)
9. [End-to-End Example: KYC Pipeline](#9-end-to-end-example-kyc-pipeline)
10. [End-to-End Example: Dataset Lineage](#10-end-to-end-example-dataset-lineage)
11. [Truth Verification for Documents and Compliance](#11-truth-verification-for-documents-and-compliance)

---

## 1. Overview

MAIP pipeline integration provides cryptographic provenance for every stage of
ML and data workflows. By inserting attestation and receipt hooks at critical
pipeline boundaries, organizations gain an immutable, verifiable chain of
custody from raw data ingestion through model inference output.

### 1.1 Design Principles

- **Non-intrusive**: Integrations attach as hooks, middleware, or plugins. Existing pipeline code requires minimal changes.
- **Configurable granularity**: Operators choose between per-record and per-batch attestation based on throughput and security requirements.
- **Framework-agnostic core**: The MAIP SDK provides a common interface; framework-specific adapters wrap it.
- **Offline-capable**: All attestations can be bundled for offline verification (see Delegation Chain spec, Section 5).

### 1.2 Core Receipt Types for Pipelines

| Receipt Type | Use Case |
|-------------|----------|
| `dataset_attestation` | Attests to a dataset's content hash, schema, and source metadata at a point in time |
| `action_receipt` | Records a transformation: input hash -> output hash, performed by a specific agent |
| `model_attestation` | Attests to a trained model's hash, training data reference, and evaluation metrics |
| `approval_receipt` | Records a human approval decision with evidence |
| `truth_claim_receipt` | Multi-witness attestation where independent parties attest to the same fact |
| `compliance_receipt` | Proves that a process met specific regulatory requirements |

---

## 2. Pipeline Insertion Points

### 2.1 Hook Architecture

MAIP hooks are inserted at the boundaries between pipeline stages. Each hook
either creates an attestation (for data/model artifacts) or a receipt (for
actions/transformations).

```
  Data          Pre-         Feature         Model        Model         Inference      Output
  Ingestion     processing   Engineering     Training     Registry      Serving        Delivery
 ┌─────────┐   ┌─────────┐  ┌─────────┐   ┌─────────┐  ┌─────────┐  ┌──────────┐  ┌─────────┐
 │  Raw     │   │ Clean / │  │ Feature │   │  Train  │  │  Store  │  │  Serve   │  │ Return  │
 │  Data    │──►│ Transform│─►│ Extract │──►│  Model  │─►│  Model  │─►│  Predict │─►│ Results │
 │  Source  │   │  Data   │  │  Store  │   │         │  │ Version │  │          │  │         │
 └────┬─────┘   └────┬────┘  └────┬────┘   └────┬────┘  └────┬────┘  └────┬─────┘  └────┬────┘
      │              │            │              │            │            │              │
      ▼              ▼            ▼              ▼            ▼            ▼              ▼
 [ATTEST]       [RECEIPT]    [ATTEST]       [RECEIPT]    [ATTEST]     [RECEIPT]      [RECEIPT]
 dataset_       action_      dataset_       action_      model_       action_        action_
 attestation    receipt      attestation    receipt      attestation  receipt        receipt
      │              │            │              │            │            │              │
      │         input: raw   feature view   input: feat  model hash   input_hash     output_hash
      │         output: clean hash + ver    output: model + metrics   output_hash    + model ref
 raw data       transform    + row count    + train data  + train      + model_att
 Merkle root    descriptor                  Merkle root   data ref
```

### 2.2 Hook Execution Model

Each hook follows a standard lifecycle:

```
Pipeline Stage Completes
        │
        ▼
┌───────────────────────────────┐
│ 1. Compute content hash(es)  │  SHA-256 of output artifact(s)
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────┐
│ 2. Build attestation/receipt │  Include input refs, output hash,
│    payload                   │  agent_id, timestamp, scopes
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────┐
│ 3. Sign with agent's key     │  Ed25519 signature over payload
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────┐
│ 4. Submit to Attestation     │  Returns attestation_id / receipt_id
│    Service                   │  Anchored in transparency log
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────┐
│ 5. Store reference in        │  Tag, metadata field, or header
│    pipeline artifact         │  depending on integration
└───────────────────────────────┘
```

### 2.3 Batch vs. Per-Record Attestation

| Mode | When to Use | Overhead |
|------|-------------|----------|
| **Per-record** | High-security pipelines, compliance-critical data, low-volume streams | ~2-5ms per attestation |
| **Per-batch** | High-throughput streams, feature materialization, bulk ETL | ~2-5ms per batch (Merkle root of N records) |

Batch attestation uses a Merkle tree: individual records are leaves, and the
Merkle root is signed. Any single record can be verified against the root
using its inclusion proof.

---

## 3. MLflow Integration

### 3.1 Architecture

```
┌────────────────────────────────────────────────┐
│                  MLflow Server                  │
│                                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐ │
│  │ Tracking │  │ Artifact │  │   Model      │ │
│  │  Server  │  │  Store   │  │   Registry   │ │
│  └────┬─────┘  └────┬─────┘  └──────┬───────┘ │
│       │              │               │         │
└───────┼──────────────┼───────────────┼─────────┘
        │              │               │
        ▼              ▼               ▼
┌──────────────────────────────────────────────┐
│          MaipMlflowPlugin (post-hooks)       │
│                                              │
│  log_artifact() ──► maip attest-artifact     │
│  log_model()   ──► maip attest-model         │
│  log_metric()  ──► (batched into run receipt)│
└──────────────────┬───────────────────────────┘
                   │
                   ▼
          Truthlocks Attestation Service
```

### 3.2 Hook: `mlflow.log_artifact()` Post-Hook

When an artifact is logged to MLflow, the MAIP plugin automatically creates a
signed attestation.

**Signed payload**:

```json
{
  "type": "artifact_attestation",
  "artifact_hash": "sha256:e3b0c44298fc1c14...",
  "artifact_path": "models/classifier_v3.pkl",
  "run_id": "abc123def456",
  "experiment_id": "exp_789",
  "model_version": "3",
  "agent_id": "maip:a1b2c3d4:01HXYZ_TRAINER...",
  "timestamp": "2026-04-06T10:30:00Z"
}
```

**Storage**: The returned `attestation_id` is logged as an MLflow tag:

```
mlflow.set_tag("maip.attestation_id", "att_01HXYZ...")
mlflow.set_tag("maip.artifact_hash", "sha256:e3b0c44298fc1c14...")
```

### 3.3 Verification

```bash
# Verify all artifacts in an MLflow run
maip verify --mlflow-run abc123def456

# Output:
#   Run: abc123def456 (experiment: exp_789)
#   Artifacts: 3 found, 3 attested
#     [PASS] models/classifier_v3.pkl  (att_01HXYZ...)
#     [PASS] data/training_set.csv     (att_01HXYZ...)
#     [PASS] metrics/eval_results.json (att_01HXYZ...)
#   Delegation chain: VALID (depth=2, root=maip:a1b2c3d4:ROOT)
#   RESULT: ALL ARTIFACTS VERIFIED

# Verify a specific model version
maip verify --mlflow-model "classifier" --version 3
```

### 3.4 Python SDK

```python
from maip.integrations.mlflow import MaipMlflowPlugin

# Initialize the plugin (auto-registers hooks)
plugin = MaipMlflowPlugin(
    agent_id="maip:a1b2c3d4:01HXYZ_TRAINER...",
    private_key_path="/secrets/agent_key.pem",
    attestation_service_url="https://attest.truthlocks.com",
    auto_attest=True,           # Automatically attest all artifacts
    attest_metrics=True,        # Include metrics in run-level receipt
    attest_params=False,        # Skip parameter attestation (optional)
)

# Standard MLflow code -- MAIP hooks fire automatically
import mlflow

with mlflow.start_run():
    mlflow.log_param("learning_rate", 0.01)
    mlflow.log_metric("accuracy", 0.95)
    mlflow.log_artifact("model.pkl")       # <-- triggers maip attest-artifact
    mlflow.sklearn.log_model(model, "model") # <-- triggers maip attest-model

    # Manual attestation for custom artifacts
    plugin.attest_artifact(
        path="custom_report.pdf",
        metadata={"report_type": "evaluation", "dataset_version": "v2.1"}
    )

# Verify programmatically
from maip.integrations.mlflow import verify_run
result = verify_run("abc123def456")
assert result.status == "VALID"
```

---

## 4. DVC (Data Version Control) Integration

### 4.1 Architecture

```
┌──────────────────────────────────────────┐
│          Developer Workstation            │
│                                          │
│  dvc add data/raw.csv                    │
│       │                                  │
│       ▼                                  │
│  data/raw.csv.dvc  (DVC metafile)        │
│       │                                  │
│  dvc push                                │
│       │                                  │
│       ▼                                  │
│  ┌─────────────────────────────────┐     │
│  │  MAIP DVC Post-Push Hook       │     │
│  │  maip attest-dataset            │     │
│  │    --hash <dvc_file_md5>        │     │
│  │    --remote s3://bucket/path    │     │
│  │    --version <git_commit>       │     │
│  └──────────────┬──────────────────┘     │
│                 │                        │
└─────────────────┼────────────────────────┘
                  │
                  ▼
         Truthlocks Attestation Service
```

### 4.2 Hook: `dvc push` Post-Hook

Configure in `.dvc/config` or as a Git hook:

```yaml
# .dvc/hooks/post-push.yaml
- name: maip-attest
  command: maip attest-dataset
  args:
    - --dvc-file=${DVC_FILE}
    - --remote-path=${REMOTE_PATH}
    - --git-commit=${GIT_COMMIT}
```

**Signed payload**:

```json
{
  "type": "dataset_attestation",
  "dvc_file_hash": "md5:abc123...",
  "remote_path": "s3://my-bucket/data/raw.csv",
  "git_commit": "e3b0c44298fc1c149afbf4c8...",
  "file_size_bytes": 1048576,
  "row_count": 50000,
  "schema_hash": "sha256:def456...",
  "agent_id": "maip:a1b2c3d4:01HXYZ_DATA_ENG...",
  "timestamp": "2026-04-06T11:00:00Z"
}
```

### 4.3 Extended `.dvc` File

The MAIP attestation ID is appended to the `.dvc` metafile:

```yaml
# data/raw.csv.dvc
outs:
- md5: abc123def456789...
  size: 1048576
  path: raw.csv
  maip_attestation_id: att_01HXYZ...
```

### 4.4 Verification

```bash
# Verify a single DVC-tracked file
maip verify --dvc data/raw.csv.dvc

# Output:
#   File: data/raw.csv
#   DVC hash: md5:abc123...
#   Remote: s3://my-bucket/data/raw.csv
#   Attestation: att_01HXYZ... (valid)
#   Agent: maip:a1b2c3d4:01HXYZ_DATA_ENG...
#   Delegation chain: VALID (depth=1)
#   RESULT: DATASET VERIFIED

# Verify all DVC files in the repo
maip verify --dvc-all

# Check data lineage
maip lineage --dvc data/features.csv.dvc
#   raw.csv (att_01HXYZ_RAW...)
#     └── cleaned.csv (att_01HXYZ_CLEAN...)
#           └── features.csv (att_01HXYZ_FEAT...)
```

---

## 5. Delta Lake / Data Lake Integration

### 5.1 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Spark Cluster                           │
│                                                             │
│  spark.read.format("delta").load("/data/customers")         │
│       │                                                     │
│       ▼                                                     │
│  ┌─────────────────────────────────────────────────┐        │
│  │  Delta Table Version Change Listener            │        │
│  │  (Spark Listener or Delta Sharing Webhook)      │        │
│  │                                                 │        │
│  │  On version change:                             │        │
│  │    1. Compute Merkle root of new version        │        │
│  │    2. Hash the schema                           │        │
│  │    3. Hash the partition spec                   │        │
│  │    4. Call maip attest-delta-version             │        │
│  └────────────────────┬────────────────────────────┘        │
│                       │                                     │
└───────────────────────┼─────────────────────────────────────┘
                        │
                        ▼
               Truthlocks Attestation Service
```

### 5.2 Signed Payload

```json
{
  "type": "dataset_attestation",
  "subtype": "delta_table_version",
  "table_path": "s3://lakehouse/data/customers",
  "table_version": 42,
  "merkle_root": "sha256:aabb1122...",
  "schema_hash": "sha256:ccdd3344...",
  "partition_spec_hash": "sha256:eeff5566...",
  "row_count": 2500000,
  "file_count": 128,
  "operation": "MERGE",
  "previous_version_attestation_id": "att_01HXYZ_V41...",
  "agent_id": "maip:a1b2c3d4:01HXYZ_ETL...",
  "timestamp": "2026-04-06T12:00:00Z"
}
```

### 5.3 Storage

The attestation ID is stored in the Delta table's properties:

```sql
ALTER TABLE customers SET TBLPROPERTIES (
  'maip.attestation_id' = 'att_01HXYZ_V42...',
  'maip.merkle_root' = 'sha256:aabb1122...'
);
```

### 5.4 Time-Travel Verification

Delta Lake's time-travel capability pairs naturally with MAIP's attestation model:

```bash
# Verify the current version of a Delta table
maip verify --delta "s3://lakehouse/data/customers"

# Verify a specific historical version
maip verify --delta "s3://lakehouse/data/customers" --version 42

# Verify a table as of a specific timestamp
maip verify --delta "s3://lakehouse/data/customers" --as-of "2026-04-01T00:00:00Z"

# Output:
#   Table: s3://lakehouse/data/customers
#   Version: 42
#   Merkle root: sha256:aabb1122...
#   Schema hash: sha256:ccdd3344...
#   Attestation: att_01HXYZ_V42... (valid)
#   Signed at: 2026-04-06T12:00:00Z by maip:a1b2c3d4:01HXYZ_ETL...
#   Previous version: 41 (att_01HXYZ_V41..., also valid)
#   RESULT: TABLE VERSION VERIFIED
```

### 5.5 Lineage Across Versions

```bash
maip lineage --delta "s3://lakehouse/data/customers" --depth 5

# Output:
#   Version 42 (att_01HXYZ_V42, MERGE,  2026-04-06T12:00:00Z)
#     └── Version 41 (att_01HXYZ_V41, UPDATE, 2026-04-05T08:00:00Z)
#           └── Version 40 (att_01HXYZ_V40, INSERT, 2026-04-04T14:00:00Z)
#                 └── Version 39 (att_01HXYZ_V39, DELETE, 2026-04-03T09:00:00Z)
#                       └── Version 38 (att_01HXYZ_V38, INSERT, 2026-04-02T16:00:00Z)
```

---

## 6. Kafka / PubSub Streaming

### 6.1 Architecture

```
 ┌──────────────┐         ┌───────────────────┐         ┌──────────────┐
 │   Producer   │         │   Kafka Cluster    │         │   Consumer   │
 │              │         │                   │         │              │
 │  App Logic   │         │  ┌─────────────┐  │         │  ┌────────┐  │
 │      │       │         │  │   Topic      │  │         │  │ MAIP   │  │
 │      ▼       │         │  │             │  │         │  │ Verify │  │
 │  ┌────────┐  │  send   │  │  msg + hdrs │  │  poll   │  │ Middle-│  │
 │  │ MAIP   │──┼────────►│  │  ┌───────┐  │  │────────►│  │ ware   │  │
 │  │ Sign   │  │         │  │  │X-MAIP-│  │  │         │  └───┬────┘  │
 │  │ Middle-│  │         │  │  │Receipt│  │  │         │      │       │
 │  │ ware   │  │         │  │  │-ID    │  │  │         │  ┌───▼────┐  │
 │  └────────┘  │         │  │  └───────┘  │  │         │  │ App    │  │
 │              │         │  └─────────────┘  │         │  │ Logic  │  │
 └──────────────┘         │                   │         │  └────────┘  │
                          │  ┌─────────────┐  │         │              │
                          │  │    DLQ       │  │         │  Fail ──────►│
                          │  │ (dead letter)│◄─┼─────────┼── verify    │
                          │  └─────────────┘  │         │              │
                          └───────────────────┘         └──────────────┘
```

### 6.2 Producer Middleware

The producer middleware signs message batches and attaches receipt headers.

```python
from maip.integrations.kafka import MaipKafkaProducer

producer = MaipKafkaProducer(
    bootstrap_servers="kafka:9092",
    agent_id="maip:a1b2c3d4:01HXYZ_PRODUCER...",
    private_key_path="/secrets/agent_key.pem",
    batch_size=1000,              # Sign Merkle root of N messages
    attestation_service_url="https://attest.truthlocks.com",
)

# Send messages -- MAIP headers added automatically
producer.send("events-topic", key=b"user-123", value=event_bytes)
# When batch is full (1000 messages), Merkle root is computed and signed.
# Each message in the batch gets headers:
#   X-MAIP-Receipt-ID: rcpt_01HXYZ...
#   X-MAIP-Batch-Root: sha256:aabb...
#   X-MAIP-Batch-Index: 42          (position in Merkle tree)
#   X-MAIP-Batch-Proof: <base64>    (Merkle inclusion proof)
```

### 6.3 Consumer Middleware

The consumer middleware verifies receipts before passing messages to application logic.

```python
from maip.integrations.kafka import MaipKafkaConsumer

consumer = MaipKafkaConsumer(
    bootstrap_servers="kafka:9092",
    group_id="my-consumer-group",
    topics=["events-topic"],
    attestation_service_url="https://attest.truthlocks.com",
    verify_mode="strict",         # "strict" = reject unverified, "permissive" = log and pass
    dlq_topic="events-topic-dlq", # Dead letter queue for failed verification
)

for message in consumer:
    # message.maip_verified == True (or message was routed to DLQ)
    process(message)
```

### 6.4 Batch Attestation Details

```
Messages in batch:  [msg_0, msg_1, msg_2, ..., msg_999]

Merkle Tree:
                         root_hash
                        /          \
                   h_01              h_23
                  /    \            /    \
              h_0       h_1    h_2       h_3
              │         │      │         │
           msg_0..249  ...    ...    msg_750..999

Receipt payload:
{
  "type": "action_receipt",
  "subtype": "kafka_batch",
  "topic": "events-topic",
  "partition": 3,
  "offset_range": [100000, 100999],
  "batch_size": 1000,
  "merkle_root": "sha256:root_hash...",
  "agent_id": "maip:a1b2c3d4:01HXYZ_PRODUCER...",
  "timestamp": "2026-04-06T13:00:00Z"
}
```

### 6.5 Kafka Headers

| Header | Value | Description |
|--------|-------|-------------|
| `X-MAIP-Receipt-ID` | `rcpt_01HXYZ...` | The batch receipt ID |
| `X-MAIP-Batch-Root` | `sha256:aabb...` | Merkle root of the batch |
| `X-MAIP-Batch-Index` | `42` | This message's index in the batch |
| `X-MAIP-Batch-Proof` | `<base64>` | Merkle inclusion proof for this message |

### 6.6 Dead Letter Queue

Messages that fail MAIP verification are routed to a DLQ with additional headers:

| Header | Value |
|--------|-------|
| `X-MAIP-Failure-Reason` | `CHAIN_BROKEN`, `REVOKED`, `EXPIRED`, `INVALID_SIGNATURE`, etc. |
| `X-MAIP-Failure-Time` | ISO 8601 timestamp of verification failure |
| `X-MAIP-Original-Topic` | The source topic |

---

## 7. Feature Store Integration

### 7.1 Supported Feature Stores

| Feature Store | Hook Mechanism | Status |
|---------------|---------------|--------|
| **Feast** | Python decorator on materialization job | Supported |
| **Tecton** | Tecton workspace webhook | Supported |
| **SageMaker Feature Store** | EventBridge rule on `PutRecord` batch completion | Supported |
| **Custom** | MAIP SDK direct call | Always available |

### 7.2 Hook: Feature Materialization Completion

When a feature view is materialized (computed and stored), the MAIP hook
creates a dataset attestation.

```python
from maip.integrations.feast import MaipFeastPlugin

# Register the plugin with Feast
plugin = MaipFeastPlugin(
    agent_id="maip:a1b2c3d4:01HXYZ_FEATURE_ENG...",
    private_key_path="/secrets/agent_key.pem",
    attestation_service_url="https://attest.truthlocks.com",
)

# Feast materialization -- MAIP hook fires on completion
feast_repo.materialize(
    start_date=datetime(2026, 4, 1),
    end_date=datetime(2026, 4, 6),
)
# Plugin automatically attests each feature view that was materialized
```

**Signed payload**:

```json
{
  "type": "dataset_attestation",
  "subtype": "feature_view",
  "feature_view_name": "user_spending_features",
  "feature_view_version": "v3",
  "materialization_range": {
    "start": "2026-04-01T00:00:00Z",
    "end": "2026-04-06T00:00:00Z"
  },
  "row_count": 1250000,
  "feature_count": 24,
  "value_distribution_hash": "sha256:ffeedd...",
  "source_data_attestation_ids": ["att_01HXYZ_SRC1...", "att_01HXYZ_SRC2..."],
  "agent_id": "maip:a1b2c3d4:01HXYZ_FEATURE_ENG...",
  "timestamp": "2026-04-06T14:00:00Z"
}
```

### 7.3 Pre-Training Verification

Before model training begins, verify that all feature views used are properly
attested:

```python
from maip.integrations.feast import verify_feature_views

# Returns a dict of feature_view_name -> VerificationResult
results = verify_feature_views(
    feature_views=["user_spending_features", "user_profile_features"],
    materialization_date="2026-04-06",
)

for view_name, result in results.items():
    if result.status != "VALID":
        raise ValueError(f"Feature view {view_name} failed verification: {result.status}")

# All feature views verified -- proceed with training
```

---

## 8. Inference Pipeline Middleware

### 8.1 Architecture

```
Client Request
      │
      ▼
┌──────────────────────────────────────────────────────────────┐
│  Web Framework (FastAPI / Flask / Express)                    │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  MAIP Inference Middleware                             │  │
│  │                                                       │  │
│  │  1. Hash request input                                │  │
│  │  2. Forward to model endpoint                         │  │
│  │  3. Hash response output                              │  │
│  │  4. Create action_receipt:                             │  │
│  │     input_hash + output_hash + model_attestation_id   │  │
│  │  5. Add X-MAIP-Receipt-ID to response headers         │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌─────────────┐                                             │
│  │ Model       │                                             │
│  │ Endpoint    │  (unchanged application code)               │
│  └─────────────┘                                             │
└──────────────────────────────────────────────────────────────┘
      │
      ▼
Client Response (with X-MAIP-Receipt-ID header)
```

### 8.2 FastAPI Middleware

```python
from fastapi import FastAPI
from maip.integrations.fastapi import MaipInferenceMiddleware

app = FastAPI()

app.add_middleware(
    MaipInferenceMiddleware,
    agent_id="maip:a1b2c3d4:01HXYZ_INFERENCE...",
    private_key_path="/secrets/agent_key.pem",
    attestation_service_url="https://attest.truthlocks.com",
    model_attestation_id="att_01HXYZ_MODEL_V3...",
    mode="per_request",           # "per_request" or "batched"
    batch_size=100,               # Only used if mode="batched"
    include_paths=["/predict", "/classify"],  # Only attest these endpoints
)

@app.post("/predict")
async def predict(input_data: PredictRequest):
    result = model.predict(input_data.features)
    return {"prediction": result}

# Client receives:
# HTTP/1.1 200 OK
# X-MAIP-Receipt-ID: rcpt_01HXYZ...
# Content-Type: application/json
# {"prediction": 0.87}
```

### 8.3 Express.js Middleware

```javascript
const { maipInferenceMiddleware } = require("@maip/express");

app.use(
  "/predict",
  maipInferenceMiddleware({
    agentId: "maip:a1b2c3d4:01HXYZ_INFERENCE...",
    privateKeyPath: "/secrets/agent_key.pem",
    attestationServiceUrl: "https://attest.truthlocks.com",
    modelAttestationId: "att_01HXYZ_MODEL_V3...",
    mode: "per_request",
  })
);

app.post("/predict", (req, res) => {
  const result = model.predict(req.body.features);
  res.json({ prediction: result });
  // X-MAIP-Receipt-ID header is automatically added by middleware
});
```

### 8.4 Receipt Payload (Inference)

```json
{
  "type": "action_receipt",
  "subtype": "inference",
  "input_hash": "sha256:1122aabb...",
  "output_hash": "sha256:3344ccdd...",
  "model_attestation_id": "att_01HXYZ_MODEL_V3...",
  "model_version": "v3.2.1",
  "endpoint": "/predict",
  "latency_ms": 45,
  "agent_id": "maip:a1b2c3d4:01HXYZ_INFERENCE...",
  "timestamp": "2026-04-06T14:30:00Z"
}
```

### 8.5 Client-Side Verification

```python
import requests
from maip import verify_receipt

response = requests.post("https://api.example.com/predict", json={"features": [1, 2, 3]})

receipt_id = response.headers["X-MAIP-Receipt-ID"]
result = verify_receipt(receipt_id, attestation_service_url="https://attest.truthlocks.com")

assert result.status == "VALID"
assert result.model_version == "v3.2.1"
assert result.output_hash == compute_hash(response.json())
```

---

## 9. End-to-End Example: KYC Pipeline

### 9.1 Pipeline Overview

```
 User uploads      OCR            Liveness       Deepfake        Identity        Human         Final KYC       Compliance
 ID document       extraction     check          scan            match           review        decision        attestation
┌──────────┐    ┌──────────┐    ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐  ┌───────────┐  ┌──────────────┐
│  Step 1  │───►│  Step 2  │───►│  Step 3  │──►│  Step 4  │──►│  Step 5  │──►│  Step 6  │─►│  Step 7   │─►│   Step 8     │
│  ATTEST  │    │  RECEIPT │    │  RECEIPT │   │  RECEIPT │   │  RECEIPT │   │  RECEIPT │  │  RECEIPT  │  │   RECEIPT    │
└──────────┘    └──────────┘    └──────────┘   └──────────┘   └──────────┘   └──────────┘  └───────────┘  └──────────────┘
```

### 9.2 Step-by-Step Flow

**Step 1: Document Upload -- `dataset_attestation`**

```json
{
  "type": "dataset_attestation",
  "subtype": "document_upload",
  "document_hash": "sha256:aabb1122...",
  "content_type": "image/jpeg",
  "file_size_bytes": 245000,
  "upload_timestamp": "2026-04-06T10:00:00Z",
  "uploader_id": "user_01HXYZ...",
  "agent_id": "maip:a1b2c3d4:01HXYZ_UPLOAD_SVC...",
  "attestation_id": "att_KYC_STEP1..."
}
```

**Step 2: OCR Extraction -- `action_receipt`**

```json
{
  "type": "action_receipt",
  "subtype": "ocr_extraction",
  "input_hash": "sha256:aabb1122...",
  "input_attestation_id": "att_KYC_STEP1...",
  "output_hash": "sha256:ccdd3344...",
  "output_description": "extracted_fields: name, dob, id_number, address",
  "agent_id": "maip:a1b2c3d4:01HXYZ_OCR_SVC...",
  "model_attestation_id": "att_OCR_MODEL_V2...",
  "confidence_score": 0.98,
  "receipt_id": "rcpt_KYC_STEP2..."
}
```

**Step 3: Liveness Check -- `action_receipt`**

```json
{
  "type": "action_receipt",
  "subtype": "liveness_check",
  "input_hash": "sha256:eeff5566...",
  "input_description": "selfie_video_hash",
  "output": {
    "liveness_score": 0.99,
    "liveness_verdict": "LIVE"
  },
  "output_hash": "sha256:7788aabb...",
  "agent_id": "maip:a1b2c3d4:01HXYZ_LIVENESS_SVC...",
  "receipt_id": "rcpt_KYC_STEP3..."
}
```

**Step 4: Deepfake Scan -- `action_receipt`**

```json
{
  "type": "action_receipt",
  "subtype": "deepfake_scan",
  "input_hash": "sha256:aabb1122...",
  "input_attestation_id": "att_KYC_STEP1...",
  "output": {
    "deepfake_score": 0.02,
    "deepfake_verdict": "AUTHENTIC"
  },
  "output_hash": "sha256:9900bbcc...",
  "agent_id": "maip:a1b2c3d4:01HXYZ_DEEPFAKE_SVC...",
  "model_attestation_id": "att_DEEPFAKE_MODEL_V1...",
  "receipt_id": "rcpt_KYC_STEP4..."
}
```

**Step 5: Identity Match -- `action_receipt`**

```json
{
  "type": "action_receipt",
  "subtype": "identity_match",
  "inputs": [
    {"type": "extracted_fields", "hash": "sha256:ccdd3344...", "receipt_id": "rcpt_KYC_STEP2..."},
    {"type": "reference_data", "hash": "sha256:ddee4455...", "source": "government_id_database"}
  ],
  "output": {
    "match_score": 0.97,
    "match_verdict": "MATCH"
  },
  "output_hash": "sha256:ffgg5566...",
  "agent_id": "maip:a1b2c3d4:01HXYZ_ID_MATCH_SVC...",
  "receipt_id": "rcpt_KYC_STEP5..."
}
```

**Step 6: Human Review -- `approval_receipt`**

```json
{
  "type": "approval_receipt",
  "reviewer_id": "human_reviewer_01HXYZ...",
  "decision": "APPROVED",
  "evidence_hash": "sha256:aabbccdd...",
  "evidence_references": [
    "rcpt_KYC_STEP2...",
    "rcpt_KYC_STEP3...",
    "rcpt_KYC_STEP4...",
    "rcpt_KYC_STEP5..."
  ],
  "review_notes_hash": "sha256:eeff0011...",
  "review_duration_seconds": 120,
  "agent_id": "maip:a1b2c3d4:01HXYZ_REVIEW_CONSOLE...",
  "receipt_id": "rcpt_KYC_STEP6..."
}
```

**Step 7: Final KYC Decision -- `truth_claim_receipt`**

```json
{
  "type": "truth_claim_receipt",
  "claim": "identity_verified",
  "subject_id": "user_01HXYZ...",
  "witnesses": [
    {"agent_id": "maip:..._OCR_SVC...", "receipt_id": "rcpt_KYC_STEP2...", "verdict": "extracted"},
    {"agent_id": "maip:..._LIVENESS_SVC...", "receipt_id": "rcpt_KYC_STEP3...", "verdict": "LIVE"},
    {"agent_id": "maip:..._DEEPFAKE_SVC...", "receipt_id": "rcpt_KYC_STEP4...", "verdict": "AUTHENTIC"},
    {"agent_id": "maip:..._REVIEW_CONSOLE...", "receipt_id": "rcpt_KYC_STEP6...", "verdict": "APPROVED"}
  ],
  "consensus_method": "unanimous",
  "consensus_score": 1.0,
  "final_verdict": "IDENTITY_VERIFIED",
  "agent_id": "maip:a1b2c3d4:01HXYZ_KYC_ORCHESTRATOR...",
  "receipt_id": "rcpt_KYC_STEP7..."
}
```

**Step 8: Compliance Attestation -- `compliance_receipt`**

```json
{
  "type": "compliance_receipt",
  "regulation": "KYC/AML",
  "jurisdiction": "US",
  "regulatory_reference": "31 CFR 1020.220",
  "evidence_hash": "sha256:11223344...",
  "evidence_receipt_ids": [
    "rcpt_KYC_STEP1...",
    "rcpt_KYC_STEP2...",
    "rcpt_KYC_STEP3...",
    "rcpt_KYC_STEP4...",
    "rcpt_KYC_STEP5...",
    "rcpt_KYC_STEP6...",
    "rcpt_KYC_STEP7..."
  ],
  "valid_from": "2026-04-06T10:30:00Z",
  "valid_until": "2027-04-06T10:30:00Z",
  "agent_id": "maip:a1b2c3d4:01HXYZ_COMPLIANCE_SVC...",
  "receipt_id": "rcpt_KYC_STEP8..."
}
```

### 9.3 KYC Verification

```bash
# Verify the entire KYC pipeline for a user
maip verify --kyc-pipeline --user user_01HXYZ... --compliance-receipt rcpt_KYC_STEP8...

# Output:
#   KYC Pipeline Verification for user_01HXYZ...
#   ──────────────────────────────────────────────
#   [PASS] Step 1: Document upload attested (att_KYC_STEP1...)
#   [PASS] Step 2: OCR extraction verified (rcpt_KYC_STEP2..., confidence=0.98)
#   [PASS] Step 3: Liveness check verified (rcpt_KYC_STEP3..., score=0.99)
#   [PASS] Step 4: Deepfake scan verified (rcpt_KYC_STEP4..., authentic)
#   [PASS] Step 5: Identity match verified (rcpt_KYC_STEP5..., score=0.97)
#   [PASS] Step 6: Human review verified (rcpt_KYC_STEP6..., APPROVED)
#   [PASS] Step 7: Truth claim verified (rcpt_KYC_STEP7..., unanimous)
#   [PASS] Step 8: Compliance attestation valid (KYC/AML, expires 2027-04-06)
#   [PASS] All agent delegation chains valid
#   ──────────────────────────────────────────────
#   RESULT: KYC PIPELINE FULLY VERIFIED
```

---

## 10. End-to-End Example: Dataset Lineage

### 10.1 Pipeline Overview

```
  Raw Data       Data Cleaning     Feature Eng.      Model Training     Model Deploy
 ┌──────────┐   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
 │ Collect  │──►│ Remove nulls │─►│ Generate     │─►│ Train model  │─►│ Deploy to    │
 │ from     │   │ Normalize    │  │ feature      │  │ Log metrics  │  │ production   │
 │ source   │   │ Deduplicate  │  │ vectors      │  │ Register     │  │ endpoint     │
 └────┬─────┘   └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
      │                │                 │                  │                 │
      ▼                ▼                 ▼                  ▼                 ▼
 dataset_          action_           action_            model_            action_
 attestation       receipt           receipt            attestation       receipt
 (Merkle root)     (transform)       (pipeline_v2)      (hash+metrics)    (deploy target)
```

### 10.2 Step-by-Step Flow

**Step 1: Raw Data Collected -- `dataset_attestation`**

```json
{
  "type": "dataset_attestation",
  "dataset_id": "ds_raw_customers_20260406",
  "merkle_root": "sha256:raw_root_aabb...",
  "row_count": 5000000,
  "column_count": 45,
  "source_metadata": {
    "source_type": "postgresql",
    "source_table": "public.customer_events",
    "extraction_query_hash": "sha256:query_hash...",
    "extraction_timestamp": "2026-04-06T01:00:00Z"
  },
  "schema_hash": "sha256:schema_1122...",
  "agent_id": "maip:a1b2c3d4:01HXYZ_ETL_EXTRACT...",
  "attestation_id": "att_LINEAGE_STEP1..."
}
```

**Step 2: Data Cleaning -- `action_receipt`**

```json
{
  "type": "action_receipt",
  "subtype": "data_transform",
  "input_attestation_id": "att_LINEAGE_STEP1...",
  "input_merkle_root": "sha256:raw_root_aabb...",
  "output_merkle_root": "sha256:clean_root_ccdd...",
  "transform_descriptor": "remove_nulls+normalize_numeric+deduplicate_on_id",
  "transform_code_hash": "sha256:transform_code_eeff...",
  "input_row_count": 5000000,
  "output_row_count": 4850000,
  "rows_removed": 150000,
  "removal_breakdown": {
    "null_rows": 120000,
    "duplicate_rows": 30000
  },
  "agent_id": "maip:a1b2c3d4:01HXYZ_ETL_CLEAN...",
  "receipt_id": "rcpt_LINEAGE_STEP2..."
}
```

**Step 3: Feature Engineering -- `action_receipt`**

```json
{
  "type": "action_receipt",
  "subtype": "feature_engineering",
  "input_receipt_id": "rcpt_LINEAGE_STEP2...",
  "input_merkle_root": "sha256:clean_root_ccdd...",
  "output_merkle_root": "sha256:feature_root_eeff...",
  "pipeline_id": "feature_pipeline_v2",
  "pipeline_code_hash": "sha256:pipeline_code_1122...",
  "feature_count": 128,
  "output_row_count": 4850000,
  "feature_names_hash": "sha256:feature_names_3344...",
  "agent_id": "maip:a1b2c3d4:01HXYZ_FEATURE_ENG...",
  "receipt_id": "rcpt_LINEAGE_STEP3..."
}
```

**Step 4: Model Training -- `model_attestation`**

```json
{
  "type": "model_attestation",
  "model_id": "model_customer_churn_v4",
  "model_hash": "sha256:model_hash_5566...",
  "model_framework": "pytorch",
  "model_architecture": "transformer_classifier",
  "training_data_attestation_id": "rcpt_LINEAGE_STEP3...",
  "training_data_merkle_root": "sha256:feature_root_eeff...",
  "evaluation_metrics": {
    "accuracy": 0.943,
    "precision": 0.921,
    "recall": 0.958,
    "f1_score": 0.939,
    "auc_roc": 0.978
  },
  "hyperparameters_hash": "sha256:hparams_7788...",
  "training_duration_seconds": 3600,
  "training_epochs": 50,
  "agent_id": "maip:a1b2c3d4:01HXYZ_TRAINER...",
  "attestation_id": "att_LINEAGE_STEP4..."
}
```

**Step 5: Model Deployment -- `action_receipt`**

```json
{
  "type": "action_receipt",
  "subtype": "model_deployment",
  "model_attestation_id": "att_LINEAGE_STEP4...",
  "model_hash": "sha256:model_hash_5566...",
  "deployment_target": "ecs:production:model-serving-cluster",
  "deployment_config_hash": "sha256:deploy_config_9900...",
  "endpoint_url": "https://api.truthlocks.com/predict/customer-churn",
  "replicas": 3,
  "canary_percentage": 10,
  "rollback_attestation_id": "att_LINEAGE_PREV_DEPLOY...",
  "agent_id": "maip:a1b2c3d4:01HXYZ_DEPLOY_SVC...",
  "receipt_id": "rcpt_LINEAGE_STEP5..."
}
```

### 10.3 Lineage Query

```bash
# Query full lineage for a deployed model
maip lineage --model model_customer_churn_v4

# Output:
#
#   Model Lineage: model_customer_churn_v4
#   ═══════════════════════════════════════════════════════════════
#
#   [DEPLOY] rcpt_LINEAGE_STEP5  2026-04-06T16:00:00Z
#   │  target: ecs:production:model-serving-cluster
#   │  agent:  maip:a1b2c3d4:01HXYZ_DEPLOY_SVC
#   │
#   └──[MODEL] att_LINEAGE_STEP4  2026-04-06T15:00:00Z
#      │  hash:     sha256:model_hash_5566...
#      │  accuracy: 0.943, f1: 0.939, auc: 0.978
#      │  agent:    maip:a1b2c3d4:01HXYZ_TRAINER
#      │
#      └──[FEATURES] rcpt_LINEAGE_STEP3  2026-04-06T12:00:00Z
#         │  pipeline:    feature_pipeline_v2
#         │  features:    128
#         │  rows:        4,850,000
#         │  agent:       maip:a1b2c3d4:01HXYZ_FEATURE_ENG
#         │
#         └──[CLEAN] rcpt_LINEAGE_STEP2  2026-04-06T08:00:00Z
#            │  transform: remove_nulls+normalize+dedup
#            │  rows in:   5,000,000 -> out: 4,850,000
#            │  agent:     maip:a1b2c3d4:01HXYZ_ETL_CLEAN
#            │
#            └──[RAW] att_LINEAGE_STEP1  2026-04-06T01:00:00Z
#               │  source:   postgresql:public.customer_events
#               │  rows:     5,000,000
#               │  agent:    maip:a1b2c3d4:01HXYZ_ETL_EXTRACT
#               │
#               [ROOT OF LINEAGE]
#
#   All delegation chains: VALID
#   All attestations anchored in transparency log: VERIFIED
#   ═══════════════════════════════════════════════════════════════

# Export lineage as JSON for programmatic consumption
maip lineage --model model_customer_churn_v4 --format json > lineage.json

# Verify entire lineage (checks every attestation and receipt in the DAG)
maip lineage --model model_customer_churn_v4 --verify
```

---

## 11. Truth Verification for Documents and Compliance

### 11.1 Document Attestation

Document attestation proves that a specific document existed in a specific form
at a specific time, signed by a specific agent or human.

```
Document Attestation Flow:

  Document          Hash            Attestation           Transparency
  (any format)      Computation     Service               Log
 ┌──────────┐      ┌──────────┐   ┌──────────────┐      ┌──────────┐
 │  PDF,    │      │ SHA-256  │   │ Sign:        │      │ Anchor   │
 │  image,  │─────►│ of file  │──►│  hash +      │─────►│ with     │
 │  JSON,   │      │ content  │   │  metadata +  │      │ Merkle   │
 │  text    │      │          │   │  agent_id +  │      │ proof    │
 │          │      │          │   │  timestamp   │      │          │
 └──────────┘      └──────────┘   └──────────────┘      └──────────┘
                                        │
                                        ▼
                                  attestation_id
                                  returned to caller
```

**Document attestation payload**:

```json
{
  "type": "dataset_attestation",
  "subtype": "document",
  "document_hash": "sha256:aabb1122...",
  "content_type": "application/pdf",
  "file_size_bytes": 524288,
  "document_metadata": {
    "title": "Q1 2026 Financial Report",
    "author": "Finance Department",
    "page_count": 42,
    "language": "en"
  },
  "agent_id": "maip:a1b2c3d4:01HXYZ_DOC_SVC...",
  "timestamp": "2026-04-06T09:00:00Z",
  "attestation_id": "att_DOC_Q1_REPORT..."
}
```

**Verification**:

```bash
# Verify a document against its attestation
maip verify --document report.pdf --attestation att_DOC_Q1_REPORT...

# Output:
#   Document: report.pdf
#   Computed hash: sha256:aabb1122...
#   Attested hash: sha256:aabb1122...  [MATCH]
#   Attested at: 2026-04-06T09:00:00Z
#   Attested by: maip:a1b2c3d4:01HXYZ_DOC_SVC...
#   Transparency log: anchored at index 54321 [VERIFIED]
#   Delegation chain: VALID (depth=1)
#   RESULT: DOCUMENT VERIFIED -- this document existed in this form at this time
```

### 11.2 Multi-Witness Truth Claims

Multi-witness truth claims allow multiple independent parties to attest to the
same fact, creating a consensus-based trust score.

```
Independent Attestors:

  Witness A            Witness B            Witness C
  (Agent/Human)        (Agent/Human)        (Agent/Human)
 ┌──────────┐         ┌──────────┐         ┌──────────┐
 │ Attest:  │         │ Attest:  │         │ Attest:  │
 │ "Fact X  │         │ "Fact X  │         │ "Fact X  │
 │  is true"│         │  is true"│         │  is true"│
 └─────┬────┘         └─────┬────┘         └─────┬────┘
       │                    │                    │
       └────────────────────┼────────────────────┘
                            │
                            ▼
                   ┌──────────────────┐
                   │ Truth Claim      │
                   │ Aggregator       │
                   │                  │
                   │ Consensus: 3/3   │
                   │ Score: 1.0       │
                   │ Verdict: TRUE    │
                   └────────┬─────────┘
                            │
                            ▼
                   truth_claim_receipt
                   (anchored in log)
```

**Truth claim receipt**:

```json
{
  "type": "truth_claim_receipt",
  "claim_id": "claim_01HXYZ...",
  "claim_statement": "Document att_DOC_123 accurately represents Q1 2026 financials",
  "claim_hash": "sha256:claim_hash...",
  "witnesses": [
    {
      "witness_id": "maip:a1b2c3d4:01HXYZ_AUDITOR_A...",
      "attestation_id": "att_WITNESS_A...",
      "verdict": "TRUE",
      "confidence": 0.95,
      "timestamp": "2026-04-06T10:00:00Z"
    },
    {
      "witness_id": "maip:a1b2c3d4:01HXYZ_AUDITOR_B...",
      "attestation_id": "att_WITNESS_B...",
      "verdict": "TRUE",
      "confidence": 0.92,
      "timestamp": "2026-04-06T10:05:00Z"
    },
    {
      "witness_id": "maip:a1b2c3d4:01HXYZ_AUDITOR_C...",
      "attestation_id": "att_WITNESS_C...",
      "verdict": "TRUE",
      "confidence": 0.97,
      "timestamp": "2026-04-06T10:10:00Z"
    }
  ],
  "consensus_method": "weighted_majority",
  "consensus_threshold": 0.67,
  "consensus_score": 1.0,
  "weighted_confidence": 0.947,
  "final_verdict": "TRUE",
  "agent_id": "maip:a1b2c3d4:01HXYZ_TRUTH_AGG...",
  "receipt_id": "rcpt_TRUTH_CLAIM_01..."
}
```

### 11.3 Compliance Flow

Compliance receipts prove that a specific data handling process met regulatory
requirements. They reference the full chain of evidence.

```
Regulatory Compliance Flow:

  Data Processing Steps           Compliance Check            Compliance Receipt
 ┌───────────────────────┐       ┌──────────────────┐       ┌──────────────────────┐
 │ Step 1: Collect data  │       │                  │       │ regulation: GDPR     │
 │   receipt: rcpt_001   │       │ Verify each step │       │ article: Art. 30     │
 │ Step 2: Consent check │──────►│ meets regulatory │──────►│ evidence: [rcpt_001, │
 │   receipt: rcpt_002   │       │ requirements     │       │   rcpt_002, rcpt_003,│
 │ Step 3: Process data  │       │                  │       │   rcpt_004]          │
 │   receipt: rcpt_003   │       │ Automated policy │       │ valid_until: ...     │
 │ Step 4: Anonymize     │       │ engine + human   │       │ auditor: agent_id    │
 │   receipt: rcpt_004   │       │ sign-off         │       │                      │
 └───────────────────────┘       └──────────────────┘       └──────────────────────┘
```

**Compliance receipt payload**:

```json
{
  "type": "compliance_receipt",
  "regulation": "GDPR",
  "regulation_version": "2016/679",
  "specific_articles": ["Art. 6(1)(a)", "Art. 30"],
  "jurisdiction": "EU",
  "compliance_check_type": "data_processing_record",
  "subject_description": "Customer data processing for churn prediction model",
  "evidence_receipt_ids": [
    "rcpt_CONSENT_CHECK...",
    "rcpt_DATA_PROCESSING...",
    "rcpt_ANONYMIZATION...",
    "rcpt_RETENTION_POLICY..."
  ],
  "evidence_hash": "sha256:combined_evidence...",
  "automated_checks_passed": 12,
  "automated_checks_total": 12,
  "human_reviewer_id": "human_dpo_01HXYZ...",
  "human_review_receipt_id": "rcpt_DPO_REVIEW...",
  "valid_from": "2026-04-06T00:00:00Z",
  "valid_until": "2027-04-06T00:00:00Z",
  "agent_id": "maip:a1b2c3d4:01HXYZ_COMPLIANCE_SVC...",
  "receipt_id": "rcpt_GDPR_COMPLIANCE_01..."
}
```

### 11.4 Dispute Resolution

When conflicting attestations exist for the same claim, MAIP triggers a
dispute resolution workflow.

```
Conflict Detection:

  Witness A: "Fact X is TRUE"    vs.    Witness B: "Fact X is FALSE"
       │                                      │
       └──────────────┬───────────────────────┘
                      │
                      ▼
             ┌─────────────────┐
             │ Conflict        │
             │ Detected        │
             │                 │
             │ truth_claim has │
             │ conflicting     │
             │ witnesses       │
             └────────┬────────┘
                      │
                      ▼
             ┌─────────────────┐
             │ Dispute         │
             │ Receipt Created │
             │                 │
             │ status: OPEN    │
             │ escalated_to:   │
             │ governance      │
             └────────┬────────┘
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
    Additional    Governance    External
    Evidence      Panel Vote    Arbitration
          │           │           │
          └───────────┼───────────┘
                      │
                      ▼
             ┌─────────────────┐
             │ Resolution      │
             │ Receipt         │
             │                 │
             │ verdict: ...    │
             │ status: CLOSED  │
             │ resolution_type:│
             │ governance_vote │
             └─────────────────┘
```

**Dispute receipt**:

```json
{
  "type": "dispute_receipt",
  "dispute_id": "disp_01HXYZ...",
  "claim_id": "claim_01HXYZ...",
  "conflicting_attestations": [
    {"witness_id": "maip:..._A", "verdict": "TRUE", "attestation_id": "att_A..."},
    {"witness_id": "maip:..._B", "verdict": "FALSE", "attestation_id": "att_B..."}
  ],
  "status": "RESOLVED",
  "resolution": {
    "resolution_type": "governance_vote",
    "panel_members": ["gov_member_1", "gov_member_2", "gov_member_3"],
    "vote_result": {"TRUE": 2, "FALSE": 1},
    "final_verdict": "TRUE",
    "rationale_hash": "sha256:rationale..."
  },
  "opened_at": "2026-04-06T11:00:00Z",
  "resolved_at": "2026-04-07T15:00:00Z",
  "agent_id": "maip:a1b2c3d4:01HXYZ_GOVERNANCE...",
  "receipt_id": "rcpt_DISPUTE_01..."
}
```

### 11.5 Verification Commands

```bash
# Verify a document's existence at a point in time
maip verify --document report.pdf --attestation att_DOC_Q1_REPORT...

# Verify a multi-witness truth claim
maip verify --truth-claim claim_01HXYZ...

# Verify compliance for a regulation
maip verify --compliance rcpt_GDPR_COMPLIANCE_01...

# Check for disputes on a claim
maip disputes --claim claim_01HXYZ...

# Full audit trail for a compliance receipt
maip audit --compliance rcpt_GDPR_COMPLIANCE_01... --full
#   Compliance Receipt: rcpt_GDPR_COMPLIANCE_01...
#   Regulation: GDPR (2016/679), Articles: Art. 6(1)(a), Art. 30
#   ──────────────────────────────────────────────
#   Evidence chain:
#     [PASS] Consent check (rcpt_CONSENT_CHECK...)
#     [PASS] Data processing record (rcpt_DATA_PROCESSING...)
#     [PASS] Anonymization step (rcpt_ANONYMIZATION...)
#     [PASS] Retention policy applied (rcpt_RETENTION_POLICY...)
#   Human review:
#     [PASS] DPO sign-off (rcpt_DPO_REVIEW..., reviewer: human_dpo_01HXYZ)
#   Automated checks: 12/12 passed
#   Delegation chains: all VALID
#   Disputes: none
#   Valid until: 2027-04-06T00:00:00Z
#   ──────────────────────────────────────────────
#   RESULT: COMPLIANCE VERIFIED
```

---

*End of MAIP Pipeline Integration Specification v1.0.0-draft*

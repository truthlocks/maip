# MAIP Protocol Specification: AI Orchestration Layer

## MAIP-SPEC-ORCH-001 | Version 1.0 | Status: DRAFT

---

## 1. Overview

The AI Orchestration Layer is the coordination substrate for multi-agent systems built on MAIP. It manages agent workflows, LLM inference pipelines, tool use, and multi-agent coordination — all with full cryptographic receipt coverage. Every delegation, action, tool call, and inference produces a signed, chained, log-anchored MAIP receipt.

**Design principles**:
- Every agent action is receipted (no silent operations)
- Scopes narrow at every delegation level (least privilege)
- Orchestrators are agents too (same identity, same receipts)
- Privacy by design: receipt payloads contain hashes, not content
- Fail closed: unverified actions are rejected

**Protocol constants**:
- `MAIP_MAX_DEPTH = 8`
- `MAX_CONCURRENT_AGENTS_PER_ORCHESTRATOR = 50`
- `MAX_WORKFLOW_STEPS = 100`
- `DEFAULT_WORKFLOW_TIMEOUT = 300s`
- `LLM_RECEIPT_MODE = hash_only` (no prompt/response content in receipts)

---

## 2. Orchestration Architecture

### 2.1 Component Roles

```
                    Human / Org Root
                         |
                   DelegationAttestation (depth=0)
                         |
                         v
              +---------------------+
              |   Orchestrator      |  maip:<tenant>:<ulid>
              |   Agent             |  scopes: [orchestrate.*]
              +---------------------+
                /        |        \
     Delegation(d=1)  Delegation(d=1)  Delegation(d=1)
              /          |          \
        +--------+  +--------+  +--------+
        | Worker |  | Worker |  | Worker |
        | Agent A|  | Agent B|  | Agent C|
        +--------+  +--------+  +--------+
         scopes:     scopes:     scopes:
         [data.read] [model.infer][data.write]
```

**Orchestrator Agent**: A MAIP-registered agent with `orchestrate.*` scopes. Responsible for:
- Receiving tasks from humans or parent orchestrators
- Decomposing tasks into sub-tasks
- Delegating to worker agents (creating DelegationAttestations)
- Collecting results and producing merge receipts
- Enforcing workflow policies (timeouts, retries, circuit breakers)

**Worker Agent**: A standard MAIP agent delegated by the orchestrator. Performs a single unit of work (LLM inference, data processing, tool use). Produces action receipts for every operation.

**Sub-Orchestrator**: A worker agent that also has `orchestrate.*` sub-scopes, enabling hierarchical delegation (depth 2+). Used for complex multi-stage workflows.

### 2.2 Registration

Orchestrator agents register with additional metadata:

```json
{
  "agent_id": "maip:abc12345:01HWX000ORCHESTRATOR",
  "agent_type": "orchestrator",
  "scopes": ["orchestrate.*", "workflow.*"],
  "capabilities": {
    "max_concurrent_workers": 50,
    "supported_patterns": ["sequential", "parallel", "hierarchical", "competitive"],
    "supported_llm_providers": ["openai", "anthropic", "bedrock"],
    "max_workflow_steps": 100
  },
  "resource_limits": {
    "max_cost_per_workflow_usd": 10.00,
    "max_tokens_per_workflow": 1000000,
    "max_wall_time_seconds": 300
  }
}
```

---

## 3. Multi-Agent Coordination Patterns

### 3.1 Sequential Pipeline

Agents execute in order. Each receives the output of the previous agent.

```
Orchestrator
    |
    | delegate(A, scopes=[data.extract])
    v
  Agent A ──receipt_A──> Orchestrator
    |                        |
    |                  delegate(B, scopes=[model.infer])
    |                        v
    |                   Agent B ──receipt_B──> Orchestrator
    |                                              |
    |                                   delegate(C, scopes=[data.write])
    |                                              v
    |                                         Agent C ──receipt_C──> Orchestrator
    v                                                                     |
                                                          merge_receipt (all step IDs)
```

**Receipt chain**:
```
receipt_A.outputs_hash = SHA-256(A's output)
receipt_B.inputs_hash  = receipt_A.outputs_hash  // proves B received A's exact output
receipt_B.outputs_hash = SHA-256(B's output)
receipt_C.inputs_hash  = receipt_B.outputs_hash  // proves C received B's exact output
merge_receipt.payload.step_receipts = [receipt_A.id, receipt_B.id, receipt_C.id]
```

**Failure handling** (configurable per step):
- `retry`: Re-execute step up to `max_attempts` with exponential backoff
- `skip`: Mark step as skipped, pass null output to next step
- `abort`: Halt workflow, generate failure receipt with partial results

---

### 3.2 Parallel Fan-Out / Fan-In

Orchestrator sends the same input to multiple agents simultaneously, then merges results.

```
                Orchestrator
               /      |      \
        delegate   delegate   delegate
             /        |        \
        Agent A    Agent B    Agent C
             \        |        /
         receipt_A receipt_B receipt_C
               \      |      /
              Orchestrator (merge)
                    |
              merge_receipt
```

**Merge receipt payload**:
```json
{
  "receipt_type": "agent.action",
  "payload": {
    "action": "orchestrate.fan_in",
    "pattern": "parallel",
    "input_hash": "SHA-256 of shared input",
    "worker_receipts": [
      { "agent_id": "maip:...:A", "receipt_id": "...", "outputs_hash": "..." },
      { "agent_id": "maip:...:B", "receipt_id": "...", "outputs_hash": "..." },
      { "agent_id": "maip:...:C", "receipt_id": "...", "outputs_hash": "..." }
    ],
    "merge_strategy": "majority_vote | weighted_average | concatenate | custom",
    "merged_outputs_hash": "SHA-256 of merged result",
    "agreement_ratio": 0.67,
    "disagreements": [
      { "agents": ["A", "C"], "field": "classification", "values": ["positive", "neutral"] }
    ]
  }
}
```

**Consensus handling**: If agents disagree on output:
1. If `agreement_ratio >= threshold` (default 0.67): accept majority result
2. If below threshold: trigger multi-witness verification (truth.claim receipts from each agent, then truth.verification)
3. If critical operation: escalate to human-in-the-loop (approval_receipt required)

---

### 3.3 Hierarchical Delegation

Root orchestrator delegates to sub-orchestrators, which delegate to leaf workers. Each level narrows scopes.

```
Root Orchestrator (depth=0, scopes=[orchestrate.*, data.*, model.*])
    |
    |── Sub-Orchestrator: Data Pipeline (depth=1, scopes=[data.read, data.transform])
    |       |── Worker: Extractor (depth=2, scopes=[data.read])
    |       |── Worker: Transformer (depth=2, scopes=[data.transform])
    |       └── Worker: Validator (depth=2, scopes=[data.read])
    |
    |── Sub-Orchestrator: ML Pipeline (depth=1, scopes=[model.train, model.evaluate])
    |       |── Worker: Trainer (depth=2, scopes=[model.train])
    |       └── Worker: Evaluator (depth=2, scopes=[model.evaluate])
    |
    └── Sub-Orchestrator: Output Pipeline (depth=1, scopes=[data.write])
            └── Worker: Writer (depth=2, scopes=[data.write])
```

**Depth budget**: Total chain depth (including human root) must not exceed `MAIP_MAX_DEPTH = 8`. Orchestrators MUST track remaining depth budget and reject delegations that would exceed it.

**Scope narrowing verification**: At each level, the orchestrator's scope validation runs:
```
ASSERT sub_orchestrator.scopes SUBSET_OF orchestrator.scopes
ASSERT worker.scopes SUBSET_OF sub_orchestrator.scopes
```

---

### 3.4 Competitive / Auction

Multiple agents bid on a task. Orchestrator selects the best agent(s) based on trust score, cost, and latency.

**Bid request** (broadcast to eligible agents):
```json
{
  "task_id": "ulid",
  "action": "model.inference",
  "requirements": {
    "min_trust_score": 0.8,
    "max_cost_usd": 0.05,
    "max_latency_ms": 2000,
    "required_scopes": ["model.infer"]
  },
  "input_hash": "SHA-256 of input data"
}
```

**Bid response** (from each agent):
```json
{
  "agent_id": "maip:...",
  "trust_score": 0.92,
  "estimated_cost_usd": 0.03,
  "estimated_latency_ms": 800,
  "capabilities": ["gpt-4o", "claude-sonnet"]
}
```

**Selection algorithm**:
```
score = (trust_weight * trust_score) + (cost_weight * (1 - normalized_cost)) + (latency_weight * (1 - normalized_latency))
// Default weights: trust=0.5, cost=0.25, latency=0.25
```

**Selection receipt**:
```json
{
  "receipt_type": "agent.action",
  "payload": {
    "action": "orchestrate.agent_selection",
    "task_id": "...",
    "candidates": 5,
    "selected_agent_id": "maip:...",
    "selection_score": 0.89,
    "selection_criteria": { "trust_weight": 0.5, "cost_weight": 0.25, "latency_weight": 0.25 }
  }
}
```

---

## 4. LLM Integration Layer

### 4.1 LLM Provider Abstraction

MAIP wraps LLM calls with a provider-agnostic interface. Each call produces an action receipt.

**Supported providers**:

| Provider | Model Examples | Integration |
|----------|---------------|-------------|
| OpenAI | gpt-4o, gpt-4o-mini | REST API via SDK |
| Anthropic | claude-sonnet-4-6, claude-opus-4-6 | REST API via SDK |
| AWS Bedrock | Claude, Titan, Llama | Bedrock API |
| Azure OpenAI | gpt-4o (Azure-hosted) | Azure REST API |
| Self-hosted | Ollama, vLLM, TGI | Local HTTP endpoint |

**LLM action receipt**:
```json
{
  "receipt_type": "agent.action",
  "agent_id": "maip:abc12345:01HWXYZ_INFERENCE_AGENT",
  "payload": {
    "action": "llm.inference",
    "provider": "anthropic",
    "model_id": "claude-sonnet-4-6",
    "prompt_hash": "SHA-256 of full prompt (system + user + context)",
    "response_hash": "SHA-256 of model response",
    "token_count": { "input": 1523, "output": 487 },
    "latency_ms": 2340,
    "cost_usd": 0.0089,
    "temperature": 0.3,
    "finish_reason": "stop"
  },
  "inputs_hash": "SHA-256 of prompt",
  "outputs_hash": "SHA-256 of response"
}
```

**Privacy guarantee**: Receipts contain ONLY hashes of prompts and responses — never the actual content. Content is stored separately (if at all) under the tenant's data governance policy.

---

### 4.2 Prompt Pipeline

Every stage of prompt construction produces a receipt:

```
1. Context Assembly
   Receipt: context_assembly
   inputs_hash = SHA-256(raw_context_sources)
   outputs_hash = SHA-256(assembled_context)

2. Prompt Construction
   Receipt: prompt_construction
   inputs_hash = SHA-256(system_prompt + user_query + assembled_context)
   outputs_hash = SHA-256(final_prompt)

3. LLM Inference
   Receipt: llm.inference
   inputs_hash = SHA-256(final_prompt)
   outputs_hash = SHA-256(raw_response)

4. Post-Processing (if applicable)
   Receipt: response_processing
   inputs_hash = SHA-256(raw_response)
   outputs_hash = SHA-256(processed_response)
```

**Chain verification**: `step_N.inputs_hash == step_(N-1).outputs_hash` at every transition. Breaking this chain means the data was modified between steps.

---

### 4.3 RAG (Retrieval-Augmented Generation) Integration

```
User Query ──> Retrieval Agent ──> Context Assembly ──> Inference Agent ──> Response
                    |                     |                    |               |
              retrieval_receipt    assembly_receipt     inference_receipt  final_receipt
```

**Retrieval receipt**:
```json
{
  "receipt_type": "agent.action",
  "payload": {
    "action": "rag.retrieval",
    "query_hash": "SHA-256 of user query",
    "vector_store": "pgvector",
    "chunks_retrieved": 5,
    "chunk_hashes": [
      "SHA-256 of chunk 1",
      "SHA-256 of chunk 2",
      "SHA-256 of chunk 3",
      "SHA-256 of chunk 4",
      "SHA-256 of chunk 5"
    ],
    "similarity_scores": [0.95, 0.91, 0.88, 0.85, 0.82],
    "source_document_ids": ["doc_001", "doc_001", "doc_003", "doc_007", "doc_012"]
  }
}
```

**Source attribution**: The retrieval receipt links the final response to specific source documents. Downstream consumers can verify: "this response was generated using chunks from documents X, Y, Z."

---

### 4.4 Tool Use & Function Calling

When an LLM agent invokes tools during inference:

```json
{
  "receipt_type": "agent.action",
  "payload": {
    "action": "tool.invocation",
    "tool_name": "search.web",
    "tool_scope_required": "tool.search.web",
    "tool_input_hash": "SHA-256 of tool input parameters",
    "tool_output_hash": "SHA-256 of tool response",
    "tool_latency_ms": 450,
    "tool_success": true,
    "parent_inference_receipt_id": "ulid of the inference that triggered this tool call"
  }
}
```

**Tool access control**:
- Each tool maps to a scope: `tool.<category>.<name>` (e.g., `tool.search.web`, `tool.db.query`, `tool.file.read`)
- Agent must have the tool's scope in its delegation chain
- Dangerous tools (e.g., `tool.db.write`, `tool.email.send`) require human approval:
  ```json
  {
    "receipt_type": "agent.action",
    "payload": {
      "action": "tool.approval_request",
      "tool_name": "email.send",
      "requires_human_approval": true,
      "approval_receipt_id": "ulid of human approval receipt"
    }
  }
  ```

**Tool registry**:
```json
{
  "tool_name": "search.web",
  "scope": "tool.search.web",
  "risk_level": "low",
  "requires_approval": false,
  "rate_limit": "100/hour",
  "description": "Search the web via configured search API"
}
```

---

## 5. Agent Workflow Engine

### 5.1 Workflow Definition Schema

```json
{
  "$schema": "maip/v1/workflow",
  "workflow_id": "01HWXYZ_WF_KYC",
  "name": "KYC Document Verification",
  "version": "1.2.0",
  "description": "End-to-end KYC verification with document extraction, validation, and compliance check",
  "orchestrator_agent_id": "maip:abc12345:01HWXYZ_ORCHESTRATOR",
  "required_scopes": ["data.read", "data.extract", "model.infer", "compliance.check"],
  "timeout_ms": 120000,
  "max_retries": 2,

  "inputs": {
    "document": { "type": "hash_reference", "required": true },
    "applicant_id": { "type": "string", "required": true }
  },

  "steps": [
    {
      "step_id": "extract",
      "name": "Document Extraction",
      "agent_type": "ocr-agent",
      "scopes": ["data.read", "data.extract"],
      "inputs": { "document": "$workflow.inputs.document" },
      "outputs": ["extracted_text", "extracted_fields"],
      "timeout_ms": 30000,
      "retry": { "max_attempts": 3, "backoff": "exponential", "initial_delay_ms": 1000 },
      "on_failure": "abort"
    },
    {
      "step_id": "validate",
      "name": "Field Validation",
      "agent_type": "validation-agent",
      "scopes": ["data.read"],
      "inputs": {
        "fields": "$steps.extract.outputs.extracted_fields"
      },
      "outputs": ["validation_result", "confidence_score"],
      "depends_on": ["extract"],
      "timeout_ms": 10000,
      "on_failure": "abort"
    },
    {
      "step_id": "verify_identity",
      "name": "Identity Verification",
      "agent_type": "inference-agent",
      "scopes": ["model.infer", "data.read"],
      "inputs": {
        "extracted_text": "$steps.extract.outputs.extracted_text",
        "applicant_id": "$workflow.inputs.applicant_id"
      },
      "outputs": ["identity_match_score", "verification_details"],
      "depends_on": ["validate"],
      "condition": "$steps.validate.outputs.validation_result == 'valid'",
      "timeout_ms": 15000,
      "on_failure": "abort"
    },
    {
      "step_id": "compliance_check",
      "name": "Compliance Check",
      "agent_type": "compliance-agent",
      "scopes": ["compliance.check"],
      "inputs": {
        "verification_details": "$steps.verify_identity.outputs.verification_details",
        "applicant_id": "$workflow.inputs.applicant_id"
      },
      "outputs": ["compliance_result", "risk_flags"],
      "depends_on": ["verify_identity"],
      "timeout_ms": 20000,
      "on_failure": "abort"
    }
  ],

  "on_complete": {
    "action": "generate_compliance_receipt",
    "regulation": "KYC/AML",
    "include_all_step_receipts": true
  },

  "on_failure": {
    "action": "generate_failure_receipt",
    "notify": ["workflow.admin"],
    "include_partial_results": true
  }
}
```

### 5.2 Workflow Execution

**Execution lifecycle**:

```
CREATED → VALIDATING → RUNNING → [step execution loop] → COMPLETED | FAILED | TIMED_OUT
```

**Step 1: Validation**
- Orchestrator validates workflow definition against schema
- Checks all required scopes are available in orchestrator's delegation
- Verifies all agent types are registered and available
- Produces `workflow.validated` receipt

**Step 2: Step Execution Loop**
For each step (respecting `depends_on` ordering):
1. Resolve inputs (substitute `$workflow.inputs.*` and `$steps.*.outputs.*`)
2. Check `condition` (if present) — skip step if false
3. Delegate to worker agent (create DelegationAttestation with step's scopes)
4. Worker executes and produces action receipt
5. Collect outputs, store in step context
6. Produce `workflow.step_completed` receipt:
   ```json
   {
     "receipt_type": "agent.action",
     "payload": {
       "action": "workflow.step_completed",
       "workflow_run_id": "ulid",
       "step_id": "extract",
       "worker_agent_id": "maip:...",
       "worker_receipt_id": "ulid",
       "duration_ms": 2340,
       "status": "completed"
     }
   }
   ```

**Step 3: Completion**
- All steps completed → generate workflow summary receipt
- Summary receipt includes all step receipt IDs, total duration, total cost

**Workflow summary receipt**:
```json
{
  "receipt_type": "agent.action",
  "payload": {
    "action": "workflow.completed",
    "workflow_id": "01HWXYZ_WF_KYC",
    "workflow_version": "1.2.0",
    "workflow_run_id": "ulid",
    "status": "completed",
    "steps_completed": 4,
    "steps_skipped": 0,
    "steps_failed": 0,
    "total_duration_ms": 47680,
    "total_cost_usd": 0.042,
    "step_receipts": ["receipt_1", "receipt_2", "receipt_3", "receipt_4"],
    "final_outputs_hash": "SHA-256 of workflow outputs"
  }
}
```

### 5.3 Workflow Versioning

- Workflows are **immutable once published** — changes create a new version
- Version format: semver (`major.minor.patch`)
- Running instances use their original version (no mid-execution upgrades)
- Version change produces a `workflow.version_published` receipt
- Old versions remain accessible for audit/replay

---

## 6. Agent Discovery & Registration

### 6.1 Capability Registration

Agents register their capabilities in the trust-registry:

```json
{
  "agent_id": "maip:abc12345:01HWXYZ_OCR",
  "agent_type": "ocr-agent",
  "capabilities": {
    "actions": ["data.extract.ocr", "data.extract.table"],
    "input_types": ["image/png", "image/jpeg", "application/pdf"],
    "output_types": ["text/plain", "application/json"],
    "languages": ["en", "es", "fr", "de", "zh"],
    "max_file_size_mb": 50
  },
  "performance": {
    "avg_latency_ms": 1200,
    "success_rate": 0.994,
    "throughput_rps": 10
  },
  "trust_score": 0.91,
  "cost_per_invocation_usd": 0.005,
  "status": "active"
}
```

### 6.2 Discovery Query

Orchestrators find agents by capability:

```
POST /api/v1/agents/discover
{
  "required_actions": ["data.extract.ocr"],
  "min_trust_score": 0.8,
  "max_cost_usd": 0.01,
  "max_latency_ms": 3000,
  "input_type": "application/pdf",
  "sort_by": "trust_score",
  "limit": 5
}
```

**Response**: Ranked list of matching agents with capabilities, trust scores, and availability.

### 6.3 Health Monitoring

- Agents send heartbeats every 30s
- Missed heartbeats → agent marked as `degraded` (after 1 miss) or `offline` (after 3 misses)
- Orchestrator automatically routes away from degraded/offline agents
- Health status changes produce receipts

---

## 7. Conversation & Session Management

### 7.1 Session Lifecycle

```
session.start → message.sent → message.received → ... → session.end
```

**Session start receipt**:
```json
{
  "receipt_type": "agent.action",
  "payload": {
    "action": "session.start",
    "session_id": "ulid",
    "agent_id": "maip:...",
    "initiator": "human | agent | system",
    "context_window_tokens": 128000,
    "session_config": {
      "max_turns": 50,
      "max_duration_ms": 3600000,
      "tools_enabled": ["search.web", "db.query"]
    }
  }
}
```

**Message receipt** (per turn):
```json
{
  "receipt_type": "agent.action",
  "payload": {
    "action": "session.message",
    "session_id": "ulid",
    "turn_number": 3,
    "role": "user | assistant | tool",
    "content_hash": "SHA-256 of message content",
    "token_count": 487,
    "tool_calls": ["tool_receipt_1", "tool_receipt_2"]
  },
  "previous_receipt_id": "previous message receipt in this session"
}
```

### 7.2 Session Handoff

Transfer a conversation between agents with full context:

```json
{
  "receipt_type": "agent.action",
  "payload": {
    "action": "session.handoff",
    "session_id": "ulid",
    "from_agent_id": "maip:...:AGENT_A",
    "to_agent_id": "maip:...:AGENT_B",
    "context_hash": "SHA-256 of transferred context",
    "turn_number_at_handoff": 12,
    "reason": "escalation | specialization | load_balancing",
    "delegation_receipt_id": "ulid of delegation from A's orchestrator to B"
  }
}
```

---

## 8. Safety & Guardrails

### 8.1 Input Guardrails

Before any LLM inference:

```json
{
  "receipt_type": "agent.action",
  "payload": {
    "action": "guardrail.input_check",
    "checks_performed": [
      { "check": "prompt_injection_detection", "result": "pass", "confidence": 0.98 },
      { "check": "pii_detection", "result": "pass", "pii_found": false },
      { "check": "content_policy", "result": "pass" }
    ],
    "input_hash": "SHA-256 of checked input",
    "all_passed": true
  }
}
```

If any check fails: block inference, generate failure receipt, escalate to human.

### 8.2 Output Guardrails

After LLM response, before delivery:

```json
{
  "receipt_type": "agent.action",
  "payload": {
    "action": "guardrail.output_check",
    "checks_performed": [
      { "check": "toxicity", "result": "pass", "score": 0.02 },
      { "check": "bias_detection", "result": "pass" },
      { "check": "hallucination_risk", "result": "warn", "score": 0.35 },
      { "check": "pii_leakage", "result": "pass" }
    ],
    "output_hash": "SHA-256 of checked output",
    "all_passed": true,
    "warnings": ["hallucination_risk: 0.35 exceeds threshold 0.30"]
  }
}
```

### 8.3 Budget Enforcement

Per-agent and per-workflow cost caps:

```json
{
  "budget_limits": {
    "per_agent": {
      "max_cost_usd_per_hour": 1.00,
      "max_tokens_per_hour": 500000,
      "max_tool_calls_per_hour": 100
    },
    "per_workflow": {
      "max_cost_usd": 10.00,
      "max_tokens": 1000000,
      "max_wall_time_seconds": 300
    }
  }
}
```

Budget exceeded → circuit breaker activates → agent paused → budget_exceeded receipt generated → escalate to admin.

### 8.4 Circuit Breaker

Automatic disable of misbehaving agents:

| Trigger | Threshold | Action |
|---------|-----------|--------|
| Error rate | > 50% over 10 requests | Pause agent, alert admin |
| Latency | > 5x average over 10 requests | Reduce traffic, alert |
| Budget | Cost exceeds limit | Hard stop, kill-switch receipt |
| Scope violation | Any attempt | Immediate kill-switch |
| Anomaly score | > 0.9 | Pause + investigation receipt |

Circuit breaker state changes produce receipts with the trigger details.

---

## 9. Observability

### 9.1 OpenTelemetry Integration

Every MAIP receipt correlates with an OTel span:

```
Trace: workflow_run_id
  └── Span: workflow.execution (orchestrator)
       ├── Span: step.extract (worker A)
       │    └── Span: llm.inference (provider call)
       ├── Span: step.validate (worker B)
       └── Span: step.verify (worker C)
            ├── Span: tool.invocation (search API)
            └── Span: llm.inference (provider call)
```

**Span attributes** (added to OTel spans):
```
maip.receipt_id = "ulid"
maip.agent_id = "maip:abc12345:..."
maip.workflow_id = "ulid"
maip.step_id = "extract"
maip.trust_score = 0.91
maip.cost_usd = 0.003
```

### 9.2 Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `maip.workflow.duration_ms` | Histogram | Workflow execution time |
| `maip.workflow.success_rate` | Gauge | % of workflows completing successfully |
| `maip.agent.latency_ms` | Histogram | Per-agent response time |
| `maip.agent.error_rate` | Gauge | Per-agent error percentage |
| `maip.agent.cost_usd` | Counter | Cumulative cost per agent |
| `maip.agent.trust_score` | Gauge | Current trust score per agent |
| `maip.llm.tokens_used` | Counter | Token usage by provider/model |
| `maip.guardrail.block_rate` | Gauge | % of inputs/outputs blocked by guardrails |
| `maip.circuit_breaker.trips` | Counter | Circuit breaker activations |

### 9.3 Alerting

| Alert | Condition | Severity |
|-------|-----------|----------|
| Agent offline | No heartbeat for 90s | WARNING |
| Workflow failure spike | > 10% failure rate in 5 min | HIGH |
| Trust score drop | Agent trust drops > 0.1 in 1h | HIGH |
| Budget approaching | > 80% of budget consumed | WARNING |
| Budget exceeded | 100% of budget consumed | CRITICAL |
| Guardrail block spike | > 5% block rate in 5 min | HIGH |
| Circuit breaker trip | Any agent circuit break | HIGH |
| Scope violation attempt | Any | CRITICAL |

---

## 10. Event-Driven Architecture

### 10.1 Event Bus

All orchestration events published to the event bus (Kafka topic: `maip.orchestration.events`, SNS topic: `maip-orchestration`).

**Event schema**:
```json
{
  "event_id": "ulid",
  "event_type": "workflow.step.completed",
  "timestamp": "ISO-8601 UTC",
  "source_agent_id": "maip:...",
  "tenant_id": "uuid",
  "payload": { ... },
  "receipt_id": "ulid of corresponding MAIP receipt"
}
```

### 10.2 Event Types

| Event | Trigger | Consumers |
|-------|---------|-----------|
| `agent.registered` | New agent registration | Discovery service, dashboards |
| `agent.health_changed` | Status change | Load balancer, orchestrator |
| `agent.revoked` | Kill switch / revocation | All verifiers, orchestrators |
| `workflow.created` | New workflow definition | Audit log |
| `workflow.started` | Workflow execution begins | Dashboards, billing |
| `workflow.step.started` | Step execution begins | Monitoring |
| `workflow.step.completed` | Step execution ends | Orchestrator, monitoring |
| `workflow.completed` | Workflow finished | Billing, analytics |
| `workflow.failed` | Workflow failed | Alerting, dashboards |
| `guardrail.blocked` | Input/output blocked | Security, alerting |
| `circuit_breaker.tripped` | Agent circuit break | Operations, alerting |
| `budget.exceeded` | Cost limit reached | Billing, alerting |

### 10.3 Event Replay

Event stream is retained for 30 days. Enables:
- Reconstruct workflow state from events (event sourcing)
- Replay workflows for debugging
- Audit trail for compliance
- Analytics on agent performance over time

---

## 11. API Endpoints

### 11.1 Workflow Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/orchestrate/workflows` | Create workflow definition |
| GET | `/api/v1/orchestrate/workflows/{id}` | Get workflow definition |
| GET | `/api/v1/orchestrate/workflows` | List workflows (tenant-scoped) |
| POST | `/api/v1/orchestrate/workflows/{id}/execute` | Execute workflow |
| GET | `/api/v1/orchestrate/runs/{run_id}` | Get workflow run status |
| GET | `/api/v1/orchestrate/runs/{run_id}/receipts` | Get all receipts for a run |
| POST | `/api/v1/orchestrate/runs/{run_id}/cancel` | Cancel running workflow |

### 11.2 Agent Discovery

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/orchestrate/agents/discover` | Find agents by capability |
| GET | `/api/v1/orchestrate/agents/{id}/health` | Get agent health status |
| GET | `/api/v1/orchestrate/agents/{id}/metrics` | Get agent performance metrics |

### 11.3 LLM Operations

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/orchestrate/llm/inference` | Single LLM inference with receipt |
| POST | `/api/v1/orchestrate/llm/rag` | RAG query with full receipt chain |
| POST | `/api/v1/orchestrate/llm/batch` | Batch inference with Merkle receipt |

### 11.4 Session Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/orchestrate/sessions` | Start new session |
| POST | `/api/v1/orchestrate/sessions/{id}/message` | Send message in session |
| POST | `/api/v1/orchestrate/sessions/{id}/handoff` | Handoff session to another agent |
| DELETE | `/api/v1/orchestrate/sessions/{id}` | End session |

### 11.5 Emergency Controls

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/orchestrate/agents/{id}/kill` | Emergency kill switch |
| POST | `/api/v1/orchestrate/agents/{id}/pause` | Pause agent (resume later) |
| POST | `/api/v1/orchestrate/agents/{id}/resume` | Resume paused agent |

---

## 12. Database Schema

### 12.1 Tables

```sql
-- Workflow definitions (immutable once published)
CREATE TABLE workflows (
    workflow_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    name            TEXT NOT NULL,
    version         TEXT NOT NULL,
    description     TEXT,
    definition      JSONB NOT NULL,  -- Full workflow definition
    orchestrator_agent_id TEXT NOT NULL,
    required_scopes TEXT[] NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      UUID NOT NULL,
    UNIQUE (tenant_id, name, version)
);

-- Workflow execution instances
CREATE TABLE workflow_runs (
    run_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id     UUID NOT NULL REFERENCES workflows(workflow_id),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    status          TEXT NOT NULL DEFAULT 'created'
                    CHECK (status IN ('created','validating','running','completed','failed','timed_out','cancelled')),
    inputs_hash     TEXT,
    outputs_hash    TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    total_cost_usd  NUMERIC(10,6) DEFAULT 0,
    total_tokens    BIGINT DEFAULT 0,
    error_message   TEXT,
    summary_receipt_id UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Step execution records
CREATE TABLE workflow_steps (
    step_execution_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id            UUID NOT NULL REFERENCES workflow_runs(run_id),
    tenant_id         UUID NOT NULL REFERENCES tenants(id),
    step_id           TEXT NOT NULL,
    worker_agent_id   TEXT,
    status            TEXT NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending','running','completed','failed','skipped','timed_out')),
    inputs_hash       TEXT,
    outputs_hash      TEXT,
    outputs           JSONB,
    receipt_id        UUID,
    started_at        TIMESTAMPTZ,
    completed_at      TIMESTAMPTZ,
    duration_ms       INT,
    cost_usd          NUMERIC(10,6) DEFAULT 0,
    error_message     TEXT,
    retry_count       INT DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Registered agent capabilities
CREATE TABLE agent_capabilities (
    capability_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        TEXT NOT NULL,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    agent_type      TEXT NOT NULL,
    capabilities    JSONB NOT NULL,
    performance     JSONB,
    cost_config     JSONB,
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active','degraded','offline','paused','revoked')),
    last_heartbeat  TIMESTAMPTZ,
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Orchestration event log
CREATE TABLE orchestration_events (
    event_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    event_type      TEXT NOT NULL,
    source_agent_id TEXT NOT NULL,
    run_id          UUID REFERENCES workflow_runs(run_id),
    receipt_id      UUID,
    payload         JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_workflow_runs_tenant ON workflow_runs(tenant_id, status);
CREATE INDEX idx_workflow_runs_workflow ON workflow_runs(workflow_id);
CREATE INDEX idx_workflow_steps_run ON workflow_steps(run_id, step_id);
CREATE INDEX idx_agent_capabilities_type ON agent_capabilities(tenant_id, agent_type, status);
CREATE INDEX idx_agent_capabilities_heartbeat ON agent_capabilities(status, last_heartbeat);
CREATE INDEX idx_orchestration_events_tenant ON orchestration_events(tenant_id, event_type, created_at DESC);
CREATE INDEX idx_orchestration_events_run ON orchestration_events(run_id, created_at);
```

### 12.2 Row-Level Security

```sql
-- RLS policies (same pattern as existing Truthlocks services)
ALTER TABLE workflows ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow_steps ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_capabilities ENABLE ROW LEVEL SECURITY;
ALTER TABLE orchestration_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_workflows ON workflows
    USING (
        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        OR current_setting('app.platform_admin_mode', true) = 'true'
    );

CREATE POLICY tenant_isolation_runs ON workflow_runs
    USING (
        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        OR current_setting('app.platform_admin_mode', true) = 'true'
    );

CREATE POLICY tenant_isolation_steps ON workflow_steps
    USING (
        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        OR current_setting('app.platform_admin_mode', true) = 'true'
    );

CREATE POLICY tenant_isolation_capabilities ON agent_capabilities
    USING (
        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        OR current_setting('app.platform_admin_mode', true) = 'true'
    );

CREATE POLICY tenant_isolation_events ON orchestration_events
    USING (
        tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        OR current_setting('app.platform_admin_mode', true) = 'true'
    );
```

---

## 13. Integration with Truthlocks Platform

| Existing Service | Orchestration Layer Usage |
|-----------------|------------------------|
| `services/signing-service` | Signs all orchestration receipts |
| `services/attestation-service` | Creates workflow/step/session attestations |
| `services/transparency-log` | Anchors all orchestration receipts |
| `services/trust-registry` | Agent capability registry, trust scores |
| `services/audit-service` | Orchestration audit trail |
| `services/machine-identity-service` | Agent identity lifecycle |
| `services/api-gateway` | Routes orchestration API endpoints |
| `packages/platform/middleware/cors.go` | CORS for orchestration endpoints |
| `apps/console` | Workflow management UI, agent dashboard |

---

## 14. Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-04-06 | Truthlocks Engineering | Initial specification |

---

*MAIP-SPEC-ORCH-001 | Apache 2.0 | github.com/truthlocksinc/maip*

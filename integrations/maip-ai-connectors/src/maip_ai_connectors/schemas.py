# Copyright 2026 Truthlocks Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Pydantic models for MAIP AI receipt payloads and API responses."""

from __future__ import annotations

from datetime import datetime, timezone

UTC = timezone.utc
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Step record used within ChainExecutionReceipt
# ---------------------------------------------------------------------------


class StepRecord(BaseModel):
    """A single step within a chain or pipeline execution.

    Attributes:
        name: Human-readable step name (e.g. 'LLMChain', 'Retriever').
        type: Step type discriminator (e.g. 'llm', 'tool', 'retriever').
        input_hash: SHA-256 hash of the step input.
        output_hash: SHA-256 hash of the step output.
        duration_ms: Execution time of the step in milliseconds.
        model_used: Model identifier used in this step, if applicable.
    """

    name: str = Field(..., description="Human-readable step name")
    type: str = Field(..., description="Step type (llm, tool, retriever, etc.)")
    input_hash: str = Field(default="", description="SHA-256 hash of step input")
    output_hash: str = Field(default="", description="SHA-256 hash of step output")
    duration_ms: int = Field(default=0, description="Step execution time in milliseconds")
    model_used: str = Field(default="", description="Model identifier used in this step")


# ---------------------------------------------------------------------------
# Receipt schemas
# ---------------------------------------------------------------------------


class LLMCallReceipt(BaseModel):
    """Receipt for a single LLM API call.

    Captures model, provider, token usage, cost, latency, and cryptographic
    hashes of both input and output for verifiable provenance.

    Attributes:
        model: Model identifier (e.g. 'gpt-4o', 'claude-sonnet-4-20250514').
        provider: Provider name ('openai', 'anthropic', 'bedrock').
        prompt_hash: SHA-256 hash of the input prompt or messages.
        completion_hash: SHA-256 hash of the model output.
        input_tokens: Number of input tokens consumed.
        output_tokens: Number of output tokens generated.
        total_tokens: Total tokens (input + output).
        estimated_cost_usd: Estimated cost of this call in USD.
        latency_ms: End-to-end latency in milliseconds.
        temperature: Temperature parameter used for generation.
        max_tokens: Maximum tokens parameter sent to the model.
        tool_calls: List of tool/function calls made by the model.
        receipt_type: MAIP receipt type discriminator.
        agent_id: Calling agent identifier.
        tenant_id: Tenant identifier.
        payload_hash: SHA-256 hash of the canonical receipt payload.
    """

    model: str = Field(..., description="Model identifier")
    provider: str = Field(..., description="Provider name")
    prompt_hash: str = Field(default="", description="SHA-256 hash of the input")
    completion_hash: str = Field(default="", description="SHA-256 hash of the output")
    input_tokens: int = Field(default=0, description="Number of input tokens")
    output_tokens: int = Field(default=0, description="Number of output tokens")
    total_tokens: int = Field(default=0, description="Total tokens (input + output)")
    estimated_cost_usd: float = Field(default=0.0, description="Estimated cost in USD")
    latency_ms: int = Field(default=0, description="End-to-end latency in milliseconds")
    temperature: float = Field(default=1.0, description="Temperature parameter")
    max_tokens: int = Field(default=0, description="Max tokens parameter")
    tool_calls: List[dict] = Field(
        default_factory=list,
        description="List of tool calls: [{name, arguments_hash}]",
    )
    receipt_type: str = Field(
        default="llm_call_receipt",
        description="MAIP receipt type discriminator",
    )
    agent_id: str = Field(default="", description="Calling agent identifier")
    tenant_id: str = Field(default="", description="Tenant identifier")
    payload_hash: str = Field(default="", description="SHA-256 hash of the canonical payload")


class ChainExecutionReceipt(BaseModel):
    """Receipt for a chain or pipeline execution spanning multiple steps.

    Attributes:
        chain_type: Chain type (e.g. 'RetrievalQA', 'AgentExecutor').
        framework: Orchestration framework ('langchain', 'llamaindex', 'crewai', 'autogen').
        steps: Ordered list of step records.
        total_llm_calls: Total number of LLM calls within the chain.
        total_tokens: Total tokens consumed across all steps.
        total_estimated_cost_usd: Aggregate cost in USD.
        total_duration_ms: Total chain execution time in milliseconds.
        receipt_type: MAIP receipt type discriminator.
        agent_id: Calling agent identifier.
        tenant_id: Tenant identifier.
        payload_hash: SHA-256 hash of the canonical receipt payload.
    """

    chain_type: str = Field(..., description="Chain type identifier")
    framework: str = Field(..., description="Orchestration framework name")
    steps: List[StepRecord] = Field(default_factory=list, description="Ordered step records")
    total_llm_calls: int = Field(default=0, description="Total LLM calls in the chain")
    total_tokens: int = Field(default=0, description="Total tokens consumed")
    total_estimated_cost_usd: float = Field(default=0.0, description="Aggregate cost in USD")
    total_duration_ms: int = Field(default=0, description="Total execution time in milliseconds")
    receipt_type: str = Field(
        default="chain_execution_receipt",
        description="MAIP receipt type discriminator",
    )
    agent_id: str = Field(default="", description="Calling agent identifier")
    tenant_id: str = Field(default="", description="Tenant identifier")
    payload_hash: str = Field(default="", description="SHA-256 hash of the canonical payload")


class AgentActionReceipt(BaseModel):
    """Receipt for a single agent action (tool invocation, reasoning step).

    Attributes:
        agent_name: Name of the agent performing the action.
        action: Action description or type.
        tool_name: Name of the tool invoked, if any.
        tool_input_hash: SHA-256 hash of the tool input.
        tool_output_hash: SHA-256 hash of the tool output.
        reasoning_hash: SHA-256 hash of the agent's reasoning or thought process.
        receipt_type: MAIP receipt type discriminator.
        agent_id: Calling agent identifier.
        tenant_id: Tenant identifier.
        payload_hash: SHA-256 hash of the canonical receipt payload.
    """

    agent_name: str = Field(..., description="Name of the agent")
    action: str = Field(..., description="Action description or type")
    tool_name: Optional[str] = Field(default=None, description="Tool name, if applicable")
    tool_input_hash: str = Field(default="", description="SHA-256 hash of tool input")
    tool_output_hash: str = Field(default="", description="SHA-256 hash of tool output")
    reasoning_hash: str = Field(default="", description="SHA-256 hash of agent reasoning")
    receipt_type: str = Field(
        default="agent_action_receipt",
        description="MAIP receipt type discriminator",
    )
    agent_id: str = Field(default="", description="Calling agent identifier")
    tenant_id: str = Field(default="", description="Tenant identifier")
    payload_hash: str = Field(default="", description="SHA-256 hash of the canonical payload")


class EmbeddingReceipt(BaseModel):
    """Receipt for an embedding API call.

    Attributes:
        model: Model identifier used for embedding.
        provider: Provider name ('openai', 'anthropic', 'bedrock').
        num_texts: Number of texts embedded in this call.
        total_tokens: Total tokens consumed.
        dimensions: Embedding vector dimensionality.
        input_hash: SHA-256 hash of concatenated input texts.
        receipt_type: MAIP receipt type discriminator.
        agent_id: Calling agent identifier.
        tenant_id: Tenant identifier.
        payload_hash: SHA-256 hash of the canonical receipt payload.
    """

    model: str = Field(..., description="Embedding model identifier")
    provider: str = Field(..., description="Provider name")
    num_texts: int = Field(default=0, description="Number of texts embedded")
    total_tokens: int = Field(default=0, description="Total tokens consumed")
    dimensions: int = Field(default=0, description="Embedding vector dimensionality")
    input_hash: str = Field(default="", description="SHA-256 hash of concatenated inputs")
    receipt_type: str = Field(
        default="embedding_receipt",
        description="MAIP receipt type discriminator",
    )
    agent_id: str = Field(default="", description="Calling agent identifier")
    tenant_id: str = Field(default="", description="Tenant identifier")
    payload_hash: str = Field(default="", description="SHA-256 hash of the canonical payload")


# ---------------------------------------------------------------------------
# API response schemas
# ---------------------------------------------------------------------------


class ReceiptResponse(BaseModel):
    """Signed receipt returned by the server; extra evidence fields are retained."""
    model_config = {"extra": "allow", "populate_by_name": True}
    receipt_id: str
    status: str
    created_at: datetime | None = None
    issued_at: datetime | None = None
    signature: str = ""
    signing_envelope: dict | None = None
    metadata: dict = Field(default_factory=dict)
    chain_hash: str | None = None
    log_index: int | None = None

class ReceiptVerifyResponse(BaseModel):
    """Online signature and lifecycle verdict; chain/log checks are separate."""
    valid: bool
    verdict: str
    reason: str = ""
    receipt_id: str
    signature_verified: bool = False
    transparency_verified: bool = False
    chain_verified: bool = False
    receipt: ReceiptResponse | None = None

    @model_validator(mode="after")
    def validate_verdict(self):
        if self.valid != (self.verdict == "VALID") or (self.valid and not self.signature_verified):
            raise ValueError("Inconsistent receipt verification response")
        return self

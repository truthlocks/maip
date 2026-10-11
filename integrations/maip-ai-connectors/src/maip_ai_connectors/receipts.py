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

"""Receipt generation and cryptographic hashing utilities for AI operations."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Union

from pydantic import BaseModel

from maip_ai_connectors.config import MAIPConfig
from maip_ai_connectors.schemas import (
    AgentActionReceipt,
    ChainExecutionReceipt,
    EmbeddingReceipt,
    LLMCallReceipt,
    StepRecord,
)
from maip_ai_connectors.utils.cost_estimator import CostEstimator
from maip_ai_connectors.utils.token_counter import TokenCounter

logger = logging.getLogger(__name__)

AnyReceipt = Union[LLMCallReceipt, ChainExecutionReceipt, AgentActionReceipt, EmbeddingReceipt]


def hash_content(content: str) -> str:
    """Compute a SHA-256 hex digest of the given string content.

    Args:
        content: The string to hash.

    Returns:
        A lowercase hex-encoded SHA-256 digest.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def hash_receipt_payload(receipt: BaseModel) -> str:
    """Compute a SHA-256 digest of the canonical JSON representation of a receipt.

    The receipt is serialised with sorted keys and no whitespace to ensure
    deterministic hashing regardless of field insertion order.

    Args:
        receipt: The receipt model to hash.

    Returns:
        A lowercase hex-encoded SHA-256 digest.
    """
    payload = receipt.model_dump(mode="json", exclude={"payload_hash"})
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_llm_call_receipt(
    *,
    model: str,
    provider: str,
    prompt: str,
    completion: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_ms: int = 0,
    temperature: float = 1.0,
    max_tokens: int = 0,
    tool_calls: list[dict] | None = None,
    config: MAIPConfig | None = None,
) -> LLMCallReceipt:
    """Build a complete LLM call receipt with hashes, token counts, and cost estimate.

    If ``input_tokens`` or ``output_tokens`` are zero, they will be estimated
    from the prompt/completion text length using the token counter utility.

    Args:
        model: Model identifier (e.g. 'gpt-4o').
        provider: Provider name ('openai', 'anthropic', 'bedrock').
        prompt: The raw input prompt or serialised messages.
        completion: The raw model output text.
        input_tokens: Number of input tokens (0 to auto-estimate).
        output_tokens: Number of output tokens (0 to auto-estimate).
        latency_ms: End-to-end call latency in milliseconds.
        temperature: Temperature parameter used.
        max_tokens: Max tokens parameter sent.
        tool_calls: Optional list of tool call records.
        config: Optional MAIP configuration.

    Returns:
        A fully populated ``LLMCallReceipt`` with payload_hash set.
    """
    cfg = config or MAIPConfig()

    if input_tokens == 0:
        input_tokens = TokenCounter.count(prompt, model=model, provider=provider)
    if output_tokens == 0:
        output_tokens = TokenCounter.count(completion, model=model, provider=provider)

    total_tokens = input_tokens + output_tokens
    estimated_cost = CostEstimator.estimate(model, input_tokens, output_tokens)

    hashed_tool_calls: list[dict] = []
    if tool_calls:
        for tc in tool_calls:
            hashed_tool_calls.append({
                "name": tc.get("name", ""),
                "arguments_hash": hash_content(
                    json.dumps(tc.get("arguments", {}), sort_keys=True, separators=(",", ":"))
                ),
            })

    receipt = LLMCallReceipt(
        model=model,
        provider=provider,
        prompt_hash=hash_content(prompt),
        completion_hash=hash_content(completion),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=estimated_cost,
        latency_ms=latency_ms,
        temperature=temperature,
        max_tokens=max_tokens,
        tool_calls=hashed_tool_calls,
        agent_id=cfg.agent_id,
        tenant_id=cfg.tenant_id,
    )
    receipt.payload_hash = hash_receipt_payload(receipt)
    return receipt


def build_chain_execution_receipt(
    *,
    chain_type: str,
    framework: str,
    steps: list[StepRecord],
    total_llm_calls: int = 0,
    total_tokens: int = 0,
    total_estimated_cost_usd: float = 0.0,
    total_duration_ms: int = 0,
    config: MAIPConfig | None = None,
) -> ChainExecutionReceipt:
    """Build a chain execution receipt aggregating multiple step records.

    Args:
        chain_type: Chain type (e.g. 'RetrievalQA', 'AgentExecutor').
        framework: Framework name ('langchain', 'llamaindex', 'crewai', 'autogen').
        steps: Ordered list of step records.
        total_llm_calls: Total LLM calls in the chain.
        total_tokens: Total tokens consumed across all steps.
        total_estimated_cost_usd: Aggregate cost in USD.
        total_duration_ms: Total execution time in milliseconds.
        config: Optional MAIP configuration.

    Returns:
        A fully populated ``ChainExecutionReceipt`` with payload_hash set.
    """
    cfg = config or MAIPConfig()

    receipt = ChainExecutionReceipt(
        chain_type=chain_type,
        framework=framework,
        steps=steps,
        total_llm_calls=total_llm_calls,
        total_tokens=total_tokens,
        total_estimated_cost_usd=total_estimated_cost_usd,
        total_duration_ms=total_duration_ms,
        agent_id=cfg.agent_id,
        tenant_id=cfg.tenant_id,
    )
    receipt.payload_hash = hash_receipt_payload(receipt)
    return receipt


def build_agent_action_receipt(
    *,
    agent_name: str,
    action: str,
    tool_name: str | None = None,
    tool_input: str = "",
    tool_output: str = "",
    reasoning: str = "",
    config: MAIPConfig | None = None,
) -> AgentActionReceipt:
    """Build an agent action receipt with cryptographic hashes of all content.

    Args:
        agent_name: Name of the agent performing the action.
        action: Action description or type.
        tool_name: Name of the tool invoked, if any.
        tool_input: Raw tool input string to hash.
        tool_output: Raw tool output string to hash.
        reasoning: Raw reasoning or thought content to hash.
        config: Optional MAIP configuration.

    Returns:
        A fully populated ``AgentActionReceipt`` with payload_hash set.
    """
    cfg = config or MAIPConfig()

    receipt = AgentActionReceipt(
        agent_name=agent_name,
        action=action,
        tool_name=tool_name,
        tool_input_hash=hash_content(tool_input) if tool_input else "",
        tool_output_hash=hash_content(tool_output) if tool_output else "",
        reasoning_hash=hash_content(reasoning) if reasoning else "",
        agent_id=cfg.agent_id,
        tenant_id=cfg.tenant_id,
    )
    receipt.payload_hash = hash_receipt_payload(receipt)
    return receipt


def build_embedding_receipt(
    *,
    model: str,
    provider: str,
    texts: list[str],
    total_tokens: int = 0,
    dimensions: int = 0,
    config: MAIPConfig | None = None,
) -> EmbeddingReceipt:
    """Build an embedding receipt with token count and input hash.

    Args:
        model: Embedding model identifier.
        provider: Provider name.
        texts: List of input texts that were embedded.
        total_tokens: Total tokens consumed (0 to auto-estimate).
        dimensions: Embedding vector dimensionality.
        config: Optional MAIP configuration.

    Returns:
        A fully populated ``EmbeddingReceipt`` with payload_hash set.
    """
    cfg = config or MAIPConfig()

    if total_tokens == 0:
        total_tokens = sum(
            TokenCounter.count(t, model=model, provider=provider) for t in texts
        )

    concatenated = "\n".join(texts)

    receipt = EmbeddingReceipt(
        model=model,
        provider=provider,
        num_texts=len(texts),
        total_tokens=total_tokens,
        dimensions=dimensions,
        input_hash=hash_content(concatenated),
        agent_id=cfg.agent_id,
        tenant_id=cfg.tenant_id,
    )
    receipt.payload_hash = hash_receipt_payload(receipt)
    return receipt


def measure_latency_ms(start_time: float) -> int:
    """Calculate elapsed milliseconds from a ``time.perf_counter()`` start value.

    Args:
        start_time: The result of ``time.perf_counter()`` at operation start.

    Returns:
        Elapsed time in milliseconds, rounded to the nearest integer.
    """
    return int((time.perf_counter() - start_time) * 1000)

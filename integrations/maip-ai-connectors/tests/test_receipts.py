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

"""Tests for receipt generation and hashing utilities."""

from __future__ import annotations

import pytest

from maip_ai_connectors.config import MAIPConfig
from maip_ai_connectors.receipts import (
    build_agent_action_receipt,
    build_chain_execution_receipt,
    build_embedding_receipt,
    build_llm_call_receipt,
    hash_content,
    hash_receipt_payload,
    measure_latency_ms,
)
from maip_ai_connectors.schemas import (
    AgentActionReceipt,
    ChainExecutionReceipt,
    EmbeddingReceipt,
    LLMCallReceipt,
    StepRecord,
)


# ---------------------------------------------------------------------------
# Tests: hash_content
# ---------------------------------------------------------------------------


class TestHashContent:
    def test_deterministic(self) -> None:
        """Verify same input always produces same hash."""
        h1 = hash_content("hello world")
        h2 = hash_content("hello world")
        assert h1 == h2

    def test_hex_length(self) -> None:
        """Verify SHA-256 produces 64-char hex digest."""
        h = hash_content("test")
        assert len(h) == 64

    def test_different_inputs_produce_different_hashes(self) -> None:
        """Verify different inputs produce different hashes."""
        h1 = hash_content("input_a")
        h2 = hash_content("input_b")
        assert h1 != h2

    def test_empty_string(self) -> None:
        """Verify hashing an empty string produces a valid hash."""
        h = hash_content("")
        assert len(h) == 64

    def test_unicode(self) -> None:
        """Verify hashing unicode text works correctly."""
        h = hash_content("Hello, world! Hola, mundo!")
        assert len(h) == 64


# ---------------------------------------------------------------------------
# Tests: hash_receipt_payload
# ---------------------------------------------------------------------------


class TestHashReceiptPayload:
    def test_deterministic(self) -> None:
        """Verify same receipt always produces same hash."""
        receipt = LLMCallReceipt(model="gpt-4o", provider="openai")
        h1 = hash_receipt_payload(receipt)
        h2 = hash_receipt_payload(receipt)
        assert h1 == h2

    def test_hex_length(self) -> None:
        """Verify SHA-256 hex digest length."""
        receipt = LLMCallReceipt(model="gpt-4o", provider="openai")
        h = hash_receipt_payload(receipt)
        assert len(h) == 64

    def test_different_inputs_produce_different_hashes(self) -> None:
        """Verify different receipts produce different hashes."""
        r1 = LLMCallReceipt(model="gpt-4o", provider="openai")
        r2 = LLMCallReceipt(model="gpt-4o-mini", provider="openai")
        assert hash_receipt_payload(r1) != hash_receipt_payload(r2)

    def test_hash_excludes_payload_hash_field(self) -> None:
        """Verify setting payload_hash does not change the computed digest."""
        r1 = LLMCallReceipt(model="gpt-4o", provider="openai")
        h_before = hash_receipt_payload(r1)
        r1.payload_hash = "should-be-ignored"
        h_after = hash_receipt_payload(r1)
        assert h_before == h_after

    def test_works_with_all_receipt_types(self) -> None:
        """Verify hashing works for all receipt types."""
        llm = LLMCallReceipt(model="gpt-4o", provider="openai")
        chain = ChainExecutionReceipt(chain_type="RetrievalQA", framework="langchain")
        agent = AgentActionReceipt(agent_name="test", action="run")
        embed = EmbeddingReceipt(model="text-embedding-3-small", provider="openai")

        for receipt in [llm, chain, agent, embed]:
            h = hash_receipt_payload(receipt)
            assert len(h) == 64


# ---------------------------------------------------------------------------
# Tests: build_llm_call_receipt
# ---------------------------------------------------------------------------


class TestBuildLLMCallReceipt:
    def test_basic_receipt(self) -> None:
        """Verify basic LLM call receipt generation."""
        receipt = build_llm_call_receipt(
            model="gpt-4o",
            provider="openai",
            prompt="Hello, world!",
            completion="Hi there!",
            input_tokens=10,
            output_tokens=5,
            latency_ms=250,
        )
        assert receipt.model == "gpt-4o"
        assert receipt.provider == "openai"
        assert receipt.input_tokens == 10
        assert receipt.output_tokens == 5
        assert receipt.total_tokens == 15
        assert receipt.latency_ms == 250
        assert receipt.prompt_hash != ""
        assert receipt.completion_hash != ""
        assert receipt.payload_hash != ""

    def test_auto_estimates_tokens(self) -> None:
        """Verify tokens are estimated when not provided."""
        receipt = build_llm_call_receipt(
            model="gpt-4o",
            provider="openai",
            prompt="Hello, world!",
            completion="Hi there!",
        )
        assert receipt.input_tokens > 0
        assert receipt.output_tokens > 0

    def test_cost_estimation(self) -> None:
        """Verify cost is estimated for known models."""
        receipt = build_llm_call_receipt(
            model="gpt-4o",
            provider="openai",
            prompt="Hello",
            completion="Hi",
            input_tokens=1000,
            output_tokens=500,
        )
        assert receipt.estimated_cost_usd > 0.0

    def test_with_tool_calls(self) -> None:
        """Verify tool calls are hashed in the receipt."""
        receipt = build_llm_call_receipt(
            model="gpt-4o",
            provider="openai",
            prompt="Find the weather",
            completion="",
            tool_calls=[
                {"name": "get_weather", "arguments": {"city": "NYC"}},
            ],
        )
        assert len(receipt.tool_calls) == 1
        assert receipt.tool_calls[0]["name"] == "get_weather"
        assert "arguments_hash" in receipt.tool_calls[0]

    def test_config_fields(self) -> None:
        """Verify config agent_id and tenant_id are set."""
        cfg = MAIPConfig(agent_id="agent-x", tenant_id="tenant-y")
        receipt = build_llm_call_receipt(
            model="gpt-4o",
            provider="openai",
            prompt="test",
            completion="test",
            config=cfg,
        )
        assert receipt.agent_id == "agent-x"
        assert receipt.tenant_id == "tenant-y"

    def test_receipt_type(self) -> None:
        """Verify receipt type is set correctly."""
        receipt = build_llm_call_receipt(
            model="gpt-4o",
            provider="openai",
            prompt="test",
            completion="test",
        )
        assert receipt.receipt_type == "llm_call_receipt"


# ---------------------------------------------------------------------------
# Tests: build_chain_execution_receipt
# ---------------------------------------------------------------------------


class TestBuildChainExecutionReceipt:
    def test_basic_receipt(self) -> None:
        """Verify basic chain execution receipt."""
        steps = [
            StepRecord(name="LLM", type="llm", duration_ms=100, model_used="gpt-4o"),
            StepRecord(name="Parser", type="parser", duration_ms=10),
        ]
        receipt = build_chain_execution_receipt(
            chain_type="RetrievalQA",
            framework="langchain",
            steps=steps,
            total_llm_calls=1,
            total_tokens=500,
            total_duration_ms=110,
        )
        assert receipt.chain_type == "RetrievalQA"
        assert receipt.framework == "langchain"
        assert len(receipt.steps) == 2
        assert receipt.total_llm_calls == 1
        assert receipt.payload_hash != ""

    def test_empty_steps(self) -> None:
        """Verify receipt with no steps."""
        receipt = build_chain_execution_receipt(
            chain_type="SimpleChain",
            framework="langchain",
            steps=[],
        )
        assert len(receipt.steps) == 0
        assert receipt.payload_hash != ""

    def test_receipt_type(self) -> None:
        """Verify receipt type."""
        receipt = build_chain_execution_receipt(
            chain_type="Test",
            framework="langchain",
            steps=[],
        )
        assert receipt.receipt_type == "chain_execution_receipt"


# ---------------------------------------------------------------------------
# Tests: build_agent_action_receipt
# ---------------------------------------------------------------------------


class TestBuildAgentActionReceipt:
    def test_basic_receipt(self) -> None:
        """Verify basic agent action receipt."""
        receipt = build_agent_action_receipt(
            agent_name="research_agent",
            action="tool_invocation",
            tool_name="web_search",
            tool_input="MAIP protocol",
            tool_output="Results found",
        )
        assert receipt.agent_name == "research_agent"
        assert receipt.action == "tool_invocation"
        assert receipt.tool_name == "web_search"
        assert receipt.tool_input_hash != ""
        assert receipt.tool_output_hash != ""
        assert receipt.payload_hash != ""

    def test_with_reasoning(self) -> None:
        """Verify reasoning is hashed."""
        receipt = build_agent_action_receipt(
            agent_name="agent",
            action="think",
            reasoning="I should search for information about MAIP",
        )
        assert receipt.reasoning_hash != ""

    def test_empty_tool_fields(self) -> None:
        """Verify empty tool fields produce empty hashes."""
        receipt = build_agent_action_receipt(
            agent_name="agent",
            action="think",
        )
        assert receipt.tool_input_hash == ""
        assert receipt.tool_output_hash == ""
        assert receipt.reasoning_hash == ""

    def test_receipt_type(self) -> None:
        """Verify receipt type."""
        receipt = build_agent_action_receipt(
            agent_name="agent",
            action="run",
        )
        assert receipt.receipt_type == "agent_action_receipt"

    def test_none_tool_name(self) -> None:
        """Verify None tool name is preserved."""
        receipt = build_agent_action_receipt(
            agent_name="agent",
            action="think",
            tool_name=None,
        )
        assert receipt.tool_name is None


# ---------------------------------------------------------------------------
# Tests: build_embedding_receipt
# ---------------------------------------------------------------------------


class TestBuildEmbeddingReceipt:
    def test_basic_receipt(self) -> None:
        """Verify basic embedding receipt."""
        receipt = build_embedding_receipt(
            model="text-embedding-3-small",
            provider="openai",
            texts=["hello", "world"],
            total_tokens=10,
            dimensions=1536,
        )
        assert receipt.model == "text-embedding-3-small"
        assert receipt.provider == "openai"
        assert receipt.num_texts == 2
        assert receipt.total_tokens == 10
        assert receipt.dimensions == 1536
        assert receipt.input_hash != ""
        assert receipt.payload_hash != ""

    def test_auto_estimates_tokens(self) -> None:
        """Verify tokens are estimated when not provided."""
        receipt = build_embedding_receipt(
            model="text-embedding-3-small",
            provider="openai",
            texts=["Hello, world! This is a test sentence."],
        )
        assert receipt.total_tokens > 0

    def test_receipt_type(self) -> None:
        """Verify receipt type."""
        receipt = build_embedding_receipt(
            model="text-embedding-3-small",
            provider="openai",
            texts=["test"],
        )
        assert receipt.receipt_type == "embedding_receipt"

    def test_single_text(self) -> None:
        """Verify single text embedding receipt."""
        receipt = build_embedding_receipt(
            model="text-embedding-3-small",
            provider="openai",
            texts=["single text"],
        )
        assert receipt.num_texts == 1

    def test_empty_texts(self) -> None:
        """Verify empty text list produces valid receipt."""
        receipt = build_embedding_receipt(
            model="text-embedding-3-small",
            provider="openai",
            texts=[],
        )
        assert receipt.num_texts == 0


# ---------------------------------------------------------------------------
# Tests: measure_latency_ms
# ---------------------------------------------------------------------------


class TestMeasureLatencyMs:
    def test_returns_positive_integer(self) -> None:
        """Verify latency measurement returns a non-negative integer."""
        import time

        start = time.perf_counter()
        time.sleep(0.01)
        result = measure_latency_ms(start)
        assert isinstance(result, int)
        assert result >= 10

    def test_zero_elapsed(self) -> None:
        """Verify near-zero elapsed time returns small value."""
        import time

        start = time.perf_counter()
        result = measure_latency_ms(start)
        assert isinstance(result, int)
        assert result >= 0

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

"""Tests for the LangChain MAIP callback handler."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from maip_ai_connectors.config import MAIPConfig
from maip_ai_connectors.langchain.callback import MAIPCallbackHandler
from maip_ai_connectors.schemas import LLMCallReceipt, ChainExecutionReceipt, AgentActionReceipt


def _config() -> MAIPConfig:
    """Create a test config with auto_receipt disabled to avoid background tasks."""
    return MAIPConfig(
        api_url="https://test.local",
        api_key="test-key",
        tenant_id="tenant-001",
        agent_id="agent-001",
        auto_receipt=False,
    )


def _mock_llm_result(
    text: str = "Hello!",
    token_usage: dict | None = None,
    model_name: str = "",
) -> MagicMock:
    """Build a mock LangChain LLMResult."""
    generation = MagicMock()
    generation.text = text
    generation.message = MagicMock()
    generation.message.tool_calls = []

    result = MagicMock()
    result.generations = [[generation]]
    result.llm_output = {
        "token_usage": token_usage or {"prompt_tokens": 10, "completion_tokens": 5},
        "model_name": model_name,
    }
    return result


class TestMAIPCallbackHandler:
    def test_on_llm_start_end_generates_receipt(self) -> None:
        """Verify LLM start/end cycle produces an LLMCallReceipt."""
        handler = MAIPCallbackHandler(_config())
        run_id = uuid4()

        handler.on_llm_start(
            serialized={"kwargs": {"model_name": "gpt-4o"}, "id": ["openai", "ChatOpenAI"]},
            prompts=["What is MAIP?"],
            run_id=run_id,
        )

        handler.on_llm_end(
            response=_mock_llm_result("MAIP is a protocol."),
            run_id=run_id,
        )

        receipts = handler.get_receipts()
        assert len(receipts) == 1
        assert isinstance(receipts[0], LLMCallReceipt)
        assert receipts[0].model == "gpt-4o"
        assert receipts[0].provider == "openai"

    def test_on_llm_end_without_start_is_safe(self) -> None:
        """Verify on_llm_end for unknown run_id does not crash."""
        handler = MAIPCallbackHandler(_config())
        handler.on_llm_end(
            response=_mock_llm_result(),
            run_id=uuid4(),
        )
        assert len(handler.get_receipts()) == 0

    def test_on_chain_start_end_generates_receipt(self) -> None:
        """Verify chain start/end cycle produces a ChainExecutionReceipt."""
        handler = MAIPCallbackHandler(_config())
        run_id = uuid4()

        handler.on_chain_start(
            serialized={"id": ["langchain", "chains", "RetrievalQA"]},
            inputs={"query": "What is MAIP?"},
            run_id=run_id,
        )

        handler.on_chain_end(
            outputs={"result": "A protocol"},
            run_id=run_id,
        )

        receipts = handler.get_receipts()
        assert len(receipts) == 1
        assert isinstance(receipts[0], ChainExecutionReceipt)
        assert receipts[0].chain_type == "RetrievalQA"
        assert receipts[0].framework == "langchain"

    def test_on_tool_start_end_generates_receipt(self) -> None:
        """Verify tool start/end cycle produces an AgentActionReceipt."""
        handler = MAIPCallbackHandler(_config())
        run_id = uuid4()

        handler.on_tool_start(
            serialized={"name": "web_search"},
            input_str="search for MAIP",
            run_id=run_id,
        )

        handler.on_tool_end(
            output="Found 10 results",
            run_id=run_id,
        )

        receipts = handler.get_receipts()
        assert len(receipts) == 1
        assert isinstance(receipts[0], AgentActionReceipt)
        assert receipts[0].tool_name == "web_search"

    def test_on_llm_error_cleans_up(self) -> None:
        """Verify on_llm_error removes tracking state without generating receipt."""
        handler = MAIPCallbackHandler(_config())
        run_id = uuid4()

        handler.on_llm_start(
            serialized={"kwargs": {"model_name": "gpt-4o"}, "id": []},
            prompts=["test"],
            run_id=run_id,
        )
        handler.on_llm_error(
            error=RuntimeError("test error"),
            run_id=run_id,
        )

        assert len(handler.get_receipts()) == 0
        assert str(run_id) not in handler._active_runs

    def test_clear_receipts(self) -> None:
        """Verify clear_receipts empties the list."""
        handler = MAIPCallbackHandler(_config())
        run_id = uuid4()

        handler.on_llm_start(
            serialized={"kwargs": {"model_name": "gpt-4o"}, "id": []},
            prompts=["test"],
            run_id=run_id,
        )
        handler.on_llm_end(response=_mock_llm_result(), run_id=run_id)
        assert len(handler.get_receipts()) == 1

        handler.clear_receipts()
        assert len(handler.get_receipts()) == 0

    def test_detect_provider_anthropic(self) -> None:
        """Verify Anthropic models are detected correctly."""
        assert MAIPCallbackHandler._detect_provider("claude-sonnet-4-20250514", {}) == "anthropic"

    def test_detect_provider_openai(self) -> None:
        """Verify OpenAI models are detected correctly."""
        assert MAIPCallbackHandler._detect_provider("gpt-4o", {}) == "openai"

    def test_detect_provider_bedrock(self) -> None:
        """Verify Bedrock models are detected correctly."""
        assert (
            MAIPCallbackHandler._detect_provider(
                "anthropic.claude-3-sonnet-20240229-v1:0", {}
            )
            == "bedrock"
        )

    def test_detect_provider_from_serialized(self) -> None:
        """Verify provider detection from serialized config."""
        assert (
            MAIPCallbackHandler._detect_provider(
                "unknown",
                {"id": ["langchain_openai", "ChatOpenAI"]},
            )
            == "openai"
        )

    def test_token_usage_from_llm_output(self) -> None:
        """Verify token counts are extracted from LLM output."""
        handler = MAIPCallbackHandler(_config())
        run_id = uuid4()

        handler.on_llm_start(
            serialized={"kwargs": {"model_name": "gpt-4o"}, "id": []},
            prompts=["test"],
            run_id=run_id,
        )
        handler.on_llm_end(
            response=_mock_llm_result(
                token_usage={"prompt_tokens": 50, "completion_tokens": 25}
            ),
            run_id=run_id,
        )

        receipt = handler.get_receipts()[0]
        assert isinstance(receipt, LLMCallReceipt)
        assert receipt.input_tokens == 50
        assert receipt.output_tokens == 25

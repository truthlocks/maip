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

"""Tests for the OpenAI MAIP provider wrapper."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from maip_ai_connectors.config import MAIPConfig
from maip_ai_connectors.schemas import LLMCallReceipt, EmbeddingReceipt


def _config() -> MAIPConfig:
    """Create a test config with auto_receipt disabled."""
    return MAIPConfig(
        api_url="https://test.local",
        api_key="test-key",
        tenant_id="tenant-001",
        agent_id="agent-001",
        auto_receipt=False,
    )


def _mock_chat_response(
    content: str = "Hello!",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
) -> MagicMock:
    """Build a mock OpenAI ChatCompletion response."""
    message = MagicMock()
    message.content = content
    message.tool_calls = None

    choice = MagicMock()
    choice.message = message

    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response


def _mock_embedding_response(
    dimensions: int = 1536,
    total_tokens: int = 10,
) -> MagicMock:
    """Build a mock OpenAI Embedding response."""
    embedding = MagicMock()
    embedding.embedding = [0.1] * dimensions

    usage = MagicMock()
    usage.total_tokens = total_tokens

    response = MagicMock()
    response.data = [embedding]
    response.usage = usage
    return response


class TestMAIPOpenAIWrapper:
    def test_chat_completions_create(self) -> None:
        """Verify chat completion returns response + receipt."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_chat_response()

        from maip_ai_connectors.providers.openai import MAIPOpenAIWrapper

        wrapper = MAIPOpenAIWrapper(client=mock_client, config=_config())
        response, receipt = wrapper.chat_completions_create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hi"}],
        )

        assert response is not None
        assert isinstance(receipt, LLMCallReceipt)
        assert receipt.model == "gpt-4o"
        assert receipt.provider == "openai"
        assert receipt.input_tokens == 10
        assert receipt.output_tokens == 5
        assert receipt.total_tokens == 15
        assert receipt.prompt_hash != ""
        assert receipt.completion_hash != ""
        assert receipt.payload_hash != ""

    def test_chat_completions_with_tool_calls(self) -> None:
        """Verify tool calls are captured in receipt."""
        mock_client = MagicMock()

        # Build tool call mock
        tool_call = MagicMock()
        tool_call.function.name = "get_weather"
        tool_call.function.arguments = '{"city": "NYC"}'

        message = MagicMock()
        message.content = ""
        message.tool_calls = [tool_call]

        choice = MagicMock()
        choice.message = message

        usage = MagicMock()
        usage.prompt_tokens = 20
        usage.completion_tokens = 15

        response = MagicMock()
        response.choices = [choice]
        response.usage = usage

        mock_client.chat.completions.create.return_value = response

        from maip_ai_connectors.providers.openai import MAIPOpenAIWrapper

        wrapper = MAIPOpenAIWrapper(client=mock_client, config=_config())
        _, receipt = wrapper.chat_completions_create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Weather in NYC?"}],
        )

        assert len(receipt.tool_calls) == 1
        assert receipt.tool_calls[0]["name"] == "get_weather"

    def test_embeddings_create(self) -> None:
        """Verify embedding call returns response + receipt."""
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = _mock_embedding_response()

        from maip_ai_connectors.providers.openai import MAIPOpenAIWrapper

        wrapper = MAIPOpenAIWrapper(client=mock_client, config=_config())
        response, receipt = wrapper.embeddings_create(
            model="text-embedding-3-small",
            input=["hello", "world"],
        )

        assert response is not None
        assert isinstance(receipt, EmbeddingReceipt)
        assert receipt.model == "text-embedding-3-small"
        assert receipt.provider == "openai"
        assert receipt.num_texts == 2
        assert receipt.dimensions == 1536
        assert receipt.total_tokens == 10

    def test_embeddings_create_single_string(self) -> None:
        """Verify single string input is handled."""
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = _mock_embedding_response()

        from maip_ai_connectors.providers.openai import MAIPOpenAIWrapper

        wrapper = MAIPOpenAIWrapper(client=mock_client, config=_config())
        _, receipt = wrapper.embeddings_create(
            model="text-embedding-3-small",
            input="hello world",
        )

        assert receipt.num_texts == 1

    def test_cost_estimation(self) -> None:
        """Verify cost is estimated for known model."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_chat_response(
            prompt_tokens=1000, completion_tokens=500
        )

        from maip_ai_connectors.providers.openai import MAIPOpenAIWrapper

        wrapper = MAIPOpenAIWrapper(client=mock_client, config=_config())
        _, receipt = wrapper.chat_completions_create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Test"}],
        )

        assert receipt.estimated_cost_usd > 0.0

    def test_latency_is_measured(self) -> None:
        """Verify latency is positive."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_chat_response()

        from maip_ai_connectors.providers.openai import MAIPOpenAIWrapper

        wrapper = MAIPOpenAIWrapper(client=mock_client, config=_config())
        _, receipt = wrapper.chat_completions_create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Test"}],
        )

        assert receipt.latency_ms >= 0

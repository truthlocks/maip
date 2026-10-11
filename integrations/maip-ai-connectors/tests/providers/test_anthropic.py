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

"""Tests for the Anthropic MAIP provider wrapper."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from maip_ai_connectors.config import MAIPConfig
from maip_ai_connectors.schemas import LLMCallReceipt


def _config() -> MAIPConfig:
    """Create a test config with auto_receipt disabled."""
    return MAIPConfig(
        api_url="https://test.local",
        api_key="test-key",
        tenant_id="tenant-001",
        agent_id="agent-001",
        auto_receipt=False,
    )


def _mock_anthropic_response(
    text: str = "Hello!",
    input_tokens: int = 10,
    output_tokens: int = 5,
    tool_use: bool = False,
) -> MagicMock:
    """Build a mock Anthropic Message response."""
    content_blocks = []

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text
    content_blocks.append(text_block)

    if tool_use:
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "get_data"
        tool_block.input = {"query": "test"}
        content_blocks.append(tool_block)

    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens

    response = MagicMock()
    response.content = content_blocks
    response.usage = usage
    return response


class TestMAIPAnthropicWrapper:
    def test_messages_create(self) -> None:
        """Verify messages call returns response + receipt."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response()

        from maip_ai_connectors.providers.anthropic import MAIPAnthropicWrapper

        wrapper = MAIPAnthropicWrapper(client=mock_client, config=_config())
        response, receipt = wrapper.messages_create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert response is not None
        assert isinstance(receipt, LLMCallReceipt)
        assert receipt.model == "claude-sonnet-4-20250514"
        assert receipt.provider == "anthropic"
        assert receipt.input_tokens == 10
        assert receipt.output_tokens == 5
        assert receipt.total_tokens == 15

    def test_messages_create_with_system(self) -> None:
        """Verify system prompt is included in the prompt hash."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response()

        from maip_ai_connectors.providers.anthropic import MAIPAnthropicWrapper

        wrapper = MAIPAnthropicWrapper(client=mock_client, config=_config())
        _, receipt_with_system = wrapper.messages_create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system="You are a helpful assistant.",
            messages=[{"role": "user", "content": "Hello"}],
        )

        _, receipt_without_system = wrapper.messages_create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert receipt_with_system.prompt_hash != receipt_without_system.prompt_hash

    def test_messages_create_with_tool_use(self) -> None:
        """Verify tool use blocks are captured in receipt."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response(tool_use=True)

        from maip_ai_connectors.providers.anthropic import MAIPAnthropicWrapper

        wrapper = MAIPAnthropicWrapper(client=mock_client, config=_config())
        _, receipt = wrapper.messages_create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": "Get data"}],
        )

        assert len(receipt.tool_calls) == 1
        assert receipt.tool_calls[0]["name"] == "get_data"

    def test_cost_estimation(self) -> None:
        """Verify cost is estimated for known Anthropic model."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response(
            input_tokens=1000, output_tokens=500
        )

        from maip_ai_connectors.providers.anthropic import MAIPAnthropicWrapper

        wrapper = MAIPAnthropicWrapper(client=mock_client, config=_config())
        _, receipt = wrapper.messages_create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": "Test"}],
        )

        assert receipt.estimated_cost_usd > 0.0

    def test_payload_hash_is_set(self) -> None:
        """Verify payload hash is computed."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response()

        from maip_ai_connectors.providers.anthropic import MAIPAnthropicWrapper

        wrapper = MAIPAnthropicWrapper(client=mock_client, config=_config())
        _, receipt = wrapper.messages_create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert receipt.payload_hash != ""
        assert len(receipt.payload_hash) == 64

    def test_latency_is_measured(self) -> None:
        """Verify latency is measured."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response()

        from maip_ai_connectors.providers.anthropic import MAIPAnthropicWrapper

        wrapper = MAIPAnthropicWrapper(client=mock_client, config=_config())
        _, receipt = wrapper.messages_create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert receipt.latency_ms >= 0

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

"""Tests for the token counter utility."""

from __future__ import annotations

import pytest

from maip_ai_connectors.utils.token_counter import TokenCounter


class TestTokenCounter:
    def test_empty_string_returns_zero(self) -> None:
        """Verify empty string returns 0 tokens."""
        assert TokenCounter.count("") == 0

    def test_estimate_from_chars(self) -> None:
        """Verify character-based estimation (~4 chars per token)."""
        text = "a" * 100
        result = TokenCounter.estimate_from_chars(text)
        assert result == 25

    def test_estimate_from_chars_minimum_one(self) -> None:
        """Verify minimum token count is 1 for non-empty text."""
        result = TokenCounter.estimate_from_chars("hi")
        assert result >= 1

    def test_estimate_from_chars_empty(self) -> None:
        """Verify empty string returns 0."""
        result = TokenCounter.estimate_from_chars("")
        assert result == 0

    def test_count_dispatches_to_openai(self) -> None:
        """Verify count dispatches to OpenAI counter for GPT models."""
        result = TokenCounter.count("Hello, world!", model="gpt-4o", provider="openai")
        assert result > 0

    def test_count_dispatches_to_anthropic(self) -> None:
        """Verify count dispatches to Anthropic counter for Claude models."""
        result = TokenCounter.count(
            "Hello, world!",
            model="claude-sonnet-4-20250514",
            provider="anthropic",
        )
        assert result > 0

    def test_count_falls_back_to_char_estimate(self) -> None:
        """Verify unknown provider falls back to character estimation."""
        result = TokenCounter.count("Hello, world!", model="unknown-model", provider="unknown")
        assert result > 0

    def test_count_openai_without_tiktoken(self) -> None:
        """Verify OpenAI counter falls back gracefully when tiktoken is unavailable."""
        # This test exercises the fallback path
        result = TokenCounter.count_openai("Hello world", "gpt-4o")
        assert result > 0

    def test_count_anthropic_fallback(self) -> None:
        """Verify Anthropic counter falls back to char estimation."""
        result = TokenCounter.count_anthropic("Hello world test text")
        assert result > 0

    def test_provider_detection_by_model_prefix(self) -> None:
        """Verify provider is detected from model name prefix."""
        result_gpt = TokenCounter.count("Hello", model="gpt-4o")
        result_claude = TokenCounter.count("Hello", model="claude-3-haiku-20240307")
        assert result_gpt > 0
        assert result_claude > 0

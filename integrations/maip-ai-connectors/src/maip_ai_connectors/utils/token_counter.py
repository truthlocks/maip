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

"""Token usage tracking and estimation per model provider.

Provides provider-specific token counting when the relevant library is
available (e.g. ``tiktoken`` for OpenAI models), with a character-based
fallback for environments where the tokenizer library is not installed.
"""

from __future__ import annotations

import logging
from typing import Final

logger = logging.getLogger(__name__)

# Average characters per token for fallback estimation.
_CHARS_PER_TOKEN_DEFAULT: Final[float] = 4.0
_CHARS_PER_TOKEN_CJK: Final[float] = 2.0

# Model family detection prefixes.
_OPENAI_PREFIXES: Final[tuple[str, ...]] = ("gpt-", "o1-", "o3-", "text-embedding-", "davinci")
_ANTHROPIC_PREFIXES: Final[tuple[str, ...]] = ("claude-",)


class TokenCounter:
    """Estimates token counts for different model providers.

    Uses ``tiktoken`` for OpenAI models when available; falls back to a
    character-based estimate (~4 characters per token) otherwise.

    All methods are static and stateless, suitable for concurrent use.
    """

    @staticmethod
    def count(text: str, *, model: str = "", provider: str = "") -> int:
        """Count or estimate tokens for the given text.

        Dispatches to a provider-specific counter when possible, otherwise
        falls back to a character-based estimate.

        Args:
            text: The input text to count tokens for.
            model: Model identifier for provider-specific counting.
            provider: Provider name ('openai', 'anthropic', 'bedrock').

        Returns:
            Estimated token count as an integer (always >= 0).
        """
        if not text:
            return 0

        if provider == "openai" or any(model.startswith(p) for p in _OPENAI_PREFIXES):
            return TokenCounter.count_openai(text, model)

        if provider == "anthropic" or any(model.startswith(p) for p in _ANTHROPIC_PREFIXES):
            return TokenCounter.count_anthropic(text)

        return TokenCounter.estimate_from_chars(text)

    @staticmethod
    def count_openai(text: str, model: str = "gpt-4o") -> int:
        """Count tokens using ``tiktoken`` for OpenAI models.

        Falls back to character-based estimation if ``tiktoken`` is not
        installed.

        Args:
            text: The input text.
            model: OpenAI model identifier for encoding selection.

        Returns:
            Token count.
        """
        try:
            import tiktoken

            try:
                encoding = tiktoken.encoding_for_model(model)
            except KeyError:
                encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except ImportError:
            logger.debug("tiktoken not installed; using character-based estimation for OpenAI")
            return TokenCounter.estimate_from_chars(text)

    @staticmethod
    def count_anthropic(text: str) -> int:
        """Estimate token count for Anthropic models.

        Uses the ``anthropic`` package tokenizer when available, otherwise
        falls back to character-based estimation.

        Args:
            text: The input text.

        Returns:
            Estimated token count.
        """
        try:
            from anthropic import Anthropic

            client = Anthropic()
            return client.count_tokens(text)
        except (ImportError, Exception):
            logger.debug("anthropic tokenizer unavailable; using character-based estimation")
            return TokenCounter.estimate_from_chars(text)

    @staticmethod
    def estimate_from_chars(text: str) -> int:
        """Fallback: estimate token count from character length.

        Uses approximately 4 characters per token for Latin text.

        Args:
            text: The input text.

        Returns:
            Estimated token count (always >= 1 for non-empty text).
        """
        if not text:
            return 0
        return max(1, int(len(text) / _CHARS_PER_TOKEN_DEFAULT))

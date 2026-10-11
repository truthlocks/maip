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

"""Cost estimation per provider and model.

Pricing data is expressed as USD per 1 million tokens.
"""

from __future__ import annotations

import logging
from typing import Dict, Final, Tuple

logger = logging.getLogger(__name__)

# Pricing per 1M tokens: (input_usd, output_usd)
PRICING: Final[Dict[str, Tuple[float, float]]] = {
    # OpenAI
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-4": (30.00, 60.00),
    "gpt-3.5-turbo": (0.50, 1.50),
    "o1": (15.00, 60.00),
    "o1-mini": (3.00, 12.00),
    "o1-pro": (150.00, 600.00),
    "o3": (10.00, 40.00),
    "o3-mini": (1.10, 4.40),
    "text-embedding-3-small": (0.02, 0.0),
    "text-embedding-3-large": (0.13, 0.0),
    "text-embedding-ada-002": (0.10, 0.0),
    # Anthropic
    "claude-opus-4-6": (15.00, 75.00),
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
    "claude-3-5-haiku-20241022": (0.80, 4.00),
    "claude-3-opus-20240229": (15.00, 75.00),
    "claude-3-sonnet-20240229": (3.00, 15.00),
    "claude-3-haiku-20240307": (0.25, 1.25),
    # AWS Bedrock (Anthropic models via Bedrock identifiers)
    "anthropic.claude-3-sonnet-20240229-v1:0": (3.00, 15.00),
    "anthropic.claude-3-haiku-20240307-v1:0": (0.25, 1.25),
    "anthropic.claude-3-opus-20240229-v1:0": (15.00, 75.00),
    "anthropic.claude-3-5-sonnet-20241022-v2:0": (3.00, 15.00),
    # AWS Bedrock (Amazon models)
    "amazon.titan-text-express-v1": (0.20, 0.60),
    "amazon.titan-text-lite-v1": (0.15, 0.20),
    "amazon.titan-embed-text-v1": (0.10, 0.0),
    "amazon.titan-embed-text-v2:0": (0.02, 0.0),
    # AWS Bedrock (Meta models)
    "meta.llama3-1-70b-instruct-v1:0": (0.72, 0.72),
    "meta.llama3-1-8b-instruct-v1:0": (0.22, 0.22),
    # AWS Bedrock (Mistral models)
    "mistral.mistral-large-2407-v1:0": (4.00, 12.00),
    "mistral.mistral-small-2402-v1:0": (1.00, 3.00),
}

# Tokens per USD unit (1 million).
_TOKENS_PER_UNIT: Final[float] = 1_000_000.0


class CostEstimator:
    """Estimates the cost of AI model API calls based on token usage.

    Uses a built-in pricing table that maps model identifiers to per-million-token
    rates for both input and output. Unknown models return a zero-cost estimate.

    All methods are static and stateless.
    """

    @staticmethod
    def estimate(model: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate the cost of an API call in USD.

        Args:
            model: Model identifier (must match a key in ``PRICING``).
            input_tokens: Number of input tokens consumed.
            output_tokens: Number of output tokens generated.

        Returns:
            Estimated cost in USD, rounded to 8 decimal places.
            Returns 0.0 for unknown models.
        """
        pricing = PRICING.get(model)
        if pricing is None:
            pricing = CostEstimator._fuzzy_match(model)
        if pricing is None:
            logger.debug("No pricing data for model %r; returning 0.0", model)
            return 0.0

        input_rate, output_rate = pricing
        cost = (input_tokens * input_rate / _TOKENS_PER_UNIT) + (
            output_tokens * output_rate / _TOKENS_PER_UNIT
        )
        return round(cost, 8)

    @staticmethod
    def _fuzzy_match(model: str) -> tuple[float, float] | None:
        """Attempt to match a model by prefix when an exact key is not found.

        This handles cases like versioned Bedrock model IDs or model aliases
        that share a common prefix with a known pricing entry.

        Args:
            model: Model identifier to match.

        Returns:
            The (input_rate, output_rate) tuple if a prefix match is found, else None.
        """
        model_lower = model.lower()
        best_key: str | None = None
        best_len = 0

        for key in PRICING:
            key_lower = key.lower()
            if model_lower.startswith(key_lower) or key_lower.startswith(model_lower):
                if len(key) > best_len:
                    best_key = key
                    best_len = len(key)

        if best_key is not None:
            return PRICING[best_key]
        return None

    @staticmethod
    def get_supported_models() -> list[str]:
        """Return a sorted list of all model identifiers with known pricing.

        Returns:
            Sorted list of model identifiers.
        """
        return sorted(PRICING.keys())

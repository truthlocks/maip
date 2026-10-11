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

"""OpenAI API wrapper that auto-generates MAIP receipts for every API call.

Wraps the OpenAI Python client to transparently produce ``LLMCallReceipt``
and ``EmbeddingReceipt`` objects alongside every chat completion and
embedding request.

Usage::

    from maip_ai_connectors.providers import MAIPOpenAIWrapper

    wrapper = MAIPOpenAIWrapper()
    completion, receipt = wrapper.chat_completions_create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello"}],
    )
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import openai

from maip_ai_connectors.client import MAIPClient
from maip_ai_connectors.config import MAIPConfig
from maip_ai_connectors.receipts import (
    build_embedding_receipt,
    build_llm_call_receipt,
    measure_latency_ms,
)
from maip_ai_connectors.schemas import EmbeddingReceipt, LLMCallReceipt

logger = logging.getLogger(__name__)


class MAIPOpenAIWrapper:
    """Wraps the OpenAI client to auto-generate MAIP receipts for every API call.

    Preserves the original OpenAI return value and returns a MAIP receipt
    alongside it. The receipt is also submitted to the MAIP API in the
    background when ``fire_and_forget`` is enabled.

    Args:
        client: An existing OpenAI client instance. If None, creates one.
        config: MAIP configuration. Defaults to environment-derived values.
    """

    def __init__(
        self,
        client: Optional[openai.OpenAI] = None,
        config: MAIPConfig | None = None,
    ) -> None:
        self._openai = client or openai.OpenAI()
        self._config = config or MAIPConfig()
        self._client = MAIPClient(self._config)

    def chat_completions_create(
        self, **kwargs: Any
    ) -> Tuple[Any, LLMCallReceipt]:
        """Wrap ``openai.chat.completions.create`` with receipt generation.

        Accepts the same keyword arguments as the OpenAI chat completions
        endpoint. Returns the original response alongside a receipt.

        Args:
            **kwargs: Arguments forwarded to ``chat.completions.create``.

        Returns:
            A tuple of (ChatCompletion, LLMCallReceipt).
        """
        if kwargs.get("stream"):
            raise ValueError("Streaming is not supported by this receipt wrapper; use stream=False")
        model = kwargs.get("model", "gpt-4o")
        messages = kwargs.get("messages", [])
        temperature = kwargs.get("temperature", 1.0)
        max_tokens = kwargs.get("max_tokens", 0)

        prompt_str = json.dumps(messages, default=str, sort_keys=True)

        start = time.perf_counter()
        response = self._openai.chat.completions.create(**kwargs)
        latency_ms = measure_latency_ms(start)

        # Extract completion text
        completion_parts: List[str] = []
        tool_calls: List[dict] = []
        for choice in response.choices:
            message = choice.message
            if message.content:
                completion_parts.append(message.content)
            if message.tool_calls:
                for tc in message.tool_calls:
                    tool_calls.append({
                        "name": tc.function.name,
                        "arguments": _tool_arguments(tc.function.arguments),
                    })

        completion_text = "\n".join(completion_parts)

        # Token usage from response
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        receipt = build_llm_call_receipt(
            model=model,
            provider="openai",
            prompt=prompt_str,
            completion=completion_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            temperature=float(temperature) if temperature is not None else 1.0,
            max_tokens=int(max_tokens) if max_tokens else 0,
            tool_calls=tool_calls,
            config=self._config,
        )

        if self._config.auto_receipt:
            self._client.submit_receipt_background(receipt)

        return response, receipt

    def embeddings_create(
        self, **kwargs: Any
    ) -> Tuple[Any, EmbeddingReceipt]:
        """Wrap ``openai.embeddings.create`` with receipt generation.

        Accepts the same keyword arguments as the OpenAI embeddings endpoint.
        Returns the original response alongside an embedding receipt.

        Args:
            **kwargs: Arguments forwarded to ``embeddings.create``.

        Returns:
            A tuple of (EmbeddingResponse, EmbeddingReceipt).
        """
        model = kwargs.get("model", "text-embedding-3-small")
        input_data = kwargs.get("input", [])

        # Normalize input to list of strings
        if isinstance(input_data, str):
            texts = [input_data]
        elif isinstance(input_data, list):
            texts = [str(item) for item in input_data]
        else:
            texts = [str(input_data)]

        start = time.perf_counter()
        response = self._openai.embeddings.create(**kwargs)
        latency_ms = measure_latency_ms(start)

        # Extract token count and dimensions from response
        total_tokens = response.usage.total_tokens if response.usage else 0
        dimensions = 0
        if response.data and len(response.data) > 0:
            dimensions = len(response.data[0].embedding)

        receipt = build_embedding_receipt(
            model=model,
            provider="openai",
            texts=texts,
            total_tokens=total_tokens,
            dimensions=dimensions,
            config=self._config,
        )

        if self._config.auto_receipt:
            self._client.submit_receipt_background(receipt)

        return response, receipt

    async def flush(self):
        """Wait for queued receipt delivery and surface submission failures."""
        return await self._client.flush()

    async def aclose(self):
        """Flush pending receipts and release the HTTP client."""
        await self._client.close()

    def get_submitted_receipts(self):
        """Return server-confirmed receipts; local payloads are available separately."""
        return list(self._client.submitted_receipts)


def _tool_arguments(value):
    """Preserve malformed provider arguments as evidence instead of losing the response."""
    if not value:
        return {}
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return {"raw_arguments": value}

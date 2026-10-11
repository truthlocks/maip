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

"""Anthropic API wrapper that auto-generates MAIP receipts for every API call.

Wraps the Anthropic Python client to transparently produce ``LLMCallReceipt``
objects alongside every messages API call.

Usage::

    from maip_ai_connectors.providers import MAIPAnthropicWrapper

    wrapper = MAIPAnthropicWrapper()
    message, receipt = wrapper.messages_create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": "Hello"}],
    )
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import anthropic

from maip_ai_connectors.client import MAIPClient
from maip_ai_connectors.config import MAIPConfig
from maip_ai_connectors.receipts import (
    build_llm_call_receipt,
    measure_latency_ms,
)
from maip_ai_connectors.schemas import LLMCallReceipt

logger = logging.getLogger(__name__)


class MAIPAnthropicWrapper:
    """Wraps the Anthropic client to auto-generate MAIP receipts.

    Preserves the original Anthropic return value and returns a MAIP receipt
    alongside it. The receipt is also submitted to the MAIP API in the
    background when ``fire_and_forget`` is enabled.

    Args:
        client: An existing Anthropic client instance. If None, creates one.
        config: MAIP configuration. Defaults to environment-derived values.
    """

    def __init__(
        self,
        client: Optional[anthropic.Anthropic] = None,
        config: MAIPConfig | None = None,
    ) -> None:
        self._anthropic = client or anthropic.Anthropic()
        self._config = config or MAIPConfig()
        self._client = MAIPClient(self._config)

    def messages_create(
        self, **kwargs: Any
    ) -> Tuple[Any, LLMCallReceipt]:
        """Wrap ``anthropic.messages.create`` with receipt generation.

        Accepts the same keyword arguments as the Anthropic messages endpoint.
        Returns the original response alongside a receipt.

        Args:
            **kwargs: Arguments forwarded to ``messages.create``.

        Returns:
            A tuple of (Message, LLMCallReceipt).
        """
        if kwargs.get("stream"):
            raise ValueError("Streaming is not supported by this receipt wrapper; use stream=False")
        model = kwargs.get("model", "claude-sonnet-4-20250514")
        messages = kwargs.get("messages", [])
        system = kwargs.get("system", "")
        temperature = kwargs.get("temperature", 1.0)
        max_tokens = kwargs.get("max_tokens", 0)

        # Build prompt from system + messages
        prompt_parts: List[str] = []
        if system:
            prompt_parts.append(f"system: {system}")
        prompt_parts.append(json.dumps(messages, default=str, sort_keys=True))
        prompt_str = "\n".join(prompt_parts)

        start = time.perf_counter()
        response = self._anthropic.messages.create(**kwargs)
        latency_ms = measure_latency_ms(start)

        # Extract completion text and tool use from response
        completion_parts: List[str] = []
        tool_calls: List[dict] = []
        for content_block in response.content:
            if content_block.type == "text":
                completion_parts.append(content_block.text)
            elif content_block.type == "tool_use":
                tool_calls.append({
                    "name": content_block.name,
                    "arguments": content_block.input if content_block.input else {},
                })

        completion_text = "\n".join(completion_parts)

        # Token usage from response
        usage = response.usage
        input_tokens = usage.input_tokens if usage else 0
        output_tokens = usage.output_tokens if usage else 0

        receipt = build_llm_call_receipt(
            model=model,
            provider="anthropic",
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

    async def flush(self):
        """Wait for queued receipt delivery and surface submission failures."""
        return await self._client.flush()

    async def aclose(self):
        """Flush pending receipts and release the HTTP client."""
        await self._client.close()

    def get_submitted_receipts(self):
        """Return server-confirmed receipts; local payloads are available separately."""
        return list(self._client.submitted_receipts)

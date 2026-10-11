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

"""AWS Bedrock runtime wrapper that auto-generates MAIP receipts.

Wraps the boto3 Bedrock Runtime client to produce ``LLMCallReceipt``
objects for ``invoke_model`` and ``converse`` API calls.

Usage::

    import boto3
    from maip_ai_connectors.providers import MAIPBedrockWrapper

    bedrock = boto3.client("bedrock-runtime")
    wrapper = MAIPBedrockWrapper(client=bedrock)
    response, receipt = wrapper.invoke_model(
        modelId="anthropic.claude-3-sonnet-20240229-v1:0",
        body='{"messages": [{"role": "user", "content": "Hello"}]}',
    )
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from maip_ai_connectors.client import MAIPClient
from maip_ai_connectors.config import MAIPConfig
from maip_ai_connectors.receipts import (
    build_llm_call_receipt,
    measure_latency_ms,
)
from maip_ai_connectors.schemas import LLMCallReceipt

logger = logging.getLogger(__name__)


class MAIPBedrockWrapper:
    """Wraps the AWS Bedrock Runtime client to auto-generate MAIP receipts.

    Preserves the original Bedrock response and returns a MAIP receipt
    alongside it for both ``invoke_model`` and ``converse`` operations.

    Args:
        client: A boto3 Bedrock Runtime client. If None, creates one using
                the default boto3 session.
        config: MAIP configuration. Defaults to environment-derived values.
    """

    def __init__(
        self,
        client: Any = None,
        config: MAIPConfig | None = None,
    ) -> None:
        if client is None:
            import boto3

            client = boto3.client("bedrock-runtime")
        self._bedrock = client
        self._config = config or MAIPConfig()
        self._client = MAIPClient(self._config)

    def invoke_model(self, **kwargs: Any) -> Tuple[dict, LLMCallReceipt]:
        """Wrap ``bedrock-runtime.invoke_model`` with receipt generation.

        Parses the request body and response body to extract prompt,
        completion, and token usage for receipt generation.

        Args:
            **kwargs: Arguments forwarded to ``invoke_model``.

        Returns:
            A tuple of (response_dict, LLMCallReceipt).
        """
        model_id = kwargs.get("modelId", "")
        body = kwargs.get("body", "{}")

        # Parse request body
        if isinstance(body, str):
            body_dict = json.loads(body)
        elif isinstance(body, bytes):
            body_dict = json.loads(body.decode("utf-8"))
        else:
            body_dict = body

        prompt_str = json.dumps(body_dict, default=str, sort_keys=True)
        temperature = body_dict.get("temperature", 1.0)
        max_tokens = body_dict.get("max_tokens", 0)

        start = time.perf_counter()
        response = self._bedrock.invoke_model(**kwargs)
        latency_ms = measure_latency_ms(start)

        # Parse response body
        response_body = response.get("body", None)
        if response_body is not None:
            if hasattr(response_body, "read"):
                response_bytes = response_body.read()
                response_dict = json.loads(response_bytes)
            else:
                response_dict = json.loads(response_body)
        else:
            response_dict = {}

        # Extract completion text based on model provider
        completion_text = self._extract_completion(response_dict, model_id)

        # Extract token usage
        input_tokens, output_tokens = self._extract_token_usage(response_dict, model_id)

        receipt = build_llm_call_receipt(
            model=model_id,
            provider="bedrock",
            prompt=prompt_str,
            completion=completion_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            temperature=float(temperature) if temperature is not None else 1.0,
            max_tokens=int(max_tokens) if max_tokens else 0,
            config=self._config,
        )

        if self._config.auto_receipt:
            self._client.submit_receipt_background(receipt)

        return response_dict, receipt

    def converse(self, **kwargs: Any) -> Tuple[dict, LLMCallReceipt]:
        """Wrap ``bedrock-runtime.converse`` with receipt generation.

        Uses the Bedrock Converse API which provides a unified interface
        across model providers.

        Args:
            **kwargs: Arguments forwarded to ``converse``.

        Returns:
            A tuple of (response_dict, LLMCallReceipt).
        """
        model_id = kwargs.get("modelId", "")
        messages = kwargs.get("messages", [])
        system_parts = kwargs.get("system", [])
        inference_config = kwargs.get("inferenceConfig", {})

        prompt_parts: List[str] = []
        if system_parts:
            prompt_parts.append(json.dumps(system_parts, default=str))
        prompt_parts.append(json.dumps(messages, default=str, sort_keys=True))
        prompt_str = "\n".join(prompt_parts)

        temperature = inference_config.get("temperature", 1.0)
        max_tokens = inference_config.get("maxTokens", 0)

        start = time.perf_counter()
        response = self._bedrock.converse(**kwargs)
        latency_ms = measure_latency_ms(start)

        # Extract completion from converse response
        output = response.get("output", {})
        message = output.get("message", {})
        content_blocks = message.get("content", [])

        completion_parts: List[str] = []
        tool_calls: List[dict] = []
        for block in content_blocks:
            if "text" in block:
                completion_parts.append(block["text"])
            elif "toolUse" in block:
                tool_use = block["toolUse"]
                tool_calls.append({
                    "name": tool_use.get("name", ""),
                    "arguments": tool_use.get("input", {}),
                })

        completion_text = "\n".join(completion_parts)

        # Extract token usage from converse response
        usage = response.get("usage", {})
        input_tokens = usage.get("inputTokens", 0)
        output_tokens = usage.get("outputTokens", 0)

        receipt = build_llm_call_receipt(
            model=model_id,
            provider="bedrock",
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

    # ------------------------------------------------------------------
    # Response parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_completion(response_dict: dict, model_id: str) -> str:
        """Extract completion text from a Bedrock invoke_model response.

        Handles different response formats for Anthropic, Amazon Titan,
        Meta Llama, and Mistral models.

        Args:
            response_dict: Parsed JSON response body.
            model_id: The Bedrock model identifier.

        Returns:
            The extracted completion text.
        """
        model_lower = model_id.lower()

        # Anthropic models
        if "anthropic" in model_lower:
            content = response_dict.get("content", [])
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
            return "\n".join(parts) if parts else response_dict.get("completion", "")

        # Amazon Titan models
        if "amazon.titan" in model_lower:
            results = response_dict.get("results", [])
            if results:
                return results[0].get("outputText", "")
            return response_dict.get("outputText", "")

        # Meta Llama models
        if "meta.llama" in model_lower:
            return response_dict.get("generation", "")

        # Mistral models
        if "mistral" in model_lower:
            outputs = response_dict.get("outputs", [])
            if outputs:
                return outputs[0].get("text", "")
            return ""

        # Fallback: try common keys
        for key in ("content", "completion", "generation", "outputText"):
            val = response_dict.get(key)
            if val:
                if isinstance(val, list):
                    return json.dumps(val, default=str)
                return str(val)

        return json.dumps(response_dict, default=str)

    @staticmethod
    def _extract_token_usage(response_dict: dict, model_id: str) -> Tuple[int, int]:
        """Extract token usage counts from a Bedrock invoke_model response.

        Args:
            response_dict: Parsed JSON response body.
            model_id: The Bedrock model identifier.

        Returns:
            A tuple of (input_tokens, output_tokens).
        """
        model_lower = model_id.lower()

        # Anthropic models
        if "anthropic" in model_lower:
            usage = response_dict.get("usage", {})
            return (
                usage.get("input_tokens", 0),
                usage.get("output_tokens", 0),
            )

        # Amazon Titan models
        if "amazon.titan" in model_lower:
            return (
                response_dict.get("inputTextTokenCount", 0),
                response_dict.get("results", [{}])[0].get("tokenCount", 0)
                if response_dict.get("results")
                else 0,
            )

        # Fallback: try generic usage block
        usage = response_dict.get("usage", {})
        return (
            usage.get("input_tokens", usage.get("prompt_tokens", 0)),
            usage.get("output_tokens", usage.get("completion_tokens", 0)),
        )

    async def flush(self):
        """Wait for queued receipt delivery and surface submission failures."""
        return await self._client.flush()

    async def aclose(self):
        """Flush pending receipts and release the HTTP client."""
        await self._client.close()

    def get_submitted_receipts(self):
        """Return server-confirmed receipts; local payloads are available separately."""
        return list(self._client.submitted_receipts)

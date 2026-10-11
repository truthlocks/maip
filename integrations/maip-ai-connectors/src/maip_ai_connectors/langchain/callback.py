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

"""LangChain CallbackHandler that generates MAIP receipts for all LLM operations.

Usage::

    from maip_ai_connectors.langchain import MAIPCallbackHandler

    handler = MAIPCallbackHandler()
    llm = ChatOpenAI(callbacks=[handler])
    result = llm.invoke("Hello")
    receipts = handler.get_receipts()
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Sequence, Union
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from maip_ai_connectors.client import MAIPClient
from maip_ai_connectors.config import MAIPConfig
from maip_ai_connectors.receipts import (
    AnyReceipt,
    build_agent_action_receipt,
    build_chain_execution_receipt,
    build_llm_call_receipt,
    hash_content,
    measure_latency_ms,
)
from maip_ai_connectors.schemas import StepRecord

logger = logging.getLogger(__name__)


class MAIPCallbackHandler(BaseCallbackHandler):
    """LangChain callback handler that generates MAIP receipts for all LLM operations.

    Listens to LLM start/end, chain start/end, and tool start/end events.
    Generates ``LLMCallReceipt``, ``ChainExecutionReceipt``, and
    ``AgentActionReceipt`` instances for each completed operation.

    Receipts are optionally submitted to the MAIP API in the background
    when an event loop is running. Synchronous calls confirm delivery before returning; async callers must await flush().

    Args:
        config: MAIP configuration. Defaults to environment-derived values.
    """

    name: str = "maip_callback_handler"

    def __init__(self, config: MAIPConfig | None = None) -> None:
        super().__init__()
        self._config = config or MAIPConfig()
        self._client = MAIPClient(self._config)
        self._active_runs: Dict[str, Dict[str, Any]] = {}
        self._receipts: List[AnyReceipt] = []

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    def get_receipts(self) -> List[AnyReceipt]:
        """Return all receipts generated so far.

        Returns:
            A list of receipt objects in chronological order.
        """
        return list(self._receipts)

    def clear_receipts(self) -> None:
        """Clear the accumulated receipts list."""
        self._receipts.clear()

    # ------------------------------------------------------------------
    # LLM events
    # ------------------------------------------------------------------

    def on_llm_start(
        self,
        serialized: Optional[Dict[str, Any]],
        prompts: List[str],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Record LLM call start time and input prompts.

        Args:
            serialized: Serialized LLM configuration.
            prompts: List of prompt strings sent to the LLM.
            run_id: Unique run identifier.
            parent_run_id: Parent run identifier, if nested.
            tags: Optional tags.
            metadata: Optional metadata.
            **kwargs: Additional keyword arguments.
        """
        model_name = (serialized or {}).get("kwargs", {}).get("model_name", "")
        if not model_name:
            model_name = (serialized or {}).get("kwargs", {}).get("model", "")
        if not model_name:
            model_name = (serialized or {}).get("id", ["", ""])[-1] if (serialized or {}).get("id") else ""

        self._active_runs[str(run_id)] = {
            "type": "llm",
            "start_time": time.perf_counter(),
            "prompts": prompts,
            "model": model_name,
            "serialized": serialized,
            "parent_run_id": str(parent_run_id) if parent_run_id else None,
            "invocation_params": kwargs.get("invocation_params", {}),
        }

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Generate an LLMCallReceipt on LLM completion.

        Args:
            response: The LLM result containing generations.
            run_id: Unique run identifier.
            parent_run_id: Parent run identifier, if nested.
            **kwargs: Additional keyword arguments.
        """
        run_key = str(run_id)
        run_data = self._active_runs.pop(run_key, None)
        if run_data is None:
            logger.warning("on_llm_end called for unknown run_id=%s", run_key)
            return

        prompt_text = "\n".join(run_data["prompts"])
        completion_parts: List[str] = []
        for generations in response.generations:
            for gen in generations:
                completion_parts.append(gen.text)
        completion_text = "\n".join(completion_parts)

        # Extract token usage from LLM output metadata
        llm_output = response.llm_output or {}
        token_usage = llm_output.get("token_usage", {})
        input_tokens = token_usage.get("prompt_tokens", 0)
        output_tokens = token_usage.get("completion_tokens", 0)

        # Extract model info
        model = run_data.get("model", "")
        if not model:
            model = llm_output.get("model_name", "")

        # Detect provider from model name or serialized config
        provider = self._detect_provider(model, run_data.get("serialized", {}))

        # Extract invocation params
        inv_params = run_data.get("invocation_params", {})
        temperature = inv_params.get("temperature", 1.0)
        max_tokens = inv_params.get("max_tokens", 0)

        # Extract tool calls from the response
        tool_calls: List[dict] = []
        for generations in response.generations:
            for gen in generations:
                if hasattr(gen, "message") and hasattr(gen.message, "tool_calls"):
                    for tc in gen.message.tool_calls:
                        tool_calls.append({
                            "name": tc.get("name", ""),
                            "arguments": tc.get("args", {}),
                        })

        receipt = build_llm_call_receipt(
            model=model,
            provider=provider,
            prompt=prompt_text,
            completion=completion_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=measure_latency_ms(run_data["start_time"]),
            temperature=float(temperature) if temperature is not None else 1.0,
            max_tokens=int(max_tokens) if max_tokens else 0,
            tool_calls=tool_calls,
            config=self._config,
        )
        self._receipts.append(receipt)

        if self._config.auto_receipt:
            self._client.submit_receipt_background(receipt)

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Record a failed LLM call and clean up run tracking state.

        Args:
            error: The exception that caused the failure.
            run_id: Unique run identifier.
            parent_run_id: Parent run identifier, if nested.
            **kwargs: Additional keyword arguments.
        """
        run_key = str(run_id)
        run_data = self._active_runs.pop(run_key, None)
        if run_data is not None:
            logger.error(
                "LLM call failed for run_id=%s model=%s: %s",
                run_key,
                run_data.get("model", "unknown"),
                error,
            )

    # ------------------------------------------------------------------
    # Chain events
    # ------------------------------------------------------------------

    def on_chain_start(
        self,
        serialized: Optional[Dict[str, Any]],
        inputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Record chain execution start.

        Args:
            serialized: Serialized chain configuration.
            inputs: Chain input dictionary.
            run_id: Unique run identifier.
            parent_run_id: Parent run identifier, if nested.
            tags: Optional tags.
            metadata: Optional metadata.
            **kwargs: Additional keyword arguments.
        """
        chain_id_parts = (serialized or {}).get("id", [])
        chain_type = chain_id_parts[-1] if chain_id_parts else "UnknownChain"

        self._active_runs[str(run_id)] = {
            "type": "chain",
            "start_time": time.perf_counter(),
            "chain_type": chain_type,
            "input_hash": hash_content(json.dumps(inputs, default=str, sort_keys=True)),
            "steps": [],
            "llm_calls": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "parent_run_id": str(parent_run_id) if parent_run_id else None,
        }

    def on_chain_end(
        self,
        outputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Generate a ChainExecutionReceipt on chain completion.

        Args:
            outputs: Chain output dictionary.
            run_id: Unique run identifier.
            parent_run_id: Parent run identifier, if nested.
            **kwargs: Additional keyword arguments.
        """
        run_key = str(run_id)
        run_data = self._active_runs.pop(run_key, None)
        if run_data is None:
            return
        if run_data["type"] != "chain":
            return

        duration_ms = measure_latency_ms(run_data["start_time"])

        receipt = build_chain_execution_receipt(
            chain_type=run_data["chain_type"],
            framework="langchain",
            steps=run_data.get("steps", []),
            total_llm_calls=run_data.get("llm_calls", 0),
            total_tokens=run_data.get("total_tokens", 0),
            total_estimated_cost_usd=run_data.get("total_cost", 0.0),
            total_duration_ms=duration_ms,
            config=self._config,
        )
        self._receipts.append(receipt)

        if self._config.auto_receipt:
            self._client.submit_receipt_background(receipt)

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Clean up chain tracking state on error.

        Args:
            error: The exception that caused the failure.
            run_id: Unique run identifier.
            parent_run_id: Parent run identifier, if nested.
            **kwargs: Additional keyword arguments.
        """
        run_key = str(run_id)
        self._active_runs.pop(run_key, None)
        logger.error("Chain execution failed for run_id=%s: %s", run_key, error)

    # ------------------------------------------------------------------
    # Tool events
    # ------------------------------------------------------------------

    def on_tool_start(
        self,
        serialized: Optional[Dict[str, Any]],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Record tool invocation start.

        Args:
            serialized: Serialized tool configuration.
            input_str: Tool input string.
            run_id: Unique run identifier.
            parent_run_id: Parent run identifier, if nested.
            tags: Optional tags.
            metadata: Optional metadata.
            **kwargs: Additional keyword arguments.
        """
        tool_name = (serialized or {}).get("name", "unknown_tool")

        self._active_runs[str(run_id)] = {
            "type": "tool",
            "start_time": time.perf_counter(),
            "tool_name": tool_name,
            "input_str": input_str,
            "parent_run_id": str(parent_run_id) if parent_run_id else None,
        }

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Generate an AgentActionReceipt for tool use on completion.

        Args:
            output: Tool output string.
            run_id: Unique run identifier.
            parent_run_id: Parent run identifier, if nested.
            **kwargs: Additional keyword arguments.
        """
        run_key = str(run_id)
        run_data = self._active_runs.pop(run_key, None)
        if run_data is None:
            return

        receipt = build_agent_action_receipt(
            agent_name="langchain_agent",
            action="tool_invocation",
            tool_name=run_data.get("tool_name", "unknown"),
            tool_input=run_data.get("input_str", ""),
            tool_output=str(output),
            config=self._config,
        )
        self._receipts.append(receipt)

        if self._config.auto_receipt:
            self._client.submit_receipt_background(receipt)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Clean up tool tracking state on error.

        Args:
            error: The exception that caused the failure.
            run_id: Unique run identifier.
            parent_run_id: Parent run identifier, if nested.
            **kwargs: Additional keyword arguments.
        """
        run_key = str(run_id)
        self._active_runs.pop(run_key, None)
        logger.error("Tool call failed for run_id=%s: %s", run_key, error)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_provider(model: str, serialized: Optional[Dict[str, Any]]) -> str:
        """Detect the AI provider from model name or serialized configuration.

        Bedrock model IDs use a ``provider.model`` format (e.g.
        ``anthropic.claude-3-sonnet-20240229-v1:0``) and must be checked
        before generic name-based detection.

        Args:
            model: Model identifier string.
            serialized: Serialized LLM configuration dictionary.

        Returns:
            Provider name string ('openai', 'anthropic', 'bedrock', or 'unknown').
        """
        model_lower = model.lower()

        # Bedrock models always use a dotted provider prefix (e.g. "anthropic.", "amazon.", "meta.")
        if (
            model_lower.startswith("anthropic.")
            or model_lower.startswith("amazon.")
            or model_lower.startswith("meta.")
            or model_lower.startswith("mistral.")
            or model_lower.startswith("cohere.")
            or model_lower.startswith("ai21.")
        ):
            return "bedrock"

        if "gpt" in model_lower or "o1" in model_lower or "o3" in model_lower:
            return "openai"
        if "claude" in model_lower:
            return "anthropic"

        id_parts = (serialized or {}).get("id", [])
        id_str = ".".join(id_parts).lower()
        if "openai" in id_str:
            return "openai"
        if "anthropic" in id_str:
            return "anthropic"
        if "bedrock" in id_str:
            return "bedrock"

        return "unknown"

    async def flush(self):
        """Wait for queued receipt delivery and surface submission failures."""
        return await self._client.flush()

    async def aclose(self):
        """Flush pending receipts and release the HTTP client."""
        await self._client.close()

    def get_submitted_receipts(self):
        """Return server-confirmed receipts; local payloads are available separately."""
        return list(self._client.submitted_receipts)

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

"""LangChain BaseTracer implementation for full run tracing with MAIP receipts.

Provides deeper integration than the callback handler by tracking the
complete run tree and generating receipts with full parent-child context.

Usage::

    from maip_ai_connectors.langchain import MAIPTracer

    tracer = MAIPTracer()
    llm = ChatOpenAI(callbacks=[tracer])
    result = llm.invoke("Hello")
    receipts = tracer.get_receipts()
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Union

from langchain_core.tracers.base import BaseTracer
from langchain_core.tracers.schemas import Run

from maip_ai_connectors.client import MAIPClient
from maip_ai_connectors.config import MAIPConfig
from maip_ai_connectors.receipts import (
    AnyReceipt,
    build_agent_action_receipt,
    build_chain_execution_receipt,
    build_llm_call_receipt,
    hash_content,
)
from maip_ai_connectors.schemas import StepRecord

logger = logging.getLogger(__name__)


class MAIPTracer(BaseTracer):
    """LangChain BaseTracer that generates MAIP receipts for complete run trees.

    Unlike the callback handler, the tracer receives fully-formed ``Run``
    objects after persistence, enabling richer receipt generation with
    parent-child relationships and full timing data.

    Args:
        config: MAIP configuration. Defaults to environment-derived values.
    """

    name: str = "maip_tracer"

    def __init__(self, config: MAIPConfig | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._config = config or MAIPConfig()
        self._client = MAIPClient(self._config)
        self._receipts: List[AnyReceipt] = []

    def get_receipts(self) -> List[AnyReceipt]:
        """Return all receipts generated during tracing.

        Returns:
            A list of receipt objects in chronological order.
        """
        return list(self._receipts)

    def clear_receipts(self) -> None:
        """Clear the accumulated receipts list."""
        self._receipts.clear()

    def _persist_run(self, run: Run) -> None:
        """Process a completed run and generate the appropriate MAIP receipt.

        This is the core tracer callback invoked by LangChain after a run
        is fully resolved (success or failure).

        Args:
            run: The completed LangChain Run object.
        """
        if run.error is not None:
            logger.debug("Skipping receipt for failed run %s: %s", run.id, run.error)
            return

        if run.run_type == "llm":
            self._process_llm_run(run)
        elif run.run_type == "chain":
            self._process_chain_run(run)
        elif run.run_type == "tool":
            self._process_tool_run(run)
        else:
            logger.debug("Unhandled run type %r for run %s", run.run_type, run.id)

    def _process_llm_run(self, run: Run) -> None:
        """Generate an LLMCallReceipt from a completed LLM run.

        Args:
            run: The completed LLM run.
        """
        inputs = run.inputs or {}
        prompts = inputs.get("prompts", [])
        prompt_text = "\n".join(prompts) if isinstance(prompts, list) else str(prompts)

        outputs = run.outputs or {}
        generations = outputs.get("generations", [[]])
        completion_parts: List[str] = []
        for gen_list in generations:
            for gen in gen_list:
                if isinstance(gen, dict):
                    completion_parts.append(gen.get("text", ""))
                else:
                    completion_parts.append(str(gen))
        completion_text = "\n".join(completion_parts)

        # Extract token counts from run extra data
        extra = run.extra or {}
        token_usage = extra.get("token_usage", {})
        input_tokens = token_usage.get("prompt_tokens", 0)
        output_tokens = token_usage.get("completion_tokens", 0)

        model = extra.get("invocation_params", {}).get("model_name", "")
        if not model:
            model = extra.get("invocation_params", {}).get("model", "")

        provider = self._detect_provider(model)

        latency_ms = 0
        if run.start_time and run.end_time:
            latency_ms = int((run.end_time - run.start_time).total_seconds() * 1000)

        receipt = build_llm_call_receipt(
            model=model,
            provider=provider,
            prompt=prompt_text,
            completion=completion_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            config=self._config,
        )
        self._receipts.append(receipt)

        if self._config.auto_receipt:
            self._client.submit_receipt_background(receipt)

    def _process_chain_run(self, run: Run) -> None:
        """Generate a ChainExecutionReceipt from a completed chain run.

        Args:
            run: The completed chain run.
        """
        steps: List[StepRecord] = []
        total_llm_calls = 0
        total_tokens = 0

        for child in run.child_runs or []:
            child_duration = 0
            if child.start_time and child.end_time:
                child_duration = int(
                    (child.end_time - child.start_time).total_seconds() * 1000
                )

            model_used = ""
            if child.run_type == "llm":
                total_llm_calls += 1
                extra = child.extra or {}
                model_used = extra.get("invocation_params", {}).get("model", "")

            input_str = json.dumps(child.inputs or {}, default=str, sort_keys=True)
            output_str = json.dumps(child.outputs or {}, default=str, sort_keys=True)

            steps.append(
                StepRecord(
                    name=child.name or child.run_type,
                    type=child.run_type,
                    input_hash=hash_content(input_str),
                    output_hash=hash_content(output_str),
                    duration_ms=child_duration,
                    model_used=model_used,
                )
            )

        latency_ms = 0
        if run.start_time and run.end_time:
            latency_ms = int((run.end_time - run.start_time).total_seconds() * 1000)

        chain_name = run.name or "UnknownChain"

        receipt = build_chain_execution_receipt(
            chain_type=chain_name,
            framework="langchain",
            steps=steps,
            total_llm_calls=total_llm_calls,
            total_tokens=total_tokens,
            total_duration_ms=latency_ms,
            config=self._config,
        )
        self._receipts.append(receipt)

        if self._config.auto_receipt:
            self._client.submit_receipt_background(receipt)

    def _process_tool_run(self, run: Run) -> None:
        """Generate an AgentActionReceipt from a completed tool run.

        Args:
            run: The completed tool run.
        """
        tool_input = json.dumps(run.inputs or {}, default=str, sort_keys=True)
        tool_output = json.dumps(run.outputs or {}, default=str, sort_keys=True)

        receipt = build_agent_action_receipt(
            agent_name="langchain_agent",
            action="tool_invocation",
            tool_name=run.name,
            tool_input=tool_input,
            tool_output=tool_output,
            config=self._config,
        )
        self._receipts.append(receipt)

        if self._config.auto_receipt:
            self._client.submit_receipt_background(receipt)

    @staticmethod
    def _detect_provider(model: str) -> str:
        """Detect the AI provider from a model identifier string.

        Args:
            model: Model identifier.

        Returns:
            Provider name string.
        """
        model_lower = model.lower()
        if "gpt" in model_lower or "o1" in model_lower or "o3" in model_lower:
            return "openai"
        if "claude" in model_lower:
            return "anthropic"
        if "anthropic." in model_lower or "amazon." in model_lower:
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

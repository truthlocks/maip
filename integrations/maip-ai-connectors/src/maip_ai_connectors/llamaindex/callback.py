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

"""LlamaIndex callback handler for MAIP receipt generation.

Hooks into LlamaIndex's callback system to generate receipts for LLM calls,
retrieval operations, and query engine executions.

Usage::

    from llama_index.core import Settings
    from llama_index.core.callbacks import CallbackManager
    from maip_ai_connectors.llamaindex import MAIPLlamaIndexHandler

    handler = MAIPLlamaIndexHandler()
    Settings.callback_manager = CallbackManager([handler])
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from llama_index.core.callbacks.base_handler import BaseCallbackHandler
from llama_index.core.callbacks.schema import CBEventType, EventPayload

from maip_ai_connectors.client import MAIPClient
from maip_ai_connectors.config import MAIPConfig
from maip_ai_connectors.receipts import (
    AnyReceipt,
    build_chain_execution_receipt,
    build_embedding_receipt,
    build_llm_call_receipt,
    hash_content,
    measure_latency_ms,
)
from maip_ai_connectors.schemas import StepRecord

logger = logging.getLogger(__name__)


class MAIPLlamaIndexHandler(BaseCallbackHandler):
    """LlamaIndex callback handler that generates MAIP receipts.

    Tracks LLM, embedding, retrieval, and query events to produce
    ``LLMCallReceipt``, ``EmbeddingReceipt``, and ``ChainExecutionReceipt``
    instances.

    Args:
        config: MAIP configuration. Defaults to environment-derived values.
        event_starts_to_ignore: Event types to skip on start.
        event_ends_to_ignore: Event types to skip on end.
    """

    def __init__(
        self,
        config: MAIPConfig | None = None,
        event_starts_to_ignore: Optional[List[CBEventType]] = None,
        event_ends_to_ignore: Optional[List[CBEventType]] = None,
    ) -> None:
        super().__init__(
            event_starts_to_ignore=event_starts_to_ignore or [],
            event_ends_to_ignore=event_ends_to_ignore or [],
        )
        self._config = config or MAIPConfig()
        self._client = MAIPClient(self._config)
        self._active_events: Dict[str, Dict[str, Any]] = {}
        self._active_traces: Dict[str, Dict[str, Any]] = {}
        self._receipts: List[AnyReceipt] = []

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
    # Event handlers
    # ------------------------------------------------------------------

    def on_event_start(
        self,
        event_type: CBEventType,
        payload: Optional[Dict[str, Any]] = None,
        event_id: str = "",
        parent_id: str = "",
        **kwargs: Any,
    ) -> str:
        """Record the start of a callback event.

        Args:
            event_type: The type of event (LLM, EMBEDDING, QUERY, etc.).
            payload: Event payload dictionary.
            event_id: Unique event identifier.
            parent_id: Parent event identifier for nesting.
            **kwargs: Additional keyword arguments.

        Returns:
            The event_id string.
        """
        self._active_events[event_id] = {
            "event_type": event_type,
            "start_time": time.perf_counter(),
            "payload": payload or {},
            "parent_id": parent_id,
        }
        return event_id

    def on_event_end(
        self,
        event_type: CBEventType,
        payload: Optional[Dict[str, Any]] = None,
        event_id: str = "",
        **kwargs: Any,
    ) -> None:
        """Process the end of a callback event and generate receipts.

        Args:
            event_type: The type of event.
            payload: Event payload with output data.
            event_id: Unique event identifier.
            **kwargs: Additional keyword arguments.
        """
        event_data = self._active_events.pop(event_id, None)
        if event_data is None:
            return

        end_payload = payload or {}
        latency_ms = measure_latency_ms(event_data["start_time"])

        if event_type == CBEventType.LLM:
            self._handle_llm_event(event_data, end_payload, latency_ms)
        elif event_type == CBEventType.EMBEDDING:
            self._handle_embedding_event(event_data, end_payload, latency_ms)
        elif event_type == CBEventType.QUERY:
            self._handle_query_event(event_data, end_payload, latency_ms)
        elif event_type == CBEventType.RETRIEVE:
            self._handle_retrieve_event(event_data, end_payload, latency_ms)

    def start_trace(self, trace_id: Optional[str] = None) -> None:
        """Begin a new trace scope.

        Args:
            trace_id: Optional trace identifier.
        """
        if trace_id:
            self._active_traces[trace_id] = {
                "start_time": time.perf_counter(),
                "steps": [],
                "llm_calls": 0,
                "total_tokens": 0,
                "total_cost": 0.0,
            }

    def end_trace(
        self,
        trace_id: Optional[str] = None,
        trace_map: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        """Complete a trace scope and generate a chain execution receipt.

        Args:
            trace_id: The trace identifier to complete.
            trace_map: Map of parent-to-child event IDs.
        """
        if not trace_id:
            return

        trace_data = self._active_traces.pop(trace_id, None)
        if trace_data is None:
            return

        duration_ms = measure_latency_ms(trace_data["start_time"])
        steps = trace_data.get("steps", [])

        if not steps:
            return

        receipt = build_chain_execution_receipt(
            chain_type="LlamaIndexQuery",
            framework="llamaindex",
            steps=steps,
            total_llm_calls=trace_data.get("llm_calls", 0),
            total_tokens=trace_data.get("total_tokens", 0),
            total_estimated_cost_usd=trace_data.get("total_cost", 0.0),
            total_duration_ms=duration_ms,
            config=self._config,
        )
        self._receipts.append(receipt)

        if self._config.auto_receipt:
            self._client.submit_receipt_background(receipt)

    # ------------------------------------------------------------------
    # Event processors
    # ------------------------------------------------------------------

    def _handle_llm_event(
        self,
        event_data: Dict[str, Any],
        end_payload: Dict[str, Any],
        latency_ms: int,
    ) -> None:
        """Process an LLM event and generate an LLMCallReceipt.

        Args:
            event_data: Start event data.
            end_payload: End event payload.
            latency_ms: Event duration in milliseconds.
        """
        start_payload = event_data.get("payload", {})

        # Extract prompt from start payload
        messages = start_payload.get(EventPayload.MESSAGES, [])
        prompt = ""
        if messages:
            prompt = json.dumps([str(m) for m in messages], default=str)
        elif EventPayload.PROMPT in start_payload:
            prompt = str(start_payload[EventPayload.PROMPT])

        # Extract completion from end payload
        response = end_payload.get(EventPayload.RESPONSE, None)
        completion = ""
        if response is not None:
            completion = str(response)

        # Extract model info
        serialized = start_payload.get(EventPayload.SERIALIZED, {})
        model = serialized.get("model", "")
        if not model:
            model = serialized.get("model_name", "")

        # Detect provider
        provider = "unknown"
        model_lower = model.lower()
        if "gpt" in model_lower or "o1" in model_lower:
            provider = "openai"
        elif "claude" in model_lower:
            provider = "anthropic"

        # Token counts from response metadata
        token_usage = end_payload.get("token_usage", {})
        input_tokens = token_usage.get("prompt_tokens", 0)
        output_tokens = token_usage.get("completion_tokens", 0)

        receipt = build_llm_call_receipt(
            model=model,
            provider=provider,
            prompt=prompt,
            completion=completion,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            config=self._config,
        )
        self._receipts.append(receipt)

        if self._config.auto_receipt:
            self._client.submit_receipt_background(receipt)

        # Update active trace if present
        for trace_data in self._active_traces.values():
            trace_data["llm_calls"] = trace_data.get("llm_calls", 0) + 1
            trace_data["total_tokens"] = (
                trace_data.get("total_tokens", 0) + receipt.total_tokens
            )
            trace_data["total_cost"] = (
                trace_data.get("total_cost", 0.0) + receipt.estimated_cost_usd
            )
            trace_data.setdefault("steps", []).append(
                StepRecord(
                    name="LLM",
                    type="llm",
                    input_hash=receipt.prompt_hash,
                    output_hash=receipt.completion_hash,
                    duration_ms=latency_ms,
                    model_used=model,
                )
            )

    def _handle_embedding_event(
        self,
        event_data: Dict[str, Any],
        end_payload: Dict[str, Any],
        latency_ms: int,
    ) -> None:
        """Process an embedding event and generate an EmbeddingReceipt.

        Args:
            event_data: Start event data.
            end_payload: End event payload.
            latency_ms: Event duration in milliseconds.
        """
        start_payload = event_data.get("payload", {})
        serialized = start_payload.get(EventPayload.SERIALIZED, {})

        model = serialized.get("model_name", "")
        provider = "openai" if "openai" in model.lower() else "unknown"

        chunks = start_payload.get("chunks", [])
        if not isinstance(chunks, list):
            chunks = [str(chunks)]

        receipt = build_embedding_receipt(
            model=model,
            provider=provider,
            texts=[str(c) for c in chunks],
            config=self._config,
        )
        self._receipts.append(receipt)

        if self._config.auto_receipt:
            self._client.submit_receipt_background(receipt)

    def _handle_query_event(
        self,
        event_data: Dict[str, Any],
        end_payload: Dict[str, Any],
        latency_ms: int,
    ) -> None:
        """Process a query event. Receipt is generated at trace end.

        Args:
            event_data: Start event data.
            end_payload: End event payload.
            latency_ms: Event duration in milliseconds.
        """
        for trace_data in self._active_traces.values():
            query_str = str(event_data.get("payload", {}).get(EventPayload.QUERY_STR, ""))
            response_str = str(end_payload.get(EventPayload.RESPONSE, ""))
            trace_data.setdefault("steps", []).append(
                StepRecord(
                    name="Query",
                    type="query",
                    input_hash=hash_content(query_str),
                    output_hash=hash_content(response_str),
                    duration_ms=latency_ms,
                )
            )

    def _handle_retrieve_event(
        self,
        event_data: Dict[str, Any],
        end_payload: Dict[str, Any],
        latency_ms: int,
    ) -> None:
        """Process a retrieval event. Receipt is generated at trace end.

        Args:
            event_data: Start event data.
            end_payload: End event payload.
            latency_ms: Event duration in milliseconds.
        """
        for trace_data in self._active_traces.values():
            query_str = str(event_data.get("payload", {}).get(EventPayload.QUERY_STR, ""))
            nodes = end_payload.get(EventPayload.NODES, [])
            node_str = json.dumps([str(n) for n in nodes], default=str)
            trace_data.setdefault("steps", []).append(
                StepRecord(
                    name="Retrieval",
                    type="retriever",
                    input_hash=hash_content(query_str),
                    output_hash=hash_content(node_str),
                    duration_ms=latency_ms,
                )
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

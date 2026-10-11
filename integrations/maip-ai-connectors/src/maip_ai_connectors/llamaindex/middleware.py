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

"""LlamaIndex query engine and retriever wrapper with MAIP receipt generation.

Wraps any LlamaIndex query engine to automatically generate chain execution
receipts for every query operation.

Usage::

    from maip_ai_connectors.llamaindex import MAIPQueryEngineWrapper

    engine = index.as_query_engine()
    wrapped = MAIPQueryEngineWrapper(engine)
    response = wrapped.query("What is MAIP?")
    receipts = wrapped.get_receipts()
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, List, Optional

from maip_ai_connectors.client import MAIPClient
from maip_ai_connectors.config import MAIPConfig
from maip_ai_connectors.receipts import (
    AnyReceipt,
    build_chain_execution_receipt,
    hash_content,
    measure_latency_ms,
)
from maip_ai_connectors.schemas import StepRecord

logger = logging.getLogger(__name__)


class MAIPQueryEngineWrapper:
    """Wraps a LlamaIndex query engine to auto-generate MAIP receipts.

    The wrapper intercepts ``query`` and ``aquery`` calls, measuring
    execution time and generating ``ChainExecutionReceipt`` for each.

    Args:
        query_engine: The LlamaIndex query engine to wrap.
        config: MAIP configuration. Defaults to environment-derived values.
    """

    def __init__(
        self,
        query_engine: Any,
        config: MAIPConfig | None = None,
    ) -> None:
        self._engine = query_engine
        self._config = config or MAIPConfig()
        self._client = MAIPClient(self._config)
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

    def query(self, query_str: str, **kwargs: Any) -> Any:
        """Execute a query and generate a chain execution receipt.

        Args:
            query_str: The query string.
            **kwargs: Additional arguments forwarded to the engine.

        Returns:
            The query engine response, unmodified.
        """
        start = time.perf_counter()
        response = self._engine.query(query_str, **kwargs)
        latency_ms = measure_latency_ms(start)

        self._generate_receipt(query_str, response, latency_ms)
        return response

    async def aquery(self, query_str: str, **kwargs: Any) -> Any:
        """Execute an async query and generate a chain execution receipt.

        Args:
            query_str: The query string.
            **kwargs: Additional arguments forwarded to the engine.

        Returns:
            The query engine response, unmodified.
        """
        start = time.perf_counter()
        response = await self._engine.aquery(query_str, **kwargs)
        latency_ms = measure_latency_ms(start)

        self._generate_receipt(query_str, response, latency_ms)
        return response

    def _generate_receipt(self, query_str: str, response: Any, latency_ms: int) -> None:
        """Build and store a chain execution receipt for a query.

        Args:
            query_str: The original query string.
            response: The query engine response object.
            latency_ms: Total query execution time in milliseconds.
        """
        response_text = str(response) if response is not None else ""

        # Extract source nodes if available for step records
        steps: List[StepRecord] = []
        source_nodes = getattr(response, "source_nodes", None)
        if source_nodes:
            steps.append(
                StepRecord(
                    name="Retrieval",
                    type="retriever",
                    input_hash=hash_content(query_str),
                    output_hash=hash_content(
                        json.dumps([str(n) for n in source_nodes], default=str)
                    ),
                    duration_ms=0,
                )
            )

        steps.append(
            StepRecord(
                name="Synthesis",
                type="llm",
                input_hash=hash_content(query_str),
                output_hash=hash_content(response_text),
                duration_ms=latency_ms,
            )
        )

        receipt = build_chain_execution_receipt(
            chain_type="LlamaIndexQueryEngine",
            framework="llamaindex",
            steps=steps,
            total_llm_calls=1,
            total_duration_ms=latency_ms,
            config=self._config,
        )
        self._receipts.append(receipt)

        if self._config.auto_receipt:
            self._client.submit_receipt_background(receipt)

    async def flush(self):
        """Wait for queued receipt delivery and surface submission failures."""
        return await self._client.flush()

    async def aclose(self):
        """Flush pending receipts and release the HTTP client."""
        await self._client.close()

    def get_submitted_receipts(self):
        """Return server-confirmed receipts; local payloads are available separately."""
        return list(self._client.submitted_receipts)

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

"""LangChain middleware / runnable wrapper for MAIP receipt generation.

Wraps any LangChain Runnable to automatically inject a ``MAIPCallbackHandler``
into every invocation, ensuring receipts are generated without modifying
existing chain definitions.

Usage::

    from maip_ai_connectors.langchain import MAIPRunnableWrapper

    chain = prompt | llm | parser
    wrapped = MAIPRunnableWrapper(chain)
    result = wrapped.invoke({"question": "What is MAIP?"})
    receipts = wrapped.get_receipts()
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from langchain_core.runnables import Runnable, RunnableConfig

from maip_ai_connectors.config import MAIPConfig
from maip_ai_connectors.langchain.callback import MAIPCallbackHandler
from maip_ai_connectors.receipts import AnyReceipt

logger = logging.getLogger(__name__)


class MAIPRunnableWrapper:
    """Wraps a LangChain Runnable to automatically generate MAIP receipts.

    The wrapper injects a ``MAIPCallbackHandler`` into the runnable config
    for every ``invoke``, ``ainvoke``, ``batch``, and ``abatch`` call.

    Args:
        runnable: The LangChain Runnable to wrap.
        config: MAIP configuration. Defaults to environment-derived values.
    """

    def __init__(
        self,
        runnable: Runnable,
        config: MAIPConfig | None = None,
    ) -> None:
        self._runnable = runnable
        self._config = config or MAIPConfig()
        self._handler = MAIPCallbackHandler(self._config)

    def get_receipts(self) -> List[AnyReceipt]:
        """Return all receipts generated across all invocations.

        Returns:
            A list of receipt objects in chronological order.
        """
        return self._handler.get_receipts()

    def clear_receipts(self) -> None:
        """Clear the accumulated receipts list."""
        self._handler.clear_receipts()

    def _merge_config(self, config: Optional[RunnableConfig] = None) -> RunnableConfig:
        """Merge the MAIP callback handler into the provided runnable config.

        Args:
            config: Optional existing runnable config.

        Returns:
            A config dictionary with the MAIP handler appended to callbacks.
        """
        merged: Dict[str, Any] = dict(config) if config else {}
        callbacks = list(merged.get("callbacks", []) or [])
        if self._handler not in callbacks:
            callbacks.append(self._handler)
        merged["callbacks"] = callbacks
        return merged  # type: ignore[return-value]

    def invoke(self, input: Any, config: Optional[RunnableConfig] = None, **kwargs: Any) -> Any:
        """Invoke the wrapped runnable with MAIP receipt generation.

        Args:
            input: The runnable input.
            config: Optional runnable config.
            **kwargs: Additional keyword arguments forwarded to the runnable.

        Returns:
            The runnable output, unmodified.
        """
        return self._runnable.invoke(input, self._merge_config(config), **kwargs)

    async def ainvoke(
        self, input: Any, config: Optional[RunnableConfig] = None, **kwargs: Any
    ) -> Any:
        """Asynchronously invoke the wrapped runnable with MAIP receipt generation.

        Args:
            input: The runnable input.
            config: Optional runnable config.
            **kwargs: Additional keyword arguments forwarded to the runnable.

        Returns:
            The runnable output, unmodified.
        """
        return await self._runnable.ainvoke(input, self._merge_config(config), **kwargs)

    def batch(
        self,
        inputs: List[Any],
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> List[Any]:
        """Batch-invoke the wrapped runnable with MAIP receipt generation.

        Args:
            inputs: List of runnable inputs.
            config: Optional runnable config applied to all inputs.
            **kwargs: Additional keyword arguments.

        Returns:
            List of runnable outputs, unmodified.
        """
        merged = self._merge_config(config)
        return self._runnable.batch(inputs, [merged] * len(inputs), **kwargs)

    async def abatch(
        self,
        inputs: List[Any],
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> List[Any]:
        """Async batch-invoke the wrapped runnable with MAIP receipt generation.

        Args:
            inputs: List of runnable inputs.
            config: Optional runnable config applied to all inputs.
            **kwargs: Additional keyword arguments.

        Returns:
            List of runnable outputs, unmodified.
        """
        merged = self._merge_config(config)
        return await self._runnable.abatch(inputs, [merged] * len(inputs), **kwargs)

    async def flush(self):
        """Wait for queued receipt delivery and surface submission failures."""
        return await self._handler.flush()

    async def aclose(self):
        """Flush pending receipts and release the HTTP client."""
        await self._handler.aclose()

    def get_submitted_receipts(self):
        """Return server-confirmed receipts; local payloads are available separately."""
        return list(self._handler.get_submitted_receipts())

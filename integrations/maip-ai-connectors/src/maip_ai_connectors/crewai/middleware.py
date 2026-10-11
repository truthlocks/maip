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

"""CrewAI execution wrapper that auto-injects MAIP receipt generation.

Wraps a CrewAI Crew instance to automatically track and receipt all
task executions during a crew kickoff.

Usage::

    from maip_ai_connectors.crewai import MAIPCrewWrapper

    crew = Crew(agents=[...], tasks=[...])
    wrapper = MAIPCrewWrapper(crew)
    result = wrapper.kickoff()
    receipts = wrapper.get_receipts()
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from maip_ai_connectors.config import MAIPConfig
from maip_ai_connectors.crewai.callback import MAIPCrewCallback
from maip_ai_connectors.receipts import AnyReceipt

logger = logging.getLogger(__name__)


class MAIPCrewWrapper:
    """Wraps a CrewAI Crew to auto-generate MAIP receipts during execution.

    Intercepts ``kickoff`` calls, injects a ``MAIPCrewCallback``, and
    collects all receipts generated during crew execution.

    Args:
        crew: The CrewAI Crew object to wrap.
        config: MAIP configuration. Defaults to environment-derived values.
    """

    def __init__(self, crew: Any, config: MAIPConfig | None = None) -> None:
        self._crew = crew
        self._config = config or MAIPConfig()
        self._callback = MAIPCrewCallback(self._config)

    def get_receipts(self) -> List[AnyReceipt]:
        """Return all receipts generated during crew executions.

        Returns:
            A list of receipt objects in chronological order.
        """
        return self._callback.get_receipts()

    def clear_receipts(self) -> None:
        """Clear the accumulated receipts list."""
        self._callback.clear_receipts()

    def kickoff(self, inputs: Optional[Dict[str, Any]] = None) -> Any:
        """Execute the crew with MAIP receipt generation.

        Notifies the callback of crew start, delegates to the original
        crew ``kickoff``, and notifies the callback of crew end.

        Args:
            inputs: Optional input dictionary forwarded to the crew.

        Returns:
            The crew execution result, unmodified.
        """
        self._callback.on_crew_start(self._crew)

        try:
            # Inject our callback if the crew supports step_callback
            original_callback = getattr(self._crew, "step_callback", None)
            tasks = getattr(self._crew, "tasks", [])

            # Notify task start/end for each task
            for task in tasks:
                agent = getattr(task, "agent", None)
                if agent is not None:
                    self._callback.on_task_start(task, agent)

            if inputs is not None:
                result = self._crew.kickoff(inputs=inputs)
            else:
                result = self._crew.kickoff()

            # Notify task ends
            for task in tasks:
                agent = getattr(task, "agent", None)
                output = getattr(task, "output", None)
                if agent is not None:
                    self._callback.on_task_end(task, agent, output)

            self._callback.on_crew_end(self._crew, result)
            return result

        except Exception:
            self._callback.on_crew_end(self._crew, None)
            raise

    async def flush(self):
        """Wait for queued receipt delivery and surface submission failures."""
        return await self._callback.flush()

    async def aclose(self):
        """Flush pending receipts and release the HTTP client."""
        await self._callback.aclose()

    def get_submitted_receipts(self):
        """Return server-confirmed receipts; local payloads are available separately."""
        return list(self._callback.get_submitted_receipts())

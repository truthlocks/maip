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

"""CrewAI callback handler that generates MAIP receipts for task and agent events.

Integrates with CrewAI's callback system to produce receipts for task
executions, agent actions, and full crew runs.

Usage::

    from maip_ai_connectors.crewai import MAIPCrewCallback

    callback = MAIPCrewCallback()
    crew = Crew(
        agents=[...],
        tasks=[...],
        callbacks=[callback],
    )
    result = crew.kickoff()
    receipts = callback.get_receipts()
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from maip_ai_connectors.client import MAIPClient
from maip_ai_connectors.config import MAIPConfig
from maip_ai_connectors.receipts import (
    AnyReceipt,
    build_agent_action_receipt,
    build_chain_execution_receipt,
    hash_content,
    measure_latency_ms,
)
from maip_ai_connectors.schemas import StepRecord

logger = logging.getLogger(__name__)


class MAIPCrewCallback:
    """CrewAI callback that generates MAIP receipts for task executions and agent actions.

    Tracks task start/end, agent actions, and crew lifecycle events. Produces
    ``AgentActionReceipt`` for individual tasks and ``ChainExecutionReceipt``
    for full crew executions.

    Args:
        config: MAIP configuration. Defaults to environment-derived values.
    """

    def __init__(self, config: MAIPConfig | None = None) -> None:
        self._config = config or MAIPConfig()
        self._client = MAIPClient(self._config)
        self._receipts: List[AnyReceipt] = []
        self._active_tasks: Dict[str, Dict[str, Any]] = {}
        self._crew_state: Optional[Dict[str, Any]] = None

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
    # Task events
    # ------------------------------------------------------------------

    def on_task_start(self, task: Any, agent: Any) -> None:
        """Record the start of a CrewAI task execution.

        Args:
            task: The CrewAI Task object being started.
            agent: The CrewAI Agent assigned to this task.
        """
        task_id = str(id(task))
        agent_name = getattr(agent, "role", None) or getattr(agent, "name", "unknown_agent")
        task_desc = getattr(task, "description", "")

        self._active_tasks[task_id] = {
            "start_time": time.perf_counter(),
            "agent_name": str(agent_name),
            "task_description": str(task_desc),
        }

    def on_task_end(self, task: Any, agent: Any, output: Any) -> None:
        """Generate an AgentActionReceipt on task completion.

        Args:
            task: The CrewAI Task object that completed.
            agent: The CrewAI Agent that executed the task.
            output: The task output.
        """
        task_id = str(id(task))
        task_data = self._active_tasks.pop(task_id, None)

        agent_name = ""
        task_desc = ""
        if task_data is not None:
            agent_name = task_data["agent_name"]
            task_desc = task_data["task_description"]
        else:
            agent_name = str(
                getattr(agent, "role", None) or getattr(agent, "name", "unknown_agent")
            )
            task_desc = str(getattr(task, "description", ""))

        output_str = str(output) if output is not None else ""

        receipt = build_agent_action_receipt(
            agent_name=agent_name,
            action="task_execution",
            tool_name=None,
            tool_input=task_desc,
            tool_output=output_str,
            config=self._config,
        )
        self._receipts.append(receipt)

        # Add to crew state if a crew run is active
        if self._crew_state is not None:
            latency_ms = 0
            if task_data is not None:
                latency_ms = measure_latency_ms(task_data["start_time"])
            self._crew_state["steps"].append(
                StepRecord(
                    name=f"Task: {task_desc[:50]}",
                    type="agent_task",
                    input_hash=hash_content(task_desc),
                    output_hash=hash_content(output_str),
                    duration_ms=latency_ms,
                    model_used="",
                )
            )
            self._crew_state["task_count"] += 1

        if self._config.auto_receipt:
            self._client.submit_receipt_background(receipt)

    # ------------------------------------------------------------------
    # Crew lifecycle events
    # ------------------------------------------------------------------

    def on_crew_start(self, crew: Any) -> None:
        """Record the start of a full crew execution.

        Args:
            crew: The CrewAI Crew object being kicked off.
        """
        self._crew_state = {
            "start_time": time.perf_counter(),
            "steps": [],
            "task_count": 0,
        }

    def on_crew_end(self, crew: Any, result: Any) -> None:
        """Generate a ChainExecutionReceipt for the full crew execution.

        Args:
            crew: The CrewAI Crew object that completed.
            result: The crew execution result.
        """
        if self._crew_state is None:
            return

        duration_ms = measure_latency_ms(self._crew_state["start_time"])

        receipt = build_chain_execution_receipt(
            chain_type="CrewExecution",
            framework="crewai",
            steps=self._crew_state.get("steps", []),
            total_llm_calls=self._crew_state.get("task_count", 0),
            total_duration_ms=duration_ms,
            config=self._config,
        )
        self._receipts.append(receipt)
        self._crew_state = None

        if self._config.auto_receipt:
            self._client.submit_receipt_background(receipt)

    # ------------------------------------------------------------------
    # Agent action events
    # ------------------------------------------------------------------

    def on_agent_action(
        self,
        agent: Any,
        action: str,
        tool_name: str | None = None,
        tool_input: str = "",
        tool_output: str = "",
        reasoning: str = "",
    ) -> None:
        """Generate an AgentActionReceipt for an individual agent action.

        This covers tool invocations, delegation, and reasoning steps
        that occur during task execution.

        Args:
            agent: The CrewAI Agent performing the action.
            action: Action type description.
            tool_name: Name of the tool invoked, if any.
            tool_input: Raw tool input.
            tool_output: Raw tool output.
            reasoning: Agent's reasoning or thought process.
        """
        agent_name = str(
            getattr(agent, "role", None) or getattr(agent, "name", "unknown_agent")
        )

        receipt = build_agent_action_receipt(
            agent_name=agent_name,
            action=action,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
            reasoning=reasoning,
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

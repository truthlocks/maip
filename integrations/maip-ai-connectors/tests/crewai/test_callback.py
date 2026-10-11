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

"""Tests for the CrewAI MAIP callback handler."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from maip_ai_connectors.config import MAIPConfig
from maip_ai_connectors.crewai.callback import MAIPCrewCallback
from maip_ai_connectors.schemas import AgentActionReceipt, ChainExecutionReceipt


def _config() -> MAIPConfig:
    """Create a test config with auto_receipt disabled."""
    return MAIPConfig(
        api_url="https://test.local",
        api_key="test-key",
        tenant_id="tenant-001",
        agent_id="agent-001",
        auto_receipt=False,
    )


def _mock_agent(role: str = "researcher") -> SimpleNamespace:
    """Create a mock CrewAI agent."""
    return SimpleNamespace(role=role, name=role)


def _mock_task(description: str = "Research MAIP protocol") -> SimpleNamespace:
    """Create a mock CrewAI task."""
    return SimpleNamespace(description=description)


class TestMAIPCrewCallback:
    def test_task_start_end_generates_receipt(self) -> None:
        """Verify task start/end produces an AgentActionReceipt."""
        callback = MAIPCrewCallback(_config())
        agent = _mock_agent("researcher")
        task = _mock_task("Research MAIP")

        callback.on_task_start(task, agent)
        callback.on_task_end(task, agent, "MAIP findings")

        receipts = callback.get_receipts()
        assert len(receipts) == 1
        assert isinstance(receipts[0], AgentActionReceipt)
        assert receipts[0].agent_name == "researcher"
        assert receipts[0].action == "task_execution"

    def test_task_end_without_start_still_works(self) -> None:
        """Verify task_end without prior task_start still generates receipt."""
        callback = MAIPCrewCallback(_config())
        agent = _mock_agent("writer")
        task = _mock_task("Write report")

        callback.on_task_end(task, agent, "Report content")

        receipts = callback.get_receipts()
        assert len(receipts) == 1
        assert isinstance(receipts[0], AgentActionReceipt)

    def test_crew_lifecycle_generates_chain_receipt(self) -> None:
        """Verify crew start/end produces a ChainExecutionReceipt."""
        callback = MAIPCrewCallback(_config())
        crew = MagicMock()

        callback.on_crew_start(crew)

        # Simulate task execution during crew
        agent = _mock_agent("analyst")
        task = _mock_task("Analyze data")
        callback.on_task_start(task, agent)
        callback.on_task_end(task, agent, "Analysis complete")

        callback.on_crew_end(crew, "Final result")

        receipts = callback.get_receipts()
        # Should have 1 AgentActionReceipt (task) + 1 ChainExecutionReceipt (crew)
        agent_receipts = [r for r in receipts if isinstance(r, AgentActionReceipt)]
        chain_receipts = [r for r in receipts if isinstance(r, ChainExecutionReceipt)]
        assert len(agent_receipts) == 1
        assert len(chain_receipts) == 1
        assert chain_receipts[0].chain_type == "CrewExecution"
        assert chain_receipts[0].framework == "crewai"

    def test_crew_end_without_start_is_safe(self) -> None:
        """Verify crew_end without prior start does not crash."""
        callback = MAIPCrewCallback(_config())
        callback.on_crew_end(MagicMock(), "result")
        assert len(callback.get_receipts()) == 0

    def test_on_agent_action_generates_receipt(self) -> None:
        """Verify agent action generates a receipt."""
        callback = MAIPCrewCallback(_config())
        agent = _mock_agent("coder")

        callback.on_agent_action(
            agent=agent,
            action="tool_invocation",
            tool_name="code_search",
            tool_input="find authentication patterns",
            tool_output="3 patterns found",
            reasoning="Need to find auth examples",
        )

        receipts = callback.get_receipts()
        assert len(receipts) == 1
        assert isinstance(receipts[0], AgentActionReceipt)
        assert receipts[0].tool_name == "code_search"
        assert receipts[0].reasoning_hash != ""

    def test_clear_receipts(self) -> None:
        """Verify clear_receipts empties the list."""
        callback = MAIPCrewCallback(_config())
        agent = _mock_agent("test")
        task = _mock_task("test task")
        callback.on_task_start(task, agent)
        callback.on_task_end(task, agent, "done")
        assert len(callback.get_receipts()) == 1
        callback.clear_receipts()
        assert len(callback.get_receipts()) == 0

    def test_multiple_tasks_in_crew(self) -> None:
        """Verify multiple tasks accumulate in crew chain receipt."""
        callback = MAIPCrewCallback(_config())
        crew = MagicMock()
        callback.on_crew_start(crew)

        for i in range(3):
            agent = _mock_agent(f"agent-{i}")
            task = _mock_task(f"task-{i}")
            callback.on_task_start(task, agent)
            callback.on_task_end(task, agent, f"output-{i}")

        callback.on_crew_end(crew, "final")

        chain_receipts = [
            r for r in callback.get_receipts()
            if isinstance(r, ChainExecutionReceipt)
        ]
        assert len(chain_receipts) == 1
        assert len(chain_receipts[0].steps) == 3

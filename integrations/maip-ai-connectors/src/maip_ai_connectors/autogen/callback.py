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

"""AutoGen agent message hook for MAIP receipt generation.

Integrates with AutoGen's agent messaging system to generate receipts
for every message exchange and function call in multi-agent conversations.

Usage::

    from maip_ai_connectors.autogen import MAIPAutoGenHook

    hook = MAIPAutoGenHook()
    assistant = AssistantAgent("assistant", llm_config=llm_config)
    hook.register(assistant)
    # Messages and function calls will now generate receipts
    receipts = hook.get_receipts()
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
    build_llm_call_receipt,
    hash_content,
    measure_latency_ms,
)
from maip_ai_connectors.schemas import StepRecord

logger = logging.getLogger(__name__)


class MAIPAutoGenHook:
    """AutoGen message hook for MAIP receipt generation on agent conversations.

    Tracks messages sent between agents, function calls, and conversation
    flows to produce ``AgentActionReceipt`` and ``ChainExecutionReceipt``
    instances.

    Args:
        config: MAIP configuration. Defaults to environment-derived values.
    """

    def __init__(self, config: MAIPConfig | None = None) -> None:
        self._config = config or MAIPConfig()
        self._client = MAIPClient(self._config)
        self._receipts: List[AnyReceipt] = []
        self._conversation_steps: List[StepRecord] = []
        self._conversation_start: Optional[float] = None
        self._registered_agents: List[Any] = []

    def get_receipts(self) -> List[AnyReceipt]:
        """Return all receipts generated so far.

        Returns:
            A list of receipt objects in chronological order.
        """
        return list(self._receipts)

    def clear_receipts(self) -> None:
        """Clear the accumulated receipts list."""
        self._receipts.clear()

    def register(self, agent: Any) -> None:
        """Register a hook callback with an AutoGen agent.

        Attaches this hook to the agent's ``register_hook`` method if
        available, or stores the agent reference for manual tracking.

        Args:
            agent: An AutoGen agent (ConversableAgent, AssistantAgent, etc.).
        """
        self._registered_agents.append(agent)

        if hasattr(agent, "register_hook"):
            agent.register_hook("process_last_received_message", self._process_message_hook)

    def _process_message_hook(self, message: Any) -> Any:
        """Hook invoked by AutoGen when an agent processes a received message.

        Generates a receipt for the message and returns it unmodified.

        Args:
            message: The message being processed.

        Returns:
            The message, unmodified.
        """
        if isinstance(message, dict):
            content = message.get("content", "")
            role = message.get("role", "unknown")
        elif isinstance(message, str):
            content = message
            role = "user"
        else:
            content = str(message)
            role = "unknown"

        receipt = build_agent_action_receipt(
            agent_name="autogen_agent",
            action=f"message_received_{role}",
            tool_input=str(content),
            config=self._config,
        )
        self._receipts.append(receipt)

        if self._config.auto_receipt:
            self._client.submit_receipt_background(receipt)

        return message

    # ------------------------------------------------------------------
    # Explicit event hooks
    # ------------------------------------------------------------------

    def on_message_sent(self, sender: Any, receiver: Any, message: Any) -> None:
        """Record a message sent between two agents.

        Args:
            sender: The sending agent.
            receiver: The receiving agent.
            message: The message content.
        """
        sender_name = self._agent_name(sender)
        receiver_name = self._agent_name(receiver)
        content = self._extract_content(message)

        if self._conversation_start is None:
            self._conversation_start = time.perf_counter()

        self._conversation_steps.append(
            StepRecord(
                name=f"{sender_name} -> {receiver_name}",
                type="message_sent",
                input_hash=hash_content(content),
                output_hash="",
                duration_ms=0,
            )
        )

        receipt = build_agent_action_receipt(
            agent_name=sender_name,
            action="message_sent",
            tool_input=content,
            config=self._config,
        )
        self._receipts.append(receipt)

        if self._config.auto_receipt:
            self._client.submit_receipt_background(receipt)

    def on_message_received(self, sender: Any, receiver: Any, message: Any) -> None:
        """Record a message received by an agent.

        Args:
            sender: The sending agent.
            receiver: The receiving agent.
            message: The message content.
        """
        receiver_name = self._agent_name(receiver)
        content = self._extract_content(message)

        receipt = build_agent_action_receipt(
            agent_name=receiver_name,
            action="message_received",
            tool_input=content,
            config=self._config,
        )
        self._receipts.append(receipt)

        if self._config.auto_receipt:
            self._client.submit_receipt_background(receipt)

    def on_function_call(
        self,
        agent: Any,
        function_name: str,
        arguments: Any,
        result: Any,
    ) -> None:
        """Record a function call made by an agent.

        Args:
            agent: The agent that made the function call.
            function_name: Name of the function called.
            arguments: Function arguments.
            result: Function return value.
        """
        agent_name = self._agent_name(agent)
        args_str = json.dumps(arguments, default=str, sort_keys=True) if arguments else ""
        result_str = str(result) if result is not None else ""

        receipt = build_agent_action_receipt(
            agent_name=agent_name,
            action="function_call",
            tool_name=function_name,
            tool_input=args_str,
            tool_output=result_str,
            config=self._config,
        )
        self._receipts.append(receipt)

        self._conversation_steps.append(
            StepRecord(
                name=f"{agent_name}:{function_name}",
                type="function_call",
                input_hash=hash_content(args_str),
                output_hash=hash_content(result_str),
                duration_ms=0,
                model_used="",
            )
        )

        if self._config.auto_receipt:
            self._client.submit_receipt_background(receipt)

    def finalize_conversation(self) -> Optional[AnyReceipt]:
        """Generate a ChainExecutionReceipt for the accumulated conversation.

        Should be called at the end of a multi-agent conversation to produce
        an aggregate receipt of the entire interaction.

        Returns:
            The chain execution receipt, or None if no steps were recorded.
        """
        if not self._conversation_steps:
            return None

        duration_ms = 0
        if self._conversation_start is not None:
            duration_ms = measure_latency_ms(self._conversation_start)

        receipt = build_chain_execution_receipt(
            chain_type="AutoGenConversation",
            framework="autogen",
            steps=self._conversation_steps,
            total_llm_calls=len(
                [s for s in self._conversation_steps if s.type in ("llm", "message_sent")]
            ),
            total_duration_ms=duration_ms,
            config=self._config,
        )
        self._receipts.append(receipt)
        self._conversation_steps = []
        self._conversation_start = None

        if self._config.auto_receipt:
            self._client.submit_receipt_background(receipt)

        return receipt

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _agent_name(agent: Any) -> str:
        """Extract a human-readable name from an AutoGen agent.

        Args:
            agent: An AutoGen agent object.

        Returns:
            The agent's name string.
        """
        if isinstance(agent, str):
            return agent
        return str(getattr(agent, "name", "unknown_agent"))

    @staticmethod
    def _extract_content(message: Any) -> str:
        """Extract text content from an AutoGen message.

        Args:
            message: A message string or dictionary.

        Returns:
            The message content as a string.
        """
        if isinstance(message, dict):
            return str(message.get("content", ""))
        return str(message)

    async def flush(self):
        """Wait for queued receipt delivery and surface submission failures."""
        return await self._client.flush()

    async def aclose(self):
        """Flush pending receipts and release the HTTP client."""
        await self._client.close()

    def get_submitted_receipts(self):
        """Return server-confirmed receipts; local payloads are available separately."""
        return list(self._client.submitted_receipts)

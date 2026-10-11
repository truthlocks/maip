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

"""AutoGen ConversableAgent wrapper for automatic MAIP receipt generation.

Wraps AutoGen's ConversableAgent to intercept all message exchanges and
function calls, generating MAIP receipts transparently.

Usage::

    from maip_ai_connectors.autogen import MAIPConversableAgentWrapper

    assistant = AssistantAgent("assistant", llm_config=llm_config)
    wrapper = MAIPConversableAgentWrapper(assistant)
    wrapper.initiate_chat(user_proxy, message="Hello")
    receipts = wrapper.get_receipts()
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from maip_ai_connectors.autogen.callback import MAIPAutoGenHook
from maip_ai_connectors.config import MAIPConfig
from maip_ai_connectors.receipts import AnyReceipt

logger = logging.getLogger(__name__)


class MAIPConversableAgentWrapper:
    """Wraps an AutoGen ConversableAgent for MAIP receipt generation.

    Intercepts ``initiate_chat``, ``send``, and ``receive`` methods to
    automatically generate receipts for all conversation events.

    Args:
        agent: The AutoGen ConversableAgent to wrap.
        config: MAIP configuration. Defaults to environment-derived values.
    """

    def __init__(self, agent: Any, config: MAIPConfig | None = None) -> None:
        self._agent = agent
        self._config = config or MAIPConfig()
        self._hook = MAIPAutoGenHook(self._config)
        self._hook.register(agent)

    def get_receipts(self) -> List[AnyReceipt]:
        """Return all receipts generated across all conversations.

        Returns:
            A list of receipt objects in chronological order.
        """
        return self._hook.get_receipts()

    def clear_receipts(self) -> None:
        """Clear the accumulated receipts list."""
        self._hook.clear_receipts()

    def initiate_chat(
        self,
        recipient: Any,
        message: str = "",
        **kwargs: Any,
    ) -> Any:
        """Initiate a chat with receipt tracking.

        Args:
            recipient: The agent to chat with.
            message: Initial message.
            **kwargs: Additional arguments forwarded to the agent.

        Returns:
            The chat result from the underlying agent.
        """
        self._hook.on_message_sent(self._agent, recipient, message)

        result = self._agent.initiate_chat(recipient, message=message, **kwargs)

        self._hook.finalize_conversation()
        return result

    def send(
        self,
        message: Any,
        recipient: Any,
        **kwargs: Any,
    ) -> None:
        """Send a message with receipt tracking.

        Args:
            message: The message to send.
            recipient: The receiving agent.
            **kwargs: Additional arguments forwarded to the agent.
        """
        self._hook.on_message_sent(self._agent, recipient, message)
        self._agent.send(message, recipient, **kwargs)

    def receive(
        self,
        message: Any,
        sender: Any,
        **kwargs: Any,
    ) -> None:
        """Receive a message with receipt tracking.

        Args:
            message: The message received.
            sender: The sending agent.
            **kwargs: Additional arguments forwarded to the agent.
        """
        self._hook.on_message_received(sender, self._agent, message)
        self._agent.receive(message, sender, **kwargs)

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the wrapped agent.

        Args:
            name: Attribute name.

        Returns:
            The attribute from the wrapped agent.
        """
        return getattr(self._agent, name)

    async def flush(self):
        """Wait for queued receipt delivery and surface submission failures."""
        return await self._hook.flush()

    async def aclose(self):
        """Flush pending receipts and release the HTTP client."""
        await self._hook.aclose()

    def get_submitted_receipts(self):
        """Return server-confirmed receipts; local payloads are available separately."""
        return list(self._hook.get_submitted_receipts())

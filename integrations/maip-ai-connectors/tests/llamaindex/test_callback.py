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

"""Tests for the LlamaIndex MAIP callback handler.

Uses mocks for all LlamaIndex dependencies so tests run without
installing the full llama-index package.
"""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock the llama_index modules before importing our code
# ---------------------------------------------------------------------------

_mock_base_handler = MagicMock()


class _FakeBaseCallbackHandler:
    """Minimal stand-in for LlamaIndex BaseCallbackHandler."""

    def __init__(self, event_starts_to_ignore=None, event_ends_to_ignore=None):
        self.event_starts_to_ignore = event_starts_to_ignore or []
        self.event_ends_to_ignore = event_ends_to_ignore or []


class _FakeCBEventType:
    """Fake CBEventType enum."""

    LLM = "llm"
    EMBEDDING = "embedding"
    QUERY = "query"
    RETRIEVE = "retrieve"


class _FakeEventPayload:
    """Fake EventPayload constants."""

    MESSAGES = "messages"
    PROMPT = "prompt"
    RESPONSE = "response"
    SERIALIZED = "serialized"
    QUERY_STR = "query_str"
    NODES = "nodes"


# Set up mock modules in sys.modules
_callbacks_mod = ModuleType("llama_index.core.callbacks")
_callbacks_mod.CallbackManager = MagicMock  # type: ignore[attr-defined]

_base_handler_mod = ModuleType("llama_index.core.callbacks.base_handler")
_base_handler_mod.BaseCallbackHandler = _FakeBaseCallbackHandler  # type: ignore[attr-defined]

_schema_mod = ModuleType("llama_index.core.callbacks.schema")
_schema_mod.CBEventType = _FakeCBEventType  # type: ignore[attr-defined]
_schema_mod.EventPayload = _FakeEventPayload  # type: ignore[attr-defined]

_core_mod = ModuleType("llama_index.core")
_core_mod.callbacks = _callbacks_mod  # type: ignore[attr-defined]

sys.modules["llama_index"] = ModuleType("llama_index")
sys.modules["llama_index.core"] = _core_mod
sys.modules["llama_index.core.callbacks"] = _callbacks_mod
sys.modules["llama_index.core.callbacks.base_handler"] = _base_handler_mod
sys.modules["llama_index.core.callbacks.schema"] = _schema_mod

from maip_ai_connectors.config import MAIPConfig
from maip_ai_connectors.llamaindex.callback import MAIPLlamaIndexHandler
from maip_ai_connectors.schemas import LLMCallReceipt, EmbeddingReceipt, ChainExecutionReceipt


def _config() -> MAIPConfig:
    """Create a test config with auto_receipt disabled."""
    return MAIPConfig(
        api_url="https://test.local",
        api_key="test-key",
        tenant_id="tenant-001",
        agent_id="agent-001",
        auto_receipt=False,
    )


class TestMAIPLlamaIndexHandler:
    def test_llm_event_generates_receipt(self) -> None:
        """Verify LLM event start/end produces an LLMCallReceipt."""
        handler = MAIPLlamaIndexHandler(_config())

        handler.on_event_start(
            event_type=_FakeCBEventType.LLM,
            payload={
                _FakeEventPayload.MESSAGES: ["What is MAIP?"],
                _FakeEventPayload.SERIALIZED: {"model": "gpt-4o"},
            },
            event_id="evt-1",
        )

        handler.on_event_end(
            event_type=_FakeCBEventType.LLM,
            payload={
                _FakeEventPayload.RESPONSE: "MAIP is a protocol",
                "token_usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
            event_id="evt-1",
        )

        receipts = handler.get_receipts()
        assert len(receipts) == 1
        assert isinstance(receipts[0], LLMCallReceipt)

    def test_embedding_event_generates_receipt(self) -> None:
        """Verify embedding event produces an EmbeddingReceipt."""
        handler = MAIPLlamaIndexHandler(_config())

        handler.on_event_start(
            event_type=_FakeCBEventType.EMBEDDING,
            payload={
                "chunks": ["hello", "world"],
                _FakeEventPayload.SERIALIZED: {"model_name": "text-embedding-3-small"},
            },
            event_id="evt-2",
        )

        handler.on_event_end(
            event_type=_FakeCBEventType.EMBEDDING,
            payload={},
            event_id="evt-2",
        )

        receipts = handler.get_receipts()
        assert len(receipts) == 1
        assert isinstance(receipts[0], EmbeddingReceipt)
        assert receipts[0].num_texts == 2

    def test_unknown_event_id_is_safe(self) -> None:
        """Verify on_event_end for unknown event_id does not crash."""
        handler = MAIPLlamaIndexHandler(_config())
        handler.on_event_end(
            event_type=_FakeCBEventType.LLM,
            payload={},
            event_id="nonexistent",
        )
        assert len(handler.get_receipts()) == 0

    def test_trace_lifecycle_generates_chain_receipt(self) -> None:
        """Verify trace start/end with events produces a ChainExecutionReceipt."""
        handler = MAIPLlamaIndexHandler(_config())

        handler.start_trace("trace-1")

        # Simulate LLM event within trace
        handler.on_event_start(
            event_type=_FakeCBEventType.LLM,
            payload={
                _FakeEventPayload.MESSAGES: ["query"],
                _FakeEventPayload.SERIALIZED: {"model": "gpt-4o"},
            },
            event_id="evt-3",
        )
        handler.on_event_end(
            event_type=_FakeCBEventType.LLM,
            payload={
                _FakeEventPayload.RESPONSE: "answer",
            },
            event_id="evt-3",
        )

        handler.end_trace("trace-1")

        # Should have LLM receipt + chain receipt
        receipts = handler.get_receipts()
        assert len(receipts) == 2
        llm_receipts = [r for r in receipts if isinstance(r, LLMCallReceipt)]
        chain_receipts = [r for r in receipts if isinstance(r, ChainExecutionReceipt)]
        assert len(llm_receipts) == 1
        assert len(chain_receipts) == 1
        assert chain_receipts[0].framework == "llamaindex"

    def test_clear_receipts(self) -> None:
        """Verify clear_receipts empties the list."""
        handler = MAIPLlamaIndexHandler(_config())
        handler.on_event_start(
            event_type=_FakeCBEventType.LLM,
            payload={_FakeEventPayload.SERIALIZED: {}},
            event_id="evt-4",
        )
        handler.on_event_end(
            event_type=_FakeCBEventType.LLM,
            payload={},
            event_id="evt-4",
        )
        assert len(handler.get_receipts()) == 1
        handler.clear_receipts()
        assert len(handler.get_receipts()) == 0

    def test_empty_trace_does_not_generate_receipt(self) -> None:
        """Verify trace with no events does not produce a receipt."""
        handler = MAIPLlamaIndexHandler(_config())
        handler.start_trace("trace-empty")
        handler.end_trace("trace-empty")
        assert len(handler.get_receipts()) == 0

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

"""AI model orchestration connectors for MAIP receipt generation.

Provides integrations with major AI orchestration frameworks (LangChain,
LlamaIndex, CrewAI, AutoGen) and direct model provider wrappers (OpenAI,
Anthropic, AWS Bedrock) that automatically generate MAIP receipts for
every AI model call, chain execution, and agent action.
"""

__version__ = "1.1.0"

from maip_ai_connectors.client import MAIPClient
from maip_ai_connectors.config import MAIPConfig
from maip_ai_connectors.receipts import (
    build_agent_action_receipt,
    build_chain_execution_receipt,
    build_embedding_receipt,
    build_llm_call_receipt,
    hash_content,
    hash_receipt_payload,
)
from maip_ai_connectors.schemas import (
    AgentActionReceipt,
    ChainExecutionReceipt,
    EmbeddingReceipt,
    LLMCallReceipt,
    ReceiptResponse,
    ReceiptVerifyResponse,
    StepRecord,
)

__all__ = [
    # Client
    "MAIPClient",
    "MAIPConfig",
    # Receipt builders
    "build_agent_action_receipt",
    "build_chain_execution_receipt",
    "build_embedding_receipt",
    "build_llm_call_receipt",
    "hash_content",
    "hash_receipt_payload",
    # Schemas
    "AgentActionReceipt",
    "ChainExecutionReceipt",
    "EmbeddingReceipt",
    "LLMCallReceipt",
    "ReceiptResponse",
    "ReceiptVerifyResponse",
    "StepRecord",
]

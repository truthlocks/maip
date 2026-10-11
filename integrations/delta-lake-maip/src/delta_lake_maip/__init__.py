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

"""Delta Lake plugin for MAIP receipt generation."""

__version__ = "1.1.0"

from delta_lake_maip.client import MAIPClient
from delta_lake_maip.config import DeltaMAIPConfig
from delta_lake_maip.listener import DeltaCommitListener
from delta_lake_maip.receipts import (
    generate_merge_receipt,
    generate_schema_evolution_receipt,
    generate_write_receipt,
    hash_receipt_payload,
)
from delta_lake_maip.schemas import (
    DeltaMergeReceipt,
    DeltaSchemaEvolutionReceipt,
    DeltaWriteReceipt,
    ReceiptResponse,
    ReceiptVerifyResponse,
)
from delta_lake_maip.tracker import DeltaTableTracker

__all__ = [
    "DeltaCommitListener",
    "DeltaMAIPConfig",
    "DeltaMergeReceipt",
    "DeltaSchemaEvolutionReceipt",
    "DeltaTableTracker",
    "DeltaWriteReceipt",
    "MAIPClient",
    "ReceiptResponse",
    "ReceiptVerifyResponse",
    "generate_merge_receipt",
    "generate_schema_evolution_receipt",
    "generate_write_receipt",
    "hash_receipt_payload",
]

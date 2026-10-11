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

"""MLflow plugin for MAIP receipt generation."""

__version__ = "1.1.0"

from mlflow_maip.client import MAIPClient
from mlflow_maip.config import MAIPConfig
from mlflow_maip.receipts import generate_receipt_from_run, hash_receipt_payload
from mlflow_maip.schemas import MLPipelineReceipt, ReceiptResponse, ReceiptVerifyResponse

__all__ = [
    "MAIPClient",
    "MAIPConfig",
    "generate_receipt_from_run",
    "hash_receipt_payload",
    "MLPipelineReceipt",
    "ReceiptResponse",
    "ReceiptVerifyResponse",
]

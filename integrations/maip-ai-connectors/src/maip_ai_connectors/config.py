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

"""Configuration management for the maip-ai-connectors package.

All settings can be controlled via environment variables prefixed with ``MAIP_``.
"""

from __future__ import annotations

import os

from pydantic import BaseModel, Field, model_validator


class MAIPConfig(BaseModel):
    """Configuration for MAIP AI connector integrations.

    Attributes:
        api_url: Base URL of the MAIP API.
        api_key: API key used for authentication (X-API-Key header).
        tenant_id: Optional legacy metadata; never used to authorize requests.
        agent_id: Agent identifier for the calling service or AI agent.
        auto_receipt: When ``True``, receipts are submitted automatically on event completion.
        verify_ssl: Whether to verify TLS certificates when contacting the API.
        timeout: HTTP request timeout in seconds.
        max_retries: Maximum number of retry attempts for transient failures.
        fire_and_forget: When ``True``, receipt submission runs in background without blocking.
    """

    api_url: str = Field(
        default_factory=lambda: os.environ.get(
            "MAIP_API_URL",
            "https://api.truthlocks.com/v1",
        ),
    )
    api_key: str = Field(default_factory=lambda: os.environ.get("MAIP_API_KEY", ""))
    tenant_id: str = Field(default_factory=lambda: os.environ.get("MAIP_TENANT_ID", ""))
    agent_id: str = Field(default_factory=lambda: os.environ.get("MAIP_AGENT_ID", ""))
    auto_receipt: bool = Field(default=True)
    verify_ssl: bool = Field(default=True)
    timeout: float = Field(default=30.0, gt=0)
    max_retries: int = Field(default=3, ge=0, le=10)
    fire_and_forget: bool = Field(default=True)

    bearer_token: str = Field(default="")

    @model_validator(mode="after")
    def select_environment(self):
        if "api_url" not in self.model_fields_set and not os.environ.get("MAIP_API_URL") and self.api_key.startswith("tl_test_"):
            self.api_url = "https://sandbox-api.truthlocks.com/v1"
        return self

# Copyright 2026 Truthlocks Inc.
# Licensed under the Apache License, Version 2.0

"""MAIP SDK client for interacting with the Machine Agent Identity Protocol API."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Optional
from urllib.parse import quote

import httpx

from truthlocks_maip.errors import (
    LimitExceededError,
    MaipError,
    NotFoundError,
    UnauthorizedError,
)
from truthlocks_maip.types import (
    Agent,
    AgentStatus,
    CheckGuardrailsRequest,
    ComputeTrustScoreRequest,
    CreateAgentRequest,
    CreateSessionRequest,
    Delegation,
    ExecuteOrchestrationRequest,
    GuardrailResult,
    ListResponse,
    OfferDelegationRequest,
    Orchestration,
    Session,
    TrustScore,
)

DEFAULT_BASE_URL = "https://api.truthlocks.com"
DEFAULT_TIMEOUT = 30.0


class MaipClient:
    """MAIP SDK client.

    Supports both the hosted Truthlocks API and self-hosted deployments
    by configuring the ``base_url`` parameter.

    Example::

        from truthlocks_maip import MaipClient

        client = MaipClient(api_key="your-api-key")

        agent = client.register_agent(CreateAgentRequest(
            name="my-agent",
            scope=Scope(actions=["read"], resources=["*"]),
            public_key="base64-encoded-public-key",
        ))
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        if not api_key:
            raise MaipError("api_key is required")

        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "truthlocks-maip-python/0.1.0",
            },
            timeout=timeout,
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> MaipClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # -------------------------------------------------------------------------
    # Agent Management
    # -------------------------------------------------------------------------

    def register_agent(self, request: CreateAgentRequest) -> dict[str, Any]:
        """Register a new agent identity."""
        return self._post("/v1/agents", self._to_api_dict(request))

    def list_agents(
        self,
        status: Optional[AgentStatus] = None,
        offset: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> dict[str, Any]:
        """List agents with optional filters."""
        params: dict[str, Any] = {}
        if status is not None:
            params["status"] = status.value
        if offset is not None:
            params["offset"] = offset
        if limit is not None:
            params["limit"] = limit
        return self._get("/v1/agents", params=params)

    def get_agent(self, agent_id: str) -> dict[str, Any]:
        """Retrieve a single agent by ID."""
        return self._get(f"/v1/agents/{quote(agent_id, safe='')}")

    def suspend_agent(self, agent_id: str) -> dict[str, Any]:
        """Suspend an active agent."""
        return self._post(
            f"/v1/agents/{quote(agent_id, safe='')}/suspend", {}
        )

    def revoke_agent(self, agent_id: str) -> dict[str, Any]:
        """Permanently revoke an agent identity."""
        return self._post(
            f"/v1/agents/{quote(agent_id, safe='')}/revoke", {}
        )

    # -------------------------------------------------------------------------
    # Session Management
    # -------------------------------------------------------------------------

    def create_session(self, request: CreateSessionRequest) -> dict[str, Any]:
        """Create a new authenticated session for an agent."""
        return self._post("/v1/sessions", self._to_api_dict(request))

    def terminate_session(self, session_id: str) -> dict[str, Any]:
        """Terminate an active session."""
        return self._post(
            f"/v1/sessions/{quote(session_id, safe='')}/terminate", {}
        )

    # -------------------------------------------------------------------------
    # Trust
    # -------------------------------------------------------------------------

    def get_trust_score(self, agent_id: str) -> dict[str, Any]:
        """Get the current trust score for an agent."""
        return self._get(
            f"/v1/agents/{quote(agent_id, safe='')}/trust-score"
        )

    def compute_trust_score(
        self, request: ComputeTrustScoreRequest
    ) -> dict[str, Any]:
        """Compute a fresh trust score for an agent."""
        agent_id = request.agent_id
        return self._post(
            f"/v1/agents/{quote(agent_id, safe='')}/trust-score/compute",
            self._to_api_dict(request),
        )

    # -------------------------------------------------------------------------
    # Delegation
    # -------------------------------------------------------------------------

    def offer_delegation(
        self, request: OfferDelegationRequest
    ) -> dict[str, Any]:
        """Offer a trust delegation from one agent to another."""
        return self._post("/v1/delegations", self._to_api_dict(request))

    def accept_delegation(self, delegation_id: str) -> dict[str, Any]:
        """Accept an offered delegation."""
        return self._post(
            f"/v1/delegations/{quote(delegation_id, safe='')}/accept", {}
        )

    # -------------------------------------------------------------------------
    # Orchestration
    # -------------------------------------------------------------------------

    def execute_orchestration(
        self, request: ExecuteOrchestrationRequest
    ) -> dict[str, Any]:
        """Execute a multi-agent orchestration."""
        return self._post("/v1/orchestrations", self._to_api_dict(request))

    # -------------------------------------------------------------------------
    # Guardrails
    # -------------------------------------------------------------------------

    def check_guardrails(
        self, request: CheckGuardrailsRequest
    ) -> dict[str, Any]:
        """Check guardrails before performing an action."""
        return self._post("/v1/guardrails/check", self._to_api_dict(request))

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _to_api_dict(obj: Any) -> dict[str, Any]:
        """Convert a dataclass to a dict with camelCase keys for the API."""
        raw = asdict(obj)
        return MaipClient._snake_to_camel_dict(raw)

    @staticmethod
    def _snake_to_camel(name: str) -> str:
        parts = name.split("_")
        return parts[0] + "".join(p.capitalize() for p in parts[1:])

    @staticmethod
    def _snake_to_camel_dict(d: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in d.items():
            camel_key = MaipClient._snake_to_camel(key)
            if isinstance(value, dict):
                result[camel_key] = MaipClient._snake_to_camel_dict(value)
            elif value is not None:
                result[camel_key] = value
        return result

    def _get(
        self, path: str, params: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        try:
            response = self._client.get(path, params=params)
            self._raise_for_status(response)
            return response.json()  # type: ignore[no-any-return]
        except httpx.HTTPError as exc:
            raise MaipError(f"Request failed: {exc}") from exc

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(path, json=body)
            self._raise_for_status(response)
            return response.json()  # type: ignore[no-any-return]
        except httpx.HTTPError as exc:
            raise MaipError(f"Request failed: {exc}") from exc

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.is_success:
            return

        try:
            error_body = response.json()
            message = error_body.get("message", f"HTTP {response.status_code}")
        except Exception:
            message = f"HTTP {response.status_code}"

        status = response.status_code
        if status == 401:
            raise UnauthorizedError(message)
        elif status == 404:
            raise NotFoundError("Resource", message)
        elif status == 429:
            retry_after = response.headers.get("Retry-After")
            raise LimitExceededError(
                message,
                retry_after_seconds=int(retry_after) if retry_after else None,
            )
        else:
            raise MaipError(message, status_code=status)

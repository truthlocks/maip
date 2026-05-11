"""Truthlock Python SDK client."""

from __future__ import annotations

import uuid
from typing import Any

import httpx

from .errors import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    ServerError,
    TruthlockError,
    ValidationError,
)
from .models import (
    Attestation, Issuer, IssuerKey, ProofBundle, VerifyResult, Verdict,
    ReceiptEvent, ReceiptType, MintReceiptRequest, ListReceiptsFilter,
)


class TruthlockClient:
    """Client for the Truthlocks verification API.

    Usage::

        from truthlock import TruthlockClient

        client = TruthlockClient(api_key="your-api-key")

        # Mint an attestation
        att = client.attestations.mint(
            issuer_id="iss_...",
            kid="key_...",
            alg="Ed25519",
            payload_b64url="...",
        )

        # Verify an attestation
        result = client.verify.verify_online(attestation_id=att.attestation_id)
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.truthlocks.com",
        environment: str = "production",
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._environment = environment
        self._max_retries = max_retries
        self._http = httpx.Client(
            base_url=self._base_url,
            timeout=timeout,
            headers=self._build_headers(),
        )

        self.issuers = _IssuersResource(self)
        self.keys = _KeysResource(self)
        self.attestations = _AttestationsResource(self)
        self.verify = _VerifyResource(self)
        self.receipts = _ReceiptsResource(self)

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "User-Agent": "truthlock-python/0.1.0",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        return headers

    def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        idempotent: bool = False,
    ) -> Any:
        headers: dict[str, str] = {}
        if idempotent:
            headers["Idempotency-Key"] = str(uuid.uuid4())

        attempts = 0
        last_error: Exception | None = None

        while attempts <= self._max_retries:
            try:
                resp = self._http.request(
                    method,
                    path,
                    json=json,
                    params=params,
                    headers=headers,
                )
                return self._handle_response(resp)
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_error = e
                attempts += 1
                if attempts > self._max_retries:
                    raise TruthlockError(f"Request failed after {self._max_retries} retries: {e}")

        raise TruthlockError(f"Request failed: {last_error}")

    def _handle_response(self, resp: httpx.Response) -> Any:
        if resp.status_code == 204:
            return None

        if 200 <= resp.status_code < 300:
            return resp.json()

        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        msg = body.get("message", resp.text[:200])
        code = body.get("code", "")

        if resp.status_code in (401, 403):
            raise AuthenticationError(msg, status_code=resp.status_code, error_code=code)
        if resp.status_code == 404:
            raise NotFoundError(msg, status_code=404, error_code=code)
        if resp.status_code in (400, 422):
            raise ValidationError(msg, status_code=resp.status_code, error_code=code, details=body)
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", 0)) or None
            raise RateLimitError(msg, retry_after=retry_after, status_code=429, error_code=code)
        if resp.status_code >= 500:
            raise ServerError(msg, status_code=resp.status_code, error_code=code)

        raise TruthlockError(msg, status_code=resp.status_code, error_code=code)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> TruthlockClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class _IssuersResource:
    def __init__(self, client: TruthlockClient):
        self._client = client

    def create(
        self,
        name: str,
        legal_name: str | None = None,
        display_name: str | None = None,
        **kwargs: Any,
    ) -> Issuer:
        data = {"name": name, **kwargs}
        if legal_name:
            data["legal_name"] = legal_name
        if display_name:
            data["display_name"] = display_name
        resp = self._client._request("POST", "/v1/issuers", json=data, idempotent=True)
        return Issuer(
            id=resp["id"],
            name=resp.get("name", name),
            status=resp.get("status", "ACTIVE"),
            did=resp.get("did"),
        )

    def list(self, limit: int = 50, offset: int = 0) -> list[Issuer]:
        resp = self._client._request("GET", "/v1/issuers", params={"limit": limit, "offset": offset})
        items = resp.get("items", resp) if isinstance(resp, dict) else resp
        return [Issuer(id=i["id"], name=i["name"], status=i.get("status", ""), did=i.get("did")) for i in items]

    def get(self, issuer_id: str) -> Issuer:
        resp = self._client._request("GET", f"/v1/issuers/{issuer_id}")
        return Issuer(
            id=resp["id"],
            name=resp["name"],
            status=resp.get("status", ""),
            did=resp.get("did"),
        )

    def trust(self, issuer_id: str) -> dict[str, Any]:
        return self._client._request("POST", f"/v1/issuers/{issuer_id}/trust")


class _KeysResource:
    def __init__(self, client: TruthlockClient):
        self._client = client

    def register(
        self,
        issuer_id: str,
        kid: str,
        alg: str,
        public_key_b64url: str,
        **kwargs: Any,
    ) -> IssuerKey:
        data = {"kid": kid, "alg": alg, "public_key_b64url": public_key_b64url, **kwargs}
        resp = self._client._request("POST", f"/v1/issuers/{issuer_id}/keys", json=data)
        return IssuerKey(
            kid=resp.get("kid", kid),
            issuer_id=issuer_id,
            alg=resp.get("alg", alg),
            public_key=resp.get("public_key", ""),
            status=resp.get("status", "active"),
        )

    def list(self, issuer_id: str) -> list[IssuerKey]:
        resp = self._client._request("GET", f"/v1/issuers/{issuer_id}/keys")
        items = resp.get("items", resp) if isinstance(resp, dict) else resp
        return [
            IssuerKey(
                kid=k["kid"],
                issuer_id=issuer_id,
                alg=k.get("alg", ""),
                public_key=k.get("public_key", ""),
                status=k.get("status", ""),
            )
            for k in items
        ]


class _AttestationsResource:
    def __init__(self, client: TruthlockClient):
        self._client = client

    def mint(
        self,
        issuer_id: str,
        kid: str,
        alg: str,
        payload_b64url: str,
        **kwargs: Any,
    ) -> Attestation:
        data = {
            "issuer_id": issuer_id,
            "kid": kid,
            "alg": alg,
            "payload_b64url": payload_b64url,
            **kwargs,
        }
        resp = self._client._request("POST", "/v1/attestations/mint", json=data, idempotent=True)
        return Attestation(
            attestation_id=resp["attestation_id"],
            issuer_id=issuer_id,
            kid=kid,
            alg=alg,
            status=resp.get("status", "active"),
        )

    def get(self, attestation_id: str) -> Attestation:
        resp = self._client._request("GET", f"/v1/attestations/{attestation_id}")
        return Attestation(
            attestation_id=resp.get("attestation_id", resp.get("id", attestation_id)),
            issuer_id=resp.get("issuer_id", ""),
            kid=resp.get("kid", ""),
            alg=resp.get("alg", ""),
            status=resp.get("status", ""),
            metadata=resp.get("metadata", {}),
        )

    def list(self, limit: int = 50, offset: int = 0) -> list[Attestation]:
        resp = self._client._request(
            "GET", "/v1/attestations", params={"limit": limit, "offset": offset}
        )
        items = resp.get("items", resp) if isinstance(resp, dict) else resp
        return [
            Attestation(
                attestation_id=a.get("attestation_id", a.get("id", "")),
                issuer_id=a.get("issuer_id", ""),
                kid=a.get("kid", ""),
                alg=a.get("alg", ""),
                status=a.get("status", ""),
            )
            for a in items
        ]

    def revoke(self, attestation_id: str, reason: str = "") -> dict[str, Any]:
        return self._client._request(
            "POST",
            f"/v1/attestations/{attestation_id}/revoke",
            json={"reason": reason},
        )

    def proof_bundle(self, attestation_id: str) -> ProofBundle:
        resp = self._client._request("GET", f"/v1/attestations/{attestation_id}/proof-bundle")
        return ProofBundle(
            header=resp.get("header", {}),
            attestation=resp.get("attestation", {}),
            proofs=resp.get("proofs", []),
            issuer_certificate=resp.get("issuer_certificate", {}),
            bundle_signature=resp.get("bundle_signature", {}),
        )


class _VerifyResource:
    def __init__(self, client: TruthlockClient):
        self._client = client

    def verify_online(
        self,
        attestation_id: str,
        payload_b64url: str | None = None,
    ) -> VerifyResult:
        data: dict[str, Any] = {"attestation_id": attestation_id}
        if payload_b64url:
            data["payload_b64url"] = payload_b64url
        resp = self._client._request("POST", "/v1/verify", json=data)
        return VerifyResult(
            verdict=Verdict(resp.get("verdict", "unknown")),
            attestation_id=attestation_id,
            issuer_id=resp.get("issuer_id"),
            issued_at=resp.get("issued_at"),
            details=resp.get("details", {}),
        )


class _ReceiptsResource:
    """Receipt lifecycle operations (Ticket 81: Receipt Canonical Event Schema v2)."""

    def __init__(self, client: TruthlockClient):
        self._client = client

    def mint(self, req: MintReceiptRequest, idempotency_key: str | None = None) -> ReceiptEvent:
        """Mint a cryptographically signed, transparency-log-anchored receipt."""
        import dataclasses
        data = dataclasses.asdict(req)
        headers: dict[str, str] = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        resp = self._client._request("POST", "/v1/receipts", json=data, idempotent=True)
        return self._parse_receipt(resp)

    def get(self, receipt_id: str) -> ReceiptEvent:
        """Retrieve a receipt event by ID."""
        resp = self._client._request("GET", f"/v1/receipts/{receipt_id}")
        return self._parse_receipt(resp)

    def list(self, f: ListReceiptsFilter | None = None) -> list[ReceiptEvent]:
        """List receipt events with optional filters."""
        params: dict[str, Any] = {}
        if f:
            if f.receipt_type:
                params["receipt_type"] = f.receipt_type
            if f.issuer_id:
                params["issuer_id"] = f.issuer_id
            if f.status:
                params["status"] = f.status
            params["limit"] = f.limit
            params["offset"] = f.offset
        resp = self._client._request("GET", "/v1/receipts", params=params)
        items = resp.get("items", []) if isinstance(resp, dict) else resp
        return [self._parse_receipt(r) for r in items]

    def revoke(self, receipt_id: str, reason: str = "") -> ReceiptEvent:
        """Revoke a receipt event."""
        resp = self._client._request(
            "POST",
            f"/v1/receipts/{receipt_id}/revoke",
            json={"reason": reason} if reason else {},
            idempotent=True,
        )
        return self._parse_receipt(resp)

    def list_types(self) -> list[ReceiptType]:
        """List all active receipt type families."""
        resp = self._client._request("GET", "/v1/receipt-types")
        items = resp.get("items", []) if isinstance(resp, dict) else resp
        return [
            ReceiptType(
                id=rt["id"],
                name=rt["name"],
                display_name=rt.get("display_name", rt["name"]),
                version=rt.get("version", "1.0.0"),
                status=rt.get("status", "active"),
                schema=rt.get("schema", {}),
                description=rt.get("description"),
                created_at=rt.get("created_at"),
            )
            for rt in items
        ]

    def get_type(self, name: str) -> ReceiptType:
        """Get a specific receipt type. Use 'name@version' to pin a version."""
        resp = self._client._request("GET", f"/v1/receipt-types/{name}")
        return ReceiptType(
            id=resp["id"],
            name=resp["name"],
            display_name=resp.get("display_name", resp["name"]),
            version=resp.get("version", "1.0.0"),
            status=resp.get("status", "active"),
            schema=resp.get("schema", {}),
            description=resp.get("description"),
            created_at=resp.get("created_at"),
        )

    def get_proof_bundle(self, receipt_id: str) -> dict[str, Any]:
        """Get the proof bundle for offline verification."""
        return self._client._request("GET", f"/v1/receipts/{receipt_id}/proof-bundle")

    def verify(self, receipt_id: str) -> dict[str, Any]:
        """Verify a receipt. Returns verdict: VALID|REVOKED|INVALID_SIGNATURE|KEY_COMPROMISED|NOT_FOUND"""
        return self._client._request("POST", "/v1/receipts/verify", json={"receipt_id": receipt_id})

    def search(self, **kwargs: Any) -> dict[str, Any]:
        """Search receipts. Pass q=, receipt_type=, status=, from_date=, to_date=, limit=, offset=."""
        return self._client._request("POST", "/v1/receipts/search", json=kwargs)

    def export(self, format: str = "json", filters: dict[str, Any] | None = None) -> dict[str, Any]:
        """Queue a bulk export. Returns immediately; poll get_export() for download_url."""
        return self._client._request("POST", "/v1/receipts/export", json={"format": format, "filters": filters or {}}, idempotent=True)

    def get_export(self, export_id: str) -> dict[str, Any]:
        """Get status and download_url of an export job."""
        return self._client._request("GET", f"/v1/receipts/exports/{export_id}")

    def redact(self, receipt_id: str) -> dict[str, Any]:
        """Permanently redact a receipt payload. Cryptographic proof is preserved."""
        return self._client._request("POST", f"/v1/receipts/{receipt_id}/redact", json={}, idempotent=True)

    def _parse_receipt(self, resp: dict[str, Any]) -> ReceiptEvent:
        return ReceiptEvent(
            receipt_id=resp["receipt_id"],
            receipt_type=resp["receipt_type"],
            receipt_version=resp.get("receipt_version", "1.0.0"),
            status=resp.get("status", "active"),
            issued_at=resp.get("issued_at", ""),
            tenant_id=resp.get("tenant_id", ""),
            issuer_id=resp.get("issuer_id", ""),
            payload_hash=resp.get("payload_hash", ""),
            signature=resp.get("signature", {}),
            log=resp.get("log", {}),
        )

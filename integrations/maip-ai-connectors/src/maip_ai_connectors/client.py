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

"""Receipt transport with explicit delivery results and no automatic write replay."""
from __future__ import annotations
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlsplit, urlunsplit
import httpx
from pydantic import BaseModel
from maip_ai_connectors.config import MAIPConfig
from maip_ai_connectors.exceptions import MAIPAuthError, MAIPConnectionError, MAIPError, MAIPNotFoundError, MAIPValidationError
from maip_ai_connectors.schemas import ReceiptResponse, ReceiptVerifyResponse

logger = logging.getLogger(__name__)

class MAIPClient:
    def __init__(self, config: MAIPConfig | None = None) -> None:
        self._config = config or MAIPConfig()
        self._client: httpx.AsyncClient | None = None
        self._background_tasks: set[asyncio.Task] = set()
        self.submitted_receipts: list[ReceiptResponse] = []
        self._delivery_errors: list[Exception] = []

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            cfg = self._config
            bearer = getattr(cfg, "bearer_token", "")
            if bool(cfg.api_key) == bool(bearer):
                raise MAIPAuthError("Configure exactly one workspace API key or bearer token")
            parsed = urlsplit(cfg.api_url)
            if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise MAIPValidationError("Invalid MAIP API base URL")
            path = parsed.path.rstrip("/")
            if path in ("/v1/machine-identity", "/maip/v1"):
                path = "/v1"
            if path not in ("", "/v1"):
                raise MAIPValidationError("API URL must be an origin or end in /v1")
            base = urlunsplit((parsed.scheme, parsed.netloc, "/v1/", "", ""))
            headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "maip-ai-connectors/1.1.0"}
            headers.update({"Authorization": "Bearer " + bearer} if bearer else {"X-API-Key": cfg.api_key})
            self._client = httpx.AsyncClient(base_url=base, headers=headers, verify=cfg.verify_ssl, timeout=cfg.timeout, follow_redirects=False)
        return self._client

    async def flush(self) -> list[ReceiptResponse]:
        tasks = list(self._background_tasks)
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            self._background_tasks.difference_update(tasks)
            for result in results:
                if isinstance(result, BaseException):
                    raise MAIPError("A background receipt was not confirmed; inspect the cause before retrying") from result
        if self._delivery_errors:
            error = self._delivery_errors.pop(0)
            raise MAIPError("A receipt was not confirmed; inspect the cause before retrying") from error
        return list(self.submitted_receipts)

    async def close(self) -> None:
        try:
            await self.flush()
        finally:
            if self._client is not None and not self._client.is_closed:
                await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()

    async def _request(self, method: str, path: str, *, json: dict | None = None, params: dict | None = None):
        if not path.startswith("/") or path.startswith("//") or ".." in path:
            raise MAIPValidationError("Invalid API resource path")
        attempts = 1 + (self._config.max_retries if method in ("GET", "HEAD") else 0)
        client = self._get_client()
        for attempt in range(attempts):
            try:
                response = await client.request(method, path.lstrip("/"), json=json, params=params)
            except httpx.TransportError as error:
                if attempt + 1 == attempts:
                    raise MAIPConnectionError("Request failed; a write may have succeeded and was not automatically replayed") from error
            else:
                if response.status_code not in (429, 502, 503, 504) or attempt + 1 == attempts:
                    self._raise_for_status(response)
                    try:
                        return response.json()
                    except ValueError as error:
                        raise MAIPError("API returned malformed JSON") from error
            await asyncio.sleep(min(0.5 * (2 ** attempt), 8))
        raise MAIPConnectionError("Request failed")

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.is_success:
            return
        status = response.status_code
        if status in (401, 403):
            raise MAIPAuthError("Authentication failed or permission denied")
        if status == 404:
            raise MAIPNotFoundError("Receipt or agent not found in this workspace")
        if status in (400, 409, 422):
            raise MAIPValidationError("Validation error: check agent, managed signing key and receipt fields")
        raise MAIPError(f"MAIP API returned HTTP {status}", status_code=status)

    async def create_receipt(self, receipt: BaseModel) -> ReceiptResponse:
        metadata = receipt.model_dump(mode="json")
        agent_id = metadata.get("agent_id") or self._config.agent_id
        if not agent_id:
            raise MAIPValidationError("agent_id is required; register an agent before submitting receipts")
        if self._config.agent_id and agent_id != self._config.agent_id:
            raise MAIPValidationError("Receipt agent_id differs from configured agent")
        local_type = metadata.get("receipt_type", "action")
        wire_type = local_type if local_type in {"genesis", "delegation", "action", "revocation", "data.attestation", "model.attestation", "compliance", "truth.claim", "truth.verification"} else "action"
        body = {"agent_id": agent_id, "receipt_type": wire_type, "action": local_type, "purpose": "integration evidence", "metadata": metadata}
        if metadata.get("prompt_hash"):
            body["inputs_hash"] = metadata["prompt_hash"]
        if metadata.get("completion_hash"):
            body["outputs_hash"] = metadata["completion_hash"]
        data = await self._request("POST", "/agent-receipts", json=body)
        result = ReceiptResponse.model_validate(data)
        self.submitted_receipts.append(result)
        return result

    def submit_receipt_background(self, receipt: BaseModel):
        """Schedule in an active loop, otherwise submit synchronously and report errors.

        Async callers must await flush()/close() before shutdown. With
        fire_and_forget=False delivery is confirmed before this method returns.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None and getattr(self._config, "fire_and_forget", True):
            task = loop.create_task(self.create_receipt(receipt))
            self._background_tasks.add(task)
            # Observe exceptions to avoid unhandled-task warnings; flush still raises them.
            task.add_done_callback(lambda completed: completed.exception() if not completed.cancelled() else None)
            return task
        async def submit_isolated():
            async with MAIPClient(self._config) as client:
                return await client.create_receipt(receipt)
        def run():
            return asyncio.run(submit_isolated())
        try:
            if loop is None:
                result = run()
            else:
                with ThreadPoolExecutor(max_workers=1) as worker:
                    result = worker.submit(run).result()
        except Exception as error:
            self._delivery_errors.append(error)
            raise
        self.submitted_receipts.append(result)
        return result

    def create_receipt_sync(self, receipt: BaseModel) -> ReceiptResponse:
        """Confirm delivery from synchronous integrations without reusing a closed loop."""
        cfg = self._config.model_copy(update={"fire_and_forget": False})
        result = MAIPClient(cfg).submit_receipt_background(receipt)
        self.submitted_receipts.append(result)
        return result

    async def verify_receipt(self, receipt_id: str) -> ReceiptVerifyResponse:
        data = await self._request("GET", f"/agent-receipts/verify/{quote(receipt_id, safe='')}")
        return ReceiptVerifyResponse.model_validate(data)

    async def get_receipt(self, receipt_id: str) -> ReceiptResponse:
        data = await self._request("GET", f"/agent-receipts/{quote(receipt_id, safe='')}")
        return ReceiptResponse.model_validate(data)

    async def list_receipts(self, *, agent_id: str | None = None, receipt_type: str | None = None) -> list[ReceiptResponse]:
        selected = agent_id or self._config.agent_id
        if not selected:
            raise MAIPValidationError("agent_id is required for receipt listing")
        data = await self._request("GET", f"/agent-receipts/agent/{quote(selected, safe='')}", params={"limit": 100})
        items = data if isinstance(data, list) else data.get("receipts", [])
        if not isinstance(items, list):
            raise MAIPError("Invalid receipt list response")
        return [ReceiptResponse.model_validate(item) for item in items if not receipt_type or item.get("receipt_type") == receipt_type or item.get("metadata", {}).get("receipt_type") == receipt_type]

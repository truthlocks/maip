"""Receipt API adapter using the maintained shared transport.

Filtered lists inspect up to the latest 100 receipts for the configured agent.
"""
from __future__ import annotations
from maip_ai_connectors.client import MAIPClient as BaseMAIPClient
from .config import MAIPConfig

class MAIPClient(BaseMAIPClient):
    def __init__(self, config: MAIPConfig | None = None):
        super().__init__(config or MAIPConfig())

    async def list_receipts(self, run_id: str):
        items = await super().list_receipts()
        return [r for r in items if r.metadata.get("run_id") == run_id]

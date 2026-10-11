"""Receipt API adapter using the maintained shared transport.

Filtered lists inspect up to the latest 100 receipts for the configured agent.
"""
from __future__ import annotations
from maip_ai_connectors.client import MAIPClient as BaseMAIPClient
from .config import MAIPConfig

class MAIPClient(BaseMAIPClient):
    def __init__(self, config: MAIPConfig | None = None):
        super().__init__(config or MAIPConfig())

    async def list_receipts(self, *, file_path: str | None = None, stage_name: str | None = None):
        items = await super().list_receipts()
        return [r for r in items if (not file_path or r.metadata.get("file_path") == file_path) and (not stage_name or r.metadata.get("stage_name") == stage_name)]

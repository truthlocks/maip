"""Configuration shared with the maintained receipt transport."""
import os
from pydantic import Field
from maip_ai_connectors.config import MAIPConfig as BaseMAIPConfig

class DeltaMAIPConfig(BaseMAIPConfig):
    auto_receipt: bool = Field(default_factory=lambda: os.environ.get("DELTA_MAIP_AUTO_RECEIPT", "true").lower() in ("true", "1", "yes"))
    poll_interval: float = Field(default=5.0, gt=0)

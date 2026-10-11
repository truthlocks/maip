"""Configuration shared with the maintained receipt transport."""
import os
from pydantic import Field
from maip_ai_connectors.config import MAIPConfig as BaseMAIPConfig

class MAIPConfig(BaseMAIPConfig):
    auto_receipt: bool = Field(default_factory=lambda: os.environ.get("MLFLOW_MAIP_AUTO_RECEIPT", "true").lower() in ("true", "1", "yes"))
    receipt_type: str = "ml_pipeline_receipt"

# Copyright 2026 Truthlocks Inc. — Apache 2.0
"""Truthlocks MAIP integration for LlamaIndex.

Usage::

    from truthlocks_llamaindex import MAIPLlamaIndexHandler
    handler = MAIPLlamaIndexHandler()
"""

__version__ = "1.1.0"

from maip_ai_connectors.llamaindex import MAIPLlamaIndexHandler, MAIPQueryEngineWrapper

__all__ = ["MAIPLlamaIndexHandler", "MAIPQueryEngineWrapper"]

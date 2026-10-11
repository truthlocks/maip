# Copyright 2026 Truthlocks Inc. — Apache 2.0
"""Truthlocks MAIP integration for LangChain.

Usage::

    from truthlocks_langchain import MAIPCallbackHandler
    handler = MAIPCallbackHandler()
    chain.invoke(input, config={"callbacks": [handler]})
"""

__version__ = "1.1.0"

from maip_ai_connectors.langchain import (
    MAIPCallbackHandler,
    MAIPRunnableWrapper,
    MAIPTracer,
)

__all__ = ["MAIPCallbackHandler", "MAIPRunnableWrapper", "MAIPTracer"]

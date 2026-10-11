# Copyright 2026 Truthlocks Inc. — Apache 2.0
"""Truthlocks MAIP wrapper for OpenAI.

Usage::

    from truthlocks_openai import MAIPOpenAIWrapper
    wrapper = MAIPOpenAIWrapper()
    response, receipt = wrapper.chat_completions_create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello"}],
    )
"""

__version__ = "1.1.0"

from maip_ai_connectors.providers.openai import MAIPOpenAIWrapper

__all__ = ["MAIPOpenAIWrapper"]

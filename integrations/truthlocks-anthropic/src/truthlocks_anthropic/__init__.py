# Copyright 2026 Truthlocks Inc. — Apache 2.0
"""Truthlocks MAIP wrapper for Anthropic.

Usage::

    from truthlocks_anthropic import MAIPAnthropicWrapper
    wrapper = MAIPAnthropicWrapper()
    message, receipt = wrapper.messages_create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": "Hello"}],
    )
"""

__version__ = "1.1.0"

from maip_ai_connectors.providers.anthropic import MAIPAnthropicWrapper

__all__ = ["MAIPAnthropicWrapper"]

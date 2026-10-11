# Copyright 2026 Truthlocks Inc. — Apache 2.0
"""Truthlocks MAIP integration for AutoGen.

Usage::

    from truthlocks_autogen import MAIPAutoGenHook
    hook = MAIPAutoGenHook()
"""

__version__ = "1.1.0"

from maip_ai_connectors.autogen import MAIPAutoGenHook, MAIPConversableAgentWrapper

__all__ = ["MAIPAutoGenHook", "MAIPConversableAgentWrapper"]

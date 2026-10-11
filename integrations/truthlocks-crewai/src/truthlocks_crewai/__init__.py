# Copyright 2026 Truthlocks Inc. — Apache 2.0
"""Truthlocks MAIP integration for CrewAI.

Usage::

    from truthlocks_crewai import MAIPCrewCallback
    callback = MAIPCrewCallback()
"""

__version__ = "1.1.0"

from maip_ai_connectors.crewai import MAIPCrewCallback, MAIPCrewWrapper

__all__ = ["MAIPCrewCallback", "MAIPCrewWrapper"]

"""
Observability utilities for TutorDex.

Provides shared logging, metrics, and exception handling utilities.
"""

from __future__ import annotations

from .exception_handler import swallow_exception

__all__ = ["swallow_exception"]

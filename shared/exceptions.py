"""
Custom exception classes for TutorDex.

Provides specific exception types for better error handling and debugging.
Use these instead of generic Exception to enable targeted error handling.
"""

from __future__ import annotations


class TutorDexError(Exception):
    """Base exception for all TutorDex errors"""
    pass


class DataAccessError(TutorDexError):
    """Database/API access failures (Supabase, Redis, etc.)"""
    pass


class ValidationError(TutorDexError):
    """Data validation failures"""
    pass


class ExternalServiceError(TutorDexError):
    """External API failures (LLM, Telegram, Nominatim, etc.)"""
    pass


class ConfigurationError(TutorDexError):
    """Configuration or environment variable errors"""
    pass


class AuthenticationError(TutorDexError):
    """Authentication or authorization failures"""
    pass


class RateLimitError(TutorDexError):
    """Rate limit exceeded errors"""
    pass

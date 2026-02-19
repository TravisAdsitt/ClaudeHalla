"""Mockable UTC time utility."""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return the current UTC datetime (timezone-aware). Injectable for test mocking."""
    return datetime.now(timezone.utc)


def utcnow_iso() -> str:
    """Return the current UTC datetime as an ISO-8601 string."""
    return utcnow().isoformat()

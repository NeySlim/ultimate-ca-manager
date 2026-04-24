"""Datetime utilities for UTC-safe operations with SQLite.

SQLite stores datetimes without timezone info (naive). All datetimes
in this codebase represent UTC. This module provides a utc_now()
function that uses the non-deprecated datetime.now(timezone.utc) API
but returns a naive datetime for DB compatibility.
"""
from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return current UTC time as a naive datetime.

    Uses the non-deprecated ``datetime.now(timezone.utc)`` internally,
    then strips tzinfo so the result is comparable with naive datetimes
    stored in SQLite via SQLAlchemy.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_isoformat(dt):
    """Return an ISO 8601 UTC string ending in 'Z', or None.

    Handles both naive-UTC datetimes (from SQLAlchemy/utc_now) and
    timezone-aware datetimes (from the cryptography library etc.).
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.isoformat() + 'Z'
    from datetime import timezone
    return dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')

from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return naive UTC, matching the timestamp convention in existing DB models."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def as_naive_utc(value: datetime) -> datetime:
    """Normalize an aware timestamp to UTC without changing existing naive values."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def utc_iso(value: datetime | None) -> str | None:
    """Serialize a DB timestamp as unambiguous UTC for API/browser clients."""
    return f'{as_naive_utc(value).isoformat()}Z' if value else None

"""
Human duration strings ("24h", "7d", "365d") → seconds.

UI placeholders advertise duration suffixes for TTL fields, so the backend
must accept them at the API boundary and normalize to integer seconds for
storage. Bare numbers stay valid (seconds) for API compatibility.
"""
import math
import re

_DURATION_RE = re.compile(r'^(\d+)\s*([smhdwySMHDWY]?)$')

_UNIT_SECONDS = {
    '': 1,
    's': 1,
    'm': 60,
    'h': 3600,
    'd': 86400,
    'w': 604800,
    'y': 31536000,  # 365 days — civil-year convention, leap years ignored
}

_MAX_SECONDS = 2**63 - 1  # signed BIGINT range — larger values overflow the column at commit time


def parse_duration_seconds(value, *, field='duration') -> int:
    """
    Parse a TTL/duration value to integer seconds.

    Accepts int/float (already seconds), numeric strings ("86400"), and
    unit-suffixed strings ("30m", "24h", "7d", "2w", "1y"; case-insensitive,
    optional space before the unit).

    Raises ValueError carrying the field name and the accepted formats on
    anything else (unknown units, negatives, non-finite or fractional
    floats, values beyond the BIGINT column range, empty, non-scalar
    types), so API handlers surface a clean 400 instead of a bare int()
    traceback or a 500 from the database.
    """
    hint = "use seconds or a duration like '24h', '7d', '365d' (s/m/h/d/w/y)"
    seconds = None
    if isinstance(value, bool):
        # bool is an int subclass — a JSON true/false is never a TTL
        pass
    elif isinstance(value, float) and not math.isfinite(value):
        pass
    elif isinstance(value, (int, float)):
        seconds = int(value)
        if seconds != value:  # fractional float — not a whole-second TTL
            seconds = None
    elif isinstance(value, str):
        match = _DURATION_RE.match(value.strip())
        if match:
            seconds = int(match.group(1)) * _UNIT_SECONDS[match.group(2).lower()]
    if seconds is None or seconds < 0 or seconds > _MAX_SECONDS:
        raise ValueError(f"Invalid {field}: {value!r} — {hint}")
    return seconds

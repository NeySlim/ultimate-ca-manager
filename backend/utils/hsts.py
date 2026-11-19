"""HSTS (HTTP Strict-Transport-Security) header builder.

Defaults match the historic hardcoded value (`max-age=31536000; includeSubDomains`)
so existing deployments keep the same posture unless an operator opts out.

Resolution order per setting (the same pattern as key-recovery dual control):
  env override (`/etc/ucm/ucm.env`) > DB SystemConfig > baked-in default.

HSTS can be disabled entirely (for instances serving self-signed certs during
setup — see issue #154) either by `hsts_enabled=false` in SystemConfig or by
`UCM_HSTS_ENABLED=0` in the environment.

The builder never raises when the DB / SystemConfig table is unavailable (boot
before init, safe mode): a setting the environment does not fix and the
database cannot give means no header at all.
"""
import os

_DEFAULT_MAX_AGE = 31536000  # 1 year
_DISABLED = ('false', '0', 'no', 'off')


def _is_disabled(val) -> bool:
    return str(val).strip().lower() in _DISABLED


def _env_override(key: str) -> str | None:
    """Return the env override value for a canonical key, or None."""
    val = os.environ.get(key.upper())
    if val is None:
        val = os.environ.get(key.lower())
    return val


def hsts_env_locked() -> list[str]:
    """Names of the HSTS settings currently forced by env vars.

    A non-empty list means the Settings toggle for those keys is read-only
    (the env var wins over the DB). Surfaces to the UI so it can show a
    "locked by environment" badge — same UX as key_recovery_dual_control_locked.
    """
    locked = []
    if _env_override('ucm_hsts_enabled') is not None:
        locked.append('hsts_enabled')
    if _env_override('ucm_hsts_include_subdomains') is not None:
        locked.append('hsts_include_subdomains')
    if _env_override('ucm_hsts_max_age') is not None:
        locked.append('hsts_max_age')
    return locked


# A setting the database could not give (locked, unavailable, table missing)
_UNREADABLE = object()


def _cfg_value(key: str, unreadable=None):
    """Read a SystemConfig value, tolerating any DB error / missing table."""
    try:
        from models import SystemConfig
        row = SystemConfig.query.filter_by(key=key).first()
        return row.value if row else None
    except Exception:
        return unreadable


def _setting(key: str):
    """The env override, else the database value (None when absent,
    ``_UNREADABLE`` when the database could not answer)."""
    env = _env_override(f'ucm_{key}')
    if env is not None:
        return env
    return _cfg_value(key, unreadable=_UNREADABLE)


def _enabled(val) -> bool:
    return True if val is None else not _is_disabled(val)


def _max_age(src) -> int:
    if src is None:
        return _DEFAULT_MAX_AGE
    try:
        n = int(str(src).strip())
    except (TypeError, ValueError):
        return _DEFAULT_MAX_AGE
    return max(0, n)


def build_hsts_header() -> str | None:
    """The HSTS header value, or None when HSTS is off or any of its three
    settings the environment does not fix cannot be read from the database."""
    # Unread, it may be off: one response without HSTS beats pinning a year by mistake
    enabled, subdomains, max_age = (
        _setting(k) for k in ('hsts_enabled', 'hsts_include_subdomains', 'hsts_max_age'))
    if _UNREADABLE in (enabled, subdomains, max_age) or not _enabled(enabled):
        return None
    parts = [f'max-age={_max_age(max_age)}']
    if _enabled(subdomains):
        parts.append('includeSubDomains')
    return '; '.join(parts)

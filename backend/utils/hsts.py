"""HSTS (HTTP Strict-Transport-Security) header builder.

Defaults match the historic hardcoded value (`max-age=31536000; includeSubDomains`)
so existing deployments keep the same posture unless an operator opts out.

Resolution order per setting (the same pattern as key-recovery dual control):
  env override (`/etc/ucm/ucm.env`) > DB SystemConfig > baked-in default.

HSTS can be disabled entirely (for instances serving self-signed certs during
setup — see issue #154) either by `hsts_enabled=false` in SystemConfig or by
`UCM_HSTS_ENABLED=0` in the environment.

All three helpers are DB-tolerant: they never raise if the DB / SystemConfig
table is unavailable (e.g. during boot before init, under safe mode), they just
fall back to defaults.
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


def _env_bool(key: str, default: bool) -> bool:
    """Read a boolean env override (canonical UPPER + lower), else default."""
    val = os.environ.get(key.upper()) or os.environ.get(key.lower())
    if val is None:
        return default
    return not _is_disabled(val)


def _cfg_value(key: str):
    """Read a SystemConfig value, tolerating any DB error / missing table."""
    try:
        from models import SystemConfig
        row = SystemConfig.query.filter_by(key=key).first()
        return row.value if row else None
    except Exception:
        return None


def hsts_enabled() -> bool:
    """Whether HSTS should be emitted at all."""
    env = _env_override('ucm_hsts_enabled')
    if env is not None:
        return not _is_disabled(env)
    val = _cfg_value('hsts_enabled')
    if val is None:
        return True
    return not _is_disabled(val)


def hsts_include_subdomains() -> bool:
    """Whether the `includeSubDomains` directive is emitted (when HSTS is on)."""
    env = _env_override('ucm_hsts_include_subdomains')
    if env is not None:
        return not _is_disabled(env)
    val = _cfg_value('hsts_include_subdomains')
    if val is None:
        return True
    return not _is_disabled(val)


def hsts_max_age() -> int:
    """HSTS max-age in seconds (clamped to >= 0)."""
    src = _env_override('ucm_hsts_max_age')
    if src is None:
        src = _cfg_value('hsts_max_age')
    if src is None:
        return _DEFAULT_MAX_AGE
    try:
        n = int(str(src).strip())
    except (TypeError, ValueError):
        return _DEFAULT_MAX_AGE
    return max(0, n)


def build_hsts_header() -> str | None:
    """Return the HSTS header value, or None when HSTS is disabled."""
    if not hsts_enabled():
        return None
    parts = [f'max-age={hsts_max_age()}']
    if hsts_include_subdomains():
        parts.append('includeSubDomains')
    return '; '.join(parts)

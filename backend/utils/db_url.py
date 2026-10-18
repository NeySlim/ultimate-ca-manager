"""Database URLs as SQLAlchemy is given them."""
import os
from typing import Optional

from sqlalchemy.engine import make_url

_POSTGRES_PREFIXES = ('postgresql://', 'postgres://')
_TLS_SSLMODES = ('require', 'verify-ca', 'verify-full')


def sqlalchemy_url(url: str) -> str:
    """Pin a PostgreSQL URL without a driver to psycopg2, the one UCM ships.

    SQLAlchemy 2.1 resolves a bare postgresql:// to psycopg 3. An explicit
    driver and non-PostgreSQL URLs are returned unchanged.
    """
    for prefix in _POSTGRES_PREFIXES:
        if url.startswith(prefix):
            return 'postgresql+psycopg2://' + url[len(prefix):]
    return url


def is_postgres_url(url: str) -> bool:
    """True for every PostgreSQL spelling: postgres://, postgresql://, postgresql+driver://."""
    return sqlalchemy_url(url or '').startswith(('postgresql://', 'postgresql+'))


def _postgres_tcp_setting(url, name, env_name, environ):
    """The value of a libpq setting for a URL that reaches PostgreSQL over TCP,
    '' when unset, None for a Unix socket or another database."""
    try:
        parsed = make_url(str(url))
    except Exception:
        return None
    if not parsed.drivername.startswith('postgres'):
        return None

    def query(key):
        value = parsed.query.get(key)
        return value[0] if isinstance(value, tuple) else value
    host = parsed.host or query('host') or query('hostaddr') or environ.get('PGHOST') \
        or environ.get('PGHOSTADDR')
    if not host or str(host).startswith('/'):
        return None  # Unix socket: neither TLS nor GSSAPI encryption applies
    return query(name) or environ.get(env_name) or ''


def postgres_tls_problem(url, environ=None) -> Optional[str]:
    """Why a PostgreSQL URL would reach its server over TCP without TLS, None when it would not."""
    environ = os.environ if environ is None else environ
    sslmode = _postgres_tcp_setting(url, 'sslmode', 'PGSSLMODE', environ)
    if sslmode is None:
        return None
    sslmode = sslmode or 'prefer'
    return None if sslmode in _TLS_SSLMODES else f'sslmode={sslmode}'


def postgres_gssenc_problem(url, environ=None) -> Optional[str]:
    """A GSSAPI encryption mode other than disable asked for explicitly over TCP, None otherwise."""
    environ = os.environ if environ is None else environ
    mode = _postgres_tcp_setting(url, 'gssencmode', 'PGGSSENCMODE', environ)
    return f'gssencmode={mode}' if mode and mode != 'disable' else None

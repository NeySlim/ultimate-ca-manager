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


def postgres_tls_problem(url, environ=None) -> Optional[str]:
    """Why a PostgreSQL URL would reach its server over TCP without TLS, None when it would not."""
    environ = os.environ if environ is None else environ
    try:
        parsed = make_url(str(url))
    except Exception:
        return None
    if not parsed.drivername.startswith('postgres'):
        return None

    def query(name):
        value = parsed.query.get(name)
        return value[0] if isinstance(value, tuple) else value
    host = parsed.host or query('host') or query('hostaddr') or environ.get('PGHOST') \
        or environ.get('PGHOSTADDR')
    if not host or str(host).startswith('/'):
        return None  # Unix socket: no TLS needed
    sslmode = query('sslmode') or environ.get('PGSSLMODE') or 'prefer'
    return None if sslmode in _TLS_SSLMODES else f'sslmode={sslmode}'

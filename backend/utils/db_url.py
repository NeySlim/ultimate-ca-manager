"""Database URLs as SQLAlchemy is given them."""
import logging
import os
from typing import Optional

from sqlalchemy.engine import make_url

_POSTGRES_PREFIXES = ('postgresql://', 'postgres://')
_PSYCOPG2_PREFIX = 'postgresql+psycopg2://'
_TLS_SSLMODES = ('require', 'verify-ca', 'verify-full')

logger = logging.getLogger(__name__)
_warned_psycopg2 = []


def sqlalchemy_url(url: str) -> str:
    """Pin a PostgreSQL URL without a driver to psycopg 3, which binds parameters on the server.

    An explicit driver and non-PostgreSQL URLs are returned unchanged.
    """
    for prefix in _POSTGRES_PREFIXES:
        if url.startswith(prefix):
            return 'postgresql+psycopg://' + url[len(prefix):]
    if url.startswith(_PSYCOPG2_PREFIX):
        _warn_psycopg2()
    return url


def _warn_psycopg2():
    if not _warned_psycopg2:
        _warned_psycopg2.append(True)
        logger.warning('A PostgreSQL URL names the psycopg2 driver, deprecated and removed in '
                       'the next release: write postgresql:// to use psycopg 3')


def is_postgres_url(url: str) -> bool:
    """True for every PostgreSQL spelling: postgres://, postgresql://, postgresql+driver://."""
    return (url or '').startswith(_POSTGRES_PREFIXES + ('postgresql+',))


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


# Every engine UCM builds reads its URL here: the error scrubber goes with it
from utils.db_errors import install as _install_error_scrubber  # noqa: E402

_install_error_scrubber()

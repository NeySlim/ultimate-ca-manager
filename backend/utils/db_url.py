"""Database URLs as SQLAlchemy is given them."""
import os
from typing import Optional

from sqlalchemy.engine import make_url

# postgresql+psycopg2:// is what older guides wrote: same database, the one driver UCM ships
_PSYCOPG2_PREFIX = 'postgresql+psycopg2://'
_POSTGRES_PREFIXES = ('postgresql://', 'postgres://', _PSYCOPG2_PREFIX)
_TLS_SSLMODES = ('require', 'verify-ca', 'verify-full')
_PREPARE_OFF = ('0', 'none', 'off', 'disable')


def sqlalchemy_url(url: str) -> str:
    """Pin a PostgreSQL URL to psycopg 3, which binds parameters on the server.

    Any other explicit driver, and non-PostgreSQL URLs, are returned unchanged.
    """
    for prefix in _POSTGRES_PREFIXES:
        if url.startswith(prefix):
            return 'postgresql+psycopg://' + url[len(prefix):]
    return url


def log_normalised_scheme(url, log):
    """Say once logging is up that a postgresql+psycopg2:// URL runs on psycopg 3 (scheme only)."""
    if (url or '').startswith(_PSYCOPG2_PREFIX):
        log.info('PostgreSQL URL scheme postgresql+psycopg2:// normalised to postgresql+psycopg://')


def postgres_connect_args(url, environ=None) -> dict:
    """psycopg connection arguments for a PostgreSQL URL: UCM_PG_PREPARE_THRESHOLD sets
    prepare_threshold, and 0, none, off or disable turn prepared statements off."""
    environ = os.environ if environ is None else environ
    raw = (environ.get('UCM_PG_PREPARE_THRESHOLD') or '').strip().lower()
    if not raw or not is_postgres_url(url):
        return {}
    if raw in _PREPARE_OFF:
        return {'prepare_threshold': None}
    if not raw.isdigit():
        raise ValueError(f'UCM_PG_PREPARE_THRESHOLD must be a positive integer or 0, not {raw!r}')
    return {'prepare_threshold': int(raw)}


# Client side: a dead server or a partition is noticed within about a minute, an
# unreachable one refused in ten seconds, data it never acknowledges given up after 30 s
# (the application pool and the leader's lock)
POSTGRES_KEEPALIVE_ARGS = {'keepalives': 1, 'keepalives_idle': 30, 'keepalives_interval': 10,
                           'keepalives_count': 3, 'connect_timeout': 10, 'tcp_user_timeout': 30000}


def postgres_engine_options(url, environ=None) -> dict:
    """Engine options of the application pool on PostgreSQL: each checkout pinged, so a
    connection the server dropped is replaced unseen, and the keepalives above unless the
    URL sets them; postgres_connect_args on top. Empty for another database."""
    if not is_postgres_url(url):
        return {}
    try:
        in_url = set(make_url(str(url)).query)
    except Exception:
        in_url = set()
    args = {k: v for k, v in POSTGRES_KEEPALIVE_ARGS.items() if k not in in_url}
    args.update(postgres_connect_args(url, environ))
    return {'pool_pre_ping': True, 'connect_args': args}


def database_label(url, sqlite_path) -> str:
    """The database a start announces: engine and name, never the address or the password."""
    if not url:
        return f'SQLite, {sqlite_path}'
    if not is_postgres_url(url):
        return 'DATABASE_URL'
    try:
        name = make_url(str(url)).database
    except Exception:
        name = None
    return f'PostgreSQL, database {name}' if name else 'PostgreSQL (DATABASE_URL)'


def is_postgres_url(url: str) -> bool:
    """True for every PostgreSQL spelling: postgres://, postgresql://, postgresql+driver://."""
    return (url or '').startswith(('postgresql://', 'postgres://', 'postgresql+'))


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

"""Settings the gunicorn master reads before the application exists.

mTLS and the WSTEP TLS cap decide how the listening socket is built, which
happens before Flask, SQLAlchemy and the app package are importable. These
reads therefore go straight to the driver, on whichever backend the install
uses: a PostgreSQL install used to find no SQLite file and silently serve a
socket that never asked for a client certificate.
"""
import base64
import os
import ssl
import sys

PEM_HEADER = '-----BEGIN CERTIFICATE-----'
PEM_FOOTER = '-----END CERTIFICATE-----'

# The master blocks on this read, so it must not wait on a dead server.
CONNECT_TIMEOUT_SECONDS = 5


def database_url(data_path: str) -> str:
    """The active database URL, resolved like migration_runner does.

    `DATABASE_PATH` is what the v1 upgrade writes into the service env, so
    reading only `DATA_DIR` looked at a file that install does not have.
    """
    url = os.getenv('DATABASE_URL')
    if url:
        return url
    path = os.getenv('DATABASE_PATH') or os.path.join(data_path, 'ucm.db')
    return 'sqlite:///' + str(path)


def _is_postgres(url: str) -> bool:
    return url.startswith(('postgresql://', 'postgresql+', 'postgres://'))


class BootDatabase:
    """Read-only cursor over the settings tables, on either backend.

    Queries are written with SQLite's ``?`` placeholder and translated.
    """

    def __init__(self, connection, placeholder):
        self._connection = connection
        self._placeholder = placeholder

    def rows(self, sql, params=()):
        cursor = self._connection.cursor()
        cursor.execute(sql.replace('?', self._placeholder), params)
        return cursor.fetchall()

    def one(self, sql, params=()):
        found = self.rows(sql, params)
        return found[0] if found else None

    def close(self):
        try:
            self._connection.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
        return False


def open_boot_database(data_path: str):
    """A connection to the active database, or None when there is none yet."""
    url = database_url(data_path)
    if _is_postgres(url):
        # libpq rejects SQLAlchemy's ``+driver`` suffix. The timeout is what
        # keeps a blackholed server from hanging the gunicorn master, which
        # reads this before any worker forks.
        import psycopg
        _scheme, _, rest = url.partition('://')
        return BootDatabase(
            psycopg.connect('postgresql://' + rest,
                            connect_timeout=CONNECT_TIMEOUT_SECONDS), '%s')

    path = url[len('sqlite:///'):] if url.startswith('sqlite:///') else url
    if not os.path.exists(path):
        return None
    import sqlite3
    return BootDatabase(sqlite3.connect(path), '?')


def _settings(database, keys):
    placeholders = ', '.join('?' for _ in keys)
    rows = database.rows(
        f"SELECT key, value FROM system_config WHERE key IN ({placeholders})",
        tuple(keys))
    return {key: value for key, value in rows}


def wstep_enabled(data_path: str) -> bool:
    """Whether WSTEP is administratively enabled (drives the TLS 1.2 cap)."""
    try:
        database = open_boot_database(data_path)
        if database is None:
            return False
        with database:
            return _settings(database, ('wstep_enabled',)).get(
                'wstep_enabled') == 'true'
    except Exception as e:
        print(f"WSTEP: config load failed, assuming disabled: {e}",
              file=sys.stderr)
        return False


def _decoded_pem(stored):
    """CA certificates are stored base64-wrapped; tolerate raw PEM too."""
    try:
        pem = base64.b64decode(stored).decode('utf-8')
    except Exception:
        pem = stored
    return pem if PEM_HEADER in pem and PEM_FOOTER in pem else None


def client_ca_anchor(database, ca_refid):
    """``(pem, name)`` of the trusted CA alone, or ``(None, None)``.

    It is the only trust anchor (RFC 5280 §6.1): with its ancestors in the
    store, a certificate from a sibling intermediate passed the handshake.
    """
    row = database.one(
        "SELECT crt, descr FROM certificate_authorities WHERE refid = ?",
        (ca_refid,))
    if not row or not row[0]:
        print("mTLS: trusted CA not found in database", file=sys.stderr)
        return None, None

    pem = _decoded_pem(row[0])
    if pem is None:
        print(f"mTLS: CA cert for {ca_refid} is not valid PEM format",
              file=sys.stderr)
        return None, None
    return pem, row[1] or ca_refid


def anchor_client_verification(ctx):
    """Let an intermediate trusted CA end the path: Python 3.13 sets this
    flag by default, older interpreters would refuse every client."""
    ctx.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN


def mtls_client_ca(data_path: str):
    """``(ca_pem, ca_name, required)`` when mTLS is on, else None."""
    database = open_boot_database(data_path)
    if database is None:
        return None
    with database:
        config = _settings(database, (
            'mtls_enabled', 'mtls_required', 'mtls_trusted_ca_id'))
        if config.get('mtls_enabled') != 'true':
            return None
        ca_refid = config.get('mtls_trusted_ca_id')
        if not ca_refid:
            return None
        pem, name = client_ca_anchor(database, ca_refid)
        if pem is None:
            return None
        return pem, name, config.get('mtls_required') == 'true'

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


# The bound HTTPS certificate (services/https_binding.py) and the chain last written with it
HTTPS_BOUND_KEY = 'https_bound_certificate_refid'
HTTPS_CHAIN_KEY = 'https_bound_certificate_chain'
# services/shared_files.HTTPS_GENERATED: the self-signed pair regenerated in HA
HTTPS_GENERATED_FILE = 'https.generated'


class HttpsMaterialError(Exception):
    """The database names an HTTPS certificate this node cannot write; the message is for operators."""


def _missing_table(e):
    """Upgrade: the migrations that create a table run after the master reads it."""
    import sqlite3
    if isinstance(e, sqlite3.OperationalError):
        return str(e).startswith('no such table')
    return getattr(e, 'sqlstate', None) == '42P01'  # psycopg UndefinedTable


def _certificate_text(stored):
    """Certificates are stored base64-wrapped; tolerate raw PEM too."""
    if stored.lstrip().startswith('-----BEGIN'):
        return stored
    try:
        return base64.b64decode(stored).decode('utf-8')
    except Exception:
        return stored


def _first_certificate(pem):
    """The first PEM certificate of ``pem`` without its whitespace, or None."""
    start = pem.find(PEM_HEADER)
    end = pem.find(PEM_FOOTER, start)
    if start < 0 or end < 0:
        return None
    return ''.join(pem[start:end + len(PEM_FOOTER)].split())


def _stored_bytes(stored, context):
    """A column under the master key (``utils.key_codec`` format) as raw bytes."""
    from security.encryption import key_encryption
    from utils.key_codec import load_pem_bytes
    if key_encryption.is_encrypted(stored) and not key_encryption.is_enabled:
        raise HttpsMaterialError(
            f"{context}: its private key is encrypted under the master key, which this node "
            "does not have (master.key or KEY_ENCRYPTION_KEY)")
    try:
        return load_pem_bytes(stored, context=context)
    except ValueError as e:
        raise HttpsMaterialError(str(e)) from None


def _key_text(stored, context):
    if stored.lstrip().startswith('-----BEGIN'):
        return stored  # a column from before keys were stored base64-encoded
    return _stored_bytes(stored, context).decode('utf-8')


def https_material(database):
    """``(cert_pem, key_pem, label, chain_known)`` the database says this node serves, or None.

    The bound certificate comes with the chain last written for it when that chain starts
    with it (``chain_known``), else alone. Raises HttpsMaterialError when unreadable.
    """
    config = _settings(database, (HTTPS_BOUND_KEY, HTTPS_CHAIN_KEY))
    refid = (config.get(HTTPS_BOUND_KEY) or '').strip()
    if refid:
        label = f"bound certificate {refid}"
        row = database.one("SELECT crt, prv FROM certificates WHERE refid = ?", (refid,))
        if not row or not row[0] or not row[1]:
            raise HttpsMaterialError(f"{label}: no certificate or private key in the database")
        leaf = _certificate_text(row[0])
        if _first_certificate(leaf) is None:
            raise HttpsMaterialError(f"{label}: the stored certificate is not PEM")
        key = _key_text(row[1], label)
        chain = config.get(HTTPS_CHAIN_KEY) or ''
        if chain and _first_certificate(chain) == _first_certificate(leaf):
            return chain, key, label, True
        return leaf, key, label, False
    try:
        row = database.one("SELECT content FROM shared_files WHERE name = ?", (HTTPS_GENERATED_FILE,))
    except Exception as e:
        if _missing_table(e):
            return None
        raise
    if not row or not row[0]:
        return None
    import json
    label = "regenerated self-signed certificate"
    pair = json.loads(_stored_bytes(row[0], label))
    return pair['crt'], pair['key'], label, True


def _same_file(path, text):
    try:
        with open(path, encoding='utf-8') as handle:
            return handle.read() == text
    except (OSError, UnicodeDecodeError):
        return False


def _leaf_in_file(path):
    try:
        with open(path, encoding='utf-8') as handle:
            return _first_certificate(handle.read())
    except (OSError, UnicodeDecodeError):
        return None


def _prepare(path, text, mode):
    """A complete temporary file beside ``path``, owned like the files it replaces."""
    import tempfile
    fd, tmp_path = tempfile.mkstemp(prefix='.ucm-https-', suffix='.tmp',
                                    dir=os.path.dirname(path) or '.')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(text)
        os.chmod(tmp_path, mode)
        try:
            import pwd
            ucm_user = pwd.getpwnam('ucm')
            os.chown(tmp_path, ucm_user.pw_uid, ucm_user.pw_gid)
        except (KeyError, ImportError, PermissionError):
            pass
    except BaseException:
        os.unlink(tmp_path)
        raise
    return tmp_path


def write_https_pair(cert_path, key_path, cert_pem, key_pem, backup_suffix=None):
    """Both files hold exactly these texts afterwards; False when they already did.

    Each is replaced by the rename of a complete temporary file, prepared both before
    either rename. The key is 0600; the certificate keeps the mode of the one it replaces.
    """
    cert_path, key_path = str(cert_path), str(key_path)
    if _same_file(cert_path, cert_pem) and _same_file(key_path, key_pem):
        return False
    if backup_suffix:
        import shutil
        for path in (cert_path, key_path):
            if os.path.exists(path):
                shutil.copy(path, f"{path}.backup-{backup_suffix}")
    try:
        cert_mode = os.stat(cert_path).st_mode & 0o777
    except OSError:
        mask = os.umask(0o022)
        os.umask(mask)
        cert_mode = 0o666 & ~mask
    prepared = []
    try:
        prepared.append(_prepare(cert_path, cert_pem, cert_mode))
        prepared.append(_prepare(key_path, key_pem, 0o600))
        os.replace(prepared[1], key_path)
        os.replace(prepared[0], cert_path)
    finally:
        for tmp_path in prepared:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    return True


def materialize_https(data_path, cert_path, key_path):
    """Gunicorn master, before the TLS socket: write the HTTPS pair the database names.

    Returns what happened, for the log; None when the database names none (the files are
    left to the existing startup). Raises HttpsMaterialError and leaves the files untouched
    when the named pair cannot be read.
    """
    database = open_boot_database(data_path)
    if database is None:
        return None
    with database:
        found = https_material(database)
    if found is None:
        return None
    cert_pem, key_pem, label, chain_known = found
    if not chain_known and _leaf_in_file(cert_path) == _first_certificate(cert_pem) \
            and _same_file(key_path, key_pem):
        return f"{label} already in place"  # the chain on disk was written by the application
    from datetime import datetime, timezone
    suffix = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    if write_https_pair(cert_path, key_path, cert_pem, key_pem, backup_suffix=suffix):
        return f"{label} written from the database"
    return f"{label} already in place"

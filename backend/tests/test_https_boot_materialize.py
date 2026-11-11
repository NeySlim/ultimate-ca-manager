"""The gunicorn master writes the HTTPS pair the database names before its TLS socket opens.

Read with the raw driver (no application), on SQLite and PostgreSQL; the key is decrypted
with the master key, and a pair that cannot be read leaves the files untouched.
"""
import base64
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

import boot_config
from boot_config import HttpsMaterialError, materialize_https

PG_URL = os.getenv('UCM_TEST_PG_URL')
REFID = 'boot-https-leaf'
SCHEMA = (
    "CREATE TABLE system_config (key VARCHAR(255) PRIMARY KEY, value TEXT)",
    "CREATE TABLE certificates (refid VARCHAR(64) PRIMARY KEY, crt TEXT, prv TEXT)",
    "CREATE TABLE shared_files (name VARCHAR(64) PRIMARY KEY, content TEXT NOT NULL, "
    "updated_at TIMESTAMP, updated_by VARCHAR(255))",
)


def _pair(cn):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now).not_valid_after(now + timedelta(days=1))
            .sign(key, hashes.SHA256()))
    key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
    return cert.public_bytes(serialization.Encoding.PEM).decode(), key_pem


LEAF, KEY = _pair('boot-https.example.test')
ISSUER, _ = _pair('Boot HTTPS issuing CA')
FERNET_KEY = Fernet.generate_key()


def _encrypted(data: bytes) -> str:
    """The master-key format of Certificate.prv (utils.key_codec.store_pem_bytes)."""
    return base64.b64encode(b'ENC:' + Fernet(FERNET_KEY).encrypt(data)).decode()


@pytest.fixture
def master_key(monkeypatch):
    """This node has the master key the rows were encrypted with."""
    from security.encryption import key_encryption
    monkeypatch.setattr(key_encryption, '_fernet', Fernet(FERNET_KEY))
    monkeypatch.setattr(key_encryption, '_enabled', True)


@pytest.fixture
def no_master_key(monkeypatch):
    from security.encryption import key_encryption
    monkeypatch.setattr(key_encryption, '_fernet', None)
    monkeypatch.setattr(key_encryption, '_enabled', False)


def _seed(execute, ph, settings=(), certificates=(), shared=(), tables=SCHEMA):
    for statement in tables:
        execute(statement)
    for key, value in settings:
        execute(f"INSERT INTO system_config (key, value) VALUES ({ph}, {ph})", (key, value))
    for row in certificates:
        execute(f"INSERT INTO certificates (refid, crt, prv) VALUES ({ph}, {ph}, {ph})", row)
    for name, content in shared:
        execute(f"INSERT INTO shared_files (name, content) VALUES ({ph}, {ph})", (name, content))


def _bound(chain=None):
    settings = [('https_bound_certificate_refid', REFID)]
    if chain is not None:
        settings.append(('https_bound_certificate_chain', chain))
    return dict(settings=settings, certificates=[
        (REFID, base64.b64encode(LEAF.encode()).decode(), _encrypted(KEY.encode()))])


@pytest.fixture
def install(tmp_path, monkeypatch):
    """A SQLite install seeded by the test; returns (data_path, cert_path, key_path, seed)."""
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.delenv('DATABASE_PATH', raising=False)
    tls = tmp_path / 'tls'
    tls.mkdir()

    def seed(**rows):
        connection = sqlite3.connect(str(tmp_path / 'ucm.db'))
        _seed(lambda sql, params=(): connection.execute(sql, params), '?', **rows)
        connection.commit()
        connection.close()
    return str(tmp_path), tls / 'https_cert.pem', tls / 'https_key.pem', seed


def _tls_dir(cert_path):
    return sorted(p.name for p in cert_path.parent.iterdir())


class TestSqlite:
    def test_no_files_and_a_binding_writes_the_pair_of_the_database(self, install, master_key):
        data_path, cert_path, key_path, seed = install
        seed(**_bound(chain=LEAF + ISSUER))
        assert materialize_https(data_path, cert_path, key_path) == \
            f'bound certificate {REFID} written from the database'
        assert cert_path.read_text() == LEAF + ISSUER
        assert key_path.read_text() == KEY
        assert key_path.stat().st_mode & 0o777 == 0o600
        assert _tls_dir(cert_path) == ['https_cert.pem', 'https_key.pem']

    def test_a_stale_pair_is_replaced_and_kept_as_a_backup(self, install, master_key):
        data_path, cert_path, key_path, seed = install
        seed(**_bound(chain=LEAF))
        cert_path.write_text('old certificate')
        cert_path.chmod(0o644)
        key_path.write_text('old key')
        materialize_https(data_path, cert_path, key_path)
        assert (cert_path.read_text(), key_path.read_text()) == (LEAF, KEY)
        assert cert_path.stat().st_mode & 0o777 == 0o644
        backups = [p for p in cert_path.parent.iterdir() if '.backup-' in p.name]
        assert sorted(p.read_text() for p in backups) == ['old certificate', 'old key']

    def test_a_pair_already_in_place_is_not_rewritten(self, install, master_key):
        data_path, cert_path, key_path, seed = install
        seed(**_bound(chain=LEAF))
        materialize_https(data_path, cert_path, key_path)
        inode = cert_path.stat().st_ino
        assert materialize_https(data_path, cert_path, key_path).endswith('already in place')
        assert cert_path.stat().st_ino == inode

    def test_a_chain_of_another_certificate_is_not_served(self, install, master_key):
        """A renewal that could not store its chain: the leaf alone, never someone else's."""
        data_path, cert_path, key_path, seed = install
        seed(**_bound(chain=ISSUER + LEAF))
        materialize_https(data_path, cert_path, key_path)
        assert cert_path.read_text() == LEAF

    def test_an_unknown_chain_keeps_the_files_holding_that_leaf(self, install, master_key):
        """Upgrade: the binding predates the stored chain, the files carry the one written then."""
        data_path, cert_path, key_path, seed = install
        seed(**_bound())
        cert_path.write_text(LEAF + ISSUER)
        key_path.write_text(KEY)
        assert materialize_https(data_path, cert_path, key_path).endswith('already in place')
        assert cert_path.read_text() == LEAF + ISSUER

    def test_no_binding_leaves_the_files_alone(self, install, master_key):
        data_path, cert_path, key_path, seed = install
        seed()
        cert_path.write_text('operator certificate')
        assert materialize_https(data_path, cert_path, key_path) is None
        assert cert_path.read_text() == 'operator certificate'
        assert not key_path.exists()

    def test_the_regenerated_pair_of_the_cluster_is_written(self, install, master_key):
        data_path, cert_path, key_path, seed = install
        pair = json.dumps({'crt': ISSUER, 'key': KEY}).encode()
        seed(shared=[('https.generated', _encrypted(pair))])
        materialize_https(data_path, cert_path, key_path)
        assert (cert_path.read_text(), key_path.read_text()) == (ISSUER, KEY)

    def test_before_the_migration_there_is_nothing_to_write(self, install, master_key):
        data_path, cert_path, key_path, seed = install
        seed(tables=SCHEMA[:2])
        assert materialize_https(data_path, cert_path, key_path) is None

    def test_no_master_key_is_a_readable_failure_and_no_partial_file(self, install, no_master_key):
        data_path, cert_path, key_path, seed = install
        seed(**_bound(chain=LEAF))
        with pytest.raises(HttpsMaterialError, match='master key') as raised:
            materialize_https(data_path, cert_path, key_path)
        assert REFID in str(raised.value) and 'PRIVATE' not in str(raised.value)
        assert _tls_dir(cert_path) == []

    def test_no_master_key_keeps_the_files_in_place(self, install, no_master_key):
        data_path, cert_path, key_path, seed = install
        seed(**_bound(chain=LEAF))
        cert_path.write_text('previous certificate')
        key_path.write_text('previous key')
        with pytest.raises(HttpsMaterialError):
            materialize_https(data_path, cert_path, key_path)
        assert (cert_path.read_text(), key_path.read_text()) == ('previous certificate', 'previous key')
        assert _tls_dir(cert_path) == ['https_cert.pem', 'https_key.pem']

    def test_a_failed_rename_leaves_no_temporary_file(self, install, master_key, monkeypatch):
        data_path, cert_path, key_path, seed = install
        seed(**_bound(chain=LEAF))

        def refuse(src, dst):
            raise OSError('read-only')
        monkeypatch.setattr(boot_config.os, 'replace', refuse)
        with pytest.raises(OSError):
            materialize_https(data_path, cert_path, key_path)
        assert _tls_dir(cert_path) == []


_GUNICORN_BOOT = r'''
import boot_config
boot_config.wstep_enabled = lambda data_path: False
boot_config.mtls_client_ca = lambda data_path: None
import gunicorn_config
print(gunicorn_config.certfile)
'''


def test_the_gunicorn_master_writes_the_pair_before_the_application(install):
    """The config gunicorn reads first: the files exist before the preloaded app looks for them."""
    import subprocess
    import sys
    from pathlib import Path
    data_path, cert_path, key_path, seed = install
    seed(**_bound(chain=LEAF + ISSUER))
    backend = str(Path(__file__).resolve().parent.parent)
    config_dir = Path(data_path) / 'config'
    config_dir.mkdir()
    env = {k: v for k, v in os.environ.items()
           if k not in ('DATABASE_URL', 'DATABASE_PATH', 'UCM_HA', 'KEY_ENCRYPTION_KEY_FILE')}
    env.update(DATA_DIR=data_path, UCM_BASE_PATH=data_path, PYTHONPATH=backend,
               UCM_CONFIG_DIR=str(config_dir), KEY_ENCRYPTION_KEY=FERNET_KEY.decode(),
               HTTPS_CERT_PATH=str(cert_path), HTTPS_KEY_PATH=str(key_path))
    run = subprocess.run([sys.executable, '-c', _GUNICORN_BOOT], cwd=backend, env=env,
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr
    assert f'HTTPS: bound certificate {REFID} written from the database' in run.stderr
    assert (cert_path.read_text(), key_path.read_text()) == (LEAF + ISSUER, KEY)


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_install_writes_the_pair(tmp_path, monkeypatch, master_key):
    import psycopg
    from tests.conftest import pg_bench_exclusive
    schema = f"boot_https_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    sep = '&' if '?' in PG_URL else '?'
    monkeypatch.setenv('DATABASE_URL', f'{PG_URL}{sep}options=-csearch_path%3D{schema}')
    cert_path, key_path = tmp_path / 'https_cert.pem', tmp_path / 'https_key.pem'
    with pg_bench_exclusive():
        connection = psycopg.connect(PG_URL, autocommit=True)
        cursor = connection.cursor()
        try:
            cursor.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            cursor.execute(f"CREATE SCHEMA {schema}")
            cursor.execute(f"SET search_path TO {schema}")
            _seed(lambda sql, params=(): cursor.execute(sql, params), '%s', **_bound(chain=LEAF))
            assert materialize_https(str(tmp_path), cert_path, key_path).endswith('from the database')
            assert (cert_path.read_text(), key_path.read_text()) == (LEAF, KEY)
        finally:
            cursor.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            connection.close()

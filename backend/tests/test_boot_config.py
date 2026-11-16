"""The master's pre-application reads work on both backends.

mTLS and the WSTEP TLS cap used to be read with raw sqlite3 against
``data/ucm.db``: a PostgreSQL install found no file and served a socket that
never asked for a client certificate, whatever the interface showed.
"""
import base64
import os

import pytest

from boot_config import MTLS_UNDECIDED, database_url, mtls_client_ca, wstep_enabled

PG_URL = os.getenv('UCM_TEST_PG_URL')

SCHEMA = (
    "CREATE TABLE system_config (key VARCHAR(255) PRIMARY KEY, value TEXT)",
    "CREATE TABLE certificate_authorities ("
    " refid VARCHAR(64) PRIMARY KEY, crt TEXT, descr TEXT, caref VARCHAR(64))",
)


def _pem(common_name):
    return (f"-----BEGIN CERTIFICATE-----\n{common_name}\n"
            "-----END CERTIFICATE-----\n")


def _stored(common_name):
    return base64.b64encode(_pem(common_name).encode()).decode()


SETTINGS = (
    ('mtls_enabled', 'true'),
    ('mtls_required', 'true'),
    ('mtls_trusted_ca_id', 'ca-leaf'),
    ('wstep_enabled', 'true'),
)

AUTHORITIES = (
    ('ca-leaf', _stored('LEAF'), 'Issuing CA', 'ca-root'),
    ('ca-root', _stored('ROOT'), 'Root CA', None),
)


def _seed(execute, placeholder):
    for statement in SCHEMA:
        execute(statement)
    for key, value in SETTINGS:
        execute(f"INSERT INTO system_config (key, value) VALUES ({placeholder}, {placeholder})",
                (key, value))
    for row in AUTHORITIES:
        execute("INSERT INTO certificate_authorities (refid, crt, descr, caref) "
                f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder})", row)


@pytest.fixture()
def sqlite_install(tmp_path, monkeypatch):
    """A SQLite install: no DATABASE_URL, the file sits under the data dir."""
    import sqlite3
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.delenv('DATABASE_PATH', raising=False)
    connection = sqlite3.connect(str(tmp_path / 'ucm.db'))
    _seed(lambda sql, params=(): connection.execute(sql, params), '?')
    connection.commit()
    connection.close()
    return str(tmp_path)


@pytest.fixture()
def postgres_install(tmp_path, monkeypatch):
    """A PostgreSQL install: DATABASE_URL set, no SQLite file anywhere."""
    if not PG_URL:
        pytest.skip('UCM_TEST_PG_URL not set')
    import psycopg
    monkeypatch.setenv('DATABASE_URL', PG_URL)
    from tests.conftest import pg_bench_exclusive
    # Tables in the shared bench's public schema, which other files reset
    with pg_bench_exclusive():
        connection = psycopg.connect(PG_URL, autocommit=True)
        cursor = connection.cursor()
        cursor.execute("DROP TABLE IF EXISTS system_config")
        cursor.execute("DROP TABLE IF EXISTS certificate_authorities")
        _seed(lambda sql, params=(): cursor.execute(sql, params), '%s')
        yield str(tmp_path)
        cursor.execute("DROP TABLE IF EXISTS system_config")
        cursor.execute("DROP TABLE IF EXISTS certificate_authorities")
        connection.close()


class TestSqliteInstall:
    def test_url_falls_back_to_the_data_directory(self, sqlite_install):
        assert database_url(sqlite_install).endswith('/ucm.db')

    def test_only_the_trusted_ca_is_read(self, sqlite_install):
        pem, name, required = mtls_client_ca(sqlite_install)
        assert pem == _pem('LEAF')
        assert name == 'Issuing CA'
        assert required is True

    def test_wstep_is_read(self, sqlite_install):
        assert wstep_enabled(sqlite_install) is True

    def test_database_path_wins_over_the_data_directory(
            self, sqlite_install, tmp_path, monkeypatch):
        """The v1 upgrade writes DATABASE_PATH into the service env, and
        reading only DATA_DIR looked at a file that install does not have."""
        monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'ucm.db'))
        elsewhere = str(tmp_path / 'empty')
        os.makedirs(elsewhere, exist_ok=True)
        assert mtls_client_ca(elsewhere)[1] == 'Issuing CA'

    def test_a_truncated_certificate_is_refused(self, tmp_path, monkeypatch):
        """A row holding a header and no footer is not a PEM."""
        import sqlite3
        monkeypatch.delenv('DATABASE_URL', raising=False)
        monkeypatch.delenv('DATABASE_PATH', raising=False)
        connection = sqlite3.connect(str(tmp_path / 'ucm.db'))
        for statement in SCHEMA:
            connection.execute(statement)
        for key, value in SETTINGS:
            connection.execute("INSERT INTO system_config VALUES (?, ?)", (key, value))
        truncated = base64.b64encode(
            b'-----BEGIN CERTIFICATE-----\nTRUNCATED\n').decode()
        connection.execute("INSERT INTO certificate_authorities VALUES (?, ?, ?, ?)",
                           ('ca-leaf', truncated, 'Issuing CA', None))
        connection.commit()
        connection.close()
        assert mtls_client_ca(str(tmp_path)) is None

    def test_no_database_yet_is_not_an_error(self, tmp_path, monkeypatch):
        monkeypatch.delenv('DATABASE_URL', raising=False)
        monkeypatch.delenv('DATABASE_PATH', raising=False)
        assert mtls_client_ca(str(tmp_path)) is None
        assert wstep_enabled(str(tmp_path)) is False


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
class TestPostgresInstall:
    def test_only_the_trusted_ca_is_read(self, postgres_install):
        pem, name, required = mtls_client_ca(postgres_install)
        assert pem == _pem('LEAF')
        assert name == 'Issuing CA'
        assert required is True

    def test_wstep_is_read(self, postgres_install):
        assert wstep_enabled(postgres_install) is True

    # +psycopg2 is read with psycopg 3, the one driver UCM ships
    @pytest.mark.parametrize('driver', ['psycopg', 'psycopg2'])
    def test_sqlalchemy_driver_suffix_is_accepted(self, postgres_install, monkeypatch, driver):
        scheme, _, rest = PG_URL.partition('://')
        monkeypatch.setenv('DATABASE_URL', f'{scheme}+{driver}://{rest}')
        assert mtls_client_ca(postgres_install)[1] == 'Issuing CA'


class TestAnchor:
    def test_a_parent_cycle_is_never_walked(self, tmp_path, monkeypatch):
        import sqlite3
        monkeypatch.delenv('DATABASE_URL', raising=False)
        monkeypatch.delenv('DATABASE_PATH', raising=False)
        connection = sqlite3.connect(str(tmp_path / 'ucm.db'))
        execute = lambda sql, params=(): connection.execute(sql, params)
        for statement in SCHEMA:
            execute(statement)
        for key, value in SETTINGS:
            execute("INSERT INTO system_config (key, value) VALUES (?, ?)", (key, value))
        # A repaired hierarchy that points back at itself.
        execute("INSERT INTO certificate_authorities VALUES (?, ?, ?, ?)",
                ('ca-leaf', _stored('LEAF'), 'Issuing CA', 'ca-root'))
        execute("INSERT INTO certificate_authorities VALUES (?, ?, ?, ?)",
                ('ca-root', _stored('ROOT'), 'Root CA', 'ca-leaf'))
        connection.commit()
        connection.close()

        pem, _name, _required = mtls_client_ca(str(tmp_path))
        assert pem == _pem('LEAF')


def _three_boot_reads(data_path, capsys):
    """What the gunicorn master reads before the schema exists, and what it printed."""
    from boot_config import materialize_https
    found = (wstep_enabled(data_path), mtls_client_ca(data_path),
             materialize_https(data_path, os.path.join(data_path, 'c.pem'), os.path.join(data_path, 'k.pem')))
    return found, capsys.readouterr().err


def test_a_sqlite_database_without_its_tables_is_read_as_no_settings(tmp_path, monkeypatch, capsys):
    """A first start cut before create_all: an empty file, read as a new installation."""
    import sqlite3
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.delenv('DATABASE_PATH', raising=False)
    sqlite3.connect(str(tmp_path / 'ucm.db')).close()
    assert _three_boot_reads(str(tmp_path), capsys) == ((False, MTLS_UNDECIDED, None), '')


def _master_on(tmp_path, monkeypatch):
    """The gunicorn configuration as the master loads it over the data directory *tmp_path*."""
    import importlib.util
    import gevent.monkey
    monkeypatch.setattr(gevent.monkey, 'patch_all', lambda *a, **k: None)
    monkeypatch.setenv('UCM_SCHEDULER_SUPERVISED', '')  # set by the config, undone after
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    for name in ('DATABASE_URL', 'DATABASE_PATH', 'HTTPS_CERT_PATH', 'HTTPS_KEY_PATH'):
        monkeypatch.delenv(name, raising=False)
    spec = importlib.util.spec_from_file_location(
        '_ucm_gunicorn_config_boot', os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                                  'gunicorn_config.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_lost_settings_table_keeps_the_last_known_mtls_mode(tmp_path, monkeypatch, capsys):
    """Required at the last start, settings table gone: still required, and still on record."""
    import sqlite3
    sqlite3.connect(str(tmp_path / 'ucm.db')).close()
    (tmp_path / 'mtls_ca.pem').write_text(_pem('LEAF'))
    (tmp_path / 'mtls_mode').write_text('required')
    master = _master_on(tmp_path, monkeypatch)
    assert (master.cert_reqs, master.ca_certs) == (2, str(tmp_path / 'mtls_ca.pem'))
    assert (tmp_path / 'mtls_mode').read_text() == 'required'
    assert 'keeping the last known configuration (REQUIRED)' in capsys.readouterr().err


def test_a_first_start_records_no_mtls_mode(tmp_path, monkeypatch, capsys):
    import sqlite3
    sqlite3.connect(str(tmp_path / 'ucm.db')).close()
    master = _master_on(tmp_path, monkeypatch)
    assert (master.cert_reqs, master.ca_certs) == (0, None)
    assert not (tmp_path / 'mtls_mode').exists()
    assert 'mTLS' not in capsys.readouterr().err


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_an_empty_postgres_database_is_read_as_no_settings(tmp_path, monkeypatch, capsys):
    """A first start on an empty PostgreSQL database: no warning before the schema is built."""
    import psycopg
    schema = f'boot_empty_{os.getpid()}'
    with psycopg.connect(PG_URL, autocommit=True) as connection:
        connection.execute(f'DROP SCHEMA IF EXISTS {schema} CASCADE')
        connection.execute(f'CREATE SCHEMA {schema}')
    try:
        sep = '&' if '?' in PG_URL else '?'
        monkeypatch.setenv('DATABASE_URL', f'{PG_URL}{sep}options=-csearch_path%3D{schema}')
        assert _three_boot_reads(str(tmp_path), capsys) == ((False, MTLS_UNDECIDED, None), '')
    finally:
        with psycopg.connect(PG_URL, autocommit=True) as connection:
            connection.execute(f'DROP SCHEMA IF EXISTS {schema} CASCADE')

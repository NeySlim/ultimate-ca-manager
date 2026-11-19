"""The master's pre-application reads work on both backends.

mTLS and the WSTEP TLS cap used to be read with raw sqlite3 against
``data/ucm.db``: a PostgreSQL install found no file and served a socket that
never asked for a client certificate, whatever the interface showed.
"""
import base64
import os

import pytest

from boot_config import database_url, mtls_client_ca, wstep_enabled

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

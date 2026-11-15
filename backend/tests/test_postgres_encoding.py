"""A PostgreSQL database that is not UTF8 is refused at startup, and by the package's check,
with a message naming its encoding. The real database needs UCM_TEST_PG_URL (and the right
to create a database); the other tests simulate the encoding the server answers."""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

import migration_runner

PG_URL = os.getenv('UCM_TEST_PG_URL')
UNREACHABLE = 'postgresql://ucm:x@127.0.0.1:1/ucm'


@pytest.mark.parametrize('answer', ['SQL_ASCII', b'SQL_ASCII', 'LATIN1'])
def test_a_database_not_in_utf8_is_refused_by_name_simulated(monkeypatch, capsys, answer):
    """Simulated: the server's answer is replaced; nothing after it is reached."""
    monkeypatch.setenv('DATABASE_URL', UNREACHABLE)
    monkeypatch.setattr(migration_runner, '_server_encoding',
                        lambda engine: answer.decode() if isinstance(answer, bytes) else answer)
    assert migration_runner.run_all_migrations() is False
    out = capsys.readouterr().out
    name = answer.decode() if isinstance(answer, bytes) else answer
    assert f'uses the encoding {name}; UCM needs UTF8' in out and 'docs/ADMIN_GUIDE.md' in out
    assert migration_runner.check_database() == migration_runner.CHECK_UNREADABLE
    assert f'unreadable: This PostgreSQL database uses the encoding {name}' in capsys.readouterr().out


def test_a_utf8_database_goes_on_to_the_registry_simulated(monkeypatch):
    """Simulated: UTF8 passes, and the next step, reading the registry, is reached."""
    monkeypatch.setenv('DATABASE_URL', UNREACHABLE)
    monkeypatch.setattr(migration_runner, '_server_encoding', lambda engine: 'UTF8')
    with pytest.raises(Exception, match='127.0.0.1|connect|refused'):
        migration_runner.run_all_migrations()


def test_sqlite_is_never_asked_for_an_encoding(tmp_path):
    assert migration_runner.encoding_refusal(create_engine(f'sqlite:///{tmp_path}/x.db')) is None


@pytest.mark.postgres
def test_a_sql_ascii_database_is_refused_by_name(monkeypatch, capsys):
    if not PG_URL:
        pytest.skip('UCM_TEST_PG_URL not set')
    name = f'ucm_ascii_{uuid.uuid4().hex[:8]}'
    admin = create_engine(PG_URL, isolation_level='AUTOCOMMIT')
    try:
        with admin.connect() as conn:
            conn.execute(text(f"CREATE DATABASE {name} ENCODING 'SQL_ASCII' LC_COLLATE 'C' "
                              f"LC_CTYPE 'C' TEMPLATE template0"))
    except Exception as exc:  # noqa: BLE001
        admin.dispose()
        pytest.skip(f'cannot create a database here: {exc}')
    try:
        url = make_url(PG_URL).set(database=name).render_as_string(hide_password=False)
        monkeypatch.setenv('DATABASE_URL', url)
        assert migration_runner.run_all_migrations() is False
        assert 'uses the encoding SQL_ASCII; UCM needs UTF8' in capsys.readouterr().out
        assert migration_runner.check_database() == migration_runner.CHECK_UNREADABLE
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS {name}'))
        admin.dispose()


@pytest.mark.postgres
def test_the_test_server_s_utf8_database_is_read_on_a_bare_connection():
    if not PG_URL:
        pytest.skip('UCM_TEST_PG_URL not set')
    from utils.db_url import sqlalchemy_url
    engine = create_engine(sqlalchemy_url(PG_URL))
    try:
        assert migration_runner._server_encoding(engine) == 'UTF8'
        assert migration_runner.encoding_refusal(engine) is None
    finally:
        engine.dispose()

"""SQLAlchemy's error text quotes no bound value: private keys pass through these engines."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

import migration_runner
from config.settings import Config
from models import db
from services.database_admin import copy as copy_module
from services.database_admin import migration


class _Stop(Exception):
    pass


def _recording(built):
    def create_engine(*_args, **kwargs):
        built.append(kwargs)
        raise _Stop
    return create_engine


def test_the_application_engine_hides_them(app):
    assert Config.SQLALCHEMY_ENGINE_OPTIONS['hide_parameters'] is True
    with app.app_context(), db.engine.connect() as conn, pytest.raises(SQLAlchemyError) as caught:
        conn.execute(text('INSERT INTO no_such_table VALUES (:secret)'), {'secret': 'PRIVATE-KEY-MATERIAL'})
    assert 'PRIVATE-KEY-MATERIAL' not in str(caught.value)


@pytest.mark.parametrize('copy_rows', [migration.bootstrap_auth_to_target, migration.migrate_data])
def test_a_migration_target_hides_them(app, copy_rows):
    built = []
    with app.app_context(), patch.object(migration, 'create_engine', _recording(built)), \
            patch.object(migration, 'test_connection', return_value=(True, 'ok')):
        copy_rows('sqlite:////nonexistent/target.db')
    assert built and all(kwargs.get('hide_parameters') is True for kwargs in built)


def test_a_snapshot_source_hides_them():
    built = []
    with patch.object(copy_module, 'create_engine', _recording(built)), pytest.raises(_Stop):
        with copy_module.consistent_source(SimpleNamespace(backend='sqlite', path='/nonexistent/snap.db')):
            pass
    assert built[0].get('hide_parameters') is True


@pytest.mark.parametrize('run', [migration_runner.mark_all_applied, migration_runner.run_all_migrations,
                                 migration_runner.show_status])
def test_the_migration_runner_hides_them(run):
    # Its own URL lookup is replaced: nothing here may reach a real database
    built = []
    with patch.object(migration_runner, 'create_engine', _recording(built)), \
            patch.object(migration_runner, '_get_db_url', return_value='postgresql://nobody@nowhere/none'):
        try:
            run()
        except _Stop:
            pass
    assert built and built[0].get('hide_parameters') is True


_SECRET = 'ZZSECRET-PRIVATE-KEY-MATERIAL'


def _on_postgresql(app):
    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            pytest.skip('the session app is not on PostgreSQL')


def test_a_postgresql_error_quotes_no_statement(app, caplog):
    import logging
    _on_postgresql(app)
    with app.app_context(), db.engine.connect() as conn, pytest.raises(SQLAlchemyError) as caught:
        conn.execute(text('INSERT INTO system_config (key, no_such_column) VALUES (:k, :v)'),
                     {'k': 'scrub-probe', 'v': _SECRET})
    error = caught.value
    logging.getLogger('scrub-probe').error(f'refused: {error}', exc_info=True)
    assert _SECRET not in str(error) and _SECRET not in str(error.orig)
    assert _SECRET not in caplog.text and 'LINE 1' not in caplog.text
    assert str(error.orig).startswith('column "no_such_column" of relation "system_config" does not exist')
    assert error.orig.pgcode == '42703'


def test_a_duplicate_key_keeps_its_detail(app):
    _on_postgresql(app)
    from models import SystemConfig
    with app.app_context():
        db.session.add(SystemConfig(key='scrub-probe-dup', value='a'))
        db.session.commit()
        try:
            with db.engine.connect() as conn, pytest.raises(SQLAlchemyError) as caught:
                conn.execute(text("INSERT INTO system_config (key, value) VALUES ('scrub-probe-dup', 'b')"))
            assert caught.value.orig.pgcode == '23505'
            assert 'DETAIL:  Key (key)=(scrub-probe-dup) already exists.' in str(caught.value)
            assert caught.value.orig.diag.message_detail == 'Key (key)=(scrub-probe-dup) already exists.'
        finally:
            SystemConfig.query.filter_by(key='scrub-probe-dup').delete()
            db.session.commit()


def test_sqlite_errors_are_left_as_they_are(tmp_path):
    from sqlalchemy import create_engine
    engine = create_engine(f"sqlite:///{tmp_path / 'probe.db'}")
    with engine.connect() as conn, pytest.raises(SQLAlchemyError) as caught:
        conn.execute(text('INSERT INTO nope VALUES (:v)'), {'v': _SECRET})
    assert caught.value.orig.args == ('no such table: nope',)
    engine.dispose()


@pytest.mark.parametrize('message, scrubbed', [
    ('column "x" does not exist\nLINE 1: SELECT x, \'s3cret\'\n               ^\n',
     'column "x" does not exist\n'),
    ('duplicate key value\nDETAIL:  Key (name)=(a) already exists.\n',
     'duplicate key value\nDETAIL:  Key (name)=(a) already exists.\n'),
    ('syntax error\nLINE 2: VALUES (\'s3cret\')\n        ^\nHINT:  Check it.\n',
     'syntax error\nHINT:  Check it.\n'),
    ('failed\nCONTEXT:  SQL statement "INSERT INTO t VALUES (\'s3cret\')"\nPL/pgSQL function f() line 3\n'
     'QUERY:  SELECT \'s3cret\'\n', 'failed\n'),
])
def test_the_scrubber_keeps_the_message_detail_and_hint(message, scrubbed):
    from utils.db_errors import scrub_postgres_message
    assert scrub_postgres_message(message) == scrubbed

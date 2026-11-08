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
from utils import db_errors
from utils.db_errors import sqlstate


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
    assert sqlstate(error.orig) == '42703'


def test_the_driver_puts_no_value_in_the_statement(app):
    # Scrubber off: a server error quotes the statement as the driver sent it
    _on_postgresql(app)
    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    secret = b'ZZSECRET' * 512
    event.remove(Engine, 'handle_error', db_errors._scrub)
    try:
        with app.app_context(), db.engine.connect() as conn, pytest.raises(SQLAlchemyError) as caught:
            conn.execute(text('INSERT INTO system_config (nope, key) VALUES (:v, :k)'),
                         {'v': secret, 'k': 'scrub-probe'})
    finally:
        db_errors.install()
    shown = str(caught.value)
    assert 'LINE 1: INSERT INTO system_config (nope, key) VALUES (' in shown
    # The server shows a few bytes of a quoted value before cutting the line
    assert secret[:4].hex() not in shown and 'ZZSE' not in shown


def test_a_duplicate_key_keeps_its_detail(app):
    _on_postgresql(app)
    from models import SystemConfig
    with app.app_context():
        db.session.add(SystemConfig(key='scrub-probe-dup', value='a'))
        db.session.commit()
        try:
            with db.engine.connect() as conn, pytest.raises(SQLAlchemyError) as caught:
                conn.execute(text("INSERT INTO system_config (key, value) VALUES ('scrub-probe-dup', 'b')"))
            assert sqlstate(caught.value.orig) == '23505'
            assert 'DETAIL:  Key (key)=(scrub-probe-dup) already exists.' in str(caught.value)
            assert caught.value.orig.diag.message_detail == 'Key (key)=(scrub-probe-dup) already exists.'
        finally:
            SystemConfig.query.filter_by(key='scrub-probe-dup').delete()
            db.session.commit()


@pytest.mark.parametrize('statement, pgcode, primary', [
    # NOT NULL: the DETAIL quotes the refused row
    ('INSERT INTO system_config (key, value) VALUES (NULL, :v)', '23502',
     'null value in column "key" of relation "system_config" violates not-null constraint'),
    # A refused input: the primary line quotes it
    ("INSERT INTO system_config (id, key) VALUES (CAST(:v AS integer), 'scrub-probe')", '22P02',
     'invalid input value (SQLSTATE 22P02), not shown'),
    # Out of range: the value is quoted in the middle of the line
    ("SELECT CAST(:v || '99999999999' AS integer)", '22003',
     'invalid input value (SQLSTATE 22003), not shown'),
    # Malformed JSON: the DETAIL quotes the token
    ('SELECT CAST(:v AS json)', '22P02', 'invalid input value (SQLSTATE 22P02), not shown'),
])
def test_a_refused_row_or_input_is_not_quoted(app, statement, pgcode, primary):
    _on_postgresql(app)
    value = '1' if pgcode == '22003' else _SECRET
    with app.app_context(), db.engine.connect() as conn, pytest.raises(SQLAlchemyError) as caught:
        conn.execute(text(statement), {'v': value})
    assert sqlstate(caught.value.orig) == pgcode
    shown = str(caught.value)
    assert _SECRET not in shown and '199999999999' not in shown and 'Failing row' not in shown
    assert 'DETAIL' not in shown and str(caught.value.orig).split('\n')[0] == primary


def test_sqlite_errors_are_left_as_they_are(tmp_path):
    from sqlalchemy import create_engine
    engine = create_engine(f"sqlite:///{tmp_path / 'probe.db'}")
    with engine.connect() as conn, pytest.raises(SQLAlchemyError) as caught:
        conn.execute(text('INSERT INTO nope VALUES (:v)'), {'v': _SECRET})
    assert caught.value.orig.args == ('no such table: nope',)
    engine.dispose()


@pytest.mark.parametrize('fields, kept', [
    (('column "x" does not exist',), 'column "x" does not exist'),
    (('duplicate key value', 'Key (name)=(a) already exists.'),
     'duplicate key value\nDETAIL:  Key (name)=(a) already exists.'),
    (('syntax error', None, 'Check it.'), 'syntax error\nHINT:  Check it.'),
])
def test_the_message_keeps_its_detail_and_hint(fields, kept):
    from utils.db_errors import postgres_message
    assert postgres_message(*fields) == kept


@pytest.mark.parametrize('primary, detail, pgcode, kept', [
    ('null value in column "v"', 'Failing row contains (1, null, s3cret).', '23502', 'null value in column "v"'),
    ('new row violates check constraint "c"', 'Failing row contains (-1, s3cret).', '23514',
     'new row violates check constraint "c"'),
    ('new row violates check option for view "w"', 'Failing row contains (s3cret).', '44000',
     'new row violates check option for view "w"'),
    ('invalid input syntax for type timestamp: "s3cret"', None, '22007',
     'invalid input value (SQLSTATE 22007), not shown'),
    ('value "1234567890123" is out of range for type integer', None, '22003',
     'invalid input value (SQLSTATE 22003), not shown'),
    ('invalid input syntax for type json', 'Token "s3cret" is invalid.', '22P02',
     'invalid input value (SQLSTATE 22P02), not shown'),
    # Outside class 22 a quoted name is an identifier, not an input
    ('relation "s3cret_table" does not exist', None, '42P01', 'relation "s3cret_table" does not exist'),
])
def test_the_message_drops_refused_rows_and_inputs(primary, detail, pgcode, kept):
    from utils.db_errors import postgres_message
    assert postgres_message(primary, detail, None, pgcode) == kept


class _Diag:
    def __init__(self, primary, detail=None, hint=None):
        self.message_primary, self.message_detail, self.message_hint = primary, detail, hint


class _ServerError(Exception):
    """A psycopg error as the server sends it: its text as libpq labelled it, its fields."""
    def __init__(self, text, pgcode, diag):
        super().__init__(text)
        self.sqlstate, self.diag = pgcode, diag


def _scrubbed(error):
    wrapped = Exception(f'(psycopg.errors.X) {error.args[0]}')
    db_errors._scrub(SimpleNamespace(dialect=SimpleNamespace(name='postgresql'),
                                     original_exception=error, sqlalchemy_exception=wrapped))
    return error.args[0], wrapped.args[0]


@pytest.mark.parametrize('text, pgcode, diag, kept', [
    # Server and client labels both in French: nothing here is matched as text
    ('la nouvelle ligne de la relation « t » viole la contrainte de vérification « c »\n'
     'DÉTAIL : La ligne en échec contient (c, ZZSECRET, -1).', '23514',
     _Diag('la nouvelle ligne de la relation « t » viole la contrainte de vérification « c »',
           'La ligne en échec contient (c, ZZSECRET, -1).'),
     'la nouvelle ligne de la relation « t » viole la contrainte de vérification « c »'),
    ('une valeur NULL viole la contrainte NOT NULL de la colonne « v »\n'
     'DÉTAIL : La ligne en échec contient (b, null, ZZSECRET).', '23502',
     _Diag('une valeur NULL viole la contrainte NOT NULL de la colonne « v »',
           'La ligne en échec contient (b, null, ZZSECRET).'),
     'une valeur NULL viole la contrainte NOT NULL de la colonne « v »'),
    ("syntaxe en entrée invalide pour le type integer : « ZZSECRET »\n"
     "LIGNE 1 : select cast('ZZSECRET' as integer)\n                    ^", '22P02',
     _Diag('syntaxe en entrée invalide pour le type integer : « ZZSECRET »'),
     'invalid input value (SQLSTATE 22P02), not shown'),
    ('syntaxe en entrée invalide pour le type json\nDÉTAIL : Token "ZZSECRET" is invalid.\n'
     'CONTEXTE : données JSON, ligne 1 : {ZZSECRET', '22P02',
     _Diag('syntaxe en entrée invalide pour le type json', 'Token "ZZSECRET" is invalid.'),
     'invalid input value (SQLSTATE 22P02), not shown'),
    ("la colonne « nope » n'existe pas\nLIGNE 1 : select nope from t where v='ZZSECRET'", '42703',
     _Diag("la colonne « nope » n'existe pas"), "la colonne « nope » n'existe pas"),
    ("la valeur d'une clé dupliquée rompt la contrainte unique « t_pkey »\n"
     'DÉTAIL : La clé « (k)=(a) » existe déjà.', '23505',
     _Diag("la valeur d'une clé dupliquée rompt la contrainte unique « t_pkey »",
           'La clé « (k)=(a) » existe déjà.', 'Un conseil.'),
     "la valeur d'une clé dupliquée rompt la contrainte unique « t_pkey »\n"
     'DETAIL:  La clé « (k)=(a) » existe déjà.\nHINT:  Un conseil.'),
])
def test_the_message_is_rebuilt_from_its_fields_whatever_the_language(text, pgcode, diag, kept):
    clean, wrapped = _scrubbed(_ServerError(text, pgcode, diag))
    assert clean == kept and wrapped == f'({__name__}._ServerError) {kept}'
    assert 'ZZSECRET' not in clean and 'LIGNE' not in clean and 'CONTEXTE' not in clean


def test_an_error_without_server_fields_is_left_as_it_is():
    text = 'connection failed: connection to server at "127.0.0.1", port 5432 failed\nsecond line'
    clean, _ = _scrubbed(_ServerError(text, None, _Diag(None)))
    assert clean == text


_FRENCH = 'fr_FR.UTF-8'


@pytest.mark.postgres
def test_a_server_speaking_french_quotes_no_value():
    """A role whose lc_messages is French, on a real server; the superuser URL creates it."""
    import os
    import secrets
    import psycopg
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    from utils.db_url import sqlalchemy_url

    admin_url = os.environ.get('UCM_TEST_POSTGRES_URL')
    if not admin_url:
        pytest.skip('UCM_TEST_POSTGRES_URL not set')
    role, password = f'ucm_lcfr_{secrets.token_hex(4)}', secrets.token_hex(16)
    table = f'{role}_probe'
    admin = psycopg.connect(admin_url, autocommit=True)
    try:
        if not admin.execute('SELECT rolsuper FROM pg_roles WHERE rolname = current_user').fetchone()[0]:
            pytest.skip('setting lc_messages on a role takes a superuser')
        admin.execute(f'CREATE ROLE "{role}" LOGIN PASSWORD \'{password}\'')
        try:
            admin.execute(f'ALTER ROLE "{role}" SET lc_messages = \'{_FRENCH}\'')
        except psycopg.errors.InvalidParameterValue:
            pytest.skip(f'the server has no {_FRENCH} locale')
        # The admin owns the table: the role is left with nothing to drop
        admin.execute(f'CREATE TABLE "{table}" (k text PRIMARY KEY, v text NOT NULL, n integer CHECK (n > 0))')
        admin.execute(f'GRANT SELECT, INSERT ON "{table}" TO "{role}"')
        url = make_url(sqlalchemy_url(admin_url)).set(username=role, password=password)
        engine = create_engine(url, hide_parameters=True)
        try:
            with engine.connect() as conn:
                for statement, params in [
                        (f'INSERT INTO "{table}" VALUES (:k, NULL, 1)', {'k': _SECRET}),
                        (f'INSERT INTO "{table}" VALUES (:k, :v, -1)', {'k': 'a', 'v': _SECRET}),
                        ('SELECT CAST(:v AS integer)', {'v': _SECRET}),
                        ('SELECT CAST(:v AS timestamp)', {'v': _SECRET}),
                        ('SELECT CAST(:v AS json)', {'v': '{' + _SECRET}),
                        (f'SELECT nope FROM "{table}" WHERE v = :v', {'v': _SECRET})]:
                    with pytest.raises(SQLAlchemyError) as caught:
                        conn.execute(text(statement), params)
                    conn.rollback()
                    diag = caught.value.orig.diag
                    if diag.severity == diag.severity_nonlocalized:
                        pytest.skip('the server has no French translation of its messages')
                    assert _SECRET not in str(caught.value) and _SECRET not in str(caught.value.orig), statement
        finally:
            engine.dispose()
    finally:
        admin.execute(f'DROP TABLE IF EXISTS "{table}"')
        admin.execute(f'DROP ROLE IF EXISTS "{role}"')
        admin.close()

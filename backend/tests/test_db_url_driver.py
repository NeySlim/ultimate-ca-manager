"""Every PostgreSQL URL reaches psycopg 3, which binds parameters on the
server: postgresql+psycopg2://, from older guides, included."""
import io
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from utils import db_url
from utils.db_url import sqlalchemy_url


BACKEND = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize('url, expected', [
    ('postgresql://u:p@db/ucm', 'postgresql+psycopg://u:p@db/ucm'),
    ('postgres://u:p@db/ucm', 'postgresql+psycopg://u:p@db/ucm'),
    ('postgresql+psycopg://u:p@db/ucm', 'postgresql+psycopg://u:p@db/ucm'),
    ('postgresql+psycopg2://u:p@db/ucm', 'postgresql+psycopg://u:p@db/ucm'),
    # Any other driver the administrator chose is theirs to keep
    ('postgresql+pg8000://u:p@db/ucm', 'postgresql+pg8000://u:p@db/ucm'),
    ('sqlite:////opt/ucm/data/ucm.db', 'sqlite:////opt/ucm/data/ucm.db'),
])
def test_the_driver_is_pinned(url, expected):
    assert sqlalchemy_url(url) == expected


_UCM_FORMAT = '%(asctime)s [%(name)s] %(levelname)s %(message)s'


class _Stop(Exception):
    pass


def _ucm_handlers():
    return [h for h in logging.getLogger().handlers
            if getattr(h.formatter, '_fmt', None) == _UCM_FORMAT]


def test_create_app_writes_the_normalisation_through_its_own_handler(monkeypatch):
    import app as app_module
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg2://ucm:s3cret-pw@db.invalid/ucm')
    root = logging.getLogger()
    earlier = _ucm_handlers()  # left by other apps of the session
    for handler in earlier:
        root.removeHandler(handler)
    written = []

    def hook(url, log):
        # Logging must already be up: the handler this create_app installed writes the line
        handlers = _ucm_handlers()
        assert handlers, 'the hook ran before create_app configured logging'
        stream, handlers[0].stream = handlers[0].stream, io.StringIO()
        try:
            db_url.log_normalised_scheme(url, log)
            written.append(handlers[0].stream.getvalue())
        finally:
            handlers[0].stream = stream
        raise _Stop

    monkeypatch.setattr(app_module, 'log_normalised_scheme', hook)
    # The PostgreSQL harness would put its own DATABASE_URL in place; the hook stops before any database
    create_app = getattr(app_module.create_app, '__wrapped__', app_module.create_app)
    try:
        with pytest.raises(_Stop):
            create_app('testing')
    finally:
        for handler in _ucm_handlers():
            root.removeHandler(handler)
        for handler in earlier:
            root.addHandler(handler)
    assert len(written) == 1 and '[utils.db_url] INFO PostgreSQL URL scheme postgresql+psycopg2:// ' \
        'normalised to postgresql+psycopg://' in written[0]
    assert 's3cret-pw' not in written[0] and 'db.invalid' not in written[0]


@pytest.mark.parametrize('url', ['postgresql://u:p@db/ucm', 'postgresql+psycopg://u:p@db/ucm',
                                 'sqlite:////tmp/ucm.db', ''])
def test_only_a_psycopg2_scheme_is_announced(url, caplog):
    with caplog.at_level(logging.DEBUG, logger='utils.db_url'):
        db_url.log_normalised_scheme(url, logging.getLogger('utils.db_url'))
    assert not caplog.records


@pytest.mark.parametrize('value, expected', [
    (None, {}), ('', {}), ('0', {'prepare_threshold': None}), ('none', {'prepare_threshold': None}),
    ('OFF', {'prepare_threshold': None}), ('3', {'prepare_threshold': 3}),
])
def test_the_prepare_threshold_comes_from_the_environment(value, expected):
    environ = {} if value is None else {'UCM_PG_PREPARE_THRESHOLD': value}
    assert db_url.postgres_connect_args('postgresql://u:p@db/ucm', environ) == expected


def test_the_prepare_threshold_leaves_sqlite_alone():
    assert db_url.postgres_connect_args('sqlite:////tmp/ucm.db', {'UCM_PG_PREPARE_THRESHOLD': '0'}) == {}


def test_a_malformed_prepare_threshold_is_refused():
    with pytest.raises(ValueError, match='UCM_PG_PREPARE_THRESHOLD'):
        db_url.postgres_connect_args('postgresql://u:p@db/ucm', {'UCM_PG_PREPARE_THRESHOLD': '-1'})


@pytest.mark.parametrize('value, expected', [('0', 'None'), ('', 'absent')])
def test_the_application_engine_takes_the_prepare_threshold(value, expected):
    env = dict(os.environ, DATABASE_URL='postgresql://u:p@db.invalid/ucm', UCM_PG_PREPARE_THRESHOLD=value)
    out = subprocess.run(
        [sys.executable, '-c', 'from config.settings import Config; '
         'args = Config.SQLALCHEMY_ENGINE_OPTIONS.get("connect_args"); '
         'print("absent" if args is None else args["prepare_threshold"])'],
        cwd=BACKEND, env=env, capture_output=True, text=True, check=True)
    assert out.stdout.strip().splitlines()[-1] == expected


@pytest.mark.postgres
@pytest.mark.parametrize('value, prepared', [('', True), ('0', False)])
def test_a_disabled_threshold_prepares_nothing_on_the_server(value, prepared):
    url = os.environ.get('UCM_TEST_PG_URL', '')
    if not url:
        pytest.skip('UCM_TEST_PG_URL not set')
    from sqlalchemy import create_engine, text
    args = db_url.postgres_connect_args(url, {'UCM_PG_PREPARE_THRESHOLD': value})
    engine = create_engine(sqlalchemy_url(url), connect_args=args)
    try:
        with engine.connect() as conn:
            for _ in range(8):
                conn.execute(text('SELECT 1 WHERE 1 = :x'), {'x': 1})
            count = conn.execute(text('SELECT count(*) FROM pg_prepared_statements')).scalar()
        assert (count > 0) is prepared
    finally:
        engine.dispose()


def _engine_urls(monkeypatch, module):
    """Record the URL each create_engine call of `module` receives."""
    seen = []

    def fake(url, *args, **kwargs):
        seen.append(make_url(str(url)))
        raise RuntimeError('recorded')

    monkeypatch.setattr(module, 'create_engine', fake)
    return seen


def test_the_application_connects_with_psycopg():
    env = dict(os.environ, DATABASE_URL='postgresql://u:p@db.invalid/ucm')
    out = subprocess.run(
        [sys.executable, '-c',
         'from config.settings import Config; print(Config.SQLALCHEMY_DATABASE_URI)'],
        cwd=BACKEND, env=env, capture_output=True, text=True, check=True)
    assert out.stdout.strip().splitlines()[-1] == 'postgresql+psycopg://u:p@db.invalid/ucm'


def test_the_migration_runner_connects_with_psycopg(monkeypatch):
    import migration_runner

    seen = _engine_urls(monkeypatch, migration_runner)
    monkeypatch.setenv('DATABASE_URL', 'postgresql://u:p@db.invalid/ucm')
    assert migration_runner.run_all_migrations() is False
    assert seen and seen[0].drivername == 'postgresql+psycopg'


def test_the_connection_test_uses_psycopg(monkeypatch):
    from services.database_admin import status

    seen = _engine_urls(monkeypatch, status)
    ok, _ = status.test_connection('postgresql://u:p@db.invalid/ucm')
    assert not ok
    assert seen and seen[0].drivername == 'postgresql+psycopg'


def test_the_migration_target_uses_psycopg(app, monkeypatch):
    from services.database_admin import migration

    seen = _engine_urls(monkeypatch, migration)
    with app.app_context():
        migration.bootstrap_auth_to_target('postgresql://u:p@db.invalid/ucm')
    assert seen and seen[0].drivername == 'postgresql+psycopg'


def test_the_migration_data_target_uses_psycopg(app, monkeypatch):
    from services.database_admin import migration

    seen = _engine_urls(monkeypatch, migration)
    monkeypatch.setattr(migration, 'test_connection', lambda url: (True, ''))
    with app.app_context():
        migration.migrate_data('postgresql://u:p@db.invalid/ucm')
    assert seen and seen[0].drivername == 'postgresql+psycopg'


@pytest.mark.parametrize('url', ['postgresql+psycopg://u:p@db.invalid/ucm',
                                 'postgresql+psycopg2://u:p@db.invalid/ucm'])
def test_the_connection_test_accepts_an_explicit_driver(url, monkeypatch):
    from services.database_admin import status

    seen = _engine_urls(monkeypatch, status)
    status.test_connection(url)
    assert seen and seen[0].drivername == 'postgresql+psycopg'


@pytest.mark.parametrize('url', [
    'postgresql://u:p@db/ucm', 'postgres://u:p@db/ucm',
    'postgresql+psycopg://u:p@db/ucm', 'postgresql+psycopg2://u:p@db/ucm',
])
def test_every_postgresql_spelling_is_seen_as_postgresql(url, monkeypatch):
    import migration_runner
    from services import log_bundle

    assert migration_runner._is_postgres(url)
    monkeypatch.setenv('DATABASE_URL', url)
    assert 'DB backend: postgresql' in log_bundle._system_diagnostic()


def test_a_psycopg2_url_starts_the_application_on_psycopg():
    env = dict(os.environ, DATABASE_URL='postgresql+psycopg2://u:p@db.invalid/ucm')
    out = subprocess.run(
        [sys.executable, '-c',
         'from config.settings import Config; print(Config.SQLALCHEMY_DATABASE_URI)'],
        cwd=BACKEND, env=env, capture_output=True, text=True, check=True)
    assert out.stdout.strip().splitlines()[-1] == 'postgresql+psycopg://u:p@db.invalid/ucm'


@pytest.mark.postgres
def test_a_psycopg2_url_connects_without_psycopg2():
    url = os.environ.get('UCM_TEST_PG_URL', '')
    if not url:
        pytest.skip('UCM_TEST_PG_URL not set')
    from sqlalchemy import create_engine, text
    engine = create_engine(sqlalchemy_url(url.replace('postgresql://', 'postgresql+psycopg2://', 1)))
    try:
        with engine.connect() as conn:
            assert conn.execute(text('SELECT 1')).scalar() == 1
            assert engine.dialect.driver == 'psycopg'
    finally:
        engine.dispose()


def test_a_postgres_url_is_a_postgresql_database():
    env = dict(os.environ, DATABASE_URL='postgres://u:p@db.invalid/ucm')
    out = subprocess.run(
        [sys.executable, '-c',
         'from config.settings import Config; print(Config.DATABASE_TYPE)'],
        cwd=BACKEND, env=env, capture_output=True, text=True, check=True)
    assert out.stdout.strip().splitlines()[-1] == 'postgresql'

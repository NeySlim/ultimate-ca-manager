"""Every PostgreSQL URL reaches psycopg 3, which binds parameters on the
server: postgresql+psycopg2://, from older guides, included."""
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


def test_a_psycopg2_scheme_is_normalised_once_without_a_warning(monkeypatch, caplog):
    monkeypatch.setattr(db_url, '_normalised', [])
    with caplog.at_level(logging.INFO, logger='utils.db_url'):
        sqlalchemy_url('postgresql+psycopg2://u:p@db/ucm')
        sqlalchemy_url('postgresql+psycopg2://u:p@db/ucm')
    records = [r for r in caplog.records if r.name == 'utils.db_url']
    assert [(r.levelno, 'normalised' in r.getMessage()) for r in records] == [(logging.INFO, True)]


def test_a_bare_url_logs_nothing(monkeypatch, caplog):
    monkeypatch.setattr(db_url, '_normalised', [])
    with caplog.at_level(logging.DEBUG, logger='utils.db_url'):
        sqlalchemy_url('postgresql://u:p@db/ucm')
        sqlalchemy_url('postgresql+psycopg://u:p@db/ucm')
    assert not [r for r in caplog.records if r.name == 'utils.db_url']


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

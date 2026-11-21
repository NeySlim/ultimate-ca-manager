"""The application pool on PostgreSQL survives a server restart or a partition: every
checkout is pinged, and a dead peer or an unreachable server is given up within seconds."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from services import scheduler_leader
from utils import db_url

BACKEND = Path(__file__).resolve().parent.parent
_PG = 'postgresql://u:p@db.invalid/ucm'


def test_postgresql_pings_each_checkout_with_the_leader_timeouts():
    options = db_url.postgres_engine_options(_PG, {})
    assert options['pool_pre_ping'] is True
    assert options['connect_args'] == scheduler_leader._KEEPALIVE_ARGS
    assert options['connect_args']['connect_timeout'] > 0 and options['connect_args']['keepalives'] == 1


def test_data_a_silent_server_never_acknowledges_ends_the_connection():
    """A query sent to a server that dropped off the network fails within 30 s instead of the
    kernel's retransmission timeout (about 15 minutes), so the pool and readiness recover."""
    assert db_url.postgres_engine_options(_PG, {})['connect_args']['tcp_user_timeout'] == 30000


def test_a_setting_in_the_url_is_left_to_the_url():
    args = db_url.postgres_engine_options(f'{_PG}?connect_timeout=3&keepalives_idle=5', {})['connect_args']
    assert 'connect_timeout' not in args and 'keepalives_idle' not in args
    assert args['keepalives_count'] == 3


def test_the_prepare_threshold_still_applies():
    args = db_url.postgres_engine_options(_PG, {'UCM_PG_PREPARE_THRESHOLD': '0'})['connect_args']
    assert args['prepare_threshold'] is None and args['keepalives'] == 1


def test_sqlite_gets_nothing():
    assert db_url.postgres_engine_options('sqlite:////tmp/ucm.db', {}) == {}


def test_the_application_engine_takes_them():
    env = dict(os.environ, DATABASE_URL=_PG)
    env.pop('UCM_PG_PREPARE_THRESHOLD', None)
    out = subprocess.run(
        [sys.executable, '-c', 'from config.settings import Config; o = Config.SQLALCHEMY_ENGINE_OPTIONS; '
         'print(o.get("pool_pre_ping"), o.get("connect_args", {}).get("connect_timeout"))'],
        cwd=BACKEND, env=env, capture_output=True, text=True, check=True)
    assert out.stdout.strip().splitlines()[-1] == 'True 10'


@pytest.mark.postgres
def test_a_pooled_connection_killed_by_the_server_is_replaced_unseen():
    url = os.environ.get('UCM_TEST_PG_URL', '')
    if not url:
        pytest.skip('UCM_TEST_PG_URL not set')
    from sqlalchemy import create_engine, text
    engine = create_engine(db_url.sqlalchemy_url(url), pool_size=1, max_overflow=0,
                           **db_url.postgres_engine_options(url, {}))
    admin = create_engine(db_url.sqlalchemy_url(url))
    try:
        with engine.connect() as conn:
            pid = conn.execute(text('SELECT pg_backend_pid()')).scalar()
        with admin.connect() as other:
            # The timeout makes the call wait until the backend is gone
            assert other.execute(text('SELECT pg_terminate_backend(:p, 10000)'), {'p': pid}).scalar() is True
            other.commit()
        # The pool hands its one connection out again: the ping finds it dead and reconnects
        with engine.connect() as conn:
            assert conn.execute(text('SELECT pg_backend_pid()')).scalar() != pid
    finally:
        engine.dispose()
        admin.dispose()


@pytest.mark.parametrize('url,label', [
    ('postgresql://ucm:s3cret@db.example:5432/ucmprod?sslmode=require', 'PostgreSQL, database ucmprod'),
    ('postgresql+psycopg://ucm@db/pki', 'PostgreSQL, database pki'),
    (None, 'SQLite, /data/ucm.db'),
])
def test_the_start_names_the_database_in_use(url, label):
    """Neither the address nor the password; the SQLite path only when SQLite is used."""
    assert db_url.database_label(url, '/data/ucm.db') == label

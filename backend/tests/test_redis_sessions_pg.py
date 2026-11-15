"""On PostgreSQL, Redis takes precedence over the session table (docs/HA.md, REDIS.md).

Needs both UCM_TEST_PG_URL and redis-server; not marked needs_redis, so a run without
PostgreSQL skips it even where Redis is required.
"""
import os
import uuid

import pytest

from tests.redis_support import REDIS_SERVER
from tests.test_redis_sessions import PREFIX, _store_in_fresh_process

PG_URL = os.getenv('UCM_TEST_APP_PG_URL') or os.getenv('UCM_TEST_PG_URL')

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not PG_URL, reason='no PostgreSQL URL for the Redis-over-SQL priority test'),
    pytest.mark.skipif(not REDIS_SERVER, reason='redis-server not installed'),
]


@pytest.fixture
def store(redis_server):
    client = redis_server.client()
    client.flushdb()
    yield client
    client.flushdb()


def test_on_postgresql_redis_wins_over_the_session_table(store, redis_server, tmp_path):
    """docs/HA.md: sessions in PostgreSQL, in Redis when REDIS_URL is set."""
    import psycopg
    schema = f'ucm_redis_{uuid.uuid4().hex[:8]}'
    admin = psycopg.connect(PG_URL, autocommit=True)
    admin.execute(f'CREATE SCHEMA "{schema}"')
    try:
        sep = '&' if '?' in PG_URL else '?'
        store_type, status, sid, rows, files = _store_in_fresh_process(
            tmp_path, redis_server.url(), f'{PG_URL}{sep}options=-csearch_path%3D{schema}')
        assert (store_type, status) == ('redis', 200)
        assert sid and store.exists(PREFIX + sid)
        assert not rows and files == [], 'neither the session table nor a file holds a session'
    finally:
        admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        admin.close()

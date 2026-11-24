"""A node's SQL session store holds one pool of its own, reused by every request and closed
with its application.

Counted in pg_stat_activity under the nodes' application_name: requests never add a
connection per call, and disposing the nodes leaves none open, so a run that builds many
nodes on one PostgreSQL stays under max_connections.
"""
import time

import pytest

from tests.test_factor_change_sessions import (  # noqa: F401 (fixture)
    PG_URL, _cleanup, _drop_session_table_from_metadata, _make_user, _open_session, _signed_in,
    pg_nodes)

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not PG_URL, reason='no PostgreSQL URL for the session store pool test'),
]


def _connections(name):
    import psycopg
    with psycopg.connect(PG_URL, autocommit=True) as admin:
        return admin.execute('SELECT count(*) FROM pg_stat_activity WHERE application_name = %s',
                             (name,)).fetchone()[0]


def _settled(name, expected, wait=10.0):
    """The count once a closed connection's backend has gone (it exits just after the close)."""
    deadline = time.monotonic() + wait
    while True:
        count = _connections(name)
        if count == expected or time.monotonic() > deadline:
            return count
        time.sleep(0.2)


def test_requests_reuse_the_store_pool_instead_of_opening_connections(monkeypatch):
    with pg_nodes(monkeypatch) as (first, second, name):
        user = _make_user(first)
        try:
            client = _open_session(first, user)
            assert _signed_in(client)
            opened = _connections(name)
            assert opened > 0, 'the nodes do not carry the application_name counted here'
            for _ in range(20):
                assert _signed_in(client)
            assert _connections(name) <= opened
        finally:
            _cleanup(first, user)


def test_disposing_the_nodes_closes_every_connection_they_opened(monkeypatch):
    with pg_nodes(monkeypatch) as (first, second, name):
        user = _make_user(first)
        try:
            for node in (first, second):
                assert _signed_in(_open_session(node, user))
            assert _connections(name) > 0
        finally:
            _cleanup(first, user)
    # The nodes are still referenced here: only an explicit close ends their connections
    assert _settled(name, 0) == 0

"""SQLite: a lock that a tolerant read or write swallows does not turn an unrelated 500 into
the 503 of a request that met a lock (utils/sqlite_wait.lock_not_marked).

A second sqlite3 connection really writes, or holds the file, as in
tests/test_restore_held_database.py.
"""
import json
import sqlite3

from services import jobs
from tests.test_restore_held_database import (  # noqa: F401 (fixture)
    PASSWORD, _admin_user, _api_key, busy_app, writing)

URL = '/api/v2/system/jobs'


def _broken(monkeypatch, before=None):
    def list_jobs(*a, **k):
        if before is not None:
            before()
        raise RuntimeError('not a lock')
    monkeypatch.setattr(jobs, 'list_jobs', list_jobs)


def test_an_api_key_whose_last_use_meets_a_writer_keeps_its_500(busy_app, monkeypatch):
    """The last-use update is telemetry: the lock it swallows is not the request's."""
    app, path = busy_app
    user = _admin_user(app)
    key = _api_key(app, user['id'], 3600)
    _broken(monkeypatch)
    with writing(path):
        failed = app.test_client().get(URL, headers={'X-API-Key': key})
    assert failed.status_code == 500, failed.data


def test_an_hsts_read_that_meets_a_lock_keeps_the_500(busy_app, monkeypatch):
    """The HSTS settings are read after the route: a lock taken meanwhile is not its cause."""
    app, path = busy_app
    user = _admin_user(app)
    client = app.test_client()
    r = client.post('/api/v2/auth/login',
                    data=json.dumps({'username': user['username'], 'password': PASSWORD}),
                    content_type='application/json')
    assert r.status_code == 200, r.data
    holder = sqlite3.connect(path, timeout=0, isolation_level=None)
    _broken(monkeypatch, before=lambda: holder.execute('BEGIN EXCLUSIVE'))
    try:
        failed = client.get(URL)
    finally:
        if holder.in_transaction:
            holder.execute('ROLLBACK')
        holder.close()
    assert failed.status_code == 500, failed.data
    assert 'Strict-Transport-Security' not in failed.headers


def _mark():
    from flask import g, request
    from utils import sqlite_wait
    setattr(g, sqlite_wait._LOCK_MET, request._get_current_object())


def _marked():
    from flask import g, request
    from utils import sqlite_wait
    return g.get(sqlite_wait._LOCK_MET) is request._get_current_object()


def test_a_lock_that_leaves_the_block_still_marks_the_request(app):
    import pytest
    from utils.sqlite_wait import lock_not_marked
    with app.test_request_context('/'):
        with pytest.raises(RuntimeError):
            with lock_not_marked():
                _mark()
                raise RuntimeError('database is locked')
        assert _marked()


def test_a_mark_made_before_the_block_stays(app):
    from utils.sqlite_wait import lock_not_marked
    with app.test_request_context('/'):
        _mark()
        with lock_not_marked():
            pass
        assert _marked()

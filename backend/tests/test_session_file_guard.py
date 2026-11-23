"""File session store: a guarded write and a removal of the same record never interleave.

Each test stops a save between its existence check and its write, runs a removal in
another thread meanwhile, and checks that the removal waited and still wins.
"""
import os
import subprocess
import sys
import textwrap
import threading
import time

import pytest

from tests.test_factor_change_sessions import _cleanup, _make_user, _open_session

PAUSE = 0.3


def _remove_ordinarily(app, store_id):
    app.session_interface._delete_session(store_id)


def _remove_by_restore(app, store_id):
    from services.backup.restore.invalidate import _remove_session_files
    with app.app_context():
        assert _remove_session_files() >= 1


def _remove_by_purge(app, store_id):
    from services.session_cleanup_task import SessionCleanupTask
    with app.app_context():
        SessionCleanupTask.execute()


@pytest.fixture
def file_app(app):
    if app.config.get('SESSION_TYPE') != 'filesystem':
        pytest.skip('file session store only')
    iface = app.session_interface
    assert os.path.samefile(app.config['SESSION_FILE_DIR'], iface.cache._path)
    return app


def _save_with_a_removal_in_between(app, cookie, remove, before_removal=None):
    """Saves the session the cookie opens, running ``remove`` once the save has seen its
    record; returns whether the record was still on disk when the save went on."""
    from flask import session as flask_session
    iface = app.session_interface
    sid = iface._unsign(app, cookie) if iface.use_signer else cookie
    store_id = iface._get_store_id(sid)
    path = iface.cache._get_filename(store_id)
    seen = {}
    original_get = iface.cache.get

    def get(key):
        stored = original_get(key)
        if stored is not None and key == store_id and 'thread' not in seen:
            if before_removal:
                before_removal(path)
            seen['thread'] = threading.Thread(target=remove, args=(app, store_id))
            seen['thread'].start()
            seen['thread'].join(PAUSE)
            seen['present_meanwhile'] = os.path.exists(path)
        return stored

    try:
        with app.test_request_context('/api/v2/account/profile',
                                      headers={'Cookie': f'session={cookie}'}):
            flask_session['probe'] = time.time()
            # Installed once the session is open: the read it watches is the save's own
            iface.cache.get = get
            iface.save_session(app, flask_session, app.response_class())
    finally:
        vars(iface.cache).pop('get', None)
    assert 'thread' in seen, 'the save never checked its record'
    seen['thread'].join(10)
    assert not seen['thread'].is_alive()
    return seen['present_meanwhile'], store_id


@pytest.mark.parametrize('remove', [_remove_ordinarily, _remove_by_restore],
                         ids=['sign-out', 'restore'])
def test_a_removal_during_a_save_is_never_undone(file_app, remove):
    user = _make_user(file_app)
    try:
        c = _open_session(file_app, user)
        cookie = c.get_cookie('session').value
        present, store_id = _save_with_a_removal_in_between(file_app, cookie, remove)
        assert present, 'the removal ran between the check and the write'
        assert not file_app.session_interface._record_exists(store_id)
        stale = file_app.test_client()
        stale.set_cookie('session', cookie)
        assert stale.get('/api/v2/account/profile').status_code == 401
    finally:
        _cleanup(file_app, user)


def test_the_purge_waits_and_keeps_a_session_written_meanwhile(file_app):
    user = _make_user(file_app)
    try:
        c = _open_session(file_app, user)
        cookie = c.get_cookie('session').value

        def age(path):
            old = time.time() - 10 * 86400
            os.utime(path, (old, old))

        present, store_id = _save_with_a_removal_in_between(
            file_app, cookie, _remove_by_purge, before_removal=age)
        assert present, 'the purge ran between the check and the write'
        assert file_app.session_interface._record_exists(store_id)
        assert c.get('/api/v2/account/profile').status_code == 200
    finally:
        _cleanup(file_app, user)


def test_a_save_that_cannot_take_the_lock_writes_nothing(file_app, monkeypatch):
    from flask import session as flask_session
    from utils.session_store import HELD, session_files_lock
    iface = file_app.session_interface
    monkeypatch.setattr(iface, 'lock_wait', 0.05)
    user = _make_user(file_app)
    try:
        c = _open_session(file_app, user)
        cookie = c.get_cookie('session').value
        sid = iface._unsign(file_app, cookie) if iface.use_signer else cookie
        store_id = iface._get_store_id(sid)
        with session_files_lock(iface.cache._path, exclusive=True) as state:
            assert state == HELD
            with file_app.test_request_context('/api/v2/account/profile',
                                               headers={'Cookie': f'session={cookie}'}):
                flask_session['probe'] = 'written'
                iface.save_session(file_app, flask_session, file_app.response_class())
        assert 'probe' not in iface.cache.get(store_id)
    finally:
        _cleanup(file_app, user)


_GEVENT_PROBE = textwrap.dedent('''
    from gevent import monkey
    monkey.patch_all()
    import fcntl, os, sys, tempfile
    from utils.session_store import session_files_lock
    parent = tempfile.mkdtemp()
    directory = os.path.join(parent, 'sessions')
    os.mkdir(directory)
    for exclusive in (False, True):
        with session_files_lock(directory, exclusive) as state:
            assert state == 'held', state
        for path in (directory, parent):  # the store and its turnstile
            fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                sys.exit('%s still locked after the with, exclusive=%s' % (path, exclusive))
            finally:
                os.close(fd)
    os.rmdir(directory)
    os.rmdir(parent)
''')


def test_the_store_lock_is_free_once_released_under_gevent():
    # A subprocess: patch_all() would otherwise patch the whole test run
    backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    done = subprocess.run([sys.executable, '-c', _GEVENT_PROBE], cwd=backend,
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr or done.stdout


def test_a_restore_removes_a_session_file_written_before_it_held_the_lock(file_app, monkeypatch):
    from contextlib import contextmanager
    from utils import session_store
    from services.backup.restore.invalidate import _remove_session_files
    directory = file_app.session_interface.cache._path
    late = os.path.join(directory, 'written-before-the-lock')
    real_lock = session_store.session_files_lock

    @contextmanager
    def lock_after_a_write(path, exclusive, *args, **kwargs):
        with open(late, 'wb') as handle:
            handle.write(b'session')
        with real_lock(path, exclusive, *args, **kwargs) as state:
            yield state

    monkeypatch.setattr(session_store, 'session_files_lock', lock_after_a_write)
    with file_app.app_context():
        _remove_session_files()
    assert not os.path.exists(late)


def test_a_removal_is_not_starved_by_back_to_back_saves(tmp_path):
    from utils.session_store import HELD, session_files_lock
    directory = tmp_path / 'sessions'
    directory.mkdir()
    stop = threading.Event()

    def save_again_and_again():
        while not stop.is_set():
            with session_files_lock(str(directory), exclusive=False, wait=5.0):
                time.sleep(0.01)

    savers = [threading.Thread(target=save_again_and_again) for _ in range(4)]
    for i, saver in enumerate(savers):
        saver.start()
        time.sleep(0.0025)  # staggered: the shared lock is never free between two saves
    try:
        states = []
        for _ in range(3):
            with session_files_lock(str(directory), exclusive=True, wait=1.0) as state:
                states.append(state)
    finally:
        stop.set()
        for saver in savers:
            saver.join(10)
    assert states == [HELD] * 3, states


def test_a_removal_without_the_lock_still_removes_and_says_so(file_app, monkeypatch, caplog):
    import logging
    from utils.session_store import HELD, session_files_lock
    iface = file_app.session_interface
    monkeypatch.setattr(iface, 'lock_wait', 0.05)
    user = _make_user(file_app)
    try:
        cookie = _open_session(file_app, user).get_cookie('session').value
        sid = iface._unsign(file_app, cookie) if iface.use_signer else cookie
        store_id = iface._get_store_id(sid)
        with session_files_lock(iface.cache._path, exclusive=False) as state:
            assert state == HELD
            with caplog.at_level(logging.WARNING, logger='utils.session_store'):
                iface._delete_session(store_id)
        assert not iface._record_exists(store_id)
        assert any('without its lock (busy)' in r.getMessage() for r in caplog.records)
    finally:
        _cleanup(file_app, user)


@pytest.mark.parametrize('remove', ['restore', 'purge'])
def test_a_store_wide_removal_without_the_lock_says_so(file_app, monkeypatch, caplog, remove):
    import logging
    from utils import session_store
    from utils.session_store import HELD, session_files_lock
    real_lock = session_store.session_files_lock
    monkeypatch.setattr(session_store, 'session_files_lock',
                        lambda directory, exclusive, wait=2.0: real_lock(directory, exclusive, 0.05))
    directory = file_app.session_interface.cache._path
    stale = os.path.join(directory, 'stale-session')
    with open(stale, 'wb') as handle:
        handle.write(b'session')
    old = time.time() - 10 * 86400
    os.utime(stale, (old, old))
    with session_files_lock(directory, exclusive=False) as state:
        assert state == HELD
        with caplog.at_level(logging.WARNING):
            if remove == 'restore':
                _remove_by_restore(file_app, None)
            else:
                _remove_by_purge(file_app, None)
    assert not os.path.exists(stale)
    assert any('without' in r.getMessage() and 'lock' in r.getMessage() for r in caplog.records)

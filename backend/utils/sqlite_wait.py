"""SQLite lock waits that never stop the web worker.

sqlite3 waits for a lock in its own busy handler, inside C: under gevent that stops every
request of the worker, probes included. In the web server (its requests, and every greenlet of
the gunicorn worker) a connection to a WAL database waits at most IN_C_MS in C and retries in
Python, where time.sleep yields, WEB_LOCK_WAIT_SECONDS in all per request. While a single node's
restore gate is up, every connection does so for REQUEST_LOCK_WAIT_SECONDS, and not at all once
the restore's transaction holds the database. Elsewhere (the scheduler process) sqlite3 waits
in C, as a thread can. A request that met a lock and would answer 500 answers 503.
"""
import contextlib
import logging
import sqlite3
import time

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import Pool

logger = logging.getLogger(__name__)

# What a request may wait for the lock, in Python, while the gate is up but the database not held
REQUEST_LOCK_WAIT_SECONDS = 1.0
# What a request of the web server may wait for it otherwise: sqlite3's default busy timeout
WEB_LOCK_WAIT_SECONDS = 5.0
IN_C_MS = 20
RETRY_FIRST, RETRY_MAX = 0.01, 0.1
BUSY_RETRY_AFTER_SECONDS = 5
_BUSY_INFO = 'ucm_busy_timeout'
_LOCK_MET = 'ucm_lock_met'
_WAITED = 'ucm_lock_waited'
_BUILT = 'ucm_lock_response_built'
_KEPT = 'ucm_500_kept'
_WAL = 'ucm_wal'
SQLITE_BUSY_SNAPSHOT = getattr(sqlite3, 'SQLITE_BUSY_SNAPSHOT', 517)
BUSY_MESSAGE = 'The database is busy with another write: retry shortly.'


def is_locked(exc) -> bool:
    """SQLITE_BUSY or SQLITE_LOCKED, raw or wrapped by SQLAlchemy."""
    orig = getattr(exc, 'orig', exc)
    if not isinstance(orig, sqlite3.OperationalError):
        return False
    code = getattr(orig, 'sqlite_errorcode', None)
    if code is not None:
        return code & 0xFF in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
    return 'database is locked' in str(orig) or 'database table is locked' in str(orig)


def is_busy_snapshot(exc) -> bool:
    """WAL: the transaction read a snapshot another writer has replaced since. Only a new
    transaction can write; the same statement fails again however long it waits."""
    orig = getattr(exc, 'orig', exc)
    return getattr(orig, 'sqlite_errorcode', None) == SQLITE_BUSY_SNAPSHOT


# The web worker's application: its own threads (greenlets) wait like its requests
_WEB_WORKER = []


def serve_web_worker(app):
    """gunicorn post_worker_init: every query of this process, not only its requests."""
    _WEB_WORKER[:] = [app]


def window():
    """None outside a restore gate seen by the web worker; else 'held' or 'gate'."""
    from flask import current_app, has_request_context
    from services import cluster_maintenance
    if has_request_context():
        app = current_app
    elif _WEB_WORKER:
        app = _WEB_WORKER[0]
        from utils.ha import ha_enabled
        if not ha_enabled():
            cluster_maintenance.observe_local(app)  # no request may have read the gate yet
    else:
        return None
    view = app.extensions.get(cluster_maintenance.EXTENSION)
    if view is None or not view.active() or \
            (view.row or {}).get('reason') != cluster_maintenance.LOCAL_REASON:
        return None
    return 'held' if cluster_maintenance.held_locally(view) else 'gate'


def _mode(info):
    """How a statement on this connection waits for a lock: 'held' (never), 'gate' (shortly),
    'web' (in Python), None (in sqlite3's busy handler)."""
    state = window()
    if state is not None:
        return state
    from flask import has_request_context
    if info.get(_WAL) and (_WEB_WORKER or has_request_context()):
        return 'web'
    return None


def _on_checkout(dbapi_connection, record, proxy):
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    info = record.info
    if _BUSY_INFO not in info:
        info[_BUSY_INFO + '_default'] = dbapi_connection.execute('PRAGMA busy_timeout').fetchone()[0]
        info[_BUSY_INFO] = info[_BUSY_INFO + '_default']
        # In WAL a commit never waits for a lock (its writer holds it): every wait is a
        # statement's, which Python can retry. Elsewhere a commit needs the handler in C.
        info[_WAL] = dbapi_connection.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
    wanted = IN_C_MS if _mode(info) else info[_BUSY_INFO + '_default']
    if info[_BUSY_INFO] != wanted:
        dbapi_connection.execute(f'PRAGMA busy_timeout = {int(wanted)}')
        info[_BUSY_INFO] = wanted


def _execute(cursor, statement, parameters, context, many=False):
    if context is None or context.dialect.name != 'sqlite':
        return None
    state = _mode(context.root_connection.connection.info)
    if state is None:
        return None
    from flask import g, has_app_context, has_request_context
    run = cursor.executemany if many else cursor.execute
    budget = REQUEST_LOCK_WAIT_SECONDS if state == 'gate' else WEB_LOCK_WAIT_SECONDS
    shared = has_request_context() or (state != 'web' and has_app_context())
    delay, waited_here = RETRY_FIRST, 0.0
    while True:
        changes = cursor.connection.total_changes
        tried = time.monotonic()
        try:
            if parameters is None:
                run(statement)
            else:
                run(statement, parameters)
            return True
        except sqlite3.OperationalError as exc:
            # Never again: a stale snapshot, nor a statement that already wrote rows (an
            # executemany stopped partway would write them twice)
            if not is_locked(exc) or state == 'held' or is_busy_snapshot(exc) \
                    or cursor.connection.total_changes != changes:
                raise
            # One budget per request, shared by its statements: the time they spent on locks,
            # never a window that closes some time after the first lock met
            spent = time.monotonic() - tried
            if shared:
                waited = g.get(_WAITED, 0.0) + spent
                setattr(g, _WAITED, waited)
            else:
                waited = waited_here = waited_here + spent
            if waited + delay > budget:
                raise
        slept = time.monotonic()
        time.sleep(delay)  # gevent: the other requests run meanwhile
        slept = time.monotonic() - slept
        if shared:
            setattr(g, _WAITED, g.get(_WAITED, 0.0) + slept)
        else:
            waited_here += slept
        delay = min(delay * 2, RETRY_MAX)


def _do_execute(cursor, statement, parameters, context):
    return _execute(cursor, statement, parameters, context)


def _do_execute_no_params(cursor, statement, context):
    return _execute(cursor, statement, None, context)


def _do_executemany(cursor, statement, parameters, context):
    return _execute(cursor, statement, parameters, context, many=True)


def _on_error(context):
    """Marks the request that met a SQLite lock, even if its route catches the error."""
    if not is_locked(context.original_exception):
        return
    from flask import g, has_request_context, request
    if has_request_context():
        setattr(g, _LOCK_MET, request._get_current_object())


@contextlib.contextmanager
def lock_not_marked():
    """A lock met inside and swallowed by the block does not mark the request: its 500, if
    any, has another cause. A lock error that leaves the block still marks it."""
    from flask import g, has_app_context
    if not has_app_context():
        yield
        return
    before = g.get(_LOCK_MET)
    yield
    if before is None:
        g.pop(_LOCK_MET, None)
    else:
        setattr(g, _LOCK_MET, before)


_installed = []


def install():
    """Once per process, on every engine and pool."""
    if _installed:
        return
    _installed.append(True)
    event.listen(Pool, 'checkout', _on_checkout)
    event.listen(Engine, 'do_execute', _do_execute)
    event.listen(Engine, 'do_execute_no_params', _do_execute_no_params)
    event.listen(Engine, 'do_executemany', _do_executemany)
    event.listen(Engine, 'handle_error', _on_error)


def watch_response():
    """before_request: freeze, when the route's response is built, whether a 500 met a lock.
    A lock met afterwards (headers, session store, audit) never turns that 500 into a 503."""
    from flask import after_this_request

    @after_this_request
    def _built(response):
        from flask import g, request
        # Once: a failed response processing runs the hooks again on the error's answer
        if _BUILT not in g and response.status_code == 500:
            setattr(g, _BUILT, g.get(_LOCK_MET) is request._get_current_object())
        return response


def _met_lock():
    """Whether the request met a lock: as frozen when its 500 was built, else as now."""
    from flask import g, request
    built = g.get(_BUILT)
    if built is not None:
        return built
    return g.get(_LOCK_MET) is request._get_current_object()


def locked_refusal(exc):
    """503 with Retry-After for a request that met a lock it may not wait for; else None."""
    if not is_locked(exc):
        return None
    return _refusal()


def keep_this_500():
    """The request's 500 reports a committed change and may carry a secret shown once (new
    recovery codes): never rewritten into a 503, whatever lock the request met."""
    from flask import g
    setattr(g, _KEPT, True)


def answer_locked_500(response):
    """after_request: a 500 from a request that met a SQLite lock, whatever route caught it,
    becomes the 503 with Retry-After of locked_refusal, rewritten in place (headers kept)."""
    from flask import g
    if response.status_code != 500 or g.get(_KEPT) or not _met_lock():
        return response
    refused = _refusal(serve_job=False)
    response.set_data(refused.get_data())
    response.status_code = refused.status_code
    response.headers['Content-Type'] = refused.headers['Content-Type']
    response.headers['Retry-After'] = refused.headers['Retry-After']
    return response


def _refusal(serve_job=True):
    from models import db
    try:
        db.session.rollback()
    except Exception:  # noqa: BLE001 - the answer goes out whatever the rollback says
        pass
    from services import cluster_maintenance
    if window():
        if serve_job:
            from auth.restore_hold import answer_without_database
            answer = answer_without_database()
            if answer is not None:
                return answer
        return cluster_maintenance.refusal(message=cluster_maintenance.HELD_MESSAGE)
    from flask import jsonify
    from utils.response import PROBLEM_CONTENT_TYPE, build_problem
    response = jsonify(build_problem(BUSY_MESSAGE, 503))
    response.mimetype = PROBLEM_CONTENT_TYPE
    response.status_code = 503
    response.headers['Retry-After'] = str(BUSY_RETRY_AFTER_SECONDS)
    return response

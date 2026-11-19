"""SQLite lock waits that never stop the web worker.

sqlite3 waits for a lock in its own busy handler, inside C: under gevent that stops every
request of the worker, probes included. While a single node's restore gate is up, a request's
connection waits at most IN_C_MS in C and retries in Python, where time.sleep yields; the
retries stop at once while the restore's transaction holds the database. Elsewhere (the
scheduler process, a job's thread, no gate) nothing changes.
"""
import logging
import sqlite3
import time

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import Pool

logger = logging.getLogger(__name__)

# What a request may wait for the lock, in Python, while the gate is up but the database not held
REQUEST_LOCK_WAIT_SECONDS = 1.0
IN_C_MS = 20
RETRY_FIRST, RETRY_MAX = 0.01, 0.1
BUSY_RETRY_AFTER_SECONDS = 5
_BUSY_INFO = 'ucm_busy_timeout'
_DEADLINE = 'ucm_lock_deadline'
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


def window():
    """None outside a restore gate seen by a request; else 'held' or 'gate'."""
    from flask import current_app, has_request_context
    if not has_request_context():
        return None
    from services import cluster_maintenance
    view = current_app.extensions.get(cluster_maintenance.EXTENSION)
    if view is None or not view.active() or \
            (view.row or {}).get('reason') != cluster_maintenance.LOCAL_REASON:
        return None
    return 'held' if cluster_maintenance.held_locally(view) else 'gate'


def _on_checkout(dbapi_connection, record, proxy):
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    info = record.info
    if _BUSY_INFO not in info:
        info[_BUSY_INFO + '_default'] = dbapi_connection.execute('PRAGMA busy_timeout').fetchone()[0]
        info[_BUSY_INFO] = info[_BUSY_INFO + '_default']
    wanted = IN_C_MS if window() else info[_BUSY_INFO + '_default']
    if info[_BUSY_INFO] != wanted:
        dbapi_connection.execute(f'PRAGMA busy_timeout = {int(wanted)}')
        info[_BUSY_INFO] = wanted


def _execute(cursor, statement, parameters, context, many=False):
    if context is None or context.dialect.name != 'sqlite':
        return None
    state = window()
    if state is None:
        return None
    from flask import g
    run = cursor.executemany if many else cursor.execute
    delay = RETRY_FIRST
    while True:
        try:
            if parameters is None:
                run(statement)
            else:
                run(statement, parameters)
            return True
        except sqlite3.OperationalError as exc:
            if not is_locked(exc):
                raise
            # One wait per request, shared by its statements, from the first lock it met
            deadline = g.setdefault(_DEADLINE, time.monotonic() + (
                0 if state == 'held' else REQUEST_LOCK_WAIT_SECONDS))
            if time.monotonic() + delay > deadline:
                raise
        time.sleep(delay)  # gevent: the other requests run meanwhile
        delay = min(delay * 2, RETRY_MAX)


def _do_execute(cursor, statement, parameters, context):
    return _execute(cursor, statement, parameters, context)


def _do_execute_no_params(cursor, statement, context):
    return _execute(cursor, statement, None, context)


def _do_executemany(cursor, statement, parameters, context):
    return _execute(cursor, statement, parameters, context, many=True)


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


def locked_refusal(exc):
    """503 with Retry-After for a request that met a lock it may not wait for; else None."""
    if not is_locked(exc):
        return None
    from models import db
    try:
        db.session.rollback()
    except Exception:  # noqa: BLE001 - the answer goes out whatever the rollback says
        pass
    from services import cluster_maintenance
    if window():
        return cluster_maintenance.refusal(message=cluster_maintenance.HELD_MESSAGE)
    from flask import jsonify
    from utils.response import PROBLEM_CONTENT_TYPE, build_problem
    response = jsonify(build_problem(BUSY_MESSAGE, 503))
    response.mimetype = PROBLEM_CONTENT_TYPE
    response.status_code = 503
    response.headers['Retry-After'] = str(BUSY_RETRY_AFTER_SECONDS)
    return response

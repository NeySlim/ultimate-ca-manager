"""SQL session store that keeps to its own transactions.

Flask-Session's stock SQL interface commits ``db.session``, so it would also
commit whatever a failed request left pending. This one owns a separate session
on its own engine, so saving a session never waits on the request's pool.
"""
import errno
import fcntl
import logging
import os
import random
import threading
import time
from contextlib import contextmanager
from datetime import datetime

from flask_session._utils import retry_query
from flask_session.filesystem import FileSystemSessionInterface
from flask_session.sqlalchemy import SqlAlchemySessionInterface
from flask import current_app
from itsdangerous import BadSignature, want_bytes
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


logger = logging.getLogger(__name__)

HELD, BUSY, UNSUPPORTED = 'held', 'busy', 'unsupported'


@contextmanager
def session_files_lock(directory, exclusive, wait=2.0):
    """flock on the session directory itself, which no removal can unlink: a guarded save
    holds it shared around its check and write, a removal exclusively. Taken without
    blocking and retried by sleeping, so a gevent worker yields instead of stalling."""
    try:
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        yield UNSUPPORTED
        return
    try:
        operation = (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB
        deadline = time.monotonic() + wait
        delay = 0.0005
        while True:
            try:
                fcntl.flock(fd, operation)
                state = HELD
                break
            except OSError as exc:
                if exc.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                    state = UNSUPPORTED  # e.g. an exclusive flock on an NFS directory
                    break
                if time.monotonic() >= deadline:
                    state = BUSY
                    break
                time.sleep(delay)
                delay = min(delay * 2, 0.05)
        yield state
    finally:
        os.close(fd)  # closing releases the lock


class KeepsRemovedRecordsGone:
    """A session opened from a stored record is saved only while that record exists:
    a renewal or revocation served meanwhile is never undone, and no cookie names the
    removed identifier."""

    def open_session(self, app, request):
        opened = super().open_session(app, request)
        sid = request.cookies.get(app.config['SESSION_COOKIE_NAME'])
        if sid and self.use_signer:
            try:
                sid = self._unsign(app, sid)
            except BadSignature:
                sid = None
        opened.stored_sid = sid if sid and opened.sid == sid else None
        return opened

    @staticmethod
    def _opened_from_store(session):
        stored = getattr(session, 'stored_sid', None)
        return stored is not None and stored == getattr(session, 'sid', None)

    def should_set_cookie(self, app, session):
        return not getattr(session, 'record_gone', False) and super().should_set_cookie(app, session)

    def save_session(self, app, session, response):
        # Emptied after its record was removed: the cookie now names the new identifier, keep it
        if (not session and session.modified and self._opened_from_store(session)
                and not self._record_exists(self._get_store_id(session.sid))):
            return
        super().save_session(app, session, response)


class GuardedFileSystemSessionInterface(KeepsRemovedRecordsGone, FileSystemSessionInterface):
    """Check and write are atomic only where the directory takes a flock: NFS refuses
    an exclusive one, and cachelib's capacity pruning, not a revocation, stays outside."""

    lock_wait = 2.0

    @classmethod
    def adopt(cls, app):
        app.session_interface.__class__ = cls

    def _record_exists(self, store_id):
        return self.cache.has(store_id)

    def _delete_session(self, store_id):
        with session_files_lock(self.cache._path, exclusive=True):
            super()._delete_session(store_id)

    def _upsert_session(self, session_lifetime, session, store_id):
        if not self._opened_from_store(session):
            return super()._upsert_session(session_lifetime, session, store_id)
        with session_files_lock(self.cache._path, False, self.lock_wait) as state:
            if state == BUSY:
                # A removal holds the store: writing without the lock could undo it
                logger.warning("Session not saved: the session store stayed locked")
                return
            if not self.cache.has(store_id):
                session.record_gone = True
                return
            super()._upsert_session(session_lifetime, session, store_id)


class IsolatedSqlSessionInterface(KeepsRemovedRecordsGone, SqlAlchemySessionInterface):

    _engine_lock = threading.Lock()

    @classmethod
    def adopt(cls, app):
        """Turns the interface Flask-Session installed into this one, purge hook included:
        the hook was bound before the change of class."""
        interface = app.session_interface
        interface.__class__ = cls
        hooks = app.before_request_funcs.get(None, [])
        for i, hook in enumerate(hooks):
            if getattr(hook, '__self__', None) is interface and hook.__name__ == '_cleanup_n_requests':
                hooks[i] = interface._cleanup_n_requests

    def _engine(self):
        """A pool apart from the request's, built per process so no fork shares a socket."""
        cached = getattr(self, '_own_engine', None)
        if cached is not None and cached[0] == os.getpid():
            return cached[1]
        main = self.client.engine
        if main.url.get_backend_name() == 'sqlite' and main.url.database in (None, '', ':memory:'):
            return main  # a second engine would open another, empty in-memory database
        with self._engine_lock:
            cached = getattr(self, '_own_engine', None)
            if cached is None or cached[0] != os.getpid():
                if cached is not None:
                    cached[1].dispose(close=False)  # the parent's sockets stay the parent's
                options = dict(current_app.config.get('SQLALCHEMY_ENGINE_OPTIONS') or {})
                self._own_engine = (os.getpid(), create_engine(main.url, **options))
            return self._own_engine[1]

    def _store(self):
        return sessionmaker(bind=self._engine())()

    @staticmethod
    def _writes_paused():
        # HA maintenance: a session row written now would outlive the restore's revocation
        from services.cluster_maintenance import blocks_writes
        return blocks_writes()

    def _purge_expired(self):
        if self._writes_paused():
            return
        model = self.sql_session_model
        with self._store() as s:
            s.query(model).filter(model.expiry <= datetime.utcnow()).delete(synchronize_session=False)
            s.commit()

    _delete_expired_sessions = retry_query()(_purge_expired)

    def _cleanup_n_requests(self):
        """The purge rides one request in N, a probe included: tried once, and a database
        that is away never fails that request."""
        if self.cleanup_n_requests and random.randint(0, self.cleanup_n_requests) == 0:
            try:
                self._purge_expired()
            except Exception as exc:
                current_app.logger.warning("Expired sessions not purged: %s", type(exc).__name__)

    @retry_query()
    def _retrieve_session_data(self, store_id):
        model = self.sql_session_model
        with self._store() as s:
            record = s.query(model).filter_by(session_id=store_id).first()
            if record and (record.expiry is None or record.expiry <= datetime.utcnow()):
                if not self._writes_paused():
                    s.delete(record)
                    s.commit()
                return None
            if record:
                return self.serializer.decode(want_bytes(record.data))
            return None

    @retry_query()
    def _record_exists(self, store_id):
        # An expired row counts too: the cookie then names that expired identifier, never
        # a renewed one, so deleting the row and the cookie is right.
        model = self.sql_session_model
        with self._store() as s:
            return s.query(model.id).filter_by(session_id=store_id).first() is not None

    @retry_query()
    def _delete_session(self, store_id):
        if self._writes_paused():
            return
        model = self.sql_session_model
        with self._store() as s:
            s.query(model).filter_by(session_id=store_id).delete()
            s.commit()

    @retry_query()
    def _upsert_session(self, session_lifetime, session, store_id):
        if self._writes_paused():
            return
        model = self.sql_session_model
        expiry = datetime.utcnow() + session_lifetime
        data = self.serializer.encode(session)
        with self._store() as s:
            if self._opened_from_store(session):
                # UPDATE only: a record removed since the request opened it stays removed
                updated = (s.query(model).filter_by(session_id=store_id)
                           .update({'data': data, 'expiry': expiry}, synchronize_session=False))
                s.commit()
                if not updated:
                    session.record_gone = True
                return
            record = s.query(model).filter_by(session_id=store_id).first()
            if record:
                record.data = data
                record.expiry = expiry
            else:
                s.add(model(session_id=store_id, data=data, expiry=expiry))
            s.commit()

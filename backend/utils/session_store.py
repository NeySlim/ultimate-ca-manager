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
from datetime import datetime, timedelta

from flask_session._utils import retry_query
from flask_session.filesystem import FileSystemSessionInterface
from flask_session.sqlalchemy import SqlAlchemySessionInterface
from flask import current_app
from itsdangerous import BadSignature, want_bytes
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


logger = logging.getLogger(__name__)

HELD, BUSY, UNSUPPORTED = 'held', 'busy', 'unsupported'


def _open_directory(path):
    try:
        return os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return None


def _flock_until(fd, operation, deadline):
    """HELD, BUSY once ``deadline`` passed, or UNSUPPORTED (e.g. an exclusive flock on NFS).
    Polled without blocking, so a gevent worker yields instead of stalling."""
    delay = 0.0005
    while True:
        try:
            fcntl.flock(fd, operation | fcntl.LOCK_NB)
            return HELD
        except OSError as exc:
            if exc.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                return UNSUPPORTED
            if time.monotonic() >= deadline:
                return BUSY
            time.sleep(delay)
            delay = min(delay * 2, 0.05)


def _release(fd, state):
    # Unlocked explicitly: gevent's os.close defers closing a directory to the next loop turn
    if state == HELD:
        fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)


@contextmanager
def session_files_lock(directory, exclusive, wait=2.0):
    """flock on the session directory itself, which no removal can unlink: a guarded save
    holds it shared around its check and write, a removal exclusively. Every taker first
    passes a turnstile, the parent directory held exclusively only while it waits, so saves
    arriving behind a waiting removal queue and never starve it. Without the lock, a
    removal goes on and logs it (removal_lock), a save that found it busy writes nothing."""
    fd = _open_directory(directory)
    if fd is None:
        yield UNSUPPORTED
        return
    deadline = time.monotonic() + wait
    state = gate_state = None
    gate = _open_directory(os.path.dirname(os.path.abspath(directory)))
    try:
        gate_state = _flock_until(gate, fcntl.LOCK_EX, deadline) if gate is not None else None
        state = _flock_until(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH, deadline)
        if gate is not None:
            _release(gate, gate_state)
            gate = None
        yield state
    finally:
        if gate is not None:
            _release(gate, gate_state)
        _release(fd, state)


@contextmanager
def removal_lock(directory, what, wait=2.0):
    """The exclusive lock of a removal, which goes on without it rather than leave a
    revoked session in place: that case is logged."""
    with session_files_lock(directory, True, wait) as state:
        if state != HELD:
            logger.warning("Session store %s: %s without its lock (%s), a save in flight "
                           "may write the removed session back", directory, what, state)
        yield state


# Attempts of a save that keeps the stored lock before it gives up (the lock already won)
LOCK_MERGE_ATTEMPTS = 5


def keep_stored_lock(session, stored):
    """A copy read before the lock was set takes the stored lock: only an unlock (a new
    identifier) or a sign-out (removal) lifts it, never a request saving what it read."""
    from auth.session_lock import LOCK_KEY, UNLOCK_2FA_KEY, is_locked
    if is_locked(session) or not stored or not is_locked(stored):
        return
    session[LOCK_KEY] = stored[LOCK_KEY]
    session.pop(UNLOCK_2FA_KEY, None)
    if UNLOCK_2FA_KEY in stored:
        session[UNLOCK_2FA_KEY] = stored[UNLOCK_2FA_KEY]


def carries_lock(session):
    from auth.session_lock import is_locked
    return is_locked(session)


# A move leaves this long, under the store prefix + MOVED_PREFIX + the old identifier, the new
# one: a sign-out opened before the move and saved after it ends the session there too. A
# generated identifier never holds a colon, and a cookie starting with MOVED_PREFIX opens nothing
MOVED_PREFIX = 'moved:'
MOVED_TTL = 300
MOVED_HOPS = 5


def moved_pointer(sid):
    """Value of a move's pointer: no user_id, so no count or listing reads it as a session."""
    return {'moved_to': sid}


def moved_target(value):
    return value.get('moved_to') if isinstance(value, dict) else None


def end_with_its_moves(session):
    """Empty the session as a sign-out does: its save removes the record and, when a renewal
    moved it meanwhile, the record it moved to."""
    session.clear()
    session.follows_moves = True


def _close_sockets(sids):
    from auth.session_start import close_session_sockets
    for sid in dict.fromkeys(sids):
        close_session_sockets(sid)


class KeepsRemovedRecordsGone:
    """A session opened from a stored record is saved only while that record exists:
    a renewal or revocation served meanwhile is never undone, and no cookie names the
    removed identifier. A lock stored meanwhile is kept (keep_stored_lock), also by a
    session that moves to a new identifier (rotate)."""

    def open_session(self, app, request):
        sid = request.cookies.get(app.config['SESSION_COOKIE_NAME'])
        if sid and self.use_signer:
            try:
                sid = self._unsign(app, sid)
            except BadSignature:
                sid = None
        if sid and sid.startswith(MOVED_PREFIX):
            # A move's pointer, never a session: read as no cookie
            opened = self.session_class(sid=self._generate_sid(self.sid_length),
                                        permanent=self.permanent)
        else:
            opened = super().open_session(app, request)
        opened.stored_sid = sid if sid and opened.sid == sid else None
        return opened

    def _pointer_id(self, store_id):
        """Where a move of ``store_id`` leaves its pointer, under the store's own prefix."""
        sid = store_id[len(self.key_prefix):] if store_id.startswith(self.key_prefix) else store_id
        return self._get_store_id(MOVED_PREFIX + sid)

    @staticmethod
    def _opened_from_store(session):
        stored = getattr(session, 'stored_sid', None)
        return stored is not None and stored == getattr(session, 'sid', None)

    @staticmethod
    def _refused(session):
        return getattr(session, 'record_gone', False) or getattr(session, 'store_refused', None)

    def rotate(self, session):
        """A new identifier for a session that stays (RFC 6265 §8.4), its record moved there
        now under the store's guard: a stored lock moves with it, a record removed before is
        not written back, and a later request of the old cookie finds nothing left to end.
        A refused move stands for the request (write_now); its save then updates the new record.
        A move that raised may have been done in part: refused too, the request ends on its
        error with no cookie, and the caller's record, left at its replaced version, serves no more."""
        if not session or self._refused(session):
            return
        if not self._opened_from_store(session):
            return self.regenerate(session)
        session.rotated_from = self._get_store_id(session.sid)
        session.sid = self._generate_sid(self.sid_length)
        try:
            self._upsert_session(current_app.permanent_session_lifetime, session,
                                 self._get_store_id(session.sid))
        except BaseException:
            session.store_refused = 'busy'
            raise
        finally:
            session.rotated_from = None
        if not self._refused(session):
            session.stored_sid = session.sid
        session.modified = True

    def write_now(self, app, session):
        """Writes the session at once, guarded as its save: None once stored, else 'gone' (its
        record was removed or moved meanwhile) or 'busy' (the store refused the write: held,
        paused by an HA maintenance, or the record kept changing). A refusal
        stands for the rest of the request: its save writes nothing and sends no cookie."""
        if not self._opened_from_store(session):
            session.record_gone = True
        else:
            self._upsert_session(app.permanent_session_lifetime, session,
                                 self._get_store_id(session.sid))
        if getattr(session, 'record_gone', False):
            return 'gone'
        return getattr(session, 'store_refused', None)

    def should_set_cookie(self, app, session):
        return not self._refused(session) and super().should_set_cookie(app, session)

    def _moved_to(self, store_id):
        """The identifier a move of ``store_id`` left in its pointer, or None."""
        raise NotImplementedError

    def _remove_moved(self, store_id):
        """Follows the pointers a move of ``store_id`` left: the identifiers removed."""
        removed = []
        for _hop in range(MOVED_HOPS):
            sid = self._moved_to(store_id)
            if not sid:
                break
            store_id = self._get_store_id(sid)
            if self._remove_if_present(store_id):
                removed.append(sid)
                break
        return removed

    def save_session(self, app, session, response):
        if self._refused(session):
            return
        if not (not session and session.modified and self._opened_from_store(session)):
            return super().save_session(app, session, response)
        if session.accessed:
            response.vary.add('Cookie')
        # Checked and removed at once: a record already removed means the cookie now names
        # the new identifier, so it is kept, unless a sign-out follows the move there
        store_id = self._get_store_id(session.sid)
        ended = [session.sid] if self._remove_if_present(store_id) else []
        if not ended and getattr(session, 'follows_moves', False):
            ended = self._remove_moved(store_id)
        if ended:
            response.delete_cookie(key=self.get_cookie_name(app), domain=self.get_cookie_domain(app),
                                   path=self.get_cookie_path(app))
            response.vary.add('Cookie')
        # Once the record is gone: a socket reconnecting before would pass the handshake
        _close_sockets([session.sid, *ended])


class GuardedFileSystemSessionInterface(KeepsRemovedRecordsGone, FileSystemSessionInterface):
    """Check and write are atomic only where the directory takes a flock: NFS refuses
    an exclusive one, and cachelib's capacity pruning, not a revocation, stays outside."""

    lock_wait = 2.0

    @classmethod
    def adopt(cls, app):
        app.session_interface.__class__ = cls

    def _record_exists(self, store_id):
        return self.cache.has(store_id)

    def _remove_if_present(self, store_id):
        with removal_lock(self.cache._path, 'a session removed', self.lock_wait):
            present = self._record_exists(store_id)
            if present:
                super()._delete_session(store_id)
            return present

    def _delete_session(self, store_id):
        with removal_lock(self.cache._path, 'a session removed', self.lock_wait):
            super()._delete_session(store_id)

    def _upsert_session(self, session_lifetime, session, store_id):
        moved = getattr(session, 'rotated_from', None)
        if not moved and not self._opened_from_store(session):
            return super()._upsert_session(session_lifetime, session, store_id)
        # A lock and a move are written exclusively, so no save reads the record before
        # them and writes after
        exclusive = bool(moved) or carries_lock(session)
        with session_files_lock(self.cache._path, exclusive, self.lock_wait) as state:
            if state == BUSY:
                # A removal holds the store: writing without the lock could undo it
                logger.warning("Session not saved: the session store stayed locked")
                session.store_refused = 'busy'
                return
            if moved:
                self._move(session_lifetime, session, moved, store_id)
                return
            stored = self.cache.get(store_id)
            if stored is None:
                session.record_gone = True
                return
            keep_stored_lock(session, stored)
            super()._upsert_session(session_lifetime, session, store_id)

    def _move(self, session_lifetime, session, old_id, store_id):
        # Under the exclusive lock: the guarded removal would wait for it
        stored = self.cache.get(old_id)
        if stored is None:
            session.record_gone = True
            return
        keep_stored_lock(session, stored)
        FileSystemSessionInterface._upsert_session(self, session_lifetime, session, store_id)
        self.cache.set(self._pointer_id(old_id), moved_pointer(session.sid), MOVED_TTL)
        FileSystemSessionInterface._delete_session(self, old_id)

    def _moved_to(self, store_id):
        return moved_target(self.cache.get(self._pointer_id(store_id)))


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

    def dispose(self):
        """Closes the store's own pool: an application torn down would otherwise keep its
        connections until garbage collection. The request engine stays the caller's."""
        with self._engine_lock:
            cached, self._own_engine = getattr(self, '_own_engine', None), None
        if cached is not None:
            cached[1].dispose(close=cached[0] == os.getpid())

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
        """The purge rides one request in N, never a probe (a silent database would hold it
        for the connect timeout): tried once, and a database that is away never fails it."""
        from flask import request
        from utils.public_endpoints import PROBE_PATHS
        if request.path in PROBE_PATHS:
            return
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
    def _remove_if_present(self, store_id):
        if self._writes_paused():
            return self._record_exists(store_id)
        model = self.sql_session_model
        with self._store() as s:
            removed = s.query(model).filter_by(session_id=store_id).delete()
            s.commit()
        return bool(removed)

    @retry_query()
    def _delete_session(self, store_id):
        if self._writes_paused():
            return
        model = self.sql_session_model
        with self._store() as s:
            s.query(model).filter_by(session_id=store_id).delete()
            s.commit()

    def _update_keeping_lock(self, s, session, store_id, expiry):
        """UPDATE only, so a record removed since the request opened it stays removed. An
        unlocked copy is compared and swapped against the row it read, so a lock stored in
        between is seen and kept: the lock wins on every node and both engines."""
        model = self.sql_session_model
        if carries_lock(session):
            updated = (s.query(model).filter_by(session_id=store_id)
                       .update({'data': self.serializer.encode(session), 'expiry': expiry},
                               synchronize_session=False))
            s.commit()
            if not updated:
                session.record_gone = True
            return
        for _attempt in range(LOCK_MERGE_ATTEMPTS):
            row = s.query(model.data).filter_by(session_id=store_id).first()
            s.commit()  # the read ends its transaction: SQLite never upgrades a stale reader
            if row is None:
                session.record_gone = True
                return
            keep_stored_lock(session, self.serializer.decode(want_bytes(row.data)))
            updated = (s.query(model)
                       .filter(model.session_id == store_id, model.data == row.data)
                       .update({'data': self.serializer.encode(session), 'expiry': expiry},
                               synchronize_session=False))
            s.commit()
            if updated:
                return
        session.store_refused = 'busy'
        logger.warning("Session not saved: its record kept changing under the save")

    def _move_keeping_lock(self, s, session, old_id, store_id, expiry):
        """The old row is deleted only as it was read, and the new one inserted in the same
        transaction: a lock stored in between is read again and moves too."""
        model = self.sql_session_model
        for _attempt in range(LOCK_MERGE_ATTEMPTS):
            row = s.query(model.data).filter_by(session_id=old_id).first()
            s.commit()  # the read ends its transaction: SQLite never upgrades a stale reader
            if row is None:
                session.record_gone = True
                return
            keep_stored_lock(session, self.serializer.decode(want_bytes(row.data)))
            deleted = (s.query(model).filter(model.session_id == old_id, model.data == row.data)
                       .delete(synchronize_session=False))
            if not deleted:
                s.rollback()
                continue
            s.add(model(session_id=store_id, data=self.serializer.encode(session), expiry=expiry))
            # The pointer commits with the move: a removal finding the old row gone reads it
            pointer = self._pointer_id(old_id)
            s.query(model).filter_by(session_id=pointer).delete(synchronize_session=False)
            s.add(model(session_id=pointer, data=self.serializer.encode(moved_pointer(session.sid)),
                        expiry=datetime.utcnow() + timedelta(seconds=MOVED_TTL)))
            s.commit()
            return
        session.store_refused = 'busy'
        logger.warning("Session not saved: its record kept changing under the move")

    @retry_query()
    def _moved_to(self, store_id):
        model = self.sql_session_model
        with self._store() as s:
            row = (s.query(model.data)
                   .filter(model.session_id == self._pointer_id(store_id),
                           model.expiry > datetime.utcnow()).first())
        return moved_target(self.serializer.decode(want_bytes(row.data))) if row else None

    @retry_query()
    def _upsert_session(self, session_lifetime, session, store_id):
        if self._writes_paused():
            session.store_refused = 'busy'
            return
        model = self.sql_session_model
        expiry = datetime.utcnow() + session_lifetime
        with self._store() as s:
            moved = getattr(session, 'rotated_from', None)
            if moved:
                self._move_keeping_lock(s, session, moved, store_id, expiry)
                return
            if self._opened_from_store(session):
                self._update_keeping_lock(s, session, store_id, expiry)
                return
            data = self.serializer.encode(session)
            record = s.query(model).filter_by(session_id=store_id).first()
            if record:
                record.data = data
                record.expiry = expiry
            else:
                s.add(model(session_id=store_id, data=data, expiry=expiry))
            s.commit()

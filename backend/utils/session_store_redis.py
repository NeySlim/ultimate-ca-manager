"""Redis session store with the same guard as the others; apart so that only a
Redis deployment imports the redis client."""
import logging

from flask_session._utils import total_seconds
from flask_session.redis import RedisSessionInterface
from redis.exceptions import WatchError

from utils.session_store import (LOCK_MERGE_ATTEMPTS, KeepsRemovedRecordsGone, carries_lock,
                                 keep_stored_lock)

logger = logging.getLogger(__name__)


class GuardedRedisSessionInterface(KeepsRemovedRecordsGone, RedisSessionInterface):

    @classmethod
    def adopt(cls, app):
        app.session_interface.__class__ = cls

    def _record_exists(self, store_id):
        return bool(self.client.exists(store_id))

    def _remove_if_present(self, store_id):
        return bool(self.client.delete(store_id))

    def _upsert_session(self, session_lifetime, session, store_id):
        moved = getattr(session, 'rotated_from', None)
        if not moved and not self._opened_from_store(session):
            return super()._upsert_session(session_lifetime, session, store_id)
        ttl = total_seconds(session_lifetime)
        if moved:
            return self._move(session, moved, store_id, ttl)
        if carries_lock(session):
            # SET XX: one atomic write that never recreates a key removed meanwhile
            written = self.client.set(name=store_id, value=self.serializer.encode(session),
                                      ex=ttl, xx=True)
            if written is None:
                session.record_gone = True
            return
        # An unlocked copy is written only if the key did not change since it was read
        # (WATCH): a lock stored in between is seen and kept
        with self.client.pipeline() as pipe:
            for _attempt in range(LOCK_MERGE_ATTEMPTS):
                try:
                    pipe.watch(store_id)
                    stored = pipe.get(store_id)
                    if stored is None:
                        session.record_gone = True
                        return
                    keep_stored_lock(session, self.serializer.decode(stored))
                    pipe.multi()
                    pipe.set(name=store_id, value=self.serializer.encode(session), ex=ttl, xx=True)
                    if pipe.execute()[0] is None:
                        session.record_gone = True
                    return
                except WatchError:
                    continue
                finally:
                    pipe.reset()
        session.store_refused = 'busy'
        logger.warning("Session not saved: its record kept changing under the save")

    def _move(self, session, old_id, store_id, ttl):
        """The old key is watched while it is read: a lock stored in between fails the
        transaction, is read again and moves too; a key removed meanwhile is not written back."""
        with self.client.pipeline() as pipe:
            for _attempt in range(LOCK_MERGE_ATTEMPTS):
                try:
                    pipe.watch(old_id)
                    stored = pipe.get(old_id)
                    if stored is None:
                        session.record_gone = True
                        return
                    keep_stored_lock(session, self.serializer.decode(stored))
                    pipe.multi()
                    pipe.set(name=store_id, value=self.serializer.encode(session), ex=ttl)
                    pipe.delete(old_id)
                    pipe.execute()
                    return
                except WatchError:
                    continue
                finally:
                    pipe.reset()
        session.store_refused = 'busy'
        logger.warning("Session not saved: its record kept changing under the move")

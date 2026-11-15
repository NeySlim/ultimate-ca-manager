"""Redis session store with the same guard as the others; apart so that only a
Redis deployment imports the redis client."""
from flask_session._utils import total_seconds
from flask_session.redis import RedisSessionInterface

from utils.session_store import KeepsRemovedRecordsGone


class GuardedRedisSessionInterface(KeepsRemovedRecordsGone, RedisSessionInterface):

    @classmethod
    def adopt(cls, app):
        app.session_interface.__class__ = cls

    def _record_exists(self, store_id):
        return bool(self.client.exists(store_id))

    def _upsert_session(self, session_lifetime, session, store_id):
        if not self._opened_from_store(session):
            return super()._upsert_session(session_lifetime, session, store_id)
        # SET XX: one atomic write that never recreates a key removed meanwhile
        written = self.client.set(name=store_id, value=self.serializer.encode(session),
                                  ex=total_seconds(session_lifetime), xx=True)
        if written is None:
            session.record_gone = True

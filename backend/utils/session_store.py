"""SQL session store that keeps to its own transactions.

Flask-Session's stock SQL interface commits ``db.session``, so it would also
commit whatever a failed request left pending. This one owns a separate session
on its own engine, so saving a session never waits on the request's pool.
"""
import os
import threading
from datetime import datetime

from flask_session._utils import retry_query
from flask_session.sqlalchemy import SqlAlchemySessionInterface
from flask import current_app
from itsdangerous import want_bytes
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class IsolatedSqlSessionInterface(SqlAlchemySessionInterface):

    _engine_lock = threading.Lock()

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

    @retry_query()
    def _delete_expired_sessions(self):
        model = self.sql_session_model
        with self._store() as s:
            s.query(model).filter(model.expiry <= datetime.utcnow()).delete(synchronize_session=False)
            s.commit()

    @retry_query()
    def _retrieve_session_data(self, store_id):
        model = self.sql_session_model
        with self._store() as s:
            record = s.query(model).filter_by(session_id=store_id).first()
            if record and (record.expiry is None or record.expiry <= datetime.utcnow()):
                s.delete(record)
                s.commit()
                return None
            if record:
                return self.serializer.decode(want_bytes(record.data))
            return None

    @retry_query()
    def _delete_session(self, store_id):
        model = self.sql_session_model
        with self._store() as s:
            s.query(model).filter_by(session_id=store_id).delete()
            s.commit()

    @retry_query()
    def _upsert_session(self, session_lifetime, session, store_id):
        model = self.sql_session_model
        expiry = datetime.utcnow() + session_lifetime
        data = self.serializer.encode(session)
        with self._store() as s:
            record = s.query(model).filter_by(session_id=store_id).first()
            if record:
                record.data = data
                record.expiry = expiry
            else:
                s.add(model(session_id=store_id, data=data, expiry=expiry))
            s.commit()

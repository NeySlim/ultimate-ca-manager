"""SQL session store that keeps to its own transactions.

Flask-Session's stock SQL interface commits ``db.session``, so it would also
commit whatever a failed request left pending. This one owns a separate session.
"""
from datetime import datetime

from flask_session.sqlalchemy import SqlAlchemySessionInterface
from itsdangerous import want_bytes
from sqlalchemy.orm import sessionmaker


class IsolatedSqlSessionInterface(SqlAlchemySessionInterface):

    def _store(self):
        return sessionmaker(bind=self.client.engine)()

    def _delete_expired_sessions(self):
        model = self.sql_session_model
        with self._store() as s:
            s.query(model).filter(model.expiry <= datetime.utcnow()).delete(synchronize_session=False)
            s.commit()

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

    def _delete_session(self, store_id):
        model = self.sql_session_model
        with self._store() as s:
            s.query(model).filter_by(session_id=store_id).delete()
            s.commit()

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

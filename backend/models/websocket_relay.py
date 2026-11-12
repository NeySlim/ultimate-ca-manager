"""WebSocket events waiting for the web workers (migration 149): the scheduler process's,
and in HA those of every worker of every node."""
from models import db


class WebsocketRelayEvent(db.Model):
    """One event for one room; read by each web worker past its cursor, purged after minutes."""
    __tablename__ = 'websocket_relay'
    # Ids never reused: a purge that empties the table must not move a worker's cursor back
    __table_args__ = {'sqlite_autoincrement': True}

    id = db.Column(db.BigInteger().with_variant(db.Integer, 'sqlite'), primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, index=True)
    room = db.Column(db.String(128), nullable=False)
    payload = db.Column(db.Text, nullable=False)  # JSON: {'type', 'data', 'timestamp'}

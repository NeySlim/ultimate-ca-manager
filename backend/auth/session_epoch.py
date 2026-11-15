"""The installation's session epoch: every session carries the one it began under, and a
restore advances it, so no session begun before a restore is accepted after it.

One system_config row, never exported nor restored (services/backup/installation.py),
read by every request that presents a session: all the nodes and workers of an
installation share it, whatever store holds the sessions.
"""
from models import SystemConfig, db

EPOCH_KEY = 'session.restore_epoch'
SESSION_KEY = 'restore_epoch'


def current_epoch() -> int:
    value = db.session.query(SystemConfig.value).filter_by(key=EPOCH_KEY).scalar()
    return int(value) if value else 0


def holds_current_epoch(data) -> bool:
    return (data.get(SESSION_KEY) or 0) == current_epoch()


def advance_epoch() -> int:
    """Commits the next epoch and returns it; raises when it could not be stored."""
    try:
        row = SystemConfig.query.filter_by(key=EPOCH_KEY).with_for_update().first()
        if row is None:
            row = SystemConfig(key=EPOCH_KEY, value='0',
                               description='Sessions begun before the last restore are refused')
            db.session.add(row)
        row.value = str(int(row.value or 0) + 1)
        db.session.commit()
        return int(row.value)
    except Exception:
        db.session.rollback()
        raise

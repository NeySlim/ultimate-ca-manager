"""Compare-and-set on one ``system_config`` row, the reservation of a scheduled run.

Two executors of the same scheduled work (two nodes during a leader change) read the
same previous value; the conditional write lets exactly one of them move it.
"""
import uuid
from datetime import datetime

from sqlalchemy.exc import IntegrityError

from models import SystemConfig, db


def _value_is(expected):
    return SystemConfig.value.is_(None) if expected is None else SystemConfig.value == expected


def config_compare_and_set(key: str, expected, new) -> bool:
    """Store *new* under *key* only while it still holds *expected* (None: absent or
    NULL), and commit: True when this caller moved it, False when another one did."""
    moved = SystemConfig.query.filter(SystemConfig.key == key, _value_is(expected)).update(
        {SystemConfig.value: new}, synchronize_session=False) == 1
    if not moved and expected is None:
        # Absent row: the unique key lets one insert through, the other is refused
        try:
            with db.session.begin_nested():
                db.session.add(SystemConfig(key=key, value=new))
            moved = True
        except IntegrityError:
            moved = False
    if moved:
        db.session.commit()
    return moved


def config_release(key: str, held, previous) -> bool:
    """Put *previous* back (None: remove the row) only while *key* still holds *held*."""
    query = SystemConfig.query.filter(SystemConfig.key == key, _value_is(held))
    if previous is None:
        released = query.delete(synchronize_session=False) == 1
    else:
        released = query.update({SystemConfig.value: previous},
                                synchronize_session=False) == 1
    db.session.commit()
    return released


def _held_value(key: str):
    return db.session.query(SystemConfig.value).filter_by(key=key).scalar()


class ConfigLease:
    """A lease on one ``system_config`` row, moved by compare-and-set: of two nodes running
    the same pass one holds it, and a holder that dies frees it once *duration* is over.
    Instants come from the cluster clock, the one every node compares on."""

    def __init__(self, key: str, duration):
        self.key, self.duration, self.held = key, duration, None

    def _stamp(self, now) -> str:
        return f"{now.isoformat()}|{uuid.uuid4().hex}"

    def _live(self, value, now) -> bool:
        try:
            since = datetime.fromisoformat((value or '').split('|', 1)[0])
        except ValueError:
            return False  # empty (ended) or unreadable: free
        return now - since < self.duration

    def take(self) -> bool:
        """Hold the lease unless another holder's is still live; commits."""
        from services.scheduler_leader import cluster_utc_now
        previous = _held_value(self.key)
        now = cluster_utc_now()
        if self._live(previous, now):
            db.session.rollback()
            return False
        stamp = self._stamp(now)
        if not config_compare_and_set(self.key, previous, stamp):
            return False
        self.held = stamp
        return True

    def renew(self) -> bool:
        """Push the lease forward; False once another node has taken it over."""
        from services.scheduler_leader import cluster_utc_now
        if self.held is None:
            return False
        stamp = self._stamp(cluster_utc_now())
        if not config_compare_and_set(self.key, self.held, stamp):
            self.held = None
            return False
        self.held = stamp
        return True

    def end(self) -> None:
        """Give the lease back, unless it was taken over meanwhile."""
        if self.held is None:
            return
        held, self.held = self.held, None
        try:
            config_release(self.key, held, '')
        except Exception:
            # Not given back: it frees itself once the duration is over
            db.session.rollback()

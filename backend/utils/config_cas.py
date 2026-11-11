"""Compare-and-set on one ``system_config`` row, the reservation of a scheduled run.

Two executors of the same scheduled work (two nodes during a leader change) read the
same previous value; the conditional write lets exactly one of them move it.
"""
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

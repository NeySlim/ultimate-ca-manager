"""Repair migrations replayed on what a restore wrote.

Restores run after the migrations, so rows an older archive brings back never
pass through the migration that repaired that shape on the source.
"""
import logging
from typing import Dict, Iterable

from sqlalchemy import bindparam, text

from models import db

logger = logging.getLogger(__name__)

_ORDER_DUPLICATES = '121_acme_renewal_order_duplicates'


def replay_order_repairs(ids: Iterable[int]) -> Dict[str, int]:
    """Migration 121 on the ACME client orders a restore wrote: renewal schedule and leftovers.

    A row it did not write is left alone, as a merge leaves it."""
    from migration_runner import MIGRATIONS_DIR, _load_module

    migration = _load_module(MIGRATIONS_DIR / f'{_ORDER_DUPLICATES}.py')
    db.session.flush()
    ids = sorted(ids)
    if not ids:
        return {'reissued': 0, 'dropped': 0}
    restored = ' AND acme_client_orders.id IN :ids'
    reissued = db.session.execute(text(migration._REISSUE + restored).bindparams(
        bindparam('ids', expanding=True)), {'ids': ids}).rowcount
    dropped = db.session.execute(text(migration._DROP_LEFTOVERS + restored).bindparams(
        bindparam('ids', expanding=True)), {'ids': ids}).rowcount
    # A renewal of a dropped row names nothing: same outcome as ON DELETE SET NULL, on every engine
    db.session.execute(text(
        'UPDATE acme_client_orders SET renewal_of_order_id = NULL '
        'WHERE renewal_of_order_id IS NOT NULL AND renewal_of_order_id NOT IN '
        '(SELECT id FROM acme_client_orders)'))
    db.session.expire_all()
    if reissued or dropped:
        logger.info("Restore: migration 121 replayed, %s order(s) back on the schedule, "
                    "%s leftover(s) removed", reissued, dropped)
    return {'reissued': reissued, 'dropped': dropped}

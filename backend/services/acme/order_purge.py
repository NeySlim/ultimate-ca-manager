"""Purge of expired local ACME server orders (#303).

Orders on the built-in ACME server expire (default 7 days) but nothing ever
removed them: orders, authorizations and challenges accumulated forever.
This deletes expired non-issued orders with their authorizations and
challenges, plus orphaned expired authorizations (standalone pre-authz).
Orders that reached ``valid`` are kept: they carry the link to the issued
certificate and serve as history.
"""
import logging

from models import db
from models.acme_models import AcmeAuthorization, AcmeChallenge, AcmeOrder
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

# Deleted per pass, to bound transaction size on huge backlogs.
BATCH_LIMIT = 500

_PURGEABLE_STATUSES = ('pending', 'ready', 'processing', 'invalid')


def _delete_authz(authz):
    AcmeChallenge.query.filter_by(
        authorization_id=authz.authorization_id).delete(synchronize_session=False)
    db.session.delete(authz)


def purge_expired_orders(limit: int = BATCH_LIMIT) -> dict:
    """Delete expired, non-issued local orders. Returns counters."""
    now = utc_now()
    stats = {'orders': 0, 'authorizations': 0, 'challenges': 0}

    orders = (AcmeOrder.query
              .filter(AcmeOrder.expires < now,
                      AcmeOrder.status.in_(_PURGEABLE_STATUSES))
              .order_by(AcmeOrder.id)
              .limit(limit).all())
    for order in orders:
        for authz in list(order.authorizations):
            stats['challenges'] += AcmeChallenge.query.filter_by(
                authorization_id=authz.authorization_id
            ).count()
            _delete_authz(authz)
            stats['authorizations'] += 1
        db.session.delete(order)
        stats['orders'] += 1

    # Orphaned expired authorizations (standalone pre-authz, or left behind
    # by rows deleted before this purge existed).
    orphans = (AcmeAuthorization.query
               .filter(AcmeAuthorization.expires < now,
                       AcmeAuthorization.order_id.is_(None),
                       AcmeAuthorization.status != 'valid')
               .order_by(AcmeAuthorization.id)
               .limit(limit).all())
    for authz in orphans:
        stats['challenges'] += AcmeChallenge.query.filter_by(
            authorization_id=authz.authorization_id
        ).count()
        _delete_authz(authz)
        stats['authorizations'] += 1

    # Siblings deprovisioned at validation time since 2.217, but rows
    # validated earlier (or valid orders kept as history) still store
    # pending/processing challenges next to the valid one — dead state the
    # UI would keep showing (#303 follow-up). Delete them here.
    stale = (AcmeChallenge.query
             .join(AcmeAuthorization,
                   AcmeChallenge.authorization_id == AcmeAuthorization.authorization_id)
             .filter(AcmeAuthorization.status == 'valid',
                     AcmeChallenge.status.in_(('pending', 'processing')))
             .limit(limit).all())
    for challenge in stale:
        db.session.delete(challenge)
    stats['challenges'] += len(stale)

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error(f"ACME order purge failed: {exc}")
        raise
    if any(stats.values()):
        logger.info(
            "ACME order purge: removed %(orders)d orders, "
            "%(authorizations)d authorizations, %(challenges)d challenges",
            stats,
        )
    return stats


def scheduled_purge():
    """Scheduler entry point: expired orders, then spent nonces."""
    stats = purge_expired_orders()
    from services.acme.mixins.nonce import purge_nonces
    stats['nonces'] = purge_nonces()
    return stats

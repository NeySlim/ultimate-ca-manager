"""ACME client orders left behind: cut short by a restart, or pending past any use."""
import logging
from datetime import timedelta

from sqlalchemy import or_

from models import db
from models.acme_models import AcmeClientOrder
from services.acme.order_lease import LEASE_DURATION
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

INTERRUPTED = ('Interrupted by a restart of UCM before validation: verify the challenges '
               'again, or delete the order')
PENDING_KEPT = timedelta(days=7)
# The auto-poll refreshes updated_at during its DNS wait: a fresher order may be another instance's
PROCESSING_IDLE = timedelta(minutes=15)


def _not_proxy():
    return or_(AcmeClientOrder.is_proxy_order.is_(None), AcmeClientOrder.is_proxy_order.is_(False))


def _no_live_lease(now):
    return or_(AcmeClientOrder.renewal_claimed_at.is_(None),
               AcmeClientOrder.renewal_claimed_at < now - LEASE_DURATION)


def recover_interrupted_orders() -> int:
    """At startup and at each renewal pass: an order the automatic path left ``processing``
    goes back to ``pending``, with a message. A finalization (pending key or live lease) and a
    renewal's own order, resumed by their own paths, and proxy orders are left as they are, and
    so is an order updated in the last 15 minutes: an instance sharing the database may be
    polling it."""
    now = utc_now()
    candidates = (
        AcmeClientOrder.status == 'processing', _not_proxy(), _no_live_lease(now),
        AcmeClientOrder.renewal_of_order_id.is_(None), AcmeClientOrder._pending_key.is_(None),
    )
    idle = or_(AcmeClientOrder.updated_at.is_(None), AcmeClientOrder.updated_at < now - PROCESSING_IDLE)
    count = AcmeClientOrder.query.filter(*candidates, idle).update(
        {'status': 'pending', 'error_message': INTERRUPTED}, synchronize_session=False)
    db.session.commit()
    if count:
        logger.warning("%s ACME order(s) interrupted by a restart set back to pending", count)
    active = AcmeClientOrder.query.filter(*candidates).count()
    if active:
        logger.info("%s processing ACME order(s) updated in the last 15 minutes left as they are: "
                    "another instance may be polling them", active)
    return count


def delete_order(order) -> list:
    """Stage the removal of ``order``: its TXT records, then the row; the caller commits.
    Returns what the audit entry should add: TXT records left, revocations abandoned."""
    from services.acme.acme_client_service import AcmeClientService
    notes = []
    if order.challenge_type == 'dns-01' and order.dns_provider_id:
        try:
            ok, message = AcmeClientService.cleanup_dns_challenge(order)  # no CA account: it may be gone
        except Exception as exc:
            ok, message = False, str(exc)
        if not ok:
            logger.warning("TXT records of ACME order %s not removed: %s", order.id, message)
            notes.append(f'TXT records not removed: {message}')
    owed = len(order.upstream_revocations_list)
    if owed:  # never refused: the operator chose to drop the order
        logger.warning("ACME order %s deleted with %s revocation(s) the CA never confirmed", order.id, owed)
        notes.append(f'{owed} upstream revocation(s) abandoned')
    # SQLite enforces no foreign key: the orders its renewals opened stop naming it here
    AcmeClientOrder.query.filter_by(renewal_of_order_id=order.id).update(
        {AcmeClientOrder.renewal_of_order_id: None}, synchronize_session=False)
    db.session.delete(order)
    return notes


def purge_stale_pending_orders() -> int:
    """Remove the orders pending for more than 7 days whose CA order has expired, or whose
    expiry is unknown."""
    from services.audit.staging import stage_audit_entry
    now = utc_now()
    stale = AcmeClientOrder.query.filter(
        AcmeClientOrder.status == 'pending', _not_proxy(), _no_live_lease(now),
        AcmeClientOrder.created_at < now - PENDING_KEPT,
        or_(AcmeClientOrder.expires_at.is_(None), AcmeClientOrder.expires_at < now),
    ).all()
    for order in stale:
        order_id, name = order.id, order.primary_domain
        notes = delete_order(order)
        stage_audit_entry(action='acme_order_cancel', resource_type='acme_order', resource_id=str(order_id),
                          resource_name=name,
                          details='; '.join([f'Removed ACME order {order_id}, pending for more than 7 days']
                                            + notes))
    db.session.commit()
    if stale:
        logger.info("Removed %s ACME order(s) pending for more than 7 days", len(stale))
    return len(stale)

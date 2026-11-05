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


def _not_proxy():
    return or_(AcmeClientOrder.is_proxy_order.is_(None), AcmeClientOrder.is_proxy_order.is_(False))


def _no_live_lease(now):
    return or_(AcmeClientOrder.renewal_claimed_at.is_(None),
               AcmeClientOrder.renewal_claimed_at < now - LEASE_DURATION)


def recover_interrupted_orders() -> int:
    """At startup: an order the automatic path left ``processing`` goes back to ``pending``,
    with a message. A finalization (pending key or live lease) and a renewal's own order,
    resumed by their own paths, and proxy orders are left as they are."""
    now = utc_now()
    count = AcmeClientOrder.query.filter(
        AcmeClientOrder.status == 'processing', _not_proxy(), _no_live_lease(now),
        AcmeClientOrder.renewal_of_order_id.is_(None), AcmeClientOrder._pending_key.is_(None),
    ).update({'status': 'pending', 'error_message': INTERRUPTED}, synchronize_session=False)
    db.session.commit()
    if count:
        logger.warning("%s ACME order(s) interrupted by a restart set back to pending", count)
    return count


def delete_order(order) -> None:
    """Stage the removal of ``order``: its TXT records, then the row; the caller commits."""
    from services.acme.acme_client_service import AcmeClientService
    if order.challenge_type == 'dns-01' and order.dns_provider_id:
        try:
            AcmeClientService.cleanup_dns_challenge(order)  # no CA account: it may be gone
        except Exception as exc:
            logger.warning("TXT records of ACME order %s not removed: %s", order.id, exc)
    # SQLite enforces no foreign key: the orders its renewals opened stop naming it here
    AcmeClientOrder.query.filter_by(renewal_of_order_id=order.id).update(
        {AcmeClientOrder.renewal_of_order_id: None}, synchronize_session=False)
    db.session.delete(order)


def purge_stale_pending_orders() -> int:
    """Remove the orders pending for more than 7 days whose CA order has expired too."""
    from services.audit.staging import stage_audit_entry
    now = utc_now()
    stale = AcmeClientOrder.query.filter(
        AcmeClientOrder.status == 'pending', _not_proxy(), _no_live_lease(now),
        AcmeClientOrder.created_at < now - PENDING_KEPT,
        or_(AcmeClientOrder.expires_at.is_(None), AcmeClientOrder.expires_at < now),
    ).all()
    for order in stale:
        stage_audit_entry(action='acme_order_cancel', resource_type='acme_order', resource_id=str(order.id),
                          resource_name=order.primary_domain,
                          details=f'Removed ACME order {order.id}, pending for more than 7 days')
        delete_order(order)
    db.session.commit()
    if stale:
        logger.info("Removed %s ACME order(s) pending for more than 7 days", len(stale))
    return len(stale)

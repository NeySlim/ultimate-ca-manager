"""Carrying a local revocation to the ACME CA that issued the certificate.

A certificate UCM obtained with its ACME client (or through its ACME proxy,
under an upstream account UCM holds) is published by that CA only: the
revocation reaches relying parties once the CA is told (RFC 8555 §7.6). The
revoke routes call this after the local revocation; it never raises.
"""
import base64
import logging
from datetime import timedelta
from typing import Optional, Tuple

from models import db
from models.acme_models import AcmeClientOrder
from utils.datetime_utils import utc_now
from utils.revocation_reasons import HOLD_REASONS, reason_code

logger = logging.getLogger(__name__)

#: Not a certificate obtained over ACME: nothing to do.
NOT_ACME = 'not_acme'
#: Revoked at the CA.
REVOKED = 'revoked'
#: The CA did not confirm: owed on the order, sent again by the scheduler.
OWED = 'owed'
#: No upstream account of UCM can speak for it: revoked locally only.
NO_ACCOUNT = 'no_account'
#: A hold (or its removal) is local: ACME has no hold, and a revocation there is final.
HOLD = 'hold'

# RFC 5280 §5.3.1 codes RFC 8555 §7.6 lets a client send; a hold (6) or removeFromCRL (8) never
_SENT_REASONS = {1, 2, 3, 4, 5, 9, 10}


def _order_for(cert) -> Optional[AcmeClientOrder]:
    return (AcmeClientOrder.query.filter_by(certificate_id=cert.id)
            .order_by(AcmeClientOrder.id.desc()).first())


def _client_for(order):
    """The service under the upstream account that obtained the order, or None.
    A proxy order that names no account cannot be revoked with another one."""
    from services.acme.acme_client_service import AcmeClientService
    if order.is_proxy_order and not (order.acme_client_account_id or order.account_url):
        return None
    return AcmeClientService.for_existing_order(order)


def propagate_acme_revocation(cert, reason) -> Tuple[str, Optional[str]]:
    """Revoke ``cert`` at its ACME CA, the local revocation being done.

    Returns ``(outcome, detail)``: one of the constants above, and the CA's
    error for :data:`OWED`.
    """
    if getattr(cert, 'source', None) != 'acme_client' or not cert.crt:
        return NOT_ACME, None
    from services.acme_renewal_service import _owe_upstream_revocation, send_upstream_revocation
    if reason in HOLD_REASONS or reason == 'removeFromCRL':
        return HOLD, None
    try:
        order = _order_for(cert)
        client = _client_for(order) if order is not None else None
    except Exception as exc:
        db.session.rollback()
        logger.error("Upstream account of certificate %s not resolved: %s", cert.id, exc)
        order, client = None, None
    if client is None:
        return NO_ACCOUNT, None

    code = reason_code(reason)
    code = code if code in _SENT_REASONS else None
    pem = base64.b64decode(cert.crt)
    label = f"certificate {cert.id} (serial {cert.serial_number})"
    try:
        error = send_upstream_revocation(client, pem, code, label)
    except Exception as exc:
        error = str(exc) or exc.__class__.__name__
    if error is None:
        return REVOKED, None
    logger.warning("Upstream revocation of %s failed: %s", label, error)
    not_after = cert.valid_to or utc_now() + timedelta(days=90)
    entry = {'serial': cert.serial_number, 'certificate': pem.decode(), 'reason': code,
             'not_after': not_after.isoformat()}
    # The retry pass rewrites the list under the order's lease: the debt is added under it too
    from services.acme.order_lease import OrderLease
    lease = None
    try:
        lease = OrderLease.take(order.id)
        if lease is None:
            logger.warning("Order %s is being renewed: revocation of %s owed without its lease",
                           order.id, label)
        _owe_upstream_revocation(db.session.get(AcmeClientOrder, order.id), entry, error)
    except Exception as exc:
        db.session.rollback()
        logger.error("Revocation owed by the CA for %s not kept: %s", label, exc)
    finally:
        if lease is not None:
            lease.release()
    return OWED, error


def local_only_message(outcome, detail) -> Optional[str]:
    """What the operator must know when the CA was not told, else None."""
    if outcome == OWED:
        return ('Certificate revoked in UCM, but the ACME CA did not confirm the revocation '
                f'({detail}); it is sent again automatically until the CA does.')
    if outcome == NO_ACCOUNT:
        return ('Certificate revoked in UCM only: the ACME CA account it was issued under '
                'no longer exists, so the CA was not notified. Revoke it with the CA directly.')
    if outcome == HOLD:
        return ('Certificate put on hold in UCM only: ACME has no hold, so the CA was not '
                'notified. Revoke it with a final reason to revoke it at the CA.')
    return None

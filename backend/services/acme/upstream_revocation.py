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

from sqlalchemy.exc import SQLAlchemyError

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
#: A proxy order naming no upstream account: its proxy client holds the account.
PROXY_CLIENT = 'proxy_client'
#: No ACME order of UCM names it any more: the account that obtained it is unknown.
NO_ORDER = 'no_order'
#: Looking up the order failed (database error): the account is unknown for now, not gone.
UNRESOLVED = 'unresolved'
#: A hold (or its removal) is local: ACME has no hold, and a revocation there is final.
HOLD = 'hold'

# RFC 8555 §7.6 takes an RFC 5280 §5.3.1 code: the final ones of an end-entity certificate.
# Never unspecified (0, sent absent), cA/aACompromise (2, 10: other issuers), hold (6), removeFromCRL (8)
SENT_REASONS = frozenset({1, 3, 4, 5, 9})


def _order_for(cert) -> Optional[AcmeClientOrder]:
    """The order that names ``cert``, or whose renewal moved off it into a new row."""
    order = (AcmeClientOrder.query.filter_by(certificate_id=cert.id)
             .order_by(AcmeClientOrder.id.desc()).first())
    if order is not None:
        return order
    if not cert.serial_number:
        return None
    # Serial, not row number: a restore on another installation renumbers the row
    candidates = (AcmeClientOrder.query
                  .filter(AcmeClientOrder.replaced_certificates.contains(
                      cert.serial_number, autoescape=True))
                  .order_by(AcmeClientOrder.id.desc()).all())
    return next((o for o in candidates if o.names_replaced(cert)), None)


def _client_for(order):
    """The service under the upstream account that obtained the order, or None."""
    from services.acme.acme_client_service import AcmeClientService
    return AcmeClientService.for_existing_order(order)


def propagate_acme_revocation(cert, reason) -> Tuple[str, Optional[str]]:
    """Revoke ``cert`` at its ACME CA, the local revocation being done.

    Returns ``(outcome, detail)``: one of the constants above, and the CA's
    error for :data:`OWED`.
    """
    if getattr(cert, 'source', None) != 'acme_client' or not cert.crt:
        return NOT_ACME, None
    if reason in HOLD_REASONS or reason == 'removeFromCRL':
        return HOLD, None
    order = None
    try:
        order = _order_for(cert)
        client = _client_for(order) if order is not None else None
    except Exception as exc:
        order_id = order.id if order is not None else None
        db.session.rollback()
        logger.error("Upstream account of certificate %s not resolved: %s", cert.id, exc)
        if order_id is None:
            return UNRESOLVED, ('the ACME order it was issued under could not be determined: '
                                f'{_error_text(exc)}')
        # The order is known: owed, so the scheduler sends it once the account resolves
        error = f"upstream account not resolved: {_error_text(exc)}"
        return _owe(cert, order_id, reason, error)
    if order is None:
        return NO_ORDER, None
    if client is None:
        from services.acme.acme_client_service import PROXY_ACCOUNT_UNKNOWN, AcmeClientService
        if AcmeClientService.missing_account_message(order) == PROXY_ACCOUNT_UNKNOWN:
            return PROXY_CLIENT, None
        return NO_ACCOUNT, None

    from services.acme_renewal_service import send_upstream_revocation
    pem = base64.b64decode(cert.crt)
    label = f"certificate {cert.id} (serial {cert.serial_number})"
    try:
        error = send_upstream_revocation(client, pem, _sent_code(reason), label)
    except Exception as exc:
        logger.error("Upstream revocation of %s raised: %s", label, exc)
        error = _error_text(exc)
    if error is None:
        return REVOKED, None
    logger.warning("Upstream revocation of %s failed: %s", label, error)
    return _owe(cert, order.id, reason, error)


def _error_text(exc) -> str:
    """What may leave the server: a database error's text carries its SQL and parameters."""
    if isinstance(exc, SQLAlchemyError):
        return 'Database error'
    return str(exc) or exc.__class__.__name__


def _sent_code(reason):
    code = reason_code(reason)
    return code if code in SENT_REASONS else None


def _owe(cert, order_id, reason, error):
    """``(OWED, error)`` once the revocation of ``cert`` is kept owed on the order;
    ``(UNRESOLVED, why)`` when it is not, nothing then sending it again."""
    from services.acme_renewal_service import _owe_upstream_revocation
    label = f"certificate {cert.id} (serial {cert.serial_number})"
    not_after = cert.valid_to or utc_now() + timedelta(days=90)
    entry = {'serial': cert.serial_number, 'certificate': base64.b64decode(cert.crt).decode(),
             'reason': _sent_code(reason), 'not_after': not_after.isoformat()}
    # Compare-and-set inside: safe without the order's lease, which a renewal may hold
    try:
        kept = _owe_upstream_revocation(db.session.get(AcmeClientOrder, order_id), entry, error)
    except Exception as exc:
        db.session.rollback()
        logger.error("Revocation owed by the CA for %s not kept: %s", label, exc)
        kept = False
    if kept:
        return OWED, error
    return UNRESOLVED, f'{error}; the retry could not be recorded'


def local_only_message(outcome, detail) -> Optional[str]:
    """What the operator must know when the CA was not told, else None."""
    if outcome == OWED:
        return ('Certificate revoked in UCM, but the ACME CA did not confirm the revocation '
                f'({detail}); it is sent again automatically until the CA does.')
    if outcome == NO_ACCOUNT:
        return ('Certificate revoked in UCM only: the ACME CA account it was issued under '
                'no longer exists, so the CA was not notified. Revoke it with the CA directly.')
    if outcome == PROXY_CLIENT:
        return ('Certificate revoked in UCM only: it was ordered through the ACME proxy under '
                'an upstream account UCM never recorded, so the CA was not notified. The proxy '
                'client that ordered it must revoke it with the CA.')
    if outcome == NO_ORDER:
        return ('Certificate revoked in UCM only: UCM no longer has the ACME order it was '
                'issued under, so it does not know which CA account to revoke it with. '
                'Revoke it with the CA directly.')
    if outcome == UNRESOLVED:
        return (f'Certificate revoked in UCM only, ACME CA not notified ({detail}). '
                'Revoke it with the CA directly.')
    if outcome == HOLD:
        return ('Certificate put on hold in UCM only: ACME has no hold, so the CA was not '
                'notified. Revoke it with a final reason to revoke it at the CA.')
    return None


REVOKED_MESSAGE = 'Certificate revoked successfully'


def revocation_answer(outcome, detail, message=REVOKED_MESSAGE) -> dict:
    """The ``message`` and ``meta`` of a route that revoked a certificate the ACME CA was,
    or was not, told of; ``message`` other than the default is appended, never replaced."""
    extra = '' if message == REVOKED_MESSAGE else f' {message}'
    if outcome == REVOKED:
        text = 'Certificate revoked in UCM and at the ACME CA'
        return {'message': f'{text}.{extra}' if extra else text, 'meta': {'acme_ca_revoked': True}}
    warning = local_only_message(outcome, detail)
    if warning is None:
        return {'message': message}
    meta = {'acme_local_only': True}
    if outcome == OWED:
        meta.update(acme_upstream_pending=True, acme_ca_error=str(detail)[:300])
    return {'message': f'{warning}{extra}', 'meta': meta}

"""Carrying a local revocation through to the Windows CA that issued it.

Revoking a certificate UCM obtained from a Microsoft CA is two writes: the
row here, and ``certutil -revoke`` on the issuing CA. Only the second one is
visible to a relying party. Such a certificate has no ``caref`` — UCM is not
its issuer — so UCM publishes neither a CRL entry nor an OCSP answer for it,
and the Windows CA's own CRL is the only place its revocation can appear.

This step lived in the single-certificate route, as a function returning a
Flask response, so the bulk route could not reuse it and did not. A bulk
revoke of a Microsoft CA certificate therefore flipped three columns in UCM's
database, answered ``N certificates revoked``, and left the certificate valid
everywhere it is actually checked. The renewal path does not have that
problem because its Microsoft CA guard sits in the shared service
(``services/cert/renewal.check_renewable``), which is where this now sits too.

The route keeps its own job: turning an outcome into the HTTP response, with
the wording and the ``meta`` keys clients already read.
"""

import logging
from typing import Optional, Tuple

from models import db
from utils.serial_format import serial_to_hex

logger = logging.getLogger(__name__)

#: Revoked here and on the Windows CA.
PROPAGATED = 'propagated'
#: No usable WinRM admin channel — revoked here only, nothing was attempted.
NO_CHANNEL = 'no_channel'
#: The admin channel was tried and refused. Revoked here only.
CHANNEL_FAILED = 'channel_failed'


def find_msca_for_cert(cert):
    """The MicrosoftCA connection that issued this cert, or None."""
    from models.msca import MicrosoftCA, MSCARequest
    req = (MSCARequest.query
           .filter((MSCARequest.cert_id == cert.id) | (MSCARequest.csr_id == cert.id))
           .order_by(MSCARequest.id.desc())
           .first())
    if req:
        msca = db.session.get(MicrosoftCA, req.msca_id)
        if msca:
            return msca
    if cert.imported_from and cert.imported_from.startswith('msca:'):
        return MicrosoftCA.query.filter_by(name=cert.imported_from[len('msca:'):]).first()
    return None


def propagate_revocation(cert, reason) -> Tuple[str, Optional[str]]:
    """Revoke *cert* on its Microsoft CA, the local revocation being done.

    Returns ``(outcome, detail)`` where outcome is :data:`PROPAGATED`,
    :data:`NO_CHANNEL` or :data:`CHANNEL_FAILED`, and detail is the admin
    channel's error message on :data:`CHANNEL_FAILED`, else ``None``.

    Never raises: the certificate is already revoked in UCM when this runs,
    and a Windows CA that cannot be reached must not undo that or fail the
    caller's request. The audit entry is written here, once the propagation
    has happened, so a bulk revoke records each one exactly as the
    single-certificate route does.
    """
    from services.msca_service import MicrosoftCAService, MSCAAdminChannelError

    msca = find_msca_for_cert(cert)
    if not msca or not MicrosoftCAService.admin_channel_available(msca):
        return NO_CHANNEL, None

    cert_id = cert.id
    resource_name = cert.subject or cert.refid
    msca_name = msca.name
    try:
        MicrosoftCAService.revoke_on_ca(msca, serial_to_hex(cert.serial_number), reason=reason)  # certutil reads hex
    except MSCAAdminChannelError as e:
        logger.error(f"MS CA admin-channel revoke failed for cert {cert_id}: {e}")
        return CHANNEL_FAILED, str(e)

    # Recorded after the remote revocation, on a session the revocation
    # itself already committed: this call commits whatever it is given.
    from services.audit_service import AuditService
    AuditService.log_action(
        action='msca.revoke_on_ca',
        resource_type='certificate',
        resource_id=str(cert_id),
        resource_name=resource_name,
        details=f"Revocation propagated to Microsoft CA '{msca_name}' (reason={reason})",
        success=True,
    )
    return PROPAGATED, None

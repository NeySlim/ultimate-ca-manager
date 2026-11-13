"""The SID security extension (KB5014754 strong mapping) a protocol renewal carries.

WSTEP, EST re-enrolment and SCEP RenewalReq authenticate the renewal with the
certificate being renewed: the SID comes from that certificate, never from the CSR.
"""
import logging

from utils.request_names import RequestRejected

logger = logging.getLogger(__name__)

UNRESOLVED_MESSAGE = 'Could not resolve requester identity for strong certificate mapping'
NOT_FOUND_MESSAGE = 'The requester was not found in the directory'


class RenewalAccountGone(RequestRejected):
    """The renewed certificate's SID names no directory account: refused for good."""


class RenewalIdentityUnresolved(ValueError):
    """The directory could not answer: a server fault, the same request may pass later.
    A ValueError so an approval shows the approver this message, the request left pending."""


def renewal_requester_sid(renewed_cert, ca_cert, protocol, connectors_for=None, found=None):
    """The SID ``renewed_cert``'s extension carries, None without a readable one or
    when ``ca_cert`` did not sign it (an import sets the issuer without checking).

    The enabled connectors serving the SID's domain must still find that account, as
    issuance refuses an unresolved requester; a domain none serves carries the SID over (A9).
    ``connectors_for(sid)``: the connectors to ask in their place (WSTEP: its profile's).
    ``found``: a dict that receives the ``connector`` and the ``account`` that answered.
    """
    from services.ad_connector import lookup
    from services.trust_store.csr_operations_mixin import ad_security_extension_sid
    from utils.cert_issuer import UnsupportedIssuerKey, certificate_signed_by

    sid = ad_security_extension_sid(renewed_cert)
    if sid is None:
        return None
    try:
        signed = certificate_signed_by(renewed_cert, ca_cert)
    except UnsupportedIssuerKey:
        signed = False  # unverifiable is never verified
    if not signed:
        logger.warning("%s: renewed certificate serial %x was not signed by this CA, its SID is not carried over",
                       protocol, renewed_cert.serial_number)
        return None
    from services.windows_profiles import sid_connectors
    unreachable = None
    connectors = (connectors_for or sid_connectors)(sid)
    for connector in connectors:
        account = lookup.lookup_account_by_sid(connector, sid)
        if account:
            if found is not None:
                found.update(connector=connector, account=account)
            return sid
        if account is lookup.UNREACHABLE and unreachable is None:
            unreachable = connector
    if not connectors:
        return sid
    if unreachable is not None:
        fault = lookup.connector_config_fault(unreachable)
        logger.warning("%s: the AD Connector %s cannot resolve SID %s of a renewed certificate%s",
                       protocol, unreachable.name, sid, f': {fault}' if fault else '')
        raise RenewalIdentityUnresolved(UNRESOLVED_MESSAGE)
    logger.warning("%s: SID %s of a renewed certificate names no directory account", protocol, sid)
    raise RenewalAccountGone(NOT_FOUND_MESSAGE)

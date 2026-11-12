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


class RenewalIdentityUnresolved(Exception):
    """The directory could not answer: a server fault, the same request may pass later."""


def renewal_requester_sid(renewed_cert, protocol):
    """The SID ``renewed_cert``'s extension carries, None without a readable one.

    An enabled AD Connector must still find that account, as issuance refuses an
    unresolved requester; with the connector off the SID is carried over as is.
    """
    from services.ad_connector import lookup
    from services.trust_store.csr_operations_mixin import ad_security_extension_sid

    sid = ad_security_extension_sid(renewed_cert)
    if sid is None:
        return None
    account = lookup.lookup_account_by_sid(sid)
    if account is None or account:
        return sid
    if account is lookup.UNREACHABLE:
        logger.warning("%s: the AD Connector cannot resolve SID %s of a renewed certificate", protocol, sid)
        raise RenewalIdentityUnresolved(UNRESOLVED_MESSAGE)
    logger.warning("%s: SID %s of a renewed certificate names no directory account", protocol, sid)
    raise RenewalAccountGone(NOT_FOUND_MESSAGE)

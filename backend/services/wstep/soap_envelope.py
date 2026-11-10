"""
Shared SOAP/WS-Addressing envelope construction for MS-WSTEP.

Both the RST->RSTR response and (via ``services/xcep/policy_builder.py``,
which does not use this module directly but follows the same shape) XCEP
need the same WS-Addressing header pattern. Action URIs verified against
the published MS-WSTEP specification (Microsoft Open Specifications).
"""
import datetime
import uuid

from lxml import etree

SOAP_NS = 'http://www.w3.org/2003/05/soap-envelope'
ADDRESSING_NS = 'http://www.w3.org/2005/08/addressing'
WST_NS = 'http://docs.oasis-open.org/ws-sx/ws-trust/200512'
WSSE_NS = 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd'
WSU_NS = 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd'
DS_NS = 'http://www.w3.org/2000/09/xmldsig#'
WSTEP_NS = 'http://schemas.microsoft.com/windows/pki/2009/01/enrollment'

# WS-Addressing Action URIs (MS-WSTEP section "Overview": input RST/wstep,
# output RSTRC/wstep).
ACTION_RST = 'http://schemas.microsoft.com/windows/pki/2009/01/enrollment/RST/wstep'
ACTION_RSTRC = 'http://schemas.microsoft.com/windows/pki/2009/01/enrollment/RSTRC/wstep'
ACTION_FAULT = 'http://schemas.microsoft.com/windows/pki/2009/01/enrollment/RSTRC/wstep/Fault'

ANONYMOUS_ADDRESS = 'http://www.w3.org/2005/08/addressing/anonymous'

NSMAP = {
    's': SOAP_NS,
    'a': ADDRESSING_NS,
    'wst': WST_NS,
    'wsse': WSSE_NS,
    'wstep': WSTEP_NS,
}


def build_envelope(body_element, action, to=None, relates_to=None):
    """Wrap ``body_element`` in a SOAP envelope with WS-Addressing headers.

    Args:
        body_element: an ``lxml.etree._Element`` to place inside ``s:Body``.
        action: the WS-Addressing Action URI for this message.
        to: optional ``a:To`` value (only meaningful on requests we build
            ourselves; WSTEP responses conventionally omit it since the
            reply goes to the anonymous/synchronous HTTP response channel).
        relates_to: optional ``a:RelatesTo`` value, normally the incoming
            request's ``a:MessageID``, so the client can correlate the
            response to its request.

    Returns:
        bytes: UTF-8 encoded, well-formed SOAP XML.
    """
    envelope = etree.Element('{%s}Envelope' % SOAP_NS, nsmap=NSMAP)
    header = etree.SubElement(envelope, '{%s}Header' % SOAP_NS)

    action_el = etree.SubElement(header, '{%s}Action' % ADDRESSING_NS)
    action_el.set('{%s}mustUnderstand' % SOAP_NS, '1')
    action_el.text = action

    etree.SubElement(header, '{%s}MessageID' % ADDRESSING_NS).text = f'urn:uuid:{uuid.uuid4()}'

    if relates_to:
        etree.SubElement(header, '{%s}RelatesTo' % ADDRESSING_NS).text = relates_to

    if to:
        to_el = etree.SubElement(header, '{%s}To' % ADDRESSING_NS)
        to_el.set('{%s}mustUnderstand' % SOAP_NS, '1')
        to_el.text = to

    body = etree.SubElement(envelope, '{%s}Body' % SOAP_NS)
    body.append(body_element)

    return etree.tostring(envelope, xml_declaration=True, encoding='UTF-8')


def extract_username_token(security_header):
    """Extract (username, password) from a ``wsse:Security/wsse:UsernameToken``
    element, or ``(None, None)`` if absent/malformed.

    Real MS-XCEP/MS-WSTEP UsernamePassword-bound clients send credentials
    this way — inside the SOAP message's ``wsse:Security`` header as a
    WS-Security UsernameToken — not as an HTTP ``Authorization: Basic``
    header. Confirmed against the published MS-XCEP "Initial GetPolicies
    Client Request" example (Microsoft Open Specifications): a Windows
    client configured for transport-level HTTP Basic instead reports
    WS_E_SERVER_REQUIRES_BASIC_AUTH and refuses to proceed, since that's a
    different security binding than the one it's configured to use.
    Reads the password as plain text regardless of any ``Type`` attribute
    (``#PasswordDigest`` mode is not supported — plaintext-over-TLS is the
    realistic case here and matches the published example).
    """
    if security_header is None:
        return None, None
    token = security_header.find(f'{{{WSSE_NS}}}UsernameToken')
    if token is None:
        return None, None
    username_el = token.find(f'{{{WSSE_NS}}}Username')
    password_el = token.find(f'{{{WSSE_NS}}}Password')
    username = username_el.text.strip() if username_el is not None and username_el.text else None
    password = password_el.text if password_el is not None and password_el.text else None
    if not username or not password:
        return None, None
    return username, password


# WSS 1.1 SOAP Message Security 10: the clock skew allowed past wsu:Expires
TIMESTAMP_SKEW = datetime.timedelta(minutes=5)


def message_expired(security_header, now=None):
    """Whether ``wsse:Security/wsu:Timestamp/wsu:Expires`` lies more than
    ``TIMESTAMP_SKEW`` in the past (an unreadable one counts as expired).
    False without a Timestamp, which WSTEP does not require."""
    if security_header is None:
        return False
    expires = security_header.find(f'{{{WSU_NS}}}Timestamp/{{{WSU_NS}}}Expires')
    if expires is None:
        return False
    try:
        when = datetime.datetime.fromisoformat((expires.text or '').strip())
    except ValueError:
        return True
    if when.tzinfo is None:
        when = when.replace(tzinfo=datetime.timezone.utc)
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return when + TIMESTAMP_SKEW < now


XSI_NS = 'http://www.w3.org/2001/XMLSchema-instance'


def _enrollment_detail(fault, request_id, invalid_request):
    """MS-WSTEP 3.1.4.1.3.7 CertificateEnrollmentWSDetail: no BinaryResponse
    nor ErrorCode to give (nil), InvalidRequest true for a denied request."""
    detail = etree.SubElement(fault, '{%s}Detail' % SOAP_NS)
    wsdetail = etree.SubElement(detail, '{%s}CertificateEnrollmentWSDetail' % WSTEP_NS)
    for name in ('BinaryResponse', 'ErrorCode'):
        etree.SubElement(wsdetail, '{%s}%s' % (WSTEP_NS, name)).set('{%s}nil' % XSI_NS, 'true')
    etree.SubElement(wsdetail, '{%s}InvalidRequest' % WSTEP_NS).text = \
        'true' if invalid_request else 'false'
    request_el = etree.SubElement(wsdetail, '{%s}RequestID' % WSTEP_NS)
    if request_id is None:
        request_el.set('{%s}nil' % XSI_NS, 'true')
    else:
        request_el.text = str(request_id)


def build_soap_fault(reason, code='s:Receiver', relates_to=None, subcode=None,
                     request_id=None, invalid_request=None):
    """Build a SOAP 1.2 Fault response (not a plain-text error like EST
    uses) — XML/SOAP clients parse faults specifically, and a bare HTTP
    error body would not be recognized as one. ``subcode``: a qualified
    name such as ``wsse:MessageExpired``."""
    fault = etree.Element('{%s}Fault' % SOAP_NS)
    code_el = etree.SubElement(fault, '{%s}Code' % SOAP_NS)
    etree.SubElement(code_el, '{%s}Value' % SOAP_NS).text = code
    if subcode:
        subcode_el = etree.SubElement(code_el, '{%s}Subcode' % SOAP_NS)
        etree.SubElement(subcode_el, '{%s}Value' % SOAP_NS).text = subcode
    reason_el = etree.SubElement(fault, '{%s}Reason' % SOAP_NS)
    etree.SubElement(reason_el, '{%s}Text' % SOAP_NS, attrib={
        '{http://www.w3.org/XML/1998/namespace}lang': 'en'
    }).text = reason
    if invalid_request is not None:
        _enrollment_detail(fault, request_id, invalid_request)
    return build_envelope(fault, action=ACTION_FAULT, relates_to=relates_to)

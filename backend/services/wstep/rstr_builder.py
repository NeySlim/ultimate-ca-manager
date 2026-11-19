"""
Builds the MS-WSTEP RequestSecurityTokenResponseCollection (RSTR).

Wire format verified against a real Windows Server ADCS deployment's own
WCF message trace (System.ServiceModel.MessageLogging on a lab Enterprise
CA), not the spec text alone, which is ambiguous on this exact point. The
confirmed ``RequestSecurityTokenResponse`` structure:

    TokenType
    DispositionMessage
    BinarySecurityToken (ValueType PKCS7 -- the CMC full PKI response, a
        direct child, not wrapped in RequestedSecurityToken and not a
        second sibling RequestSecurityTokenResponse)
    RequestedSecurityToken
        BinarySecurityToken (ValueType X509v3 -- the plain leaf cert)
    RequestID

The CMC token and the X509v3 token are siblings within the same
RequestSecurityTokenResponse, at different nesting depths (the CMC token
bare, the X509v3 token wrapped) -- not two separate response elements,
and not one replacing the other.

``wstep:DispositionMessage`` is required despite being declared
``nillable="true"`` with no ``minOccurs`` override -- the same "nillable
but not optional" XSD trap noted in XCEP's policy_builder.py. A response
missing it is rejected by a real client with WS_E_INVALID_FORMAT.

Element order (TokenType, DispositionMessage, BinarySecurityToken,
RequestedSecurityToken, RequestID -- no RequestType) matches both the
real ADCS trace above and an independent open-source WSTEP/MDE server
(github.com/oscartbeaumont/windows_mdm), not the published XSD's
non-normative "intended content model" annotation (a formally
order-agnostic ``xs:any`` wildcard that real Windows clients don't treat
as order-agnostic). ``RequestType`` is omitted since neither real
reference includes it.
"""
import base64

from cryptography.hazmat.primitives.serialization import Encoding
from lxml import etree

from .soap_envelope import ACTION_RSTRC, WSSE_NS, WST_NS, WSTEP_NS, build_envelope

TOKEN_TYPE_X509V3 = 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-x509-token-profile-1.0#X509v3'
# The ValueType real Windows clients put on their own PKCS#7/CMC request
# token, mirrored for the response's CMC token.
VALUE_TYPE_PKCS7 = (
    'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd#PKCS7'
)


def build_issue_response(cert, relates_to=None, request_id=None, cmc_response_der=None):
    """Build an RSTR SOAP envelope carrying the issued/renewed certificate.

    Args:
        cert: an ``cryptography.x509.Certificate`` — the issued cert.
        relates_to: the request's ``a:MessageID``, echoed back so the
            client can correlate this response to its request.
        request_id: the issued ``Certificate`` row's DB primary key, used
            as ``wstep:RequestID`` — mirrors how real ADCS assigns a real,
            positive, sequential per-request ID (visible in
            ``certutil -view``), not an arbitrary placeholder. A real
            Windows client reads a literal ``"0"`` as "no ID" rather than
            "ID zero" and fails with CERTSRV_E_PROPERTY_EMPTY, so when no
            real ID is available the element is omitted (it's
            ``minOccurs="0"``) rather than faked.
        cmc_response_der: DER bytes from ``cmc_response.build_cmc_full_pki_response``,
            if built by the caller. When present, added as a bare
            ``BinarySecurityToken`` (ValueType PKCS7) directly under
            ``RequestSecurityTokenResponse``, alongside (not inside,
            not instead of) the plain X509v3 token — see the module
            docstring for the real-ADCS trace this is based on.

    Returns:
        bytes: UTF-8 encoded, well-formed SOAP XML.
    """
    collection = etree.Element('{%s}RequestSecurityTokenResponseCollection' % WST_NS)
    rstr = etree.SubElement(collection, '{%s}RequestSecurityTokenResponse' % WST_NS)
    etree.SubElement(rstr, '{%s}TokenType' % WST_NS).text = TOKEN_TYPE_X509V3

    disposition = etree.SubElement(rstr, '{%s}DispositionMessage' % WSTEP_NS)
    disposition.set('{http://www.w3.org/XML/1998/namespace}lang', 'en-US')
    disposition.text = 'Issued'

    if cmc_response_der is not None:
        cmc_bst = etree.SubElement(
            rstr, '{%s}BinarySecurityToken' % WSSE_NS,
            ValueType=VALUE_TYPE_PKCS7,
            EncodingType='http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd#base64binary',
        )
        cmc_bst.text = base64.b64encode(cmc_response_der).decode('ascii')

    requested_token = etree.SubElement(rstr, '{%s}RequestedSecurityToken' % WST_NS)
    bst = etree.SubElement(
        requested_token, '{%s}BinarySecurityToken' % WSSE_NS,
        ValueType=TOKEN_TYPE_X509V3,
        EncodingType='http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd#base64binary',
    )
    bst.text = base64.b64encode(cert.public_bytes(Encoding.DER)).decode('ascii')

    if request_id is not None:
        etree.SubElement(rstr, '{%s}RequestID' % WSTEP_NS).text = str(request_id)

    return build_envelope(collection, action=ACTION_RSTRC, relates_to=relates_to)

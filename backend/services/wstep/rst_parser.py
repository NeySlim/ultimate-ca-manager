"""
Parses an incoming MS-WSTEP RequestSecurityToken (RST) SOAP envelope.

This is untrusted input straight off the wire, so parsing goes through
``defusedxml``'s lxml entry point (the same safe-parsing pattern already
used by ``api/v2/sso/__init__.py`` for SAML) rather than raw
``lxml.etree.fromstring``, to guard against XXE / entity-expansion.
Pure parsing, no Flask/DB coupling — mirrors how
``services/scep/message_parser.py`` keeps ASN.1 parsing separate from
protocol orchestration.
"""
import base64
from dataclasses import dataclass

from asn1crypto import cms
from asn1crypto import core as asn1_core
from asn1crypto import csr as asn1_csr
from defusedxml.lxml import fromstring as safe_fromstring

from .soap_envelope import ADDRESSING_NS, SOAP_NS, WSSE_NS, WST_NS

TOKEN_TYPE_X509V3 = 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-x509-token-profile-1.0#X509v3'
REQUEST_TYPE_ISSUE = 'http://docs.oasis-open.org/ws-sx/ws-trust/200512/Issue'
VALUE_TYPE_PKCS10 = 'http://schemas.microsoft.com/windows/pki/2009/01/enrollment#PKCS10'
# MS-WCCE 2.2.2.6 allows a PKCS#10, CMS or CMC request under either ValueType
# (the MS-WSTEP 4.1.1.1 example sends a bare PKCS#10 as "#PKCS7"): the DER decides.
_OBJECT_IDENTIFIER_TAG = 0x06

# id-cct-PKIData (RFC 5272, CMC -- Certificate Management over CMS). Real
# Windows clients wrap a CMC PKIData structure as the PKCS#7 SignedData's
# encapsulated content, not a bare CSR. PKIData.reqSequence[0] (choice
# "tcr") carries the actual PKCS#10 CertificationRequest.
_PKIDATA_CONTENT_TYPE = '1.3.6.1.5.5.7.12.2'
# Plain "data" content type (RFC 5652) -- used if a client wraps a bare
# CSR directly in PKCS#7 SignedData with no CMC layer. Not observed from
# the real client tested against, but a reasonable fallback for other
# WSTEP client implementations that might do this instead.
_DATA_CONTENT_TYPE = '1.2.840.113549.1.7.1'


class _BodyPartID(asn1_core.Integer):
    pass


class _TaggedCertificationRequest(asn1_core.Sequence):
    _fields = [
        ('body_part_id', _BodyPartID),
        ('certification_request', asn1_csr.CertificationRequest),
    ]


class _TaggedRequest(asn1_core.Choice):
    # Only the "tcr" (TaggedCertificationRequest) alternative is defined —
    # "crm" (CertReqMsg, CRMF) and "orm" (OtherRequestMessage) are valid
    # per RFC 5272 but not needed here: this parser's only job is
    # extracting a PKCS#10 CSR, which only the tcr choice carries.
    _alternatives = [
        ('tcr', _TaggedCertificationRequest, {'implicit': 0}),
    ]


class _TaggedRequestSequence(asn1_core.SequenceOf):
    _child_spec = _TaggedRequest


class _TaggedAttribute(asn1_core.Sequence):
    _fields = [
        ('body_part_id', _BodyPartID),
        ('attr_type', asn1_core.ObjectIdentifier),
        ('attr_values', asn1_core.SetOf, {'spec': asn1_core.Any}),
    ]


class _ControlSequence(asn1_core.SequenceOf):
    _child_spec = _TaggedAttribute


class _PKIData(asn1_core.Sequence):
    # RFC 5272 §3.2. cmsSequence/otherMsgSequence are typed loosely
    # (Any) since this parser never reads them -- only controlSequence
    # (skipped) and reqSequence (the CSR) matter for issuance.
    _fields = [
        ('control_sequence', _ControlSequence),
        ('req_sequence', _TaggedRequestSequence),
        ('cms_sequence', asn1_core.SequenceOf, {'spec': asn1_core.Any}),
        ('other_msg_sequence', asn1_core.SequenceOf, {'spec': asn1_core.Any}),
    ]


class RSTParseError(Exception):
    """Raised for any malformed/incomplete RST — the caller turns this
    into a SOAP fault rather than a raw 500."""


@dataclass
class ParsedRST:
    csr_der: bytes
    token_type: str | None
    request_type: str | None
    message_id: str | None
    # The wsse:Security header element (lxml), if present — only the
    # Certificate-bound renewal path sends one. None for a plain
    # UsernamePassword-bound issuance request.
    security_header: object
    # The lxml wsse:BinarySecurityToken element csr_der was read from —
    # see ws_security.SignedContent.covers for why the renewal path
    # checks this specific element rather than trusting csr_der alone.
    csr_element: object
    # True when csr_der was unwrapped from a PKCS#7/CMC envelope rather
    # than submitted as bare PKCS#10. The inner CertificationRequest in
    # that format is not reliably self-signed by real Windows clients —
    # proof of possession is established by the outer CMS signature
    # instead (see wstep_service._verify_pkcs7_pop).
    was_pkcs7_wrapped: bool
    # The client's CMC TaggedCertificationRequest bodyPartID, when
    # was_pkcs7_wrapped — the CMC full PKI response (see
    # services/wstep/cmc_response.py) must reference this same ID in its
    # CMCStatusInfoV2 bodyList to identify which request it's responding
    # to. None when not PKCS#7/CMC-wrapped.
    cmc_body_part_id: int | None
    # The outer PKCS#7 envelope's parsed ``asn1crypto.cms.SignedData``,
    # when was_pkcs7_wrapped — see wstep_service._verify_pkcs7_pop, which
    # verifies this proves possession of the inner CSR's own private key.
    # None when not PKCS#7/CMC-wrapped (nothing to verify).
    outer_signed_data: object | None


def _text(element):
    return element.text.strip() if element is not None and element.text else None


def _is_content_info(der_bytes):
    """Whether the DER SEQUENCE opens with an OID (CMS ContentInfo) rather than
    a SEQUENCE (PKCS#10 CertificationRequestInfo)."""
    if len(der_bytes) < 2 or der_bytes[0] != 0x30:
        return False
    first = der_bytes[1]
    offset = 2 + (first & 0x7f if first & 0x80 else 0)
    return len(der_bytes) > offset and der_bytes[offset] == _OBJECT_IDENTIFIER_TAG


def _unwrap_pkcs7_csr(der_bytes):
    """Extract a PKCS#10 CertificationRequest's raw DER from a PKCS#7
    SignedData envelope, per the "Full PKCS#7 request" format real
    Windows clients use. Handles both the CMC PKIData wrapping observed
    from real client interop and a plain bare-CSR-as-content fallback.

    Returns ``(csr_der, body_part_id, signed_data)`` — ``body_part_id`` is
    the CMC TaggedCertificationRequest's own ID (None for the plain-data
    fallback, which carries no CMC structure at all), needed to build a
    CMC full PKI response that references the right request.
    ``signed_data`` is the outer envelope's parsed ``cms.SignedData``, for
    ``wstep_service._verify_pkcs7_pop`` to check the CSR submitter actually
    holds the CSR's private key. Raises RSTParseError if the envelope
    doesn't match either recognized shape.
    """
    try:
        content_info = cms.ContentInfo.load(der_bytes)
        if content_info['content_type'].native != 'signed_data':
            raise ValueError(f"expected signed_data, got {content_info['content_type'].native}")
        signed_data = content_info['content']
        encap = signed_data['encap_content_info']
        inner_content_type = encap['content_type'].native
        inner_bytes = encap['content'].native
    except Exception as e:
        raise RSTParseError(f'Invalid PKCS#7 envelope: {e}')

    if inner_content_type == _PKIDATA_CONTENT_TYPE or inner_content_type == 'id_cct_pki_data':
        try:
            pki_data = _PKIData.load(inner_bytes)
            tagged_request = pki_data['req_sequence'][0]
            if tagged_request.name != 'tcr':
                raise ValueError(f'unsupported TaggedRequest choice: {tagged_request.name}')
            tcr = tagged_request.chosen
            csr_der = tcr['certification_request'].dump()
            return csr_der, tcr['body_part_id'].native, signed_data
        except (IndexError, KeyError, ValueError) as e:
            raise RSTParseError(f'Invalid CMC PKIData content: {e}')

    if inner_content_type in (_DATA_CONTENT_TYPE, 'data'):
        return inner_bytes, None, signed_data

    raise RSTParseError(f'Unsupported PKCS#7 encapsulated content type: {inner_content_type}')


def parse_rst(envelope_bytes):
    """Parse a ``RequestSecurityToken`` SOAP envelope.

    Raises ``RSTParseError`` on anything malformed. Tolerant of a missing
    or unexpected ``TokenType``/ValueType, matching EST's compatibility-
    first stance (``_require_pkcs10_content_type`` warns rather than
    rejects) — real-world clients have historically been loose about
    declaring exact MIME/ValueType strings. Whether the CSR token is a bare
    PKCS#10 or a CMS envelope (see ``_unwrap_pkcs7_csr``) is read from its
    DER, not from its ValueType.
    """
    try:
        root = safe_fromstring(envelope_bytes)
    except Exception as e:
        raise RSTParseError(f'Malformed XML: {e}')

    message_id = _text(root.find(f'.//{{{ADDRESSING_NS}}}MessageID'))
    security_header = root.find(f'.//{{{SOAP_NS}}}Header/{{{WSSE_NS}}}Security')

    rst_el = root.find(f'.//{{{WST_NS}}}RequestSecurityToken')
    if rst_el is None:
        raise RSTParseError('Missing wst:RequestSecurityToken body')

    token_type = _text(rst_el.find(f'{{{WST_NS}}}TokenType'))
    request_type = _text(rst_el.find(f'{{{WST_NS}}}RequestType'))

    bst_el = rst_el.find(f'{{{WSSE_NS}}}BinarySecurityToken')
    if bst_el is None or not (bst_el.text or '').strip():
        raise RSTParseError('Missing CSR wsse:BinarySecurityToken')
    try:
        raw_der = base64.b64decode(''.join(bst_el.text.split()), validate=True)
    except Exception as e:
        raise RSTParseError(f'Invalid base64 in BinarySecurityToken: {e}')

    was_pkcs7_wrapped = _is_content_info(raw_der)
    if was_pkcs7_wrapped:
        csr_der, cmc_body_part_id, outer_signed_data = _unwrap_pkcs7_csr(raw_der)
    else:
        csr_der, cmc_body_part_id, outer_signed_data = raw_der, None, None

    return ParsedRST(
        csr_der=csr_der,
        cmc_body_part_id=cmc_body_part_id,
        token_type=token_type,
        request_type=request_type,
        message_id=message_id,
        security_header=security_header,
        csr_element=bst_el,
        was_pkcs7_wrapped=was_pkcs7_wrapped,
        outer_signed_data=outer_signed_data,
    )

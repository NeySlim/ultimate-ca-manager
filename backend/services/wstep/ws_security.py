"""
WS-Security XML-DSig verification for MS-WSTEP's Certificate-bound
renewal binding.

A real Windows CES client configured for Certificate authentication signs
the RST itself using its current certificate's private key (structure
confirmed via the MS-MDE2 RequestSecurityToken example in the Microsoft
Open Specifications): a ``wsse:Security`` header containing a
``wsse:BinarySecurityToken`` (the signing certificate) and a
``ds:Signature`` whose ``KeyInfo`` references that token.

This module verifies the *cryptographic* signature only — it proves the
sender possesses the private key matching the embedded certificate. It
does **not** decide whether that certificate should be trusted (chains to
a UCM-issued cert, not expired, not revoked); the caller
(``wstep_service.renew``) is responsible for that. Unlike EST's mTLS
renewal, where TLS already validated the presented cert's trust chain
before the app layer ever saw it, nothing here has validated trust yet —
signature verification alone only proves possession of a private key,
not that the matching certificate is one UCM should honor.

Crucially, a valid signature over *some* part of the document does not by
itself mean the CSR the caller is about to act on is that signed content
-- ``rst_parser.parse_rst`` locates the CSR ``BinarySecurityToken`` with
its own independent, position-based search of the document, which is not
guaranteed to land on the same element this module verified. Callers
must use ``SignedContent.covers()`` (returned alongside the cert) to
confirm the specific element they intend to trust was actually inside
the verified signature before relying on it -- see ``wstep_service.renew``.
"""
import base64
from dataclasses import dataclass, field

import xmlsec

from .soap_envelope import DS_NS, WSSE_NS, WSU_NS

# The only legitimate reason a ds:Reference has no "#<id>" fragment is a
# same-document reference to the whole enveloping document via this
# transform (RFC 3275 §4.4.3.2); a bare URI="" without it is refused
# rather than assumed to mean "covers everything" -- see the Reference
# loop in verify_signed_request.
_ENVELOPED_SIGNATURE_TRANSFORM = 'http://www.w3.org/2000/09/xmldsig#enveloped-signature'

# SHA-2 public-key signatures only: SHA-1, SHA-224 and HMAC are refused.
_ALLOWED_SIGNATURE_METHODS = frozenset({
    'http://www.w3.org/2001/04/xmldsig-more#rsa-sha256',
    'http://www.w3.org/2001/04/xmldsig-more#rsa-sha384',
    'http://www.w3.org/2001/04/xmldsig-more#rsa-sha512',
    'http://www.w3.org/2001/04/xmldsig-more#ecdsa-sha256',
    'http://www.w3.org/2001/04/xmldsig-more#ecdsa-sha384',
    'http://www.w3.org/2001/04/xmldsig-more#ecdsa-sha512',
})
_ALLOWED_DIGEST_METHODS = frozenset({
    'http://www.w3.org/2001/04/xmlenc#sha256',
    'http://www.w3.org/2001/04/xmldsig-more#sha384',
    'http://www.w3.org/2001/04/xmlenc#sha512',
})


class WSSecurityError(Exception):
    """Raised when the signature is missing, malformed, or does not verify."""


@dataclass
class SignedContent:
    """The document element(s) actually covered by a verified signature.

    Built from the same ``ds:Reference`` targets ``verify_signed_request``
    registered with xmlsec and successfully verified against -- not a
    fresh lookup -- so ``covers()`` can only report true for content that
    was cryptographically confirmed, never for a same-ID lookalike placed
    elsewhere in the document.
    """
    _signed_elements: list = field(default_factory=list)

    def covers(self, element):
        """True if ``element`` is, or is a descendant of, an element the
        verified signature actually covered."""
        if element is None:
            return False
        for signed_el in self._signed_elements:
            if element is signed_el:
                return True
            for ancestor in element.iterancestors():
                if ancestor is signed_el:
                    return True
        return False


def _check_algorithms(signature_node):
    """Refuse the signature unless SignatureMethod and every DigestMethod are allowed."""
    methods = signature_node.findall(f'{{{DS_NS}}}SignedInfo/{{{DS_NS}}}SignatureMethod')
    if len(methods) != 1:
        raise WSSecurityError('ds:SignedInfo must contain exactly one SignatureMethod')
    algorithm = methods[0].get('Algorithm') or ''
    if algorithm not in _ALLOWED_SIGNATURE_METHODS:
        raise WSSecurityError(f'Signature algorithm not allowed: {algorithm or "(none)"}')
    for reference in signature_node.findall(f'{{{DS_NS}}}SignedInfo/{{{DS_NS}}}Reference'):
        digests = reference.findall(f'{{{DS_NS}}}DigestMethod')
        if len(digests) != 1:
            raise WSSecurityError('ds:Reference must contain exactly one DigestMethod')
        algorithm = digests[0].get('Algorithm') or ''
        if algorithm not in _ALLOWED_DIGEST_METHODS:
            raise WSSecurityError(f'Digest algorithm not allowed: {algorithm or "(none)"}')


def verify_signed_request(security_header):
    """Verify a ``wsse:Security`` header's ``ds:Signature``.

    Args:
        security_header: the lxml element for ``wsse:Security`` (as
            returned by ``rst_parser.ParsedRST.security_header``). Must
            not be ``None``.

    Returns:
        tuple: ``(cert_der, signed_content)`` -- the DER-encoded signing
        certificate, and a ``SignedContent`` the caller must use to
        confirm any element it relies on (e.g. the CSR token) was part of
        what this call actually verified.

    Raises:
        WSSecurityError: on any missing element or verification failure.
    """
    if security_header is None:
        raise WSSecurityError('Request is not signed (no wsse:Security header)')

    bst_el = security_header.find(f'{{{WSSE_NS}}}BinarySecurityToken')
    if bst_el is None or not (bst_el.text or '').strip():
        raise WSSecurityError('wsse:Security is missing the signing BinarySecurityToken')

    try:
        cert_der = base64.b64decode(''.join(bst_el.text.split()), validate=True)
    except Exception as e:
        raise WSSecurityError(f'Invalid base64 in signing BinarySecurityToken: {e}')

    signature_node = security_header.find(f'{{{DS_NS}}}Signature')
    if signature_node is None:
        raise WSSecurityError('wsse:Security is missing ds:Signature')

    _check_algorithms(signature_node)

    try:
        key = xmlsec.Key.from_memory(cert_der, xmlsec.constants.KeyDataFormatCertDer)
    except Exception as e:
        raise WSSecurityError(f'Could not load signing certificate: {e}')

    ctx = xmlsec.SignatureContext()
    ctx.key = key

    # Each Reference must target either a specific wsu:Id-tagged element
    # or (with the enveloped-signature transform) the whole document; find
    # and register the id-targeted ones so xmlsec can locate them (walking
    # the tree and comparing attribute values directly, rather than
    # interpolating attacker-controlled text into an XPath/ElementPath
    # expression).
    #
    # The elements found here are kept, not just registered, and returned
    # as SignedContent: this is the *only* record of what the signature
    # covers that the caller may trust. A second, independent lookup for
    # the same wsu:Id elsewhere in the document could resolve to a
    # different element than the one whose digest xmlsec verified.
    root = security_header.getroottree().getroot()
    signed_elements = []
    references = signature_node.findall(f'{{{DS_NS}}}SignedInfo/{{{DS_NS}}}Reference')
    if not references:
        raise WSSecurityError('ds:Signature has no References')
    for reference in references:
        uri = reference.get('URI') or ''
        if not uri:
            transform_algorithms = {
                t.get('Algorithm')
                for t in reference.findall(f'{{{DS_NS}}}Transforms/{{{DS_NS}}}Transform')
            }
            if _ENVELOPED_SIGNATURE_TRANSFORM not in transform_algorithms:
                raise WSSecurityError(
                    'Reference URI="" requires the enveloped-signature transform'
                )
            # xmlsec resolves URI="" against the containing document
            # itself, natively -- no id registration needed. Recording
            # `root` here means SignedContent.covers() reports true for
            # any element in the document, which is correct: this
            # transform signs everything except the ds:Signature element.
            signed_elements.append(root)
            continue
        if not uri.startswith('#') or len(uri) < 2:
            raise WSSecurityError(f'Unsupported Reference URI: {uri!r}')
        target_id = uri[1:]
        target_el = None
        for el in root.iter():
            if el.get(f'{{{WSU_NS}}}Id') == target_id:
                target_el = el
                break
        if target_el is None:
            raise WSSecurityError(f'Signed Reference target "#{target_id}" not found')
        ctx.register_id(target_el, id_attr='Id', id_ns=WSU_NS)
        signed_elements.append(target_el)

    try:
        ctx.verify(signature_node)
    except xmlsec.VerificationError as e:
        raise WSSecurityError(f'Signature verification failed: {e}')
    except xmlsec.Error as e:
        raise WSSecurityError(f'Signature processing error: {e}')

    return cert_der, SignedContent(signed_elements)

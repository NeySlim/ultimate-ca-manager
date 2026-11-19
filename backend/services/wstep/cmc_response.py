"""
Builds a CMC "full PKI response" (RFC 5272 SS4.2/4.3), the piece MS-WSTEP's
own spec text says a server "MUST also include" in the
RequestSecurityTokenResponseCollection alongside the plain X509v3
BinarySecurityToken (services/wstep/rstr_builder.py) -- confirmed against
the published MS-WSTEP wst:RequestedSecurityTokenType page.

Structurally this is the response-side mirror of the CMC request envelope
rst_parser.py already unwraps: a PKCS#7 SignedData whose encapsulated
content is a CMC PKIResponse (not PKIData), carrying a CMCStatusInfoV2
control that marks the client's original TaggedCertificationRequest
(identified by its own bodyPartID, threaded through from rst_parser.py's
ParsedRST.cmc_body_part_id) as successful. The issued certificate (and CA
chain) travel in the outer SignedData's own certificates field per RFC
5272 SS4.2, not inside the PKIResponse structure itself.

This is a degenerate (unsigned) SignedData -- empty digestAlgorithms and
signerInfos -- the same "certs-only" shape cryptography's own
pkcs7.serialize_certificates() produces and that EST's
_certs_only_response already relies on. RFC 5652 permits an empty
signerInfos SET; a real CMC responder would typically sign this with the
CA/RA's own key, which is real follow-up work, not attempted here.
"""
from asn1crypto import core as asn1_core
from asn1crypto import x509 as asn1_x509

# RFC 5272 SS4.2 -- id-pkix.id-cct(12).3
ID_CCT_PKIRESPONSE = '1.3.6.1.5.5.7.12.3'
# RFC 5272 SS6.1.1 -- id-cmc-statusInfoV2 = {id-cmc 25}, id-cmc = {id-pkix 7}
ID_CMC_STATUSINFOV2 = '1.3.6.1.5.5.7.7.25'
CMC_STATUS_SUCCESS = 0

# id-signedData (RFC 5652)
ID_SIGNED_DATA = '1.2.840.113549.1.7.2'


class _BodyPartID(asn1_core.Integer):
    pass


class _BodyList(asn1_core.SequenceOf):
    # BodyPartReference ::= CHOICE { bodyPartID BodyPartID, bodyPartPath
    # BodyPartPath } -- untagged CHOICE over tag-distinct alternatives, so
    # choosing bodyPartID encodes identically to a bare BodyPartID; the
    # bodyPartPath alternative is never used here, so the CHOICE wrapper
    # is skipped rather than modeled.
    _child_spec = _BodyPartID


class _CMCStatusInfoV2(asn1_core.Sequence):
    _fields = [
        ('cmc_status', asn1_core.Integer),
        ('body_list', _BodyList),
        ('status_string', asn1_core.UTF8String, {'optional': True}),
        # otherInfo omitted -- only meaningful for non-success status.
    ]


class _TaggedAttribute(asn1_core.Sequence):
    _fields = [
        ('body_part_id', _BodyPartID),
        ('attr_type', asn1_core.ObjectIdentifier),
        ('attr_values', asn1_core.SetOf, {'spec': asn1_core.Any}),
    ]


class _ControlSequence(asn1_core.SequenceOf):
    _child_spec = _TaggedAttribute


class _PKIResponse(asn1_core.Sequence):
    _fields = [
        ('control_sequence', _ControlSequence),
        ('cms_sequence', asn1_core.SequenceOf, {'spec': asn1_core.Any}),
        ('other_msg_sequence', asn1_core.SequenceOf, {'spec': asn1_core.Any}),
    ]


# Plain RFC 5652 SignedData/EncapsulatedContentInfo/ContentInfo, defined
# locally rather than reusing asn1crypto.cms's versions. cms's classes key
# their internal field typing off a registry of *known* contentType OIDs
# (signed_data, data, etc.) — fine for parsing (falls back to Any) but that
# fallback does not apply the field's `explicit` tag wrapping correctly
# when *constructing* a new value for an OID the registry doesn't know
# (id-cct-PKIResponse). Defining fixed-shape classes here, matching the
# same "custom local ASN.1 defs" approach rst_parser.py already uses for
# PKIData, sidesteps that entirely — every field here has one fixed type,
# so there's no dynamic resolution to fight.
class _EncapsulatedContentInfo(asn1_core.Sequence):
    _fields = [
        ('content_type', asn1_core.ObjectIdentifier),
        ('content', asn1_core.ParsableOctetString, {'explicit': 0, 'optional': True}),
    ]


class _CertificateSet(asn1_core.SetOf):
    # CertificateChoices ::= CHOICE { certificate Certificate, ... } --
    # only the untagged `certificate` alternative is ever produced here,
    # which (same reasoning as _BodyList above) encodes identically to a
    # bare Certificate.
    _child_spec = asn1_x509.Certificate


class _SignedData(asn1_core.Sequence):
    _fields = [
        ('version', asn1_core.Integer),
        ('digest_algorithms', asn1_core.SetOf, {'spec': asn1_core.Any}),
        ('encap_content_info', _EncapsulatedContentInfo),
        ('certificates', _CertificateSet, {'implicit': 0, 'optional': True}),
        ('signer_infos', asn1_core.SetOf, {'spec': asn1_core.Any}),
    ]


class _ContentInfo(asn1_core.Sequence):
    # Unlike EncapsulatedContentInfo, ContentInfo's content is `[0]
    # EXPLICIT ANY DEFINED BY contentType` (RFC 5652 SS3) -- no OCTET
    # STRING wrapper. Conflating the two produces "method should have been
    # constructed, but primitive was found" on parse.
    #
    # Typed concretely as _SignedData rather than the spec-accurate Any:
    # asn1crypto's dict-based Sequence constructor silently skips the
    # `explicit` tag wrap when the field spec is Any and the value handed
    # in is already an Asn1Value, producing a bare untagged SEQUENCE
    # instead of a [0]-tagged one. We only ever build one concrete shape
    # here, so Any's generality isn't needed anyway.
    _fields = [
        ('content_type', asn1_core.ObjectIdentifier),
        ('content', _SignedData, {'explicit': 0, 'optional': True}),
    ]


def build_cmc_full_pki_response(leaf_cert_der, chain_cert_ders, body_part_id):
    """Build a CMC full PKI response's DER bytes (the outer ContentInfo).

    Args:
        leaf_cert_der: the just-issued end-entity certificate, DER.
        chain_cert_ders: iterable of the issuing CA's chain certs, DER —
            included in the same certificates bag per RFC 5272 SS4.2.
        body_part_id: the client's original TaggedCertificationRequest
            bodyPartID (``ParsedRST.cmc_body_part_id``) to mark as
            successful. If None (client didn't send one — shouldn't
            happen for a CMC-wrapped request, but not asserted here),
            falls back to 0.

    Returns:
        bytes: DER-encoded ContentInfo(SignedData(...)).
    """
    status_info = _CMCStatusInfoV2({
        'cmc_status': CMC_STATUS_SUCCESS,
        'body_list': [int(body_part_id) if body_part_id is not None else 0],
    })
    tagged_attr = _TaggedAttribute({
        'body_part_id': 1,
        'attr_type': ID_CMC_STATUSINFOV2,
        'attr_values': [asn1_core.Any.load(status_info.dump())],
    })
    pki_response = _PKIResponse({
        'control_sequence': [tagged_attr],
        'cms_sequence': [],
        'other_msg_sequence': [],
    })

    certificates = [
        asn1_x509.Certificate.load(der)
        for der in [leaf_cert_der, *chain_cert_ders]
    ]

    signed_data = _SignedData({
        # RFC 5652 §5.1: version MUST be 3 whenever encapContentInfo's
        # eContentType is anything other than id-data (ours is
        # id-cct-PKIResponse) -- confirmed against a real captured Windows
        # client request, whose own CMC-wrapped CSR envelope uses version 3
        # for the same reason (its encapContentInfo is id-cct-PKIData,
        # also non-id-data).
        'version': 3,
        'digest_algorithms': [],
        'encap_content_info': {
            'content_type': ID_CCT_PKIRESPONSE,
            'content': pki_response.dump(),
        },
        'certificates': certificates,
        'signer_infos': [],
    })

    # Pass the Asn1Value object itself, not a pre-wrapped Any (and not raw
    # bytes) -- asn1crypto only applies the `explicit` tag wrap when it
    # has to build the Any wrapper itself; handing it an already-built Any
    # silently skips that step, producing an untagged (and unparseable)
    # SEQUENCE.
    return _ContentInfo({
        'content_type': ID_SIGNED_DATA,
        'content': signed_data,
    }).dump()

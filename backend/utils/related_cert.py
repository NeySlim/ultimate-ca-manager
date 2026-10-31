"""Related certificates (RFC 9763): the relatedCertRequest CSR attribute and
the RelatedCertificate extension that ties a certificate B to a certificate A
held by the same entity. ``locationInfo`` is one IA5String (verified erratum
8750); a SEQUENCE OF IA5String, as the ASN.1 module first printed it, is read too.
"""
import hashlib
from datetime import datetime, timezone

from asn1crypto import algos, cms, core
from asn1crypto import x509 as asn1_x509
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.hazmat.primitives.asymmetric import ec, ed448, ed25519, padding, rsa
from cryptography.x509.oid import ExtensionOID

from utils.signing_hash import signing_hash_for

RELATED_CERT_REQUEST_OID = '1.2.840.113549.1.9.16.2.60'
RELATED_CERT_EXTENSION_OID = x509.ObjectIdentifier('1.3.6.1.5.5.7.1.36')

# Digests a RelatedCertificate hash or a requester signature may use
_DIGESTS = {'sha256': hashes.SHA256, 'sha384': hashes.SHA384, 'sha512': hashes.SHA512}
_HASHLIB = {'sha256': hashlib.sha256, 'sha384': hashlib.sha384, 'sha512': hashlib.sha512}


class RelatedCertError(ValueError):
    """A relatedCertRequest attribute or RelatedCertificate extension that cannot be read."""


class BinaryTime(core.Integer):
    """RFC 6019: seconds since 1970-01-01T00:00:00Z."""


class _URIs(core.SequenceOf):
    _child_spec = core.IA5String


class LocationInfo(core.Choice):
    _alternatives = [('uri', core.IA5String), ('uris', _URIs)]


class RequesterCertificate(core.Sequence):
    _fields = [
        ('cert_id', cms.IssuerAndSerialNumber),
        ('request_time', BinaryTime),
        ('location_info', LocationInfo),
        ('signature', core.OctetBitString),
    ]


class _SetOfAny(core.SetOf):
    _child_spec = core.Any


class _Attribute(core.Sequence):
    _fields = [('type', core.ObjectIdentifier), ('values', _SetOfAny)]


class _Attributes(core.SetOf):
    _child_spec = _Attribute


# PKCS#10 with the subject and key kept as raw bytes: asn1crypto cannot parse an ML-DSA SPKI
class _RawRequestInfo(core.Sequence):
    _fields = [
        ('version', core.Integer),
        ('subject', core.Any),
        ('subject_pk_info', core.Any),
        ('attributes', _Attributes, {'implicit': 0}),
    ]


class _RawRequest(core.Sequence):
    _fields = [
        ('certification_request_info', _RawRequestInfo),
        ('signature_algorithm', core.Any),
        ('signature', core.OctetBitString),
    ]


class _DigestAlgorithmIdentifier(core.Sequence):
    # RFC 5754 §2: SHA-2 parameters are generated absent, read absent or NULL
    _fields = [('algorithm', algos.DigestAlgorithmId), ('parameters', core.Any, {'optional': True})]


class RelatedCertificate(core.Sequence):
    _fields = [('hash_algorithm', _DigestAlgorithmIdentifier), ('hash_value', core.OctetString)]


def _strict_load(spec, der: bytes, what: str):
    """*der* parsed as *spec*, refused unless it is exactly its own DER re-encoding."""
    try:
        value = spec.load(der, strict=True)
        value.native  # parse every field now, not on first use
        if value.dump(force=True) != der:
            raise ValueError('not DER')
    except Exception as e:
        raise RelatedCertError(f'Malformed {what}: {e}') from e
    return value


# ---- RelatedCertificate extension ------------------------------------------

def related_hash_name(cert_a: x509.Certificate) -> str:
    """The digest named by A's own signature algorithm when it is a SHA-2, else SHA-256 (RFC 9763 §4.1)."""
    try:
        name = getattr(cert_a.signature_hash_algorithm, 'name', None)
    except Exception:  # an algorithm pyca cannot name
        name = None
    return name if name in _DIGESTS else 'sha256'


def related_certificate_extension(cert_a: x509.Certificate) -> x509.UnrecognizedExtension:
    """id-pe-relatedCert carrying the hash of the whole of *cert_a*; add it non-critical."""
    name = related_hash_name(cert_a)
    der = RelatedCertificate({
        'hash_algorithm': {'algorithm': name},
        'hash_value': _HASHLIB[name](cert_a.public_bytes(Encoding.DER)).digest(),
    }).dump()
    return x509.UnrecognizedExtension(RELATED_CERT_EXTENSION_OID, der)


def read_related_certificate(cert_b: x509.Certificate):
    """``(hash name, hash value)`` of *cert_b*'s RelatedCertificate extension, None without one."""
    try:
        ext = cert_b.extensions.get_extension_for_oid(RELATED_CERT_EXTENSION_OID)
    except x509.ExtensionNotFound:
        return None
    value = _strict_load(RelatedCertificate, ext.value.value, 'RelatedCertificate extension')
    name = value['hash_algorithm']['algorithm'].native
    if name not in _HASHLIB:
        raise RelatedCertError(f'RelatedCertificate hash {name} is not supported')
    return name, value['hash_value'].native


def references(cert_b: x509.Certificate, cert_a: x509.Certificate) -> bool:
    """Whether *cert_b*'s RelatedCertificate extension names *cert_a* (RFC 9763 §4.2)."""
    found = read_related_certificate(cert_b)
    if found is None:
        return False
    name, value = found
    return _HASHLIB[name](cert_a.public_bytes(Encoding.DER)).digest() == value


# ---- relatedCertRequest attribute ------------------------------------------

def issuer_and_serial(cert_a: x509.Certificate) -> cms.IssuerAndSerialNumber:
    return cms.IssuerAndSerialNumber({
        'issuer': asn1_x509.Name.load(cert_a.issuer.public_bytes()),
        'serial_number': cert_a.serial_number,
    })


def binary_time(moment: datetime) -> int:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return int(moment.timestamp())


def signed_content(cert_id: cms.IssuerAndSerialNumber, request_time: int) -> bytes:
    """DER(IssuerAndSerialNumber) || DER(BinaryTime), what the requester signs (RFC 9763 §3.1)."""
    return cert_id.dump(force=True) + BinaryTime(request_time).dump(force=True)


def sign_with(private_key, data: bytes) -> bytes:
    """*data* signed by *private_key* with its own scheme and registry digest."""
    algorithm = signing_hash_for(private_key)
    if isinstance(private_key, rsa.RSAPrivateKey):
        return private_key.sign(data, padding.PKCS1v15(), algorithm)
    if isinstance(private_key, ec.EllipticCurvePrivateKey):
        return private_key.sign(data, ec.ECDSA(algorithm))
    return private_key.sign(data)


def verify_with(public_key, signature: bytes, data: bytes) -> bool:
    """Whether *signature* over *data* verifies under *public_key*; RSA (v1.5 or PSS)
    and ECDSA are read with SHA-256, SHA-384 or SHA-512."""
    try:
        if isinstance(public_key, rsa.RSAPublicKey):
            for digest in _DIGESTS.values():
                for pad in (padding.PKCS1v15(),
                            padding.PSS(padding.MGF1(digest()), padding.PSS.AUTO)):
                    try:
                        public_key.verify(signature, data, pad, digest())
                        return True
                    except InvalidSignature:
                        continue
            return False
        if isinstance(public_key, ec.EllipticCurvePublicKey):
            for digest in _DIGESTS.values():
                try:
                    public_key.verify(signature, data, ec.ECDSA(digest()))
                    return True
                except InvalidSignature:
                    continue
            return False
        if isinstance(public_key, (ed25519.Ed25519PublicKey, ed448.Ed448PublicKey)):
            public_key.verify(signature, data)
            return True
        verify = getattr(public_key, 'verify', None)
        if verify is None:
            return False
        verify(signature, data)  # ML-DSA: verify(signature, data)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def data_url_for(certificates) -> str:
    """A data URL holding a degenerate PKCS#7 of *certificates*, A first (RFC 9763 §3.1, RFC 2397)."""
    import base64
    from cryptography.hazmat.primitives.serialization import pkcs7
    der = pkcs7.serialize_certificates(list(certificates), Encoding.DER)
    return 'data:application/pkcs7-mime;base64,' + base64.b64encode(der).decode('ascii')


def build_request(cert_a: x509.Certificate, key_a, location: str, request_time=None) -> bytes:
    """DER of a RequesterCertificate naming *cert_a*, signed by its private key *key_a*."""
    moment = binary_time(request_time or datetime.now(timezone.utc))
    cert_id = issuer_and_serial(cert_a)
    return RequesterCertificate({
        'cert_id': cert_id,
        'request_time': moment,
        'location_info': LocationInfo(name='uri', value=location),
        'signature': sign_with(key_a, signed_content(cert_id, moment)),
    }).dump()


def parse_request(der: bytes) -> RequesterCertificate:
    return _strict_load(RequesterCertificate, der, 'relatedCertRequest attribute')


def request_time(req: RequesterCertificate) -> datetime:
    """The naive UTC moment a request says it was made."""
    try:
        return datetime.fromtimestamp(req['request_time'].native, timezone.utc).replace(tzinfo=None)
    except (OverflowError, OSError, ValueError) as e:
        raise RelatedCertError(f'relatedCertRequest requestTime is out of range: {e}') from e


def request_signature_valid(req: RequesterCertificate, public_key) -> bool:
    """Whether the request was signed by the key of the certificate it names."""
    content = signed_content(req['cert_id'], req['request_time'].native)
    return verify_with(public_key, req['signature'].native, content)


def requested_issuer_der(req: RequesterCertificate) -> bytes:
    return req['cert_id']['issuer'].dump(force=True)


def requested_serial(req: RequesterCertificate) -> int:
    return req['cert_id']['serial_number'].native


def request_from_csr_der(csr_der: bytes):
    """The RequesterCertificate a CSR carries, None without one; refused when
    the attribute is repeated or holds anything but one value."""
    try:
        attributes = list(_RawRequest.load(csr_der)['certification_request_info']['attributes'])
        found = [attr for attr in attributes if attr['type'].dotted == RELATED_CERT_REQUEST_OID]
    except Exception as e:
        raise RelatedCertError(f'Unreadable CSR attributes: {e}') from e
    if not found:
        return None
    if len(found) > 1 or len(found[0]['values']) != 1:
        raise RelatedCertError('A CSR carries one relatedCertRequest attribute with one value')
    return parse_request(found[0]['values'][0].dump())


def csr_with_request(csr: x509.CertificateSigningRequest, private_key, request_der: bytes
                     ) -> x509.CertificateSigningRequest:
    """*csr* with the relatedCertRequest attribute added, signed again by its own *private_key*."""
    original = _RawRequest.load(csr.public_bytes(Encoding.DER))
    info = original['certification_request_info']
    attributes = list(info['attributes']) + [_Attribute({
        'type': RELATED_CERT_REQUEST_OID,
        'values': [core.Any.load(request_der)],
    })]
    info = _RawRequestInfo({
        'version': info['version'],
        'subject': info['subject'],
        'subject_pk_info': info['subject_pk_info'],
        'attributes': attributes,
    })
    rebuilt = _RawRequest({
        'certification_request_info': info,
        'signature_algorithm': original['signature_algorithm'],
        'signature': _sign_like(private_key, info.dump(), csr),
    }).dump()
    out = x509.load_der_x509_csr(rebuilt)
    if not out.is_signature_valid:
        raise RelatedCertError('The CSR could not be signed again with its attribute')
    return out


def _sign_like(private_key, tbs: bytes, csr) -> bytes:
    """*tbs* signed with the scheme and digest *csr* was signed with."""
    algorithm = csr.signature_hash_algorithm
    if isinstance(private_key, rsa.RSAPrivateKey):
        return private_key.sign(tbs, padding.PKCS1v15(), algorithm)
    if isinstance(private_key, ec.EllipticCurvePrivateKey):
        return private_key.sign(tbs, ec.ECDSA(algorithm))
    return private_key.sign(tbs)


# ---- key purposes ------------------------------------------------------------

_KU_BITS = ('digital_signature', 'content_commitment', 'key_encipherment', 'data_encipherment',
            'key_agreement', 'key_cert_sign', 'crl_sign')


def _ku_bits(usage: x509.KeyUsage) -> set:
    bits = {name for name in _KU_BITS if getattr(usage, name)}
    if usage.key_agreement:
        bits |= {name for name in ('encipher_only', 'decipher_only') if getattr(usage, name)}
    return bits


def usages_outside(cert_a: x509.Certificate, key_usage, ekus) -> list:
    """Key usage bits and EKU OIDs asserted for B (*key_usage*, *ekus*; None when
    B carries none) that A does not carry (RFC 9763 §4.1). A without the
    extension, or with anyExtendedKeyUsage, restricts nothing."""
    outside = []
    if key_usage is not None:
        try:
            a_usage = cert_a.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE).value
            outside += sorted(_ku_bits(key_usage) - _ku_bits(a_usage))
        except x509.ExtensionNotFound:
            pass
    if ekus:
        try:
            a_ekus = set(cert_a.extensions.get_extension_for_oid(ExtensionOID.EXTENDED_KEY_USAGE).value)
            if x509.ExtendedKeyUsageOID.ANY_EXTENDED_KEY_USAGE not in a_ekus:
                outside += [oid.dotted_string for oid in ekus if oid not in a_ekus]
        except x509.ExtensionNotFound:
            pass
    return outside

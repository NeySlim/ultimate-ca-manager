"""Key encryption of an encrypted EST serverkeygen response (RFC 7030 §4.4.2), chosen from the
CSR's SMIMECapabilities (RFC 8551 §2.5.2) in the client's order of preference."""
from dataclasses import dataclass

from asn1crypto import algos, cms, core, csr as asn1_csr
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec, rsa

import fips_mode
from utils import key_algorithms
from utils.cms_envelope import OAEP_HASHES, oaep_parameters

SMIME_CAPABILITIES_OID = '1.2.840.113549.1.9.15'
RSAES_OAEP = '1.2.840.113549.1.1.7'
RSA_ENCRYPTION = '1.2.840.113549.1.1.1'

# RFC 3565 §5.1: AES-CBC, by OID: (asn1crypto name, key bytes)
CONTENT_CIPHERS = {
    '2.16.840.1.101.3.4.1.2': ('aes128_cbc', 16),
    '2.16.840.1.101.3.4.1.22': ('aes192_cbc', 24),
    '2.16.840.1.101.3.4.1.42': ('aes256_cbc', 32),
}
AES256_CBC = '2.16.840.1.101.3.4.1.42'
# RFC 3565 §2.3.2: id-aes*-wrap, parameters absent
KEY_WRAPS = {
    '2.16.840.1.101.3.4.1.5': ('aes128_wrap', 16),
    '2.16.840.1.101.3.4.1.25': ('aes192_wrap', 24),
    '2.16.840.1.101.3.4.1.45': ('aes256_wrap', 32),
}
# RFC 5753 §7.1.4, by OID: (name, KDF hash); every supported curve has cofactor 1, so the
# cofactor primitive gives the standard shared secret
KEY_AGREEMENTS = {
    f'1.3.132.1.{arc}.{n}': (f'dhSinglePass-{kind}-{h}kdf-scheme', h)
    for arc, kind in ((11, 'stdDH'), (14, 'cofactorDH'))
    for n, h in enumerate(('sha224', 'sha256', 'sha384', 'sha512'))
}
STD_DH_SHA256 = '1.3.132.1.11.1'
# Key transport and agreement UCM recognises without using: sha1kdf ECDH, ECMQV, X25519/X448,
# RFC 8418 HKDF, RSA-KEM (RFC 5990); one listed means the client named its key encipherment
_OTHER_KEY_ENCIPHERMENT = frozenset((
    '1.2.840.113549.1.9.16.3.14',
    '1.3.133.16.840.63.0.2', '1.3.133.16.840.63.0.3', '1.3.133.16.840.63.0.16',
    '1.3.132.1.15.0', '1.3.132.1.15.1', '1.3.132.1.15.2', '1.3.132.1.15.3',
    '1.3.101.110', '1.3.101.111',
    '1.2.840.113549.1.9.16.3.19', '1.2.840.113549.1.9.16.3.20', '1.2.840.113549.1.9.16.3.21',
))
_OAEP_FIELDS = frozenset(('hash_algorithm', 'mask_gen_algorithm', 'p_source_algorithm'))


def _rfc3560_oaep(arc):
    digest = f'300d0609608648016503040{arc}0500'
    return bytes.fromhex(f'302b{digest}301a06092a864886f70d010108{digest}')


# RFC 3560 §5 capability parameters as printed there, without the [0] and [1] tags of its
# ASN.1 module; matched byte for byte (RFC 8551 §2.5.2)
_RFC3560_OAEP = {
    _rfc3560_oaep('201'): ('sha256', 'sha256'),
    _rfc3560_oaep('202'): ('sha384', 'sha384'),
    _rfc3560_oaep('203'): ('sha512', 'sha512'),
}
_KARI_CURVES = (ec.SECP256R1, ec.SECP384R1, ec.SECP521R1,
                ec.BrainpoolP256R1, ec.BrainpoolP384R1, ec.BrainpoolP512R1)


@dataclass(frozen=True)
class KeyTransport:
    """RSAES-OAEP with its hashes, or RSAES-PKCS1-v1_5 when ``oaep_hash`` is None."""
    oaep_hash: str | None = 'sha256'
    mgf_hash: str | None = 'sha256'

    def fits(self, public_key, content_key_size):
        """RFC 8017 §7.1.1 and §7.2.1: the CEK fits the modulus under this padding."""
        k = (public_key.key_size + 7) // 8
        if self.oaep_hash is None:
            return content_key_size <= k - 11
        return content_key_size <= k - 2 * OAEP_HASHES[self.oaep_hash].digest_size - 2


@dataclass(frozen=True)
class KeyAgreement:
    scheme: str = STD_DH_SHA256  # key agreement OID
    wrap: str = '2.16.840.1.101.3.4.1.45'

    @property
    def kdf_hash(self):
        return KEY_AGREEMENTS[self.scheme][1]


@dataclass(frozen=True)
class KeyEncryption:
    content: str  # content-encryption OID
    recipient: KeyTransport | KeyAgreement

    @property
    def content_name(self):
        return CONTENT_CIPHERS[self.content][0]

    @property
    def content_key_size(self):
        return CONTENT_CIPHERS[self.content][1]


class UnsupportedCapabilities(ValueError):
    """The client's SMIMECapabilities list nothing UCM can encrypt to; the message says what is."""


def smime_capabilities(csr_der):
    """[(capability OID, parameters DER or None)] of the CSR's SMIMECapabilities, None when absent.
    ValueError when the attribute is repeated, multi-valued or does not parse."""
    try:
        info = asn1_csr.CertificationRequest.load(csr_der)['certification_request_info']
        found = [a for a in info['attributes'] if a['type'].dotted == SMIME_CAPABILITIES_OID]
        if not found:
            return None
        if len(found) > 1:
            raise ValueError('more than one SMIMECapabilities attribute')
        values = found[0]['values']
        values = values.parse(_AnySet) if isinstance(values, core.Any) else values
        if len(values) != 1:
            raise ValueError('SMIMECapabilities must carry a single value')  # RFC 8551 §2.5.2
        capabilities = cms.SMIMECapabilites.load(values[0].dump(), strict=True)
        out = []
        for capability in capabilities:
            params = capability['parameters']
            # the client's own bytes: RFC 8551 §2.5.2 matches capabilities by binary comparison
            out.append((capability['capability_id'].dotted,
                        None if isinstance(params, core.Void) else params.dump()))
        return out
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f'unreadable SMIMECapabilities: {e}') from e


class _AnySet(core.SetOf):
    _child_spec = core.Any


def recipient_refusal(cert):
    """Why the server-generated key cannot be encrypted to *cert*, None when it can
    (RFC 7030 §4.4.1.2: key transport or key agreement asserted, or use unrestricted)."""
    try:
        usage = cert.extensions.get_extension_for_class(x509.KeyUsage).value
    except x509.ExtensionNotFound:
        usage = None
    # RFC 4055 §1.2: an id-RSASSA-PSS key signs only
    if cert.public_key_algorithm_oid.dotted_string == '1.2.840.113549.1.1.10':
        return 'Requested asymmetric key is an RSASSA-PSS key, which does not allow key transport'
    public_key = cert.public_key()
    if isinstance(public_key, rsa.RSAPublicKey):
        if usage is not None and not usage.key_encipherment:
            return 'Requested asymmetric key does not allow key transport'
        if public_key.key_size < 2048:
            return 'Client RSA key under 2048 bits: key transport refused'
        return None
    if isinstance(public_key, ec.EllipticCurvePublicKey):
        if usage is not None and not usage.key_agreement:
            return 'Requested asymmetric key does not allow key agreement'
        if not isinstance(public_key.curve, _KARI_CURVES):
            return f'Unsupported client key agreement curve: {public_key.curve.name}'
        if fips_mode.enabled() and not key_algorithms.fips_approved_for_key(public_key):
            return f'Client key agreement curve {public_key.curve.name} not available in FIPS mode'
        return None
    return 'Unsupported client key: RSA key transport or EC key agreement only'


def _key_transport(oid, params_der):
    """The KeyTransport a capability names, None when UCM cannot use it."""
    if oid == RSA_ENCRYPTION:
        return None if fips_mode.enabled() else KeyTransport(None, None)
    if oid != RSAES_OAEP:
        return None
    if params_der in _RFC3560_OAEP:
        return KeyTransport(*_RFC3560_OAEP[params_der])
    try:
        params = algos.RSAESOAEPParams.load(params_der, strict=True) if params_der else None
        # Fields asn1crypto does not know show as numbered keys: not defaults to assume
        if params is not None and not _known_fields(params.native, _OAEP_FIELDS):
            return None
        hash_name, mgf_hash, label = oaep_parameters(params)
    except Exception:
        return None
    if label or hash_name not in OAEP_HASHES or mgf_hash not in OAEP_HASHES:
        return None
    return KeyTransport(hash_name, mgf_hash)


def _known_fields(native, top):
    if isinstance(native, dict):
        if top is not None and not set(native) <= top:
            return False
        return all(not (isinstance(k, str) and k.isdigit()) and _known_fields(v, None)
                   for k, v in native.items())
    return True


def _key_agreement(oid, params_der):
    if oid not in KEY_AGREEMENTS or not params_der:
        return None
    try:
        wrap = cms.KeyEncryptionAlgorithm.load(params_der)
        wrap_oid = wrap['algorithm'].dotted
        wrap_params = wrap['parameters']
    except (ValueError, TypeError):
        return None
    # RFC 3565 §2.3.2 has them absent; NULL is read as absent, as RFC 4055 §2.1 does for hashes
    if wrap_oid not in KEY_WRAPS or not (
            isinstance(wrap_params, core.Void) or wrap_params.dump() == b'\x05\x00'):
        return None
    return KeyAgreement(oid, wrap_oid)


def supported_text(public_key):
    """What UCM can encrypt to *public_key*, for the problem text of a refusal."""
    content = 'content encryption AES-128-CBC, AES-192-CBC or AES-256-CBC'
    if isinstance(public_key, ec.EllipticCurvePublicKey):
        return ('supported: key agreement dhSinglePass-stdDH or -cofactorDH with sha224kdf, '
                'sha256kdf, sha384kdf or sha512kdf and id-aes128-wrap, id-aes192-wrap or '
                f'id-aes256-wrap; {content} of the key wrap size')
    # SHA-1 OAEP stays in FIPS mode, as for SCEP (SP 800-131A: a non-signature use)
    transport = 'key transport RSAES-OAEP with SHA-1, SHA-224, SHA-256, SHA-384 or SHA-512'
    if not fips_mode.enabled():
        transport += ', or RSAES-PKCS1-v1_5 when nothing else is listed'
    return f'supported: {transport}; {content}'


def _aes_cbc(size):
    return next(oid for oid, (_, s) in CONTENT_CIPHERS.items() if s == size)


def choose_key_encryption(public_key, capabilities):
    """The KeyEncryption for *public_key* from *capabilities* (smime_capabilities output); the
    defaults when they are None. UnsupportedCapabilities when key transport or agreement entries
    are listed and none is usable; content ciphers fall back to AES-CBC (RFC 8551 §2.5.2: partial)."""
    is_ec = isinstance(public_key, ec.EllipticCurvePublicKey)
    if capabilities is None:
        return KeyEncryption(AES256_CBC, KeyAgreement() if is_ec else KeyTransport())

    contents = [oid for oid, _ in capabilities if oid in CONTENT_CIPHERS]
    named = any(o in (RSA_ENCRYPTION, RSAES_OAEP) or o in KEY_AGREEMENTS
                or o in _OTHER_KEY_ENCIPHERMENT for o, _ in capabilities)
    if is_ec:
        agreements = [a for a in (_key_agreement(o, p) for o, p in capabilities) if a]
        if not agreements and not named:
            agreements = [KeyAgreement()]
        # RFC 8551 §2.3: the key wrap and the content cipher have the same key size
        for content in contents:
            for agreement in agreements:
                if CONTENT_CIPHERS[content][1] == KEY_WRAPS[agreement.wrap][1]:
                    return KeyEncryption(content, agreement)
        if agreements:
            return KeyEncryption(_aes_cbc(KEY_WRAPS[agreements[0].wrap][1]), agreements[0])
    else:
        content = contents[0] if contents else AES256_CBC
        transports = [t for t in (_key_transport(o, p) for o, p in capabilities) if t]
        if not transports and not named:
            transports = [KeyTransport()]
        transports = [t for t in transports if t.fits(public_key, CONTENT_CIPHERS[content][1])]
        # RSAES-PKCS1-v1_5 only when the client lists no OAEP UCM can use
        transport = next((t for t in transports if t.oaep_hash), transports[0] if transports else None)
        if transport is not None:
            return KeyEncryption(content, transport)
    raise UnsupportedCapabilities(
        f'SMIMECapabilities list no supported key encryption for this client key; '
        f'{supported_text(public_key)}')

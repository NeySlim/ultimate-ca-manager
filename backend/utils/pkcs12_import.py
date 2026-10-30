"""PKCS#12 import in FIPS mode: the module has no PKCS12KDF, so no archive's
MAC can be verified and every read fails as a wrong password. Refused first,
with a message naming the formats that do import."""
from asn1crypto import pkcs12 as asn1_pkcs12

import fips_mode
from fips_mode import FipsRestricted

REFUSAL = ('PKCS#12 import not available in FIPS mode: import the certificate '
           'as PEM and the private key as PEM or encrypted PKCS#8')


def looks_like_pkcs12(data) -> bool:
    """A PFX v3 whose authSafe is data or signedData (RFC 7292 section 4)."""
    if not isinstance(data, (bytes, bytearray)):
        return False
    try:
        pfx = asn1_pkcs12.Pfx.load(bytes(data))
        return (pfx['version'].native == 'v3'
                and pfx['auth_safe']['content_type'].native in ('data', 'signed_data'))
    except Exception:
        return False


UNREADABLE_KEY = ('The private key in this PKCS#12 cannot be read: PKCS#12 import does not '
                  'support post-quantum keys such as ML-DSA. Import the certificate and the '
                  'private key as PEM files instead')


def load_key_and_certificates(data, password):
    """pyca's PKCS#12 reader; a key it cannot decode once the password is accepted
    (ML-DSA, which pyca has no PKCS#12 support for) raises UnsupportedForKeyAlgorithm."""
    from cryptography.hazmat.primitives.serialization import pkcs12
    from utils.algorithm_refusal import UnsupportedForKeyAlgorithm
    try:
        return pkcs12.load_key_and_certificates(data, password)
    except ValueError as exc:
        # pyca says "Invalid password or PKCS12 data" before it reaches the key
        if 'deserialize key data' not in str(exc):
            raise
        raise UnsupportedForKeyAlgorithm(UNREADABLE_KEY, export_format='PKCS#12') from exc


def refuse_pkcs12_import(data=None) -> None:
    """Raise FipsRestricted in FIPS mode, for ``data`` that is a PKCS#12
    (or unconditionally when the caller already knows it is one)."""
    if fips_mode.enabled() and (data is None or looks_like_pkcs12(data)):
        raise FipsRestricted(REFUSAL)

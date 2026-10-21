"""PKCS#12 encryption profiles for every archive UCM produces (#331).

Two profiles, the same two the rest of the ecosystem settled on:

* **modern** (default): what ``BestAvailableEncryption`` yields with OpenSSL 3,
  PBES2 with AES-256-CBC and PBKDF2-HMAC-SHA256 for the key and certificate
  bags, HMAC-SHA256 for the integrity MAC. Read by OpenSSL 1.1.1+, Java 12+,
  Windows 10 1709 / Server 2019+, macOS 15 / iOS 18+, Android 16+.
* **legacy** (the "compatibility" checkbox): PBES1 with 3-key Triple DES
  and SHA-1 for both bags, HMAC-SHA1 MAC, the ``-descert`` profile of
  OpenSSL 1.1 and the ``LegacyDES`` profile of go-pkcs12 / cert-manager.
  Read by everything above plus the importers that reject PBES2 or a SHA-2
  MAC with a misleading "wrong password": Android 15 and earlier (Bouncy
  Castle 1.68 fork), macOS 14 / iOS 17 and earlier, Windows Server 2016
  and earlier, Java 11 before 11.0.1 and Java 8 before 8u301. RC2-40, what
  ``openssl pkcs12 -legacy`` emits for certificates, is deliberately not
  offered: OpenSSL 3 itself cannot read it without the legacy provider.

Legacy protects the archive less well than AES-256; it is an explicit,
per-export opt-in, never a stored default.
"""
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs12

import compliance_profiles
import fips_mode

_TRUE_STRINGS = frozenset({'1', 'true', 'yes', 'on'})


def legacy_flag(value) -> bool:
    """Parse the ``legacy`` export option (a JSON boolean, or a form string)."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in _TRUE_STRINGS


def pkcs12_encryption(password, legacy: bool = False, *, ca_id=None, caref=None):
    """The ``encryption_algorithm`` for ``pkcs12.serialize_key_and_certificates``.
    The legacy profile is refused in FIPS mode and for a CA (*ca_id*, or the
    issuer *caref* of a certificate) that holds a compliance profile."""
    secret = password.encode() if isinstance(password, str) else bytes(password)
    if not legacy:
        return serialization.BestAvailableEncryption(secret)
    fips_mode.refuse('PKCS#12 legacy encryption (3DES/SHA-1)')
    compliance_profiles.refuse_legacy_pkcs12(ca_id=ca_id, caref=caref)
    return (
        serialization.PrivateFormat.PKCS12.encryption_builder()
        .key_cert_algorithm(pkcs12.PBES.PBESv1SHA1And3KeyTripleDESCBC)
        .hmac_hash(hashes.SHA1())
        .build(secret)
    )

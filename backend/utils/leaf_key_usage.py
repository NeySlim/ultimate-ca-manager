"""Key-algorithm-aware KeyUsage for certificates, leaf and sub-CA (#327).

keyEncipherment and dataEncipherment describe RSA key transport: the
certified public key encrypts a symmetric key (or data) directly. No other
key type UCM issues for can do that. RFC 5480 §3 restricts an id-ecPublicKey
end-entity certificate to digitalSignature, nonRepudiation and keyAgreement
(encipherOnly/decipherOnly only under keyAgreement); RFC 8410 §5 and
RFC 9881 §5 restrict Ed25519/Ed448 and ML-DSA to the signature bits.

UCM's leaf profiles were written with RSA in mind and asserted
keyEncipherment on every server-class certificate whatever the key, so an
ECDSA leaf carried a bit it cannot honour unless a template with the bit
deselected was used, which an ACME order (no template to select) could not
do, and certificate linters flagged the result. Every leaf issuance path
(issue form, approval workflow, Sign CSR, ACME, EST, SCEP, WSTEP) now routes
its KeyUsage through this module, so the same key gets the same bits
whichever way it arrives, with no configuration needed.
"""
from typing import Iterable, Optional

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, ExtensionOID


def key_usage_for_key(
    public_key,
    usage: x509.KeyUsage,
    ekus: Optional[Iterable[x509.ObjectIdentifier]] = None,
) -> x509.KeyUsage:
    """Return *usage* with the bits *public_key*'s algorithm cannot honour cleared.

    RSA keys pass through untouched. An EC key loses keyEncipherment and
    dataEncipherment; when the certificate is an S/MIME one (emailProtection
    in *ekus*) that encryption intent is kept as keyAgreement instead, which
    is how an EC key encrypts in CMS (ECDH, RFC 5753 §3.1) and the bit
    S/MIME clients such as NSS require on an EC recipient certificate.
    Any other key type (Ed25519, Ed448, ML-DSA) keeps only the signature bits.
    digitalSignature is set when no other bit is left (RFC 5280 §4.2.1.3).
    """
    if isinstance(public_key, rsa.RSAPublicKey):
        return usage

    wants_encryption = usage.key_encipherment or usage.data_encipherment
    key_agreement = usage.key_agreement
    if isinstance(public_key, ec.EllipticCurvePublicKey):
        if wants_encryption and ExtendedKeyUsageOID.EMAIL_PROTECTION in set(ekus or ()):
            key_agreement = True
    else:
        key_agreement = False

    # encipherOnly/decipherOnly are only readable (and only meaningful) when
    # keyAgreement was set on the source usage.
    encipher_only = decipher_only = False
    if key_agreement and usage.key_agreement:
        encipher_only, decipher_only = usage.encipher_only, usage.decipher_only

    # RFC 5280 §4.2.1.3: at least one bit; a usage that only asked to encrypt signs instead
    digital_signature = usage.digital_signature or not (
        usage.content_commitment or key_agreement or usage.key_cert_sign or usage.crl_sign)
    return x509.KeyUsage(
        digital_signature=digital_signature,
        content_commitment=usage.content_commitment,
        key_encipherment=False,
        data_encipherment=False,
        key_agreement=key_agreement,
        key_cert_sign=usage.key_cert_sign,
        crl_sign=usage.crl_sign,
        encipher_only=encipher_only,
        decipher_only=decipher_only,
    )


_ENCRYPTION_BITS = (('key_encipherment', 'keyEncipherment'), ('data_encipherment', 'dataEncipherment'),
                    ('key_agreement', 'keyAgreement'))


def key_usage_notice(public_key, asked: x509.KeyUsage, granted: x509.KeyUsage) -> Optional[str]:
    """Notice naming the encryption bits *asked* had and *granted* lost, None when none was lost.
    An encryption intent kept as keyAgreement (S/MIME on EC) is not a loss."""
    from utils import key_algorithms, notices
    kept_as_agreement = granted.key_agreement and not asked.key_agreement
    dropped = [name for attr, name in _ENCRYPTION_BITS
               if getattr(asked, attr) and not getattr(granted, attr)
               and not (kept_as_agreement and attr != 'key_agreement')]
    if not dropped:
        return None
    label = key_algorithms.label_for_public_key(public_key) or type(public_key).__name__
    return notices.key_usage_dropped(
        dropped, label, key_algorithms.family_for_public_key(public_key),
        signature_added=granted.digital_signature and not asked.digital_signature)


def builder_key_usage(builder: x509.CertificateBuilder) -> Optional[x509.KeyUsage]:
    return next((e.value for e in builder._extensions if e.oid == ExtensionOID.KEY_USAGE), None)


def constrain_builder_key_usage(
    builder: x509.CertificateBuilder,
) -> x509.CertificateBuilder:
    """Apply :func:`key_usage_for_key` to the KeyUsage already on *builder*.

    For the CSR-driven paths (sign_csr, SCEP), where the KeyUsage is settled
    before the ExtendedKeyUsage is known. CertificateBuilder is immutable and
    cannot swap an extension, so a changed KeyUsage means rebuilding the
    builder with the same fields, the way sign_csr already does when it
    re-merges EKUs. A builder without a KeyUsage, or whose KeyUsage needs no
    change, is returned as is.
    """
    ku_ext = next(
        (e for e in builder._extensions if e.oid == ExtensionOID.KEY_USAGE), None
    )
    if ku_ext is None:
        return builder
    eku_ext = next(
        (e for e in builder._extensions if e.oid == ExtensionOID.EXTENDED_KEY_USAGE),
        None,
    )
    fixed = key_usage_for_key(
        builder._public_key, ku_ext.value, eku_ext.value if eku_ext else None
    )
    if fixed == ku_ext.value:
        return builder

    rebuilt = (
        x509.CertificateBuilder()
        .subject_name(builder._subject_name)
        .issuer_name(builder._issuer_name)
        .public_key(builder._public_key)
        .serial_number(builder._serial_number)
        .not_valid_before(builder._not_valid_before)
        .not_valid_after(builder._not_valid_after)
    )
    for ext in builder._extensions:
        value = fixed if ext.oid == ExtensionOID.KEY_USAGE else ext.value
        rebuilt = rebuilt.add_extension(value, ext.critical)
    return rebuilt

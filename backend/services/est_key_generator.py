"""The EST key generator certificate of a CA (RFC 7030 §4.4.2: the party that generated the
key signs the package). Issued by the CA with digitalSignature only, so it works under a root
whose own keyUsage is keyCertSign and cRLSign; made on first use and replaced in place."""
import hashlib
import logging
from datetime import timedelta

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import NameOID
from sqlalchemy.exc import IntegrityError

import fips_mode
from models import db
from models.est_signer_cert import EstSignerCert
from utils import key_algorithms
from utils.datetime_utils import cert_not_before, utc_now

logger = logging.getLogger(__name__)

SUBJECT_CN = 'EST key generator'
LIFETIME_DAYS = 365
RENEW_DAYS = 30


def _fingerprint(ca_cert):
    return hashlib.sha256(ca_cert.public_bytes(serialization.Encoding.DER)).hexdigest()


def delegate_key_label(ca_public_key):
    """The CA's family where OpenSSL verifies it in CMS (Ed448 gives Ed25519), FIPS-approved."""
    family = key_algorithms.family_for_public_key(ca_public_key)
    if family == 'RSA':
        label = 'RSA-3072'
    elif family in ('EC', 'ML-DSA'):
        label = key_algorithms.label_for_public_key(ca_public_key)
    else:
        label = 'ED25519'
    if fips_mode.enabled() and not key_algorithms.fips_approved(label):
        from utils.issuance_defaults import _of_strength, _security_bits
        label = _of_strength('EC', _security_bits(ca_public_key)).label
    return label


def _issue(ca, ca_cert, key):
    """A certificate for *key* signed by *ca* through its signing key, HSM included."""
    from services.ca.ca_signing import CASigningMixin
    from services.hsm.ca_key_loader import get_ca_signing_key
    from services.policy_service import PolicyEvaluationService, PolicyViolation
    from utils.ca_signing_window import check_issuer_window, clamp_not_after
    from utils.signing_hash import rsa_padding_for
    from utils.x509_aki import authority_key_identifier_from_issuer

    CASigningMixin._check_ca_offline(ca)
    check_issuer_window(ca_cert)
    ca_key = get_ca_signing_key(ca)
    names = [*ca_cert.subject.get_attributes_for_oid(NameOID.ORGANIZATION_NAME),
             x509.NameAttribute(NameOID.COMMON_NAME, SUBJECT_CN)]
    not_after = clamp_not_after(utc_now() + timedelta(days=LIFETIME_DAYS), ca_cert)
    builder = (
        x509.CertificateBuilder()
        .subject_name(x509.Name(names))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(cert_not_before())
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
            encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(authority_key_identifier_from_issuer(ca_cert), critical=False)
    )
    # The CA key's own digest and signature rules; no issuance policy scopes an internal signer
    sign_hash, violations = PolicyEvaluationService.checked_signing_hash(
        [], ca_key, None, explicit=True,
        key_type=key_algorithms.label_for_public_key(key.public_key()),
        context={'operation': 'issuance', 'ca_id': ca.id, 'subject': SUBJECT_CN})
    if violations:
        raise PolicyViolation('; '.join(violations))
    cert = builder.sign(ca_key, sign_hash, rsa_padding=rsa_padding_for(ca_key, sign_hash))
    return cert, not_after


def _load(row):
    from utils.key_codec import load_pem_bytes
    key = serialization.load_pem_private_key(
        load_pem_bytes(row.prv, context=f'EST key generator of CA {row.ca_id}'), password=None)
    return key, x509.load_pem_x509_certificate(row.crt.encode())


def _current(row, fingerprint, ca_cert):
    """Whether *row* may keep signing: same CA certificate, and a renewal would not gain time."""
    if row is None or row.issuer_fingerprint != fingerprint:
        return False
    if row.not_after - utc_now() >= timedelta(days=RENEW_DAYS):
        return True
    from utils.ca_signing_window import clamp_not_after
    return clamp_not_after(utc_now() + timedelta(days=LIFETIME_DAYS), ca_cert) <= row.not_after


def key_generator(ca, ca_cert):
    """(private key, certificate) of the CA's key generator, issued or re-issued as needed.

    Two first requests at once insert one row: the loser of the unique ca_id reads the winner's.
    """
    from utils.key_codec import store_pem_bytes
    fingerprint = _fingerprint(ca_cert)
    row = EstSignerCert.query.filter_by(ca_id=ca.id).first()
    if _current(row, fingerprint, ca_cert):
        return _load(row)
    key = key_algorithms.generate(delegate_key_label(ca_cert.public_key()))
    cert, not_after = _issue(ca, ca_cert, key)
    values = dict(
        crt=cert.public_bytes(serialization.Encoding.PEM).decode(),
        prv=store_pem_bytes(key.private_bytes(serialization.Encoding.PEM,
                                              serialization.PrivateFormat.PKCS8,
                                              serialization.NoEncryption())),
        issuer_fingerprint=fingerprint, not_after=not_after, created_at=utc_now())
    try:
        with db.session.begin_nested():
            if row is None:
                db.session.add(EstSignerCert(ca_id=ca.id, **values))
            else:
                for name, value in values.items():
                    setattr(row, name, value)
        db.session.commit()
    except IntegrityError:  # the savepoint is rolled back, the caller's transaction kept
        winner = EstSignerCert.query.filter_by(ca_id=ca.id).first()
        logger.info('EST key generator of CA %s made by a concurrent request', ca.id)
        return _load(winner)
    logger.info('EST key generator of CA %s issued, valid until %s', ca.id, not_after)
    return key, cert

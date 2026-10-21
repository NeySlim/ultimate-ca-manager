"""An unknown signature hash is refused, not replaced by SHA-256.

`HASH_ALGORITHMS.get(digest, SHA256())` signed 'sha1' or a typo in SHA-256
without a word: a policy or a compliance profile could not guarantee the hash
it was asked for. SHA-224 left the table to match the policy digests.
"""
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from services.policy_service import PolicyEvaluationService
from services.trust_store.constants import hash_algorithm
from services.trust_store.csr_operations_mixin import CSROperationsMixin

SUBJECT = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'hash fallback')])


@pytest.mark.parametrize('name, expected', [
    (None, hashes.SHA256), ('', hashes.SHA256), ('sha384', hashes.SHA384), (' SHA512 ', hashes.SHA512),
])
def test_known_hashes_resolve(name, expected):
    assert isinstance(hash_algorithm(name), expected)


@pytest.mark.parametrize('name', ['sha1', 'md5', 'sha224', 'sha3_256', 'sha265'])
def test_unknown_hashes_are_refused(name):
    with pytest.raises(ValueError, match='Unsupported signature hash'):
        hash_algorithm(name)


def test_csr_generation_refuses_an_unknown_hash():
    with pytest.raises(ValueError, match='Unsupported signature hash'):
        CSROperationsMixin.generate_csr(SUBJECT, key_type='prime256v1', digest='sha1')


def test_ca_csr_generation_refuses_an_unknown_hash():
    with pytest.raises(ValueError, match='Unsupported signature hash'):
        CSROperationsMixin.generate_ca_csr(SUBJECT, ec.generate_private_key(ec.SECP256R1()), digest='sha1')


def test_checked_signing_hash_reports_an_unknown_hash(app):
    with app.app_context():
        _, violations = PolicyEvaluationService.checked_signing_hash(
            [], ec.generate_private_key(ec.SECP256R1()), 'sha1')
    assert any('Unsupported signature hash' in v for v in violations)


def test_tsa_refuses_an_eddsa_signer_instead_of_signing_v15():
    from datetime import datetime, timedelta, timezone
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from services.tsa_service import TSAService
    key = ed25519.Ed25519PrivateKey.generate()
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(SUBJECT).issuer_name(SUBJECT)
            .public_key(key.public_key()).serial_number(1)
            .not_valid_before(now).not_valid_after(now + timedelta(days=1))
            .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.TIME_STAMPING]), critical=True)
            .sign(key, None))
    tsa = TSAService(cert, key)
    with pytest.raises(ValueError, match='RSA or ECDSA'):
        tsa._build_signed_response(b'\x30\x00', False, 'sha256')


def test_tsa_does_not_offer_an_eddsa_signer(app):
    """Refused when chosen, not at every timestamp request afterwards."""
    import base64, uuid
    from datetime import datetime, timedelta, timezone
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from api.v2.tsa import _validate_signer_refid
    from models import db, Certificate
    from utils.key_codec import store_pem_bytes
    key = ed25519.Ed25519PrivateKey.generate()
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(SUBJECT).issuer_name(SUBJECT)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
            .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.TIME_STAMPING]), critical=True)
            .sign(key, None))
    with app.app_context():
        row = Certificate(refid=str(uuid.uuid4()), descr='Ed TSA', subject=SUBJECT.rfc4514_string(),
                          crt=base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode(),
                          prv=store_pem_bytes(key.private_bytes(serialization.Encoding.PEM,
                                                                serialization.PrivateFormat.PKCS8,
                                                                serialization.NoEncryption())))
        db.session.add(row); db.session.commit()
        error, _ = _validate_signer_refid(row.refid)
    assert error and 'RSA or ECDSA' in error

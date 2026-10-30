"""Post-quantum test material, made once by OpenSSL 3.5 (``fixtures/pqc/regenerate.sh``)
and only read here: no test runs openssl."""
import base64
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization

PQC_DIR = Path(__file__).parent / 'fixtures' / 'pqc'
P12_PASSWORD = b'pqc-fixture'   # as in regenerate.sh


def fixture_bytes(name: str) -> bytes:
    return (PQC_DIR / name).read_bytes()


def load_mldsa_key():
    """The fixture ML-DSA-65 private key (seed-only PKCS#8, the layout pyca reads)."""
    return serialization.load_pem_private_key(fixture_bytes('mldsa65-seed.pem'), None)


@pytest.fixture
def mldsa_key():
    return load_mldsa_key()


@pytest.fixture
def mldsa_csr():
    """CSR made by OpenSSL with ``mldsa_key``, subject CN=UCM PQC fixture ML-DSA-65."""
    return x509.load_pem_x509_csr(fixture_bytes('mldsa65-csr.pem'))


@pytest.fixture
def mldsa_ca(app):
    """CA row inserted directly with the self-signed ``mldsa65-cert.pem`` and ``mldsa_key``,
    since UCM cannot create an ML-DSA CA yet; runs inside an app context."""
    with mldsa_ca_row(app) as ca:
        yield ca


@contextmanager
def mldsa_ca_row(app):
    """Body of ``mldsa_ca``; its CRLs and certificates go with it."""
    from models import CA, db
    pem = fixture_bytes('mldsa65-cert.pem')
    cert = x509.load_pem_x509_certificate(pem)
    name = cert.subject.rfc4514_string()
    refid = f'pqc-mldsa65-{uuid.uuid4().hex[:12]}'
    with app.app_context():
        ca = CA(refid=refid, descr=f'PQC fixture {refid}', serial=0,
                crt=base64.b64encode(pem).decode(),
                prv=base64.b64encode(fixture_bytes('mldsa65-seed.pem')).decode(),
                subject=name, issuer=name, serial_number=str(cert.serial_number),
                ski=cert.extensions.get_extension_for_class(
                    x509.SubjectKeyIdentifier).value.key_identifier.hex(':').upper(),
                valid_from=cert.not_valid_before_utc, valid_to=cert.not_valid_after_utc,
                imported_from='manual')
        db.session.add(ca)
        db.session.commit()
        ca_id = ca.id
        try:
            yield ca
        finally:
            from models import Certificate, CRLMetadata
            db.session.rollback()
            # Children first: a reused id would inherit them, and PostgreSQL refuses the delete.
            CRLMetadata.query.filter_by(ca_id=ca_id).delete()
            Certificate.query.filter_by(caref=refid).delete()
            CA.query.filter_by(refid=refid).delete()
            db.session.commit()

"""The TrustStore layer generates a key without the database: with no key_type it falls
back to the baseline key; the callers that know a CA, a template or the policies pass theirs."""
import base64

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from utils import issuance_defaults

SUBJECT = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'no-db.example.test')])


def test_generate_csr_outside_an_app_context_uses_the_baseline_key(monkeypatch):
    from services.trust_store import TrustStoreService
    monkeypatch.setattr(issuance_defaults, 'BASELINE_ISSUE_KEY', 'RSA-3072')
    csr_pem, _ = TrustStoreService.generate_csr(SUBJECT)
    key = x509.load_pem_x509_csr(csr_pem).public_key()
    assert isinstance(key, rsa.RSAPublicKey) and key.key_size == 3072


def test_service_csr_without_key_type_follows_the_global_policies(app, monkeypatch):
    from models import Certificate, db
    from services.cert_service import CertificateService
    monkeypatch.setattr(issuance_defaults, 'default_issue_key_type', lambda *a, **k: 'RSA-3072')
    with app.app_context():
        row = CertificateService.generate_csr(descr='no-db-svc', dn={'CN': 'no-db-svc.example.test'})
        csr = x509.load_pem_x509_csr(base64.b64decode(row.csr))
        assert csr.public_key().key_size == 3072
        db.session.delete(db.session.get(Certificate, row.id))
        db.session.commit()

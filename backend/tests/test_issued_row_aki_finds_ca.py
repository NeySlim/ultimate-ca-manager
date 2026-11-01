"""A row issued by the shared CSR trunk or imported from a Microsoft CA keeps the
AKI/SKI the crt listener writes, so find_ca_by_ski(row.aki) finds the issuing CA."""
import base64
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from models import CA, Certificate, db
from services.ca_service import CAService
from utils.cert_issuer import find_ca_by_ski
from utils.key_codec import load_pem_bytes


def _csr(cn):
    key = ec.generate_private_key(ec.SECP256R1())
    return (x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
            .sign(key, hashes.SHA256()))


def _assert_finds(row, ca, cert):
    ski = cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value.digest
    assert row.ski == ski.hex(':').upper()
    assert row.aki == ca.ski
    assert find_ca_by_ski(row.aki).id == ca.id


def test_sign_csr_row_aki_finds_its_ca(app, create_ca):
    ca_data = create_ca(cn='AKI lookup CA (CSR trunk)')
    with app.app_context():
        ca = db.session.get(CA, ca_data['id'])
        cert_pem, _ = CAService.sign_csr_from_crypto(ca=ca, csr=_csr('aki-trunk.example.test'),
                                                     validity_days=30, source='test')
        cert = x509.load_pem_x509_certificate(
            cert_pem.encode() if isinstance(cert_pem, str) else cert_pem)
        row = Certificate.query.filter_by(serial_number=str(cert.serial_number)).one()
        _assert_finds(row, ca, cert)


def _ca_signed(ca, cn):
    """A leaf the CA signs directly, standing in for what the Microsoft CA returns."""
    ca_cert = x509.load_pem_x509_certificate(base64.b64decode(ca.crt))
    ca_key = serialization.load_pem_private_key(load_pem_bytes(ca.prv), password=None)
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.now(timezone.utc)
    return (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
            .issuer_name(ca_cert.subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=30))
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(
                ca_cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value),
                critical=False)
            .sign(ca_key, hashes.SHA256()))


def test_msca_import_row_aki_finds_its_ca(app, create_ca):
    from api.v2.msca import _import_signed_cert
    ca_data = create_ca(cn='AKI lookup CA (MS CA import)')
    with app.app_context():
        ca = db.session.get(CA, ca_data['id'])
        msca = SimpleNamespace(name='aki-lookup')
        # Without a CSR row: a new certificate row
        cert = _ca_signed(ca, 'aki-msca-new.example.test')
        _import_signed_cert(None, cert.public_bytes(serialization.Encoding.PEM).decode(),
                            msca, 'WebServer', None)
        row = Certificate.query.filter_by(serial_number=format(cert.serial_number, 'X')).one()
        _assert_finds(row, ca, cert)
        # With a CSR row: updated in place
        pending = Certificate(refid=uuid.uuid4().hex[:8], descr='aki msca csr', csr=base64.b64encode(
            _csr('aki-msca-csr.example.test').public_bytes(serialization.Encoding.PEM)).decode())
        db.session.add(pending)
        db.session.commit()
        cert = _ca_signed(ca, 'aki-msca-csr.example.test')
        _import_signed_cert(pending, cert.public_bytes(serialization.Encoding.PEM).decode(),
                            msca, 'WebServer', None)
        _assert_finds(db.session.get(Certificate, pending.id), ca, cert)


def test_renewed_row_aki_finds_its_ca(app, create_ca, create_cert):
    from services.cert.renewal import renew_certificate_in_place
    ca_data = create_ca(cn='AKI lookup CA (renewal)')
    cert_id = create_cert(ca_id=ca_data['id'], cn='aki-renew.example.test')['id']
    with app.app_context():
        renew_certificate_in_place(db.session.get(Certificate, cert_id))
        db.session.expire_all()
        row = db.session.get(Certificate, cert_id)
        assert row.renewed_times == 1
        cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
        _assert_finds(row, db.session.get(CA, ca_data['id']), cert)

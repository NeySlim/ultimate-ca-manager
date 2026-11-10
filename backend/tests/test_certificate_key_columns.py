"""certificates.key_bits and sig_hash follow crt on every issuance path, so the
dashboard compliance counters read columns instead of parsing PEM."""
import base64
import re
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from cryptography.x509.oid import NameOID

from models import CA, Certificate, db
from tests.dashboard_pem import self_signed, sha1_rsa

BACKEND = Path(__file__).resolve().parent.parent


def _columns(app, cert_id):
    with app.app_context():
        row = db.session.get(Certificate, cert_id)
        return row.key_bits, row.sig_hash


@pytest.fixture
def made_cas(auth_client):
    """CAs a test creates, deleted after its certificates (``cleanup`` depends on this)."""
    ids = []
    yield ids
    for ca_id in ids:
        r = auth_client.delete(f'/api/v2/cas/{ca_id}')
        assert r.status_code in (200, 204), r.data


@pytest.fixture
def own_ca(create_ca, made_cas):
    def make(cn):
        ca = create_ca(cn=cn)
        made_cas.append(ca['id'])
        return ca
    return make


@pytest.fixture
def cleanup(app, made_cas):
    ids = []
    yield ids
    with app.app_context():
        for cert_id in ids:
            row = db.session.get(Certificate, cert_id)
            if row is not None:
                db.session.delete(row)
        db.session.commit()


def test_setting_crt_sets_both_columns():
    row = Certificate(refid='kc', descr='kc', crt=self_signed(
        rsa.generate_private_key(public_exponent=65537, key_size=2048), hashes.SHA384()))
    assert (row.key_bits, row.sig_hash) == (2048, 'sha384')
    row.crt = sha1_rsa()
    assert (row.key_bits, row.sig_hash) == (2048, 'sha1')
    row.crt = self_signed(ec.generate_private_key(ec.SECP256R1()))
    assert (row.key_bits, row.sig_hash) == (256, 'sha256')
    row.crt = self_signed(ed25519.Ed25519PrivateKey.generate())
    assert (row.key_bits, row.sig_hash) == (None, None)


def test_the_issue_form(app, create_cert, own_ca, cleanup):
    cert = create_cert(cn='kc-form.test', ca_id=own_ca('KC Form CA')['id'], key_type='RSA', key_size=3072)
    cleanup.append(cert['id'])
    assert _columns(app, cert['id']) == (3072, 'sha256')


def test_signing_a_request_alone_and_in_bulk(app, auth_client, own_ca, cleanup):
    ca = own_ca('KC CSR CA')
    ids = []
    for i in range(2):
        key = ec.generate_private_key(ec.SECP384R1())
        csr = (x509.CertificateSigningRequestBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f'kc-csr{i}.test')]))
               .sign(key, hashes.SHA256()))
        r = auth_client.post('/api/v2/csrs/upload', json={
            'pem': csr.public_bytes(serialization.Encoding.PEM).decode(), 'name': f'kc-csr{i}'})
        assert r.status_code in (200, 201), r.data
        ids.append(r.get_json()['data']['id'])
    cleanup.extend(ids)
    r = auth_client.post(f'/api/v2/csrs/{ids[0]}/sign', json={'ca_id': ca['id'], 'validity_days': 30})
    assert r.status_code in (200, 201), r.data
    r = auth_client.post('/api/v2/csrs/bulk/sign', json={'ids': ids[1:], 'ca_id': ca['id'], 'validity_days': 30})
    assert r.status_code == 200, r.data
    for csr_id in ids:
        bits, sig_hash = _columns(app, csr_id)
        assert bits == 384 and sig_hash is not None


def test_import(app, cleanup):
    from services.cert_service import CertificateService
    pem = base64.b64decode(sha1_rsa('kc-import.test')).decode()
    with app.app_context():
        cleanup.append(CertificateService.import_certificate(descr='kc-import', cert_pem=pem).id)
    assert _columns(app, cleanup[0]) == (2048, 'sha1')


def test_in_place_renewal(app, create_cert, own_ca, cleanup):
    from services.cert.renewal import renew_certificate_in_place
    cert = create_cert(cn='kc-renew.test', ca_id=own_ca('KC Renew CA')['id'], key_type='EC', curve='P-256')
    cleanup.append(cert['id'])
    with app.app_context():
        row = db.session.get(Certificate, cert['id'])
        row.key_bits = row.sig_hash = None  # only the renewal can set them again
        db.session.commit()
        renew_certificate_in_place(db.session.get(Certificate, cert['id']), username='admin')
        db.session.commit()
    assert _columns(app, cert['id']) == (256, 'sha256')


def test_tsa_signer(app, own_ca, cleanup):
    from services import tsa_signer_cert
    ca = own_ca('KC TSA CA')
    with app.app_context():
        issued = tsa_signer_cert.issue_tsa_signer_certificate(
            ca=db.session.get(CA, ca['id']), cn='kc-tsa.test', key_type='ec', curve='EC-P256')
        cleanup.append(issued.id)
    assert _columns(app, cleanup[0]) == (256, 'sha256')


# Writes that skip the ORM attribute event leave the columns empty
_BYPASS = re.compile(r'bulk_(insert|update|save)_\w*\(\s*Certificate\b|insert\(\s*Certificate\b|'
                     r'INSERT\s+INTO\s+certificates\b|UPDATE\s+certificates\s+SET\b[^"\']*\bcrt\b', re.I)
_QUERY_UPDATE_OF_CRT = re.compile(r'\.update\(\s*\{\s*Certificate\.crt\s*:')


def test_no_writer_of_crt_skips_the_attribute_event():
    sources = [p for p in BACKEND.rglob('*.py')
               if not {'tests', 'migrations', '.venv', 'venv'} & set(p.relative_to(BACKEND).parts)]
    bypass = [str(p.relative_to(BACKEND)) for p in sources if _BYPASS.search(p.read_text(errors='ignore'))]
    assert bypass == []
    for path in sources:
        text = path.read_text(errors='ignore')
        for match in _QUERY_UPDATE_OF_CRT.finditer(text):
            # the claim UPDATE is followed by the ORM assignment that fires the listener
            assert re.search(r'\bcertificate\.crt\s*=', text[match.end():match.end() + 600]), path

"""Importing a cross-certificate no longer overwrites the self-signed root.

The cross-certificate of root B by root A shares B's subject and key, so the
import matched it to B and replaced B's own certificate, parent and validity
with A's (#400). Until cross-certificates can be attached, it is refused.
"""
import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from models import db, CA


def _cert(subject_key, cn, issuer_key=None, issuer_cn=None, days=365):
    now = datetime.now(timezone.utc)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_cn or cn)])
    signer = issuer_key or subject_key
    return (x509.CertificateBuilder().subject_name(subject).issuer_name(issuer)
            .public_key(subject_key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=days))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(subject_key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(signer.public_key()), critical=False)
            .sign(signer, hashes.SHA256()))


def _pem(cert):
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def _import(auth_client, path, cert):
    return auth_client.post(path, data={'pem_content': _pem(cert)}, content_type='multipart/form-data')


@pytest.fixture
def roots(auth_client, request):
    tag = request.node.name[-24:]
    key_a, key_b = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    root_a, root_b = _cert(key_a, f'XRoot A {tag}'), _cert(key_b, f'XRoot B {tag}')
    for cert in (root_a, root_b):
        r = _import(auth_client, '/api/v2/cas/import', cert)
        assert r.status_code in (200, 201), r.data
    cross = _cert(key_b, f'XRoot B {tag}', key_a, f'XRoot A {tag}', days=200)
    return root_b, cross, key_b


@pytest.mark.parametrize('path', ['/api/v2/cas/import', '/api/v2/certificates/import'])
def test_cross_certificate_does_not_replace_the_root(app, auth_client, roots, path):
    root_b, cross, _ = roots
    r = _import(auth_client, path, cross)
    assert r.status_code == 409, r.data
    assert b'cross-certificate' in r.data
    with app.app_context():
        rows = CA.query.filter(CA.subject == root_b.subject.rfc4514_string()).all()
        assert len(rows) == 1
        stored = x509.load_pem_x509_certificate(base64.b64decode(rows[0].crt))
        assert stored.serial_number == root_b.serial_number
        assert rows[0].caref is None


def test_reissued_self_signed_root_still_updates_its_record(app, auth_client, roots):
    root_b, _, key_b = roots
    reissued = _cert(key_b, root_b.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value, days=730)
    r = _import(auth_client, '/api/v2/cas/import', reissued)
    assert r.status_code in (200, 201), r.data
    with app.app_context():
        rows = CA.query.filter(CA.subject == root_b.subject.rfc4514_string()).all()
        assert len(rows) == 1
        stored = x509.load_pem_x509_certificate(base64.b64decode(rows[0].crt))
        assert stored.serial_number == reissued.serial_number


def test_cross_signed_renewal_csr_does_not_replace_the_root(app, auth_client, create_ca):
    """renew-csr signed by another root, then installed: the same overwrite."""
    from tests.test_ca_external_csr import _make_external_root, _sign_csr_as_external_root
    root = create_ca(cn='XRoot renew-csr B')
    other_key, other_cert = _make_external_root(cn='XRoot renew-csr A')
    csr = json.loads(auth_client.post(f"/api/v2/cas/{root['id']}/renew-csr", data='{}',
                                      content_type='application/json').data)['data']['csr_pem']
    cross = _sign_csr_as_external_root(csr, other_key, other_cert, days=200)
    with app.app_context():
        before = db.session.get(CA, root['id']).crt
    r = auth_client.post(f"/api/v2/cas/{root['id']}/certificate", data=json.dumps({'pem_content': cross}),
                         content_type='application/json')
    assert r.status_code in (400, 409), r.data
    assert b'cross-certificate' in r.data
    with app.app_context():
        ca = db.session.get(CA, root['id'])
        assert ca.crt == before and ca.caref is None

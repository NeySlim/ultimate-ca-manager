"""Every import entry fires certificate.imported for a row that gets its first
certificate, once: the import route, a pending CSR completed, the Smart Import."""
import base64
import datetime
import json

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from models import Certificate, db
from tests.deploy_leftovers import delete_leftovers
from tests.event_recorder import events, cert_events  # noqa: F401
from tests.test_approval_on_sign_and_renew import _csr_row
from tests.test_import_review import _cert, _gen, _import, _ca_from_fixture, _store_cert

IMPORT = '/api/v2/certificates/import'
_cleanup = pytest.fixture(autouse=True)(delete_leftovers)


def _external_cert_for(app, csr_id):
    with app.app_context():
        csr = x509.load_pem_x509_csr(base64.b64decode(db.session.get(Certificate, csr_id).csr))
    issuer_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.datetime.now(datetime.timezone.utc)
    return (x509.CertificateBuilder().subject_name(csr.subject)
            .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'External CA')]))
            .public_key(csr.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=30))
            .sign(issuer_key, hashes.SHA256()))


def test_route_import_of_a_new_certificate_fires_imported(app, auth_client, events):
    key = _gen()
    r = _import(auth_client, IMPORT, _cert('ev-import-new.example.com', key))
    assert r.status_code == 201, r.data
    cert_id = json.loads(r.data)['data']['id']
    assert cert_events(events, cert_id) == [('certificate.imported', cert_id)]


def test_route_import_completing_a_pending_csr_fires_imported(app, auth_client, events):
    csr_id = _csr_row(app, 'ev-import-csr.example.com')
    r = _import(auth_client, IMPORT, _external_cert_for(app, csr_id))
    assert r.status_code == 200, r.data
    assert json.loads(r.data)['data']['id'] == csr_id
    assert cert_events(events, csr_id) == [('certificate.imported', csr_id)]


def test_smart_import_completing_a_pending_csr_fires_imported_once(app, events):
    from services.smart_import.importer import SmartImporter
    csr_id = _csr_row(app, 'ev-smart-csr.example.com')
    cert = _external_cert_for(app, csr_id)
    with app.app_context():
        SmartImporter().execute(cert.public_bytes(serialization.Encoding.PEM).decode())
    assert cert_events(events, csr_id) == [('certificate.imported', csr_id)]


def test_route_import_into_a_row_without_certificate_fires_imported(app, auth_client, create_ca, events):
    ca = create_ca(cn='ev-keyonly CA')
    ca_cert, ca_key, caref, _ = _ca_from_fixture(app, ca)
    key = _gen()
    cert_id = _store_cert(app, _cert('ev-keyonly.example.com', key, issuer_cert=ca_cert, signer=ca_key),
                          key, caref=caref)
    with app.app_context():
        db.session.get(Certificate, cert_id).crt = None
        db.session.commit()
    events.clear()
    new = _cert('ev-keyonly.example.com', key, issuer_cert=ca_cert, signer=ca_key)
    r = _import(auth_client, IMPORT, new)
    assert r.status_code == 200, r.data
    assert cert_events(events, cert_id) == [('certificate.imported', cert_id)]

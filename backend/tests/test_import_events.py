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
from tests.test_mtls_serial_per_issuer import same_serial  # noqa: F401

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


@pytest.fixture
def committed(app, monkeypatch, events):
    """Per certificate event, whether another connection saw its row when it fired."""
    from sqlalchemy import text
    from services.events import event_bus
    seen, inner = [], event_bus.emit

    def check(event_type, payload, ca_refid=None, meta=None):
        cid = ((payload or {}).get('certificate') or {}).get('id')
        if event_type.startswith('certificate.') and cid is not None:
            with db.engine.connect() as other:
                seen.append(other.execute(text('SELECT count(*) FROM certificates WHERE id = :id'),
                                          {'id': cid}).scalar() == 1)
        return inner(event_type, payload, ca_refid, meta)
    monkeypatch.setattr(event_bus, 'emit', check)
    return seen


def _rows_of(app, pem):
    from cryptography.x509 import load_pem_x509_certificate
    cert = load_pem_x509_certificate(pem.encode())
    with app.app_context():
        return [r.id for r in Certificate.query.filter_by(
            serial_number=str(cert.serial_number), issuer=cert.issuer.rfc4514_string())]


@pytest.mark.parametrize('route', ['enroll-import', 'user-import'])
def test_mtls_import_fires_imported_once_after_commit(app, auth_client, same_serial, events, committed, route):
    _serial, pem, _ = same_serial
    url, body = (('/api/v2/mtls/enroll-import', {'pem': pem}) if route == 'enroll-import'
                 else ('/api/v2/users/1/mtls/certificates', {'mode': 'import', 'pem': pem}))
    r = auth_client.post(url, json=body)
    assert r.status_code == 201, r.get_json()
    [cert_id] = _rows_of(app, pem)
    assert cert_events(events, cert_id) == [('certificate.imported', cert_id)]
    assert committed == [True]


def test_mtls_enrolment_of_a_recorded_certificate_fires_nothing(app, auth_client, same_serial, events):
    import uuid
    from tests.test_mtls_serial_per_issuer import _info
    serial, pem, _ = same_serial
    info = _info(pem)
    with app.app_context():
        row = Certificate(refid=str(uuid.uuid4()), descr='recorded', cert_type='usr_cert',
                          crt=base64.b64encode(pem.encode()).decode(), subject=info['subject_dn'],
                          issuer=info['issuer_dn'], serial_number=str(serial), created_by='admin')
        db.session.add(row)
        db.session.commit()
    events.clear()
    r = auth_client.post('/api/v2/mtls/enroll-import', json={'pem': pem})
    assert r.status_code == 201, r.get_json()
    assert [e for e, _ in events if e.startswith('certificate.')] == []


def _opnsense_rows():
    import uuid
    from tests.test_import_ca_serial_unique import _pki
    ca_pem, leaf_pem = _pki()
    ca_refid = uuid.uuid4().hex[:13]
    return ca_refid, ca_pem, leaf_pem


def test_opnsense_route_fires_imported_per_created_certificate(app, auth_client, monkeypatch, events, committed):
    """Two copies of one certificate: one row is created, one event fires, after the commit."""
    import uuid
    from api.v2 import import_opnsense
    from tests.test_import_ca_serial_unique import _cleanup
    from tests.test_opnsense_import import _Session
    ca_refid, ca_pem, leaf_pem = _opnsense_rows()
    ca_rows = [{'uuid': str(uuid.uuid4()), 'refid': ca_refid, 'descr': f'Root {ca_refid}',
                'crt': base64.b64encode(ca_pem).decode(), 'serial': '1'}]
    cert_rows = [{'uuid': str(uuid.uuid4()), 'refid': uuid.uuid4().hex[:13], 'caref': ca_refid,
                  'descr': f'copy {i} {ca_refid}', 'crt_payload': leaf_pem.decode(),
                  'cert_type': 'server_cert'} for i in range(2)]
    monkeypatch.setattr(import_opnsense, 'create_session',
                        lambda verify_ssl=True: _Session(ca_rows, cert_rows))
    try:
        r = auth_client.post('/api/v2/import/opnsense/import', json={
            'host': '192.0.2.10', 'port': 443, 'api_key': 'k', 'api_secret': 's',
            'verify_ssl': False, 'items': []})
        assert r.status_code == 200, r.data
        with app.app_context():
            [cert_id] = [c.id for c in Certificate.query.filter_by(caref=ca_refid)]
        assert cert_events(events, cert_id) == [('certificate.imported', cert_id)]
        assert [e for e, _ in events if e.startswith('certificate.')] == ['certificate.imported']
        assert committed == [True]
    finally:
        with app.app_context():
            _cleanup(ca_refid)


def test_opnsense_service_fires_imported_per_created_certificate(app, monkeypatch, tmp_path, events, committed):
    import uuid
    from services.opnsense import importer
    from tests.test_import_ca_serial_unique import _cleanup
    monkeypatch.setattr(importer, '__file__', str(tmp_path / 'services' / 'opnsense' / 'importer.py'))
    ca_refid, ca_pem, leaf_pem = _opnsense_rows()
    rows = [{'refid': uuid.uuid4().hex[:13], 'caref': ca_refid, 'descr': f'copy {i}',
             'crt': base64.b64encode(leaf_pem).decode(), 'serial_number': '4242'} for i in range(2)]
    with app.app_context():
        try:
            importer.ImportMixin().import_cas(
                [{'refid': ca_refid, 'descr': 'root', 'crt': base64.b64encode(ca_pem).decode(),
                  'is_root': True}])
            assert importer.ImportMixin().import_certificates(rows)['imported'] == 1
            [cert_id] = [c.id for c in Certificate.query.filter_by(caref=ca_refid)]
            assert cert_events(events, cert_id) == [('certificate.imported', cert_id)]
            assert [e for e, _ in events if e.startswith('certificate.')] == ['certificate.imported']
            assert committed == [True]
        finally:
            db.session.rollback()
            _cleanup(ca_refid)

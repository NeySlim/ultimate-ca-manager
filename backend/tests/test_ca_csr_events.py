"""csr.submitted on every way a request enters, ca.created for a CA signed from a request."""
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from tests.deploy_leftovers import delete_leftovers
from services.events import event_bus


# FK-aware purge: crl_metadata and other children go with their CA.
_cleanup = pytest.fixture(autouse=True)(delete_leftovers)


@pytest.fixture
def seen(monkeypatch):
    events = []
    real = event_bus.emit

    def capture(event_type, payload, ca_refid=None, meta=None):
        events.append((event_type, payload, meta))
        return real(event_type, payload, ca_refid, meta)

    monkeypatch.setattr(event_bus, 'emit', capture)
    return events


def _pem(cn):
    key = ec.generate_private_key(ec.SECP256R1())
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
           .sign(key, hashes.SHA256()))
    return csr.public_bytes(serialization.Encoding.PEM).decode()


def _of(events, kind):
    return [e for e in events if e[0] == kind]


def test_an_uploaded_request_is_announced(auth_client, seen):
    r = auth_client.post('/api/v2/csrs/upload', json={'pem': _pem('upload-evt.example.test')})
    assert r.status_code == 201, r.data
    sent = _of(seen, 'csr.submitted')
    assert len(sent) == 1 and sent[0][1]['csr']['id'] == r.get_json()['data']['id']
    assert sent[0][2].get('actor') == 'admin'


def test_an_imported_request_is_announced(auth_client, seen):
    r = auth_client.post('/api/v2/csrs/import', data={'pem_content': _pem('import-evt.example.test')},
                         content_type='multipart/form-data')
    assert r.status_code == 201, r.data
    sent = _of(seen, 'csr.submitted')
    assert len(sent) == 1 and sent[0][1]['csr']['id'] == r.get_json()['data']['id']
    assert sent[0][2].get('actor') == 'admin'


def test_signing_a_request_as_a_ca_announces_the_new_ca(auth_client, create_ca, seen):
    ca = create_ca(cn='Sign Event CA')
    up = auth_client.post('/api/v2/csrs/upload', json={'pem': _pem('Sub Event CA')})
    csr_id = up.get_json()['data']['id']
    r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign',
                         json={'ca_id': ca['id'], 'validity_days': 30, 'cert_type': 'intermediate_ca'})
    assert r.status_code == 200, r.get_json()
    sent = [e for e in _of(seen, 'ca.created') if e[1]['ca'].get('id') != ca['id']]
    assert len(sent) == 1


def test_a_request_brought_by_the_smart_import_is_announced(auth_client, seen, monkeypatch):
    import json
    from models import db

    order = []
    real_emit, real_commit = event_bus.emit, db.session.commit

    def emit(event_type, payload, ca_refid=None, meta=None):
        if event_type == 'csr.submitted':
            order.append('emit')
        return real_emit(event_type, payload, ca_refid, meta)

    def commit():
        order.append('commit')
        return real_commit()

    monkeypatch.setattr(event_bus, 'emit', emit)
    monkeypatch.setattr(db.session, 'commit', commit)
    r = auth_client.post('/api/v2/import/execute', data=json.dumps({
        'content': _pem('smart-evt.example.test'), 'options': {'import_csrs': True}}),
        content_type='application/json')
    assert r.status_code in (200, 201), r.data
    ids = r.get_json()['data']['imported_ids']['csrs']
    sent = _of(seen, 'csr.submitted')
    assert len(ids) == 1 and [e[1]['csr']['id'] for e in sent] == ids
    assert sent[0][2].get('actor') == 'admin'
    # Announced after the import's commit, never before it
    assert 'commit' in order[:order.index('emit')]

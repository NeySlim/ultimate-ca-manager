"""A CA arriving with its private key must clear the RSA floor; the same CA without a key is still read."""
import base64
import io
import json
import uuid

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from cryptography.hazmat.primitives.serialization import pkcs12

from models import CA
from tests.fixtures.cross_pki import key_pem, make_cert, new_key, pem
from tests.test_opnsense_import import _Session

WEAK = 1024


@pytest.fixture(autouse=True)
def _forget_cas(app):
    from models import db
    with app.app_context():
        before = {c.id for c in CA.query.all()}
    yield
    with app.app_context():
        # ORM delete: SQLite tests run without foreign keys, so a bulk delete would orphan cross rows
        for ca in CA.query.filter(~CA.id.in_(before)).all():
            db.session.delete(ca)
        db.session.commit()


def _weak_key():
    return rsa.generate_private_key(65537, WEAK)


def _ca(tag, key):
    return make_cert(f'Weak CA {tag}', key)


def _post(auth_client, path, **form):
    return auth_client.post(path, data=form, content_type='multipart/form-data')


def _stored(app, cert):
    with app.app_context():
        return CA.query.filter_by(subject=cert.subject.rfc4514_string()).all()


def test_rule_refuses_only_short_rsa():
    from utils.key_type import weak_ca_key_refusal
    msg = weak_ca_key_refusal(_weak_key())
    assert str(WEAK) in msg and '2048' in msg
    assert weak_ca_key_refusal(_weak_key().public_key()) == msg
    assert weak_ca_key_refusal(key_pem(_weak_key())) == msg
    assert weak_ca_key_refusal(new_key('rsa')) is None
    assert weak_ca_key_refusal(ec.generate_private_key(ec.SECP192R1())) is None
    assert weak_ca_key_refusal(ed25519.Ed25519PrivateKey.generate()) is None
    assert weak_ca_key_refusal(None) is None


@pytest.mark.parametrize('path', ['/api/v2/cas/import', '/api/v2/certificates/import'])
def test_pem_with_weak_key_is_refused_and_without_key_imported(app, auth_client, path):
    key = _weak_key()
    cert = _ca(uuid.uuid4().hex[:8], key)
    r = _post(auth_client, path, pem_content=pem(cert) + key_pem(key))
    assert r.status_code == 400, r.data
    message = json.loads(r.data)['message']
    assert str(WEAK) in message and '2048' in message
    assert _stored(app, cert) == []

    r = _post(auth_client, path, pem_content=pem(cert))
    assert r.status_code in (200, 201), r.data
    assert len(_stored(app, cert)) == 1


@pytest.mark.parametrize('path', ['/api/v2/cas/import', '/api/v2/certificates/import'])
def test_pkcs12_with_weak_key_is_refused(app, auth_client, path):
    key = _weak_key()
    cert = _ca(uuid.uuid4().hex[:8], key)
    blob = pkcs12.serialize_key_and_certificates(
        b'weak', key, cert, None, serialization.BestAvailableEncryption(b'pw'))
    r = auth_client.post(path, data={'file': (io.BytesIO(blob), 'weak.p12'), 'password': 'pw'},
                         content_type='multipart/form-data')
    assert r.status_code == 400, r.data
    assert '2048' in json.loads(r.data)['message']
    assert _stored(app, cert) == []


def test_weak_key_cannot_be_attached_to_a_stored_ca(app, auth_client):
    key = _weak_key()
    cert = _ca(uuid.uuid4().hex[:8], key)
    assert _post(auth_client, '/api/v2/cas/import', pem_content=pem(cert)).status_code == 201
    r = _post(auth_client, '/api/v2/cas/import', pem_content=pem(cert) + key_pem(key))
    assert r.status_code == 400, r.data
    assert _stored(app, cert)[0].prv is None


def test_ec_ca_with_key_still_imported(app, auth_client):
    key = new_key()
    cert = _ca(uuid.uuid4().hex[:8], key)
    r = _post(auth_client, '/api/v2/cas/import', pem_content=pem(cert) + key_pem(key))
    assert r.status_code == 201, r.data
    assert _stored(app, cert)[0].prv


def test_smart_import_refuses_the_weak_ca_and_keeps_the_others(app):
    from services.smart_import.importer import SmartImporter
    weak_key, good_key = _weak_key(), new_key()
    tag = uuid.uuid4().hex[:8]
    weak, good = _ca(f'w{tag}', weak_key), _ca(f'g{tag}', good_key)
    with app.app_context():
        result = SmartImporter().execute(pem(weak) + key_pem(weak_key) + pem(good) + key_pem(good_key))
        assert result.cas_imported == 1
        named = [w for w in result.warnings if f'w{tag}' in w]
        assert named and '1024' in named[0] and '2048' in named[0]
        assert CA.query.filter_by(subject=weak.subject.rfc4514_string()).count() == 0
        assert CA.query.filter_by(subject=good.subject.rfc4514_string()).one().prv


def test_smart_import_reads_the_weak_ca_without_its_key(app):
    from services.smart_import.importer import SmartImporter
    weak = _ca(uuid.uuid4().hex[:8], _weak_key())
    with app.app_context():
        result = SmartImporter().execute(pem(weak))
        assert result.cas_imported == 1
        assert CA.query.filter_by(subject=weak.subject.rfc4514_string()).one().prv is None


def _row(cert, descr, key=None):
    row = {'uuid': str(uuid.uuid4()), 'refid': uuid.uuid4().hex[:13], 'descr': descr,
           'crt': base64.b64encode(pem(cert).encode()).decode(), 'serial': '1'}
    if key is not None:
        row['prv'] = base64.b64encode(key_pem(key).encode()).decode()
    return row


def _opnsense(auth_client, monkeypatch, ca_rows, items=()):
    from api.v2 import import_opnsense
    monkeypatch.setattr(import_opnsense, 'create_session', lambda verify_ssl=True: _Session(ca_rows, []))
    r = auth_client.post('/api/v2/import/opnsense/import', json={
        'host': '192.0.2.10', 'port': 443, 'api_key': 'k', 'api_secret': 's',
        'verify_ssl': False, 'items': list(items)})
    assert r.status_code == 200, r.data
    return json.loads(r.data)['data']


def test_opnsense_route_refuses_weak_ca_with_key_only(app, auth_client, monkeypatch):
    tag = uuid.uuid4().hex[:8]
    weak_key, readonly_key, good_key = _weak_key(), _weak_key(), new_key()
    weak, readonly, good = _ca(f'w{tag}', weak_key), _ca(f'r{tag}', readonly_key), _ca(f'g{tag}', good_key)
    body = _opnsense(auth_client, monkeypatch, [
        _row(weak, f'weak {tag}', weak_key), _row(readonly, f'readonly {tag}'), _row(good, f'good {tag}', good_key)])
    assert body['imported']['cas'] == 2
    assert body['skipped'] == 1
    assert any(f'weak {tag}' in e and '1024' in e and '2048' in e for e in body['errors'])
    assert _stored(app, weak) == []
    assert _stored(app, readonly)[0].prv is None
    assert _stored(app, good)[0].prv


def test_opnsense_route_judges_the_key_it_would_store(app, auth_client, monkeypatch):
    """A row carrying both fields stores ``prv``: that key is the one judged."""
    tag = uuid.uuid4().hex[:8]
    weak_key, good_key = _weak_key(), new_key()
    weak = _ca(f'both{tag}', weak_key)
    row = _row(weak, f'both {tag}', weak_key)
    row['prv_payload'] = key_pem(good_key)
    body = _opnsense(auth_client, monkeypatch, [row])
    assert body['imported']['cas'] == 0 and body['skipped'] == 1
    assert any(f'both {tag}' in e and '2048' in e for e in body['errors'])
    assert _stored(app, weak) == []


def test_opnsense_route_refuses_a_key_field_that_is_not_base64(app, auth_client, monkeypatch):
    tag = uuid.uuid4().hex[:8]
    key = new_key()
    cert = _ca(f'bad{tag}', key)
    row = _row(cert, f'bad {tag}')
    row['prv'] = 'not base64 at all!'
    body = _opnsense(auth_client, monkeypatch, [row])
    assert body['imported']['cas'] == 0 and body['skipped'] == 1
    assert any(f'bad {tag}' in e and 'could not be read' in e for e in body['errors'])
    assert _stored(app, cert) == []


def test_opnsense_config_importer_refuses_weak_ca_with_key_only(app):
    from services.opnsense.importer import ImportMixin
    tag = uuid.uuid4().hex[:8]
    weak_key, good_key = _weak_key(), new_key()
    weak, good = _ca(f'w{tag}', weak_key), _ca(f'g{tag}', good_key)

    def data(cert, key, descr):
        return {'refid': uuid.uuid4().hex[:13], 'descr': descr, 'is_root': True,
                'crt': base64.b64encode(pem(cert).encode()).decode(),
                'prv': base64.b64encode(key_pem(key).encode()).decode(),
                'subject': cert.subject.rfc4514_string(), 'issuer': cert.issuer.rfc4514_string()}

    with app.app_context():
        stats = ImportMixin().import_cas([data(weak, weak_key, f'weak {tag}'), data(good, good_key, f'good {tag}')])
        assert stats['imported'] == 1 and stats['failed'] == 1
        assert any(f'weak {tag}' in e and '2048' in e for e in stats['errors'])
        assert CA.query.filter_by(subject=weak.subject.rfc4514_string()).count() == 0


def test_ca_service_import_refuses_weak_key(app):
    from services.ca_service import CAService
    key = _weak_key()
    cert = _ca(uuid.uuid4().hex[:8], key)
    with app.app_context():
        with pytest.raises(ValueError, match='2048'):
            CAService.import_ca('weak', pem(cert), key_pem(key))


@pytest.mark.parametrize('path', ['/api/v2/cas/import', '/api/v2/certificates/import'])
def test_pkcs12_weak_key_without_import_key_is_read(app, auth_client, path):
    key = _weak_key()
    cert = _ca(uuid.uuid4().hex[:8], key)
    blob = pkcs12.serialize_key_and_certificates(
        b'weak', key, cert, None, serialization.BestAvailableEncryption(b'pw'))
    r = auth_client.post(path, data={'file': (io.BytesIO(blob), 'weak.p12'), 'password': 'pw',
                                     'import_key': 'false'}, content_type='multipart/form-data')
    assert r.status_code in (200, 201), r.data
    stored = _stored(app, cert)
    assert len(stored) == 1 and stored[0].prv is None


def test_weak_key_cannot_be_posted_to_a_keyless_ca(app, auth_client):
    key = _weak_key()
    cert = _ca(uuid.uuid4().hex[:8], key)
    assert _post(auth_client, '/api/v2/cas/import', pem_content=pem(cert)).status_code == 201
    ca_id = _stored(app, cert)[0].id
    r = auth_client.post(f'/api/v2/cas/{ca_id}/key', json={'key': key_pem(key)})
    assert r.status_code == 400, r.data
    assert '2048' in json.loads(r.data)['message']
    assert _stored(app, cert)[0].prv is None


def test_opnsense_cross_entry_cannot_carry_a_weak_key_to_its_counterpart(app, auth_client, monkeypatch):
    tag = uuid.uuid4().hex[:8]
    a_key, b_key = new_key(), _weak_key()
    root_a = _ca(f'a{tag}', a_key)
    root_b = _ca(f'b{tag}', b_key)
    cross_b = make_cert(f'Weak CA b{tag}', b_key, issuer_cn=f'Weak CA a{tag}', issuer_key=a_key)
    body = _opnsense(auth_client, monkeypatch, [
        _row(root_a, f'A {tag}', a_key), _row(root_b, f'B {tag}'), _row(cross_b, f'B cross {tag}', b_key)])
    assert body['cross_certificates_attached'] == 1
    assert any('2048' in e for e in body['errors'])
    with app.app_context():
        assert CA.query.filter_by(descr=f'B {tag}').one().prv is None


@pytest.mark.parametrize('path', ['/api/v2/cas/import', '/api/v2/certificates/import'])
def test_weak_key_of_a_pending_request_does_not_become_the_ca_key(app, auth_client, path):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.x509.oid import NameOID
    key = _weak_key()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f'Weak pending {uuid.uuid4().hex[:8]}')])
    csr = (x509.CertificateSigningRequestBuilder().subject_name(name)
           .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
           .sign(key, hashes.SHA256()))
    r = _post(auth_client, '/api/v2/csrs/import', pem_content=csr.public_bytes(serialization.Encoding.PEM).decode())
    assert r.status_code in (200, 201), r.data
    csr_id = json.loads(r.data)['data']['id']
    r = auth_client.post(f'/api/v2/csrs/{csr_id}/key', json={'key': key_pem(key)})
    assert r.status_code in (200, 201), r.data
    cert = make_cert(name.rfc4514_string().split('=', 1)[1], key,
                     issuer_cn=f'External root {uuid.uuid4().hex[:8]}', issuer_key=new_key('rsa'))

    r = _post(auth_client, path, pem_content=pem(cert))
    assert r.status_code == 400, r.data
    message = json.loads(r.data)['message']
    assert str(WEAK) in message and '2048' in message
    assert _stored(app, cert) == []


@pytest.mark.parametrize('unreadable', [
    b'-----BEGIN PRIVATE KEY-----\nbm90IGEga2V5\n-----END PRIVATE KEY-----\n',
    'not a key at all',
    b'',
])
def test_an_unreadable_key_pem_is_refused_not_admitted(unreadable):
    from utils.key_type import weak_ca_key_refusal
    assert 'could not be read' in weak_ca_key_refusal(unreadable)


def test_an_encrypted_key_pem_is_refused_not_admitted():
    from utils.key_type import weak_ca_key_refusal
    sealed = new_key().private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                     serialization.BestAvailableEncryption(b'pw'))
    assert 'could not be read' in weak_ca_key_refusal(sealed)
    assert weak_ca_key_refusal(None) is None


def test_certificates_import_asks_write_cas_before_judging_the_key(app, auth_client):
    from tests.conftest import assert_success
    created = assert_success(auth_client.post('/api/v2/account/apikeys', json={
        'name': f'cert-only-{uuid.uuid4().hex[:6]}',
        'permissions': ['read:certificates', 'write:certificates']}), 201)
    key = _weak_key()
    cert = _ca(uuid.uuid4().hex[:8], key)
    r = app.test_client().post('/api/v2/certificates/import', headers={'X-API-Key': created['key']},
                               data={'pem_content': pem(cert) + key_pem(key)}, content_type='multipart/form-data')
    assert r.status_code == 403, r.data
    assert _stored(app, cert) == []

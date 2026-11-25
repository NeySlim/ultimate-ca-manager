"""A password given with a PEM export encrypts the key in the file; it is never ignored."""
import re

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from models import AuditLog

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates', 'drop_new_users')

PASSWORD = 'Export-Passw0rd!'
OTHER = 'Another-Passw0rd!'
KEY_MARK = b'PRIVATE KEY-----'  # one BEGIN and one END per key block


def _split(pem):
    """(certificate blocks, key block) of a PEM file."""
    text = pem.decode()
    certs = re.findall(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', text, re.S)
    key = re.search(r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----\n?', text, re.S)
    return certs, key.group(0).encode()


def _assert_encrypted(key_block):
    with pytest.raises(TypeError):
        load_pem_private_key(key_block, password=None)
    with pytest.raises(ValueError):
        load_pem_private_key(key_block, password=OTHER.encode())
    assert load_pem_private_key(key_block, password=PASSWORD.encode()) is not None


def _last_audit(app, rtype, rid, action='private_key_exported'):
    with app.app_context():
        return AuditLog.query.filter_by(action=action, resource_type=rtype,
                                        resource_id=str(rid)).order_by(AuditLog.id.desc()).first().details


@pytest.fixture(scope='module')
def cert_id(create_cert):
    return create_cert(cn='pem-pw.example.com')['id']


@pytest.fixture(scope='module')
def ca_id(create_ca):
    return create_ca(cn='Pem Pw CA')['id']


def _url(kind, rid):
    return f'/api/v2/certificates/{rid}/export' if kind == 'certificate' else f'/api/v2/cas/{rid}/export'


@pytest.mark.parametrize('kind', ['certificate', 'ca'])
@pytest.mark.parametrize('chain', [False, True])
def test_pem_with_key_and_password_encrypts_the_key(app, auth_client, cert_id, ca_id, kind, chain):
    rid = cert_id if kind == 'certificate' else ca_id
    body = {'format': 'pem', 'include_key': True, 'include_chain': chain}
    plain = auth_client.post(_url(kind, rid), json=body)
    enc = auth_client.post(_url(kind, rid), json={**body, 'password': PASSWORD})
    assert plain.status_code == enc.status_code == 200
    assert KEY_MARK in plain.data and b'ENCRYPTED' not in plain.data
    assert b'BEGIN ENCRYPTED PRIVATE KEY' in enc.data
    assert enc.data.count(KEY_MARK) == 2  # BEGIN and END of one block, no clear copy
    p_certs, _ = _split(plain.data)
    e_certs, key_block = _split(enc.data)
    assert e_certs == p_certs
    _assert_encrypted(key_block)
    assert _last_audit(app, kind, rid).endswith('PEM (password-protected)')
    assert PASSWORD not in _last_audit(app, kind, rid)


@pytest.mark.parametrize('kind', ['certificate', 'ca'])
def test_pem_with_password_but_no_key_is_unchanged(auth_client, cert_id, ca_id, kind):
    rid = cert_id if kind == 'certificate' else ca_id
    a = auth_client.post(_url(kind, rid), json={'format': 'pem'})
    b = auth_client.post(_url(kind, rid), json={'format': 'pem', 'password': PASSWORD})
    assert b.status_code == 200 and b.data == a.data
    assert KEY_MARK not in b.data


def test_pem_with_key_without_password_stays_clear(auth_client, cert_id):
    r = auth_client.post(_url('certificate', cert_id), json={'format': 'pem', 'include_key': True})
    assert KEY_MARK in r.data and b'ENCRYPTED' not in r.data
    load_pem_private_key(_split(r.data)[1], password=None)


def test_short_password_with_pem_key_is_refused(auth_client, cert_id):
    r = auth_client.post(_url('certificate', cert_id),
                         json={'format': 'pem', 'include_key': True, 'password': 'short'})
    assert r.status_code == 400


def test_hybrid_bundle_audit_says_whether_the_keys_were_encrypted(app, auth_client, create_ca):
    from tests.test_related_certificates_pair import _pair
    a, _b = _pair(auth_client, create_ca, 'pem-pw-hybrid.example.com')
    url = f"/api/v2/certificates/{a['id']}/export"
    assert auth_client.post(url, json={'format': 'hybrid-bundle', 'include_key': True,
                                       'password': PASSWORD}).status_code == 200
    assert _last_audit(app, 'certificate', a['id']).endswith('HYBRID-BUNDLE (password-protected)')
    assert auth_client.post(url, json={'format': 'hybrid-bundle', 'include_key': True}).status_code == 200
    assert _last_audit(app, 'certificate', a['id']).endswith('HYBRID-BUNDLE (unencrypted)')


def _enrolment(app, create_cert, username, label):
    from tests.test_user_certificate_key_export_guard import _enrolment_for
    return _enrolment_for(app, create_cert, username, label)


def test_user_certificate_pem_with_password_encrypts_the_key(app, auth_client, create_user, create_cert):
    create_user(username='pempwuser', role='viewer')
    rid, _ = _enrolment(app, create_cert, 'pempwuser', 'pempw-label')
    url = f'/api/v2/user-certificates/{rid}/export'
    plain = auth_client.post(url, json={'format': 'pem', 'include_key': True})
    enc = auth_client.post(url, json={'format': 'pem', 'include_key': True, 'password': PASSWORD})
    assert plain.status_code == enc.status_code == 200
    assert KEY_MARK in plain.data and b'ENCRYPTED' not in plain.data
    assert b'BEGIN ENCRYPTED PRIVATE KEY' in enc.data and enc.data.count(KEY_MARK) == 2
    assert _split(enc.data)[0] == _split(plain.data)[0]
    _assert_encrypted(_split(enc.data)[1])
    assert '(password-protected)' in _last_audit(app, 'user_certificate', rid, 'user_certificate_exported')
    bad = auth_client.post(url, json={'format': 'pem', 'include_key': True, 'password': 'short'})
    assert bad.status_code == 400


@pytest.mark.parametrize('fmt', ['pem', 'key'])
def test_an_offline_ca_key_is_not_sealed_under_a_second_password(auth_client, create_ca, fmt):
    """Its stored key is sealed under the offline password: a second one answers 409, not 500."""
    ca = create_ca(cn=f'Pem Pw offline {fmt}')
    offline = auth_client.post(f"/api/v2/cas/{ca['id']}/offline",
                               json={'password': 'OfflineP@ss2026!', 'mode': 'password_protected'})
    assert offline.status_code == 200, offline.data[:300]
    url = f"/api/v2/cas/{ca['id']}/export"
    body = {'format': fmt, **({'include_key': True} if fmt == 'pem' else {})}

    r = auth_client.post(url, json={**body, 'password': PASSWORD})
    assert r.status_code == 409, r.data[:300]
    assert KEY_MARK not in r.data

    kept = auth_client.post(url, json=body)
    assert kept.status_code == 200, kept.data[:300]
    blocks = re.findall(rb'-----BEGIN ([A-Z ]*)PRIVATE KEY-----', kept.data)
    assert blocks == [b'ENCRYPTED '], blocks


@pytest.mark.parametrize('body', [{'format': 'pem', 'include_key': True}, {'format': 'key'}])
def test_a_ca_key_export_password_follows_the_export_password_rule(auth_client, ca_id, body):
    r = auth_client.post(_url('ca', ca_id), json={**body, 'password': 'short'})
    assert r.status_code == 400, r.data[:300]
    assert KEY_MARK not in r.data and 'between 8 and' in r.get_json()['message']

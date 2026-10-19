"""A CA key leaves UCM only with read:private_keys.

The CA export route asked for write:cas alone, which the built-in Operator
role holds, so an Operator could take the key of any CA as PKCS#12, PFX,
JKS, a key file or PEM with key. Taking a CA offline in file_exported mode
hands the same key over as a download. Both now ask for read:private_keys,
like the certificate export does.
"""
import hashlib
import json
import secrets

import pytest

from models import CA, User, db
from models.api_key import APIKey

OFFLINE_PASSWORD = 'OfflineP@ss2026!'
EXPORT_PASSWORD = 'ExportPass123!'

# Every request shape of POST /cas/<id>/export that carries the key.
KEY_EXPORTS = [
    {'format': 'pkcs12', 'password': EXPORT_PASSWORD},
    {'format': 'pfx', 'password': EXPORT_PASSWORD},
    {'format': 'jks', 'password': EXPORT_PASSWORD},
    {'format': 'key'},
    {'format': 'pem', 'include_key': True},
]
KEY_EXPORT_IDS = ['pkcs12', 'pfx', 'jks', 'key', 'pem+key']


def _login(app, username):
    client = app.test_client()
    r = client.post('/api/v2/auth/login',
                    data=json.dumps({'username': username, 'password': 'TestPass123!'}),
                    content_type='application/json')
    assert r.status_code == 200, r.data
    return client


@pytest.fixture
def operator(app, create_user):
    create_user(username='op_ca_key_export_probe', role='operator')
    return _login(app, 'op_ca_key_export_probe')


def _scoped_key(app, permissions, name):
    """An API key owned by an admin but narrowed to ``permissions``."""
    username = 'ca_key_scope_owner'
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        if not user:
            user = User(username=username, email=f'{username}@test.local',
                        password_hash='!', role='admin', active=True)
            db.session.add(user)
            db.session.commit()
        raw = f'ucm_ak_{secrets.token_urlsafe(32)}'
        db.session.add(APIKey(user_id=user.id,
                              key_hash=hashlib.sha256(raw.encode()).hexdigest(),
                              key_prefix=raw[:12], name=name,
                              permissions=json.dumps(permissions)))
        db.session.commit()
    return raw


@pytest.fixture
def key_holder(app):
    """write:cas plus read:private_keys, without the admin wildcard."""
    return _scoped_key(app, ['read:cas', 'write:cas', 'read:private_keys'], 'ca-key-holder')


@pytest.fixture
def writer_only(app):
    """write:cas without read:private_keys, owner is an admin."""
    return _scoped_key(app, ['read:cas', 'write:cas'], 'ca-writer-only')


def _export(client, ca_id, body, headers=None):
    return client.post(f'/api/v2/cas/{ca_id}/export', data=json.dumps(body),
                       content_type='application/json', headers=headers or {})


class TestCAKeyExport:
    @pytest.mark.parametrize('body', KEY_EXPORTS, ids=KEY_EXPORT_IDS)
    def test_operator_is_refused(self, operator, create_ca, body):
        ca = create_ca(cn='Operator Key Export Probe CA')
        r = _export(operator, ca['id'], body)
        assert r.status_code == 403, (
            f'an Operator exported a CA key ({body["format"]}): {r.status_code}')
        assert b'PRIVATE KEY' not in r.data

    @pytest.mark.parametrize('body', KEY_EXPORTS, ids=KEY_EXPORT_IDS)
    def test_write_cas_alone_is_refused(self, app, writer_only, create_ca, body):
        ca = create_ca(cn='Writer Key Export Probe CA')
        r = _export(app.test_client(), ca['id'], body, {'X-API-Key': writer_only})
        assert r.status_code == 403, r.data[:200]

    @pytest.mark.parametrize('body', KEY_EXPORTS, ids=KEY_EXPORT_IDS)
    def test_admin_exports(self, auth_client, create_ca, body):
        ca = create_ca(cn='Admin Key Export Probe CA')
        r = _export(auth_client, ca['id'], body)
        assert r.status_code == 200, r.data[:200]

    @pytest.mark.parametrize('body', KEY_EXPORTS, ids=KEY_EXPORT_IDS)
    def test_read_private_keys_scope_exports(self, app, key_holder, create_ca, body):
        ca = create_ca(cn='Scoped Key Export Probe CA')
        r = _export(app.test_client(), ca['id'], body, {'X-API-Key': key_holder})
        assert r.status_code == 200, r.data[:200]

    def test_operator_still_exports_the_certificate(self, operator, create_ca):
        ca = create_ca(cn='Operator Cert Export Probe CA')
        r = _export(operator, ca['id'], {'format': 'pem'})
        assert r.status_code == 200
        assert b'BEGIN CERTIFICATE' in r.data
        assert b'PRIVATE KEY' not in r.data


def _offline(client, ca_id, mode, headers=None):
    return client.post(f'/api/v2/cas/{ca_id}/offline',
                       data=json.dumps({'password': OFFLINE_PASSWORD, 'mode': mode}),
                       content_type='application/json', headers=headers or {})


def _ca_state(app, ca_id):
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        return bool(ca.offline), bool(ca.prv)


class TestOfflineFileExport:
    def test_operator_is_refused_and_the_ca_is_untouched(self, app, operator, create_ca):
        ca = create_ca(cn='Operator Offline File Probe CA')
        r = _offline(operator, ca['id'], 'file_exported')
        assert r.status_code == 403, f'an Operator took a CA key as a file: {r.status_code}'
        assert b'PRIVATE KEY' not in r.data
        assert _ca_state(app, ca['id']) == (False, True)

    def test_write_cas_alone_is_refused(self, app, writer_only, create_ca):
        ca = create_ca(cn='Writer Offline File Probe CA')
        r = _offline(app.test_client(), ca['id'], 'file_exported', {'X-API-Key': writer_only})
        assert r.status_code == 403
        assert _ca_state(app, ca['id']) == (False, True)

    def test_operator_keeps_password_protected_mode(self, app, operator, create_ca):
        ca = create_ca(cn='Operator Offline Password Probe CA')
        r = _offline(operator, ca['id'], 'password_protected')
        assert r.status_code == 200, r.data[:200]
        assert b'PRIVATE KEY' not in r.data

    def test_admin_takes_the_file(self, app, auth_client, create_ca):
        ca = create_ca(cn='Admin Offline File Probe CA')
        r = _offline(auth_client, ca['id'], 'file_exported')
        assert r.status_code == 200, r.data[:200]
        assert b'ENCRYPTED PRIVATE KEY' in r.data
        assert _ca_state(app, ca['id']) == (True, False)

    def test_read_private_keys_scope_takes_the_file(self, app, key_holder, create_ca):
        ca = create_ca(cn='Scoped Offline File Probe CA')
        r = _offline(app.test_client(), ca['id'], 'file_exported', {'X-API-Key': key_holder})
        assert r.status_code == 200, r.data[:200]
        assert b'ENCRYPTED PRIVATE KEY' in r.data

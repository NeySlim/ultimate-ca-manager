"""An SSH CA names its certificates principals@CA unless told otherwise (#432).

sshd logs the key ID as the holder's identity, so a requester must not pick it.
"""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text

from tests.fresh_app import fresh_app_fixtures
from tests.test_ssh import _generate_test_ssh_key, post_json

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

PG_URL = os.getenv('UCM_TEST_PG_URL')


def _ca(auth_client, descr, **extra):
    r = post_json(auth_client, '/api/v2/ssh/cas', {'descr': descr, 'ca_type': 'user', 'key_type': 'ed25519',
                                                  'allow_any_principal': True, **extra})
    assert r.status_code == 201, r.data
    return r.get_json()['data']


def _sign(auth_client, ca_id, **extra):
    return post_json(auth_client, '/api/v2/ssh/certificates', {
        'ca_id': ca_id, 'public_key': _generate_test_ssh_key(),
        'cert_type': 'user', 'principals': ['alice', 'bob'], **extra})


def _generate(auth_client, ca_id, **extra):
    return post_json(auth_client, '/api/v2/ssh/certificates/generate', {
        'ca_id': ca_id, 'key_type': 'ecdsa-p256',
        'cert_type': 'user', 'principals': ['alice'], **extra})


def _serial(auth_client, ca_id):
    return auth_client.get(f'/api/v2/ssh/cas/{ca_id}').get_json()['data']['serial_counter']


def test_a_new_ca_names_its_certificates(auth_client):
    ca = _ca(auth_client, 'KeyID default CA')
    assert ca['allow_custom_key_id'] is False
    r = _sign(auth_client, ca['id'])
    assert r.status_code == 201, r.data
    assert r.get_json()['data']['key_id'] == 'alice,bob@KeyID default CA'


@pytest.mark.parametrize('issue', [_sign, _generate])
def test_a_chosen_key_id_is_refused_before_a_serial_is_spent(auth_client, issue):
    ca = _ca(auth_client, f'KeyID refuse CA {issue.__name__}')
    before = _serial(auth_client, ca['id'])
    r = issue(auth_client, ca['id'], key_id='i_can_write_anything_here')
    assert r.status_code == 400
    assert 'key ID' in r.get_json()['message']
    assert _serial(auth_client, ca['id']) == before


def test_the_key_id_the_ca_would_set_is_accepted(auth_client):
    ca = _ca(auth_client, 'KeyID same CA')
    r = _sign(auth_client, ca['id'], key_id=' alice,bob@KeyID same CA ')
    assert r.status_code == 201, r.data
    assert r.get_json()['data']['key_id'] == 'alice,bob@KeyID same CA'


@pytest.mark.parametrize('blank', ['', '   ', None])
def test_a_blank_key_id_falls_back_to_the_ca_name(auth_client, blank):
    ca = _ca(auth_client, f'KeyID blank CA {blank!r}')
    r = _sign(auth_client, ca['id'], key_id=blank)
    assert r.status_code == 201, r.data
    assert r.get_json()['data']['key_id'] == f'alice,bob@KeyID blank CA {blank!r}'


@pytest.mark.parametrize('issue', [_sign, _generate])
def test_the_setting_lets_requesters_name_the_certificate(auth_client, issue):
    ca = _ca(auth_client, f'KeyID custom CA {issue.__name__}', allow_custom_key_id=True)
    r = issue(auth_client, ca['id'], key_id='  ticket-4321  ')
    assert r.status_code == 201, r.data
    assert r.get_json()['data']['key_id'] == 'ticket-4321'


def test_the_setting_can_be_changed_and_must_be_a_boolean(auth_client):
    ca = _ca(auth_client, 'KeyID toggle CA')
    r = auth_client.put(f"/api/v2/ssh/cas/{ca['id']}", json={'allow_custom_key_id': 'yes'})
    assert r.status_code == 400
    r = auth_client.put(f"/api/v2/ssh/cas/{ca['id']}", json={'allow_custom_key_id': True})
    assert r.status_code == 200 and r.get_json()['data']['allow_custom_key_id'] is True
    assert _sign(auth_client, ca['id'], key_id='chosen').status_code == 201
    r = auth_client.put(f"/api/v2/ssh/cas/{ca['id']}", json={'allow_custom_key_id': False})
    assert r.status_code == 200
    assert _sign(auth_client, ca['id'], key_id='chosen').status_code == 400


def test_an_imported_ca_starts_with_the_setting_off_unless_asked(auth_client):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    for descr, extra, want in (('KeyID import off', {}, False),
                               ('KeyID import on', {'allow_custom_key_id': True}, True)):
        pem = ed25519.Ed25519PrivateKey.generate().private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
            serialization.NoEncryption()).decode()
        r = post_json(auth_client, '/api/v2/ssh/cas/import', {
            'descr': descr, 'ca_type': 'user', 'private_key': pem, **extra})
        assert r.status_code == 201, r.data
        assert r.get_json()['data']['allow_custom_key_id'] is want


def test_a_backup_carries_the_setting(app, auth_client):
    from models import db
    from models.ssh import SSHCertificateAuthority
    from services.backup_service import BackupService
    from tests.test_backup_export_manifest import PASSWORD, _only
    ca = _ca(auth_client, 'KeyID backup CA', allow_custom_key_id=True)
    with app.app_context():
        svc = BackupService()
        blob = svc.create_backup(PASSWORD, include=_only('ssh_cas'))
        row = db.session.get(SSHCertificateAuthority, ca['id'])
        row.allow_custom_key_id = False
        db.session.commit()
        svc.restore_backup(blob, PASSWORD, mode='merge')
        db.session.expire_all()
        assert db.session.get(SSHCertificateAuthority, ca['id']).allow_custom_key_id is True


def test_a_principal_cannot_forge_a_list_in_the_key_id(auth_client):
    r = post_json(auth_client, '/api/v2/ssh/cas', {'descr': 'KeyID comma CA', 'ca_type': 'user',
                                                  'key_type': 'ed25519', 'allowed_principals': ['alice*']})
    assert r.status_code == 201, r.data
    r = _sign(auth_client, r.get_json()['data']['id'], principals=['alice,root'])
    assert r.status_code == 400
    assert 'comma' in r.get_json()['message']


def test_the_refusal_names_the_option(auth_client):
    ca = _ca(auth_client, 'KeyID message CA')
    r = _sign(auth_client, ca['id'], key_id='mine')
    assert 'Let requesters set the key ID' in r.get_json()['message']

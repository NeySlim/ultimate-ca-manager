"""Archives written before 2.230 restore, and say what they could not place.

Their references are bare source numbers. A required link that cannot be
placed leaves its row out with a line in the result, never refuses the whole
archive; nested group members are listed, nested WebAuthn keys are read under
their user; an HSM secret encrypted under another installation's key is named,
provider included.
"""
import base64
import json

import pytest
from cryptography.fernet import Fernet

from models import db
from services.backup.restore_report import with_restore_warnings
from tests.test_backup_cross_installation import Keys, _installation
from tests.test_backup_hostile_corpus import PASSWORD, _forged, _service


@pytest.fixture
def here(app, tmp_path):
    with _installation(app, f"sqlite:///{tmp_path / 'older.db'}", Keys(tmp_path, 'older')), \
            app.app_context():
        from models import User
        db.session.add(User(username='older-admin', email='o@example.test',
                            password_hash='x' * 32, role='admin', active=True))
        db.session.commit()
        yield
        db.session.rollback()


def _restore(sections, mutate, mode='merge'):
    blob = _forged(sections, mutate=mutate)
    results = _service().restore_backup(blob, PASSWORD, mode=mode)
    db.session.expire_all()
    return results


def _user(username):
    from models import User
    user = User(username=username, email=f'{username}@example.test',
                password_hash='x' * 32, role='viewer', active=True)
    db.session.add(user)
    db.session.commit()
    return user


# -- P2-9: API keys and ACME domains of the pre-2.230 shape -------------------

OLD_KEY = {'user_id': 4242, 'key_hash': 'older-hash', 'name': 'older key',
           'permissions': '[]', 'is_active': True, 'expires_at': None, 'created_at': None}
OLD_DOMAIN = {'domain': 'older.example.test', 'dns_provider_id': 77, 'issuing_ca_id': 88,
              'is_wildcard_allowed': True, 'auto_approve': False, 'created_by': 'admin'}


def test_an_api_key_named_by_number_is_left_out_not_the_archive(here):
    from models.api_key import APIKey

    results = _restore(['users', 'api_keys'], lambda data: data.update(api_keys=[dict(OLD_KEY)]))

    assert APIKey.query.filter_by(key_hash='older-hash').first() is None
    assert results['api_keys'] == 0
    assert any('api_keys older-hash' in line for line in results['left_out'])
    assert 'left out' in with_restore_warnings('Restored.', results)


def test_an_api_key_already_here_keeps_its_owner(here):
    from models.api_key import APIKey

    owner = _user('older-owner')
    db.session.add(APIKey(user_id=owner.id, key_hash='older-hash', name='before',
                          permissions='[]'))
    db.session.commit()

    results = _restore(['users', 'api_keys'], lambda data: data.update(api_keys=[dict(OLD_KEY)]))

    key = APIKey.query.filter_by(key_hash='older-hash').one()
    assert (key.user_id, key.name) == (owner.id, 'older key')
    assert results['left_out'] == []


def test_an_acme_domain_named_by_number_is_left_out_not_the_archive(here):
    from models.acme_models import AcmeDomain

    results = _restore(['acme_domains'], lambda data: data.update(acme_domains=[dict(OLD_DOMAIN)]))

    assert AcmeDomain.query.filter_by(domain='older.example.test').first() is None
    assert any('acme_domains older.example.test' in line for line in results['left_out'])


# -- P2-10: nested group members and WebAuthn keys ----------------------------

def _nested_groups(members):
    def mutate(data):
        data.pop('group_members', None)
        data['groups'] = [{'name': 'older-group', 'description': '', 'permissions': '[]',
                           'members': members}]
    return mutate


def test_a_nested_member_named_by_number_never_lands_on_another_account(here):
    from models.group import Group, GroupMember

    other = _user('older-someone-else')
    results = _restore(['groups'], _nested_groups([{'user_id': other.id, 'role': 'member'}]))

    group = Group.query.filter_by(name='older-group').one()
    assert GroupMember.query.filter_by(group_id=group.id).count() == 0
    assert any('user number' in line for line in results['left_out'])


def test_nested_webauthn_keys_are_read(here):
    from models import User
    from models.webauthn import WebAuthnCredential

    credential = {'credential_id': base64.b64encode(b'older-credential').decode(),
                  'public_key': base64.b64encode(b'cose-key').decode(),
                  'sign_count': 7, 'name': 'YubiKey', 'aaguid': None}

    def mutate(data):
        data.pop('webauthn_credentials', None)
        for user in data['users']:
            if user['username'] == 'older-admin':
                user['webauthn_credentials'] = [credential, {'credential_id': '!!'}]

    results = _restore(['users'], mutate)

    admin = User.query.filter_by(username='older-admin').one()
    restored = WebAuthnCredential.query.filter_by(user_id=admin.id).one()
    assert (restored.credential_id, restored.sign_count, restored.name) == \
        (b'older-credential', 7, 'YubiKey')
    assert results['webauthn_credentials'] == 1
    assert any('WebAuthn key 1 was left out' in line for line in results['left_out'])


# -- P1-1: an HSM secret under another installation's key ---------------------

def test_an_hsm_secret_under_another_key_is_named_in_the_result(here, caplog):
    foreign = Fernet(Fernet.generate_key()).encrypt(b'1234').decode()

    def mutate(data):
        data['hsm_providers'] = [{'name': 'older-hsm', 'type': 'pkcs11',
                                  'config': json.dumps({'pin': foreign, 'slot': 1})}]

    results = _restore(['hsm_providers'], mutate)

    assert results['dropped_secrets'] == ['hsm_providers older-hsm: pin']
    assert "hsm_providers older-hsm lost field pin" in caplog.text
    assert 'older-hsm' in with_restore_warnings('Restored.', results)


# -- a row left out is not counted --------------------------------------------

@pytest.mark.parametrize('module, method, section, row', [
    ('services.backup.restore_core', '_restore_certificates', 'certificates',
     {'refid': 'older-left-out', 'descr': 'older'}),
    ('services.backup.restore_extended', '_restore_acme_client_orders', 'acme_client_orders',
     {'order_url': 'https://acme.example.test/order/1', 'domains': '[]',
      'environment': 'production', 'created_at': '2026-01-01T00:00:00'}),
])
def test_a_row_apply_columns_leaves_out_is_not_counted(here, monkeypatch, module, method,
                                                       section, row):
    import importlib
    from services.backup.restore import RestorePlan

    monkeypatch.setattr(importlib.import_module(module), 'apply_columns',
                        lambda instance, *args, **kwargs: (db.session.expunge(instance), False)[1])
    data = {section: [row]}
    results = {section: 0}
    restore = getattr(_service(), method)
    if section == 'certificates':
        restore(data, results, b'k' * 32, RestorePlan.build(data))
    else:
        restore(data, results, RestorePlan.build(data))

    assert results[section] == 0

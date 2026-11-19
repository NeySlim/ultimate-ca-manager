"""An archive of a multi-tenant OIDC provider restores its accepted tenants and its tenant-scoped
identities: two accounts with the same ``sub`` in two tenants stay two accounts, in either mode,
SQLite and PostgreSQL. GUIDs invented."""
import json
import os
import uuid

import pytest

from models import db, User, UserSSOIdentity
from models.sso import SSOProvider
from tests.test_backup_cross_installation import Keys, _installation
from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
NOPASS = '!SSO_NO_PASSWORD!'
TENANT_A = '0f1e2d3c-4b5a-4968-8778-a6b5c4d3e2f1'
TENANT_B = '1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d'
AUTHORITY = 'https://idp.example/organizations/v2.0'
ENGINES = [
    'sqlite',
    pytest.param('postgresql', marks=[
        pytest.mark.postgres, pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')]),
]


@pytest.fixture(params=ENGINES)
def target(request, app, tmp_path):
    keys = Keys(tmp_path, f'tenants-{request.param}')
    if request.param == 'sqlite':
        with _installation(app, f"sqlite:///{tmp_path / 'target.db'}", keys), app.app_context():
            yield request.param
            db.session.rollback()
        return
    with _a_schema_of_our_own(f'sso_tenants_{uuid.uuid4().hex[:10]}') as url:
        with _installation(app, url, keys, is_postgresql=True), app.app_context():
            yield request.param
            db.session.rollback()


def _restore(data, mode):
    from services.backup_service import BackupService
    return BackupService()._restore_payload(data, os.urandom(32), mode)


def _archive(tenants):
    users, identities = [], []
    for number, (name, tid) in enumerate((('mt-alice', TENANT_A), ('mt-bob', TENANT_B)), start=900):
        users.append({'username': name, 'email': f'{name}@tenants.test', 'role': 'viewer',
                      'active': True, 'password_hash': NOPASS, 'force_password_change': False,
                      'custom_role_id': None, 'custom_role_id_ref': None})
        identities.append({'user_id': number, 'user_id_ref': {'username': name}, 'provider_id': 41,
                           'provider_id_ref': {'name': 'entra'}, 'orphan_of': None,
                           'external_id': f'{tid}/same-sub', 'created_by': None})
    return {'sso_providers': [{'name': 'entra', 'provider_type': 'oauth2', 'enabled': True,
                               'default_role': 'viewer', 'oauth2_issuer': AUTHORITY,
                               'oauth2_tenants': tenants}],
            'users': users, 'user_sso_identities': identities}


@pytest.mark.parametrize('mode', ['merge', 'replace'])
def test_the_tenants_and_the_tenant_scoped_identities_come_back(target, mode):
    _restore(_archive(json.dumps([TENANT_A, TENANT_B])), mode)
    db.session.expire_all()
    provider = SSOProvider.query.filter_by(name='entra').one()
    assert json.loads(provider.oauth2_tenants) == [TENANT_A, TENANT_B]
    assert provider.to_dict()['oauth2_tenants'] == [TENANT_A, TENANT_B]
    held = {User.query.get(r.user_id).username: r.external_id
            for r in UserSSOIdentity.query.filter_by(provider_id=provider.id)}
    assert held == {'mt-alice': f'{TENANT_A}/same-sub', 'mt-bob': f'{TENANT_B}/same-sub'}


def test_an_archive_without_the_column_restores_a_single_issuer_provider(target):
    data = _archive(None)
    del data['sso_providers'][0]['oauth2_tenants']
    _restore(data, 'replace')
    db.session.expire_all()
    provider = SSOProvider.query.filter_by(name='entra').one()
    assert provider.oauth2_tenants is None and provider.to_dict()['oauth2_tenants'] == []


_UNREADABLE = {'wildcard': '["*"]', 'not_json': 'nope', 'object': '{"a": 1}', 'number': 42,
               'braces': f'["{{{TENANT_A}}}"]'}


def _refused(data, mode, *words):
    from services.backup.errors import BackupSchemaError
    with pytest.raises(BackupSchemaError) as refused:
        _restore(data, mode)
    db.session.rollback()
    message = str(refused.value)
    assert "'entra'" in message and 'Nothing has been changed' in message, message
    assert all(word in message for word in words), message
    assert SSOProvider.query.filter_by(name='entra').first() is None
    assert User.query.filter_by(username='mt-alice').first() is None


@pytest.mark.parametrize('mode', ['merge', 'replace'])
@pytest.mark.parametrize('value', sorted(_UNREADABLE))
def test_unreadable_archived_tenants_are_refused_before_any_write(target, mode, value):
    _refused(_archive(_UNREADABLE[value]), mode, 'accepted tenants')


@pytest.mark.parametrize('mode', ['merge', 'replace'])
def test_archived_tenants_without_id_token_verification_are_refused(target, mode):
    data = _archive(json.dumps([TENANT_A]))
    data['sso_providers'][0]['id_token_verify'] = False
    _refused(data, mode, 'ID token verification')


@pytest.mark.parametrize('mode', ['merge', 'replace'])
@pytest.mark.parametrize('value', ['["*"]', json.dumps(['9188040d-6c67-4c5b-b112-36a304b66dad'])],
                         ids=['unreadable', 'not_accepted'])
def test_archived_role_tenants_off_the_accepted_list_are_refused(target, mode, value):
    data = _archive(json.dumps([TENANT_A, TENANT_B]))
    data['sso_providers'][0]['oauth2_role_tenants'] = value
    _refused(data, mode, 'role tenants')


@pytest.mark.parametrize('mode', ['merge', 'replace'])
def test_archived_role_tenants_and_expected_tenants_come_back(target, mode):
    data = _archive(json.dumps([TENANT_A, TENANT_B]))
    data['sso_providers'][0]['oauth2_role_tenants'] = json.dumps([TENANT_B])
    data['user_sso_identities'][0].update(external_id=None, expected_tenant=TENANT_A)
    _restore(data, mode)
    db.session.expire_all()
    provider = SSOProvider.query.filter_by(name='entra').one()
    assert provider.to_dict()['oauth2_role_tenants'] == [TENANT_B]
    row = UserSSOIdentity.query.filter_by(provider_id=provider.id, external_id=None).one()
    assert row.expected_tenant == TENANT_A


def test_to_dict_shows_an_unreadable_stored_value_as_it_is(target):
    """Never as an empty list, which would read as a provider of one issuer."""
    provider = SSOProvider(name='raw', provider_type='oauth2', oauth2_tenants='["*"]',
                           oauth2_role_tenants='nope')
    assert provider.to_dict()['oauth2_tenants'] == ['*']
    assert provider.to_dict()['oauth2_role_tenants'] == 'nope'

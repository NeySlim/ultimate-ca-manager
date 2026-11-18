"""No restore ends with two SSO providers of one type, and no account names a provider that is gone.

An archive holding two of a type is refused. A replacement removes the provider here that the
archive's provider of its type replaces: its accounts keep its IdP as orphans. A merge keeps the
provider here and leaves the archive's out: the accounts the archive attaches to it come back as
orphans of its IdP. Each case runs on a database of its own, SQLite and PostgreSQL, with archives
of 3.0 (identity rows) and of 2.254 (the provider on the account row).
"""
import os
import uuid

import pytest

from models import db, User, UserSSOIdentity
from models.sso import SSOProvider
from services.backup.errors import BackupSchemaError
from tests.test_backup_cross_installation import Keys, _installation
from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
NOPASS = '!SSO_NO_PASSWORD!'
ENGINES = [
    'sqlite',
    pytest.param('postgresql', marks=[
        pytest.mark.postgres, pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')]),
]
FORMATS = ['3.0', '2.254']


@pytest.fixture(params=ENGINES)
def target(request, app, tmp_path):
    keys = Keys(tmp_path, f'one-per-type-{request.param}')
    if request.param == 'sqlite':
        with _installation(app, f"sqlite:///{tmp_path / 'target.db'}", keys), app.app_context():
            yield request.param
            db.session.rollback()
        return
    with _a_schema_of_our_own(f'sso_per_type_{uuid.uuid4().hex[:10]}') as url:
        with _installation(app, url, keys, is_postgresql=True), app.app_context():
            yield request.param
            db.session.rollback()


def _here(name, kind, idp):
    row = SSOProvider(name=name, provider_type=kind, enabled=True, auto_create_users=True,
                      default_role='viewer', **_idp(kind, idp))
    db.session.add(row)
    db.session.flush()
    return row.id


def _idp(kind, idp):
    return {'oauth2': {'oauth2_issuer': idp}, 'saml': {'saml_entity_id': idp},
            'ldap': {'ldap_server': idp}}[kind]


def _account(name, provider_id, external_id):
    user = User(username=name, email=f'{name}@per-type.test', role='viewer', active=True,
                password_hash=NOPASS)
    db.session.add(user)
    db.session.flush()
    row = UserSSOIdentity(user_id=user.id, provider_id=provider_id)
    row.bind(external_id)
    db.session.add(row)
    db.session.flush()
    return user.id


def _archived_provider(name, kind, idp):
    return {'name': name, 'provider_type': kind, 'enabled': True, 'default_role': 'viewer', **_idp(kind, idp)}


def _archived_account(fmt, name, provider_name, external_id, number=41):
    """The account rows of an archive whose account ``name`` the provider ``provider_name`` opens."""
    user = {'username': name, 'email': f'{name}@per-type.test', 'role': 'viewer', 'active': True,
            'password_hash': NOPASS, 'force_password_change': False,
            'custom_role_id': None, 'custom_role_id_ref': None}
    if fmt == '2.254':
        user.update(auth_source='oauth2', sso_provider_id=number,
                    sso_provider_id_ref={'name': provider_name}, sso_external_id=external_id,
                    sso_orphan_of=None)
        return {'users': [user]}
    return {'users': [user], 'user_sso_identities': [{
        'user_id': 900, 'user_id_ref': {'username': name}, 'provider_id': number,
        'provider_id_ref': {'name': provider_name}, 'orphan_of': None, 'external_id': external_id,
        'created_by': None}]}


def _restore(data, mode):
    from services.backup_service import BackupService
    return BackupService()._restore_payload(data, os.urandom(32), mode)


def _providers():
    return sorted((p.provider_type, p.name, p.id) for p in SSOProvider.query)


def _rows(username):
    user = User.query.filter_by(username=username).one()
    return [(row.provider_id, row.external_id, row.orphan_of)
            for row in UserSSOIdentity.query.filter_by(user_id=user.id).order_by(UserSSOIdentity.id)]


def _one_per_type_and_no_dangling_provider():
    kinds = [kind for kind, _name, _id in _providers()]
    assert len(kinds) == len(set(kinds)), _providers()
    ids = {pid for _kind, _name, pid in _providers()}
    dangling = [r.provider_id for r in UserSSOIdentity.query if r.provider_id is not None
                and r.provider_id not in ids]
    assert dangling == []


# --- The archive itself -------------------------------------------------------------------------

@pytest.mark.parametrize('mode', ['merge', 'replace'])
def test_an_archive_holding_two_providers_of_a_type_is_refused(target, mode):
    corp = _here('corp', 'oauth2', 'https://corp.example')
    db.session.commit()
    data = {'users': [{'username': 'admin-keep', 'role': 'admin', 'active': True,
                       'password_hash': 'x', 'email': 'k@per-type.test'}],
            'sso_providers': [_archived_provider('okta', 'oauth2', 'https://okta.example'),
                              _archived_provider('dir', 'ldap', 'ldap.example'),
                              _archived_provider('entra', 'oauth2', 'https://entra.example')]}
    with pytest.raises(BackupSchemaError) as refused:
        _restore(data, mode)
    db.session.rollback()
    message = str(refused.value)
    assert ("the archive holds 2 SSO providers of type oauth2: 'okta', 'entra'" in message
            and 'Nothing has been changed' in message), message
    assert 'UNIQUE' not in message.upper()
    assert _providers() == [('oauth2', 'corp', corp)]
    assert User.query.filter_by(username='admin-keep').first() is None


# --- A replacement: the archive's provider of the type replaces the one here --------------------

@pytest.mark.parametrize('fmt', FORMATS)
def test_a_replacement_replaces_the_provider_of_the_type(target, fmt):
    corp = _here('corp', 'oauth2', 'https://corp.example')
    _account('alice', corp, 'alice-at-corp')
    db.session.commit()
    data = {'sso_providers': [_archived_provider('okta', 'oauth2', 'https://okta.example')],
            **_archived_account(fmt, 'alice', 'okta', 'alice-at-okta')}
    results = _restore(data, 'replace')
    db.session.expire_all()
    okta = SSOProvider.query.filter_by(name='okta').one()
    assert _providers() == [('oauth2', 'okta', okta.id)]
    # The archive's account is attached to the archive's provider, never to corp's row
    assert _rows('alice') == [(okta.id, 'alice-at-okta', None)]
    assert any("the oauth2 provider 'corp'" in w and "replaced by the archive's oauth2 provider 'okta'" in w
               for w in results['warnings']), results['warnings']
    _one_per_type_and_no_dangling_provider()


def test_a_replacement_of_the_providers_alone_keeps_the_accounts_as_orphans_of_their_idp(target):
    """Section selection: the archive carries no account; those here keep the IdP they were bound by."""
    corp = _here('corp', 'oauth2', 'https://corp.example')
    _account('bob', corp, 'bob-at-corp')
    db.session.commit()
    results = _restore({'sso_providers': [_archived_provider('okta', 'oauth2', 'https://okta.example')]},
                       'replace')
    db.session.expire_all()
    okta = SSOProvider.query.filter_by(name='okta').one()
    assert _providers() == [('oauth2', 'okta', okta.id)]
    assert _rows('bob') == [(None, 'bob-at-corp', 'oauth2:https://corp.example')]
    assert any("'corp'" in w for w in results['warnings']), results['warnings']
    _one_per_type_and_no_dangling_provider()


def test_a_replacement_whose_name_is_held_by_another_type_replaces_that_provider(target):
    sso = _here('sso', 'saml', 'https://saml.example')
    _account('carol', sso, 'carol-at-saml')
    db.session.commit()
    results = _restore({'sso_providers': [_archived_provider('sso', 'oauth2', 'https://okta.example')]},
                       'replace')
    db.session.expire_all()
    new = SSOProvider.query.filter_by(name='sso').one()
    assert new.provider_type == 'oauth2'
    assert _rows('carol') == [(None, 'carol-at-saml', 'saml:https://saml.example')]
    assert any("the saml provider 'sso'" in w for w in results['warnings']), results['warnings']
    _one_per_type_and_no_dangling_provider()


@pytest.mark.parametrize('mode', ['merge', 'replace'])
def test_the_same_provider_is_updated_in_place(target, mode):
    corp = _here('corp', 'oauth2', 'https://corp.example')
    _account('dave', corp, 'dave-at-corp')
    db.session.commit()
    archived = dict(_archived_provider('corp', 'oauth2', 'https://corp.example'), display_name='Corp SSO')
    results = _restore({'sso_providers': [archived]}, mode)
    db.session.expire_all()
    assert _providers() == [('oauth2', 'corp', corp)]
    assert db.session.get(SSOProvider, corp).display_name == 'Corp SSO'
    assert _rows('dave') == [(corp, 'dave-at-corp', None)]
    assert not [w for w in results['warnings'] if w.startswith('sso_providers:')], results['warnings']


# --- A merge: the provider here stays, the archive's is left out --------------------------------

@pytest.mark.parametrize('fmt', FORMATS)
def test_a_merge_keeps_the_provider_of_the_type_here(target, fmt):
    corp = _here('corp', 'oauth2', 'https://corp.example')
    _account('erin', corp, 'erin-at-corp')
    db.session.commit()
    data = {'sso_providers': [_archived_provider('okta', 'oauth2', 'https://okta.example')],
            **_archived_account(fmt, 'frank', 'okta', 'frank-at-okta')}
    results = _restore(data, 'merge')
    db.session.expire_all()
    assert _providers() == [('oauth2', 'corp', corp)]
    assert _rows('erin') == [(corp, 'erin-at-corp', None)]
    # Never attached to corp: an orphan of okta's IdP, which a provider of that IdP takes back
    assert _rows('frank') == [(None, 'frank-at-okta', 'oauth2:https://okta.example')]
    assert any("the archive's oauth2 provider 'okta' is not restored" in w and "'corp'" in w
               for w in results['warnings']), results['warnings']
    # The restore report's To do list carries it
    from services.backup.restore_report import restore_todo_lines
    assert any("'okta' is not restored" in line for line in restore_todo_lines(results))
    _one_per_type_and_no_dangling_provider()


def test_a_merge_whose_name_is_held_by_another_type_leaves_it_out(target):
    sso = _here('sso', 'saml', 'https://saml.example')
    db.session.commit()
    results = _restore({'sso_providers': [_archived_provider('sso', 'oauth2', 'https://okta.example')]},
                       'merge')
    db.session.expire_all()
    assert _providers() == [('saml', 'sso', sso)]
    assert any("'sso' is not restored: a saml provider holds its name here" in w
               for w in results['warnings']), results['warnings']


def test_a_merge_adds_a_provider_of_a_type_not_here(target):
    corp = _here('corp', 'oauth2', 'https://corp.example')
    db.session.commit()
    results = _restore({'sso_providers': [_archived_provider('dir', 'ldap', 'ldap.example')]}, 'merge')
    db.session.expire_all()
    kinds = [(kind, name) for kind, name, _id in _providers()]
    assert kinds == [('ldap', 'dir'), ('oauth2', 'corp')]
    assert db.session.get(SSOProvider, corp) is not None
    assert not [w for w in results['warnings'] if w.startswith('sso_providers:')], results['warnings']


# --- A merge whose left-out provider speaks to the IdP of the one here -------------------------

@pytest.mark.parametrize('fmt', FORMATS)
def test_a_merge_attaches_the_identities_of_the_same_idp_to_the_provider_here(target, fmt):
    """One subject of one IdP is one row (OIDC Core §5.7): never an orphan beside the live one."""
    corp = _here('corp', 'oauth2', 'https://same.example')
    _account('gina', corp, 'gina-sub')
    db.session.commit()
    archived = _archived_account(fmt, 'gina', 'okta', 'gina-sub')
    hank = _archived_account(fmt, 'hank', 'okta', 'hank-sub')
    archived['users'] += hank['users']
    if fmt == '3.0':
        archived['user_sso_identities'] += hank['user_sso_identities']
    results = _restore({'sso_providers': [_archived_provider('okta', 'oauth2', 'https://same.example/')],
                        **archived}, 'merge')
    db.session.expire_all()
    assert _providers() == [('oauth2', 'corp', corp)]
    assert _rows('gina') == [(corp, 'gina-sub', None)]
    assert _rows('hank') == [(corp, 'hank-sub', None)]
    assert any("'okta' is not restored" in w and "the same IdP" in w
               for w in results['warnings']), results['warnings']
    _one_per_type_and_no_dangling_provider()


def test_a_merge_never_attaches_the_identities_of_another_idp(target):
    corp = _here('corp', 'oauth2', 'https://corp.example')
    _account('ivan', corp, 'ivan-sub')
    db.session.commit()
    _restore({'sso_providers': [_archived_provider('okta', 'oauth2', 'https://okta.example')],
              **_archived_account('3.0', 'ivan', 'okta', 'ivan-sub')}, 'merge')
    db.session.expire_all()
    assert _rows('ivan') == [(corp, 'ivan-sub', None), (None, 'ivan-sub', 'oauth2:https://okta.example')]


@pytest.mark.parametrize('fmt', FORMATS)
def test_a_replacement_by_a_provider_of_the_same_idp_leaves_one_row_per_subject(target, fmt):
    corp = _here('corp', 'oauth2', 'https://same.example')
    _account('gina', corp, 'gina-sub')
    db.session.commit()
    _restore({'sso_providers': [_archived_provider('okta', 'oauth2', 'https://same.example')],
              **_archived_account(fmt, 'gina', 'okta', 'gina-sub')}, 'replace')
    db.session.expire_all()
    okta = SSOProvider.query.filter_by(name='okta').one()
    assert _rows('gina') == [(okta.id, 'gina-sub', None)]
    _one_per_type_and_no_dangling_provider()

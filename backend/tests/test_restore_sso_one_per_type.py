"""No restore ends with two SSO providers of one type, and no account names a provider that is gone.

An archive holding two of a type is refused. A replacement removes the provider here that the
archive's provider of its type replaces: its accounts keep its IdP as orphans. A merge keeps the
provider here and leaves the archive's out: the accounts the archive attaches to it come back as
orphans of its IdP, or, when it speaks to the IdP of the provider here, attached to that provider
if the account holds no row of the IdP yet (one subject of one IdP is one row). Each case runs on a database of its own, SQLite and PostgreSQL, with archives
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


@pytest.mark.parametrize('fmt', FORMATS)
def test_a_merge_whose_name_is_held_by_another_type_attaches_to_the_provider_of_the_same_idp(target, fmt):
    """The same IdP is judged against the provider here of the archived one's type, not the holder."""
    _here('corp', 'ldap', 'ldap.example')
    okta = _here('okta', 'oauth2', 'https://same.example')
    _account('gina', okta, 'gina-sub')
    db.session.commit()
    results = _restore({'sso_providers': [_archived_provider('corp', 'oauth2', 'https://same.example')],
                        **_archived_account(fmt, 'gina', 'corp', 'gina-sub')}, 'merge')
    db.session.expire_all()
    assert _rows('gina') == [(okta, 'gina-sub', None)]
    assert any("'corp' is not restored: a ldap provider holds its name here" in w
               and "the same IdP" in w and "'okta'" in w
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


@pytest.mark.parametrize('fmt', FORMATS)
def test_a_merge_keeps_the_live_binding_at_the_provider_of_the_same_idp(target, fmt):
    """One IdP behind two registrations can give two subjects (OIDC Core §8, pairwise): the
    binding here stays; a 3.0 archive's subject comes back as an orphan of the IdP, a 2.254
    account that holds rows here keeps them alone (the legacy merge rule)."""
    okta = _here('okta', 'oauth2', 'https://same.example')
    _account('gina', okta, 'gina-new')
    db.session.commit()
    results = _restore({'sso_providers': [_archived_provider('corp', 'oauth2', 'https://same.example')],
                        **_archived_account(fmt, 'gina', 'corp', 'gina-old')}, 'merge')
    db.session.expire_all()
    orphan = [(None, 'gina-old', 'oauth2:https://same.example')] if fmt == '3.0' else []
    assert _rows('gina') == [(okta, 'gina-new', None)] + orphan
    kept = [w for w in results['warnings'] if "'gina' is bound here to provider 'okta'" in w]
    assert len(kept) == (1 if fmt == '3.0' else 0), results['warnings']
    _one_per_type_and_no_dangling_provider()


def test_a_merge_adds_no_row_for_the_live_binding_of_the_same_idp(target):
    okta = _here('okta', 'oauth2', 'https://same.example')
    _account('gina', okta, 'gina-sub')
    db.session.commit()
    _restore({'sso_providers': [_archived_provider('corp', 'oauth2', 'https://same.example')],
              **_archived_account('3.0', 'gina', 'corp', 'gina-sub')}, 'merge')
    db.session.expire_all()
    assert _rows('gina') == [(okta, 'gina-sub', None)]


# --- The matrix: the account's rows here before a merge, by archive format and IdP ---------------
#
# Here: corp (oauth2, issuer https://same.example). Archive: okta, left out by the merge, binding
# gina to A. 'same' : okta's issuer is corp's (K = their IdP key); 'other' : okta.example (K = its
# key). P = corp's row, A = the archive's subject, B = another subject of IdP K.
# Columns: rows after the merge; the user_sso_identities warning ('bound', 'orphan' or None);
# per signed-in subject at corp: whether gina opens, and her rows after the sign-in.
P, A, B, K = 'P', 'gina-sub', 'gina-here', 'K'
STATES = {
    'none': [],
    'bound_same': [(P, A, None)],
    'bound_other': [(P, B, None)],
    'pending': [(P, None, None)],
    'orphan_same': [(None, A, K)],
    'orphan_other': [(None, B, K)],
}
MATRIX = {
    ('same', '3.0', 'none'): ([(P, A, None)], None, {A: (True, [(P, A, None)])}),
    ('same', '3.0', 'bound_same'): ([(P, A, None)], None, {A: (True, [(P, A, None)])}),
    ('same', '3.0', 'bound_other'): ([(P, B, None), (None, A, K)], 'bound', {
        A: (False, [(P, B, None), (None, A, K)]), B: (True, [(P, B, None), (None, A, K)])}),
    ('same', '3.0', 'pending'): ([(P, A, None)], None, {A: (True, [(P, A, None)])}),
    ('same', '3.0', 'orphan_same'): ([(None, A, K)], None, {A: (True, [(P, A, None)])}),
    ('same', '3.0', 'orphan_other'): ([(None, B, K), (None, A, K)], 'orphan', {
        A: (True, [(None, B, K), (P, A, None)]), B: (True, [(P, B, None), (None, A, K)])}),
    # A 2.254 account that holds rows here keeps them alone (the legacy merge rule)
    ('same', '2.254', 'none'): ([(P, A, None)], None, {A: (True, [(P, A, None)])}),
    ('same', '2.254', 'bound_same'): ([(P, A, None)], None, {A: (True, [(P, A, None)])}),
    ('same', '2.254', 'bound_other'): ([(P, B, None)], None, {
        A: (False, [(P, B, None)]), B: (True, [(P, B, None)])}),
    ('same', '2.254', 'pending'): ([(P, None, None)], None, {A: (True, [(P, A, None)])}),
    ('same', '2.254', 'orphan_same'): ([(None, A, K)], None, {A: (True, [(P, A, None)])}),
    ('same', '2.254', 'orphan_other'): ([(None, B, K)], None, {
        A: (False, [(None, B, K)]), B: (True, [(P, B, None)])}),
    # Another IdP: never attached to corp, never taken back by a sign-in at corp
    ('other', '3.0', 'none'): ([(None, A, K)], None, {A: (False, [(None, A, K)])}),
    ('other', '3.0', 'bound_same'): ([(P, A, None), (None, A, K)], None, {
        A: (True, [(P, A, None), (None, A, K)])}),
    ('other', '3.0', 'bound_other'): ([(P, B, None), (None, A, K)], None, {
        A: (False, [(P, B, None), (None, A, K)]), B: (True, [(P, B, None), (None, A, K)])}),
    ('other', '3.0', 'pending'): ([(P, None, None), (None, A, K)], None, {
        A: (True, [(P, A, None), (None, A, K)])}),
    ('other', '3.0', 'orphan_same'): ([(None, A, K)], None, {A: (False, [(None, A, K)])}),
    ('other', '3.0', 'orphan_other'): ([(None, B, K), (None, A, K)], None, {
        A: (False, [(None, B, K), (None, A, K)]), B: (False, [(None, B, K), (None, A, K)])}),
    ('other', '2.254', 'none'): ([(None, A, K)], None, {A: (False, [(None, A, K)])}),
    ('other', '2.254', 'bound_same'): ([(P, A, None)], None, {A: (True, [(P, A, None)])}),
    ('other', '2.254', 'bound_other'): ([(P, B, None)], None, {
        A: (False, [(P, B, None)]), B: (True, [(P, B, None)])}),
    ('other', '2.254', 'pending'): ([(P, None, None)], None, {A: (True, [(P, A, None)])}),
    ('other', '2.254', 'orphan_same'): ([(None, A, K)], None, {A: (False, [(None, A, K)])}),
    ('other', '2.254', 'orphan_other'): ([(None, B, K)], None, {
        A: (False, [(None, B, K)]), B: (False, [(None, B, K)])}),
}
WARNINGS = {'bound': "the account 'gina' is bound here to provider 'corp' under another subject",
            'orphan': "the account 'gina' holds an orphan of the IdP of provider 'corp' under another subject"}
MATRIX_CASES = [pytest.param(*case, subject, id=f'{"-".join(case)}-signs-in-{subject}')
                for case, (_after, _warning, logins) in MATRIX.items() for subject in logins]


def _sign_in(provider_id, subject):
    """The sign-in at the provider here with ``subject``, by the login's own resolution."""
    from flask import current_app
    from api.v2.sso.ldap_routes import _get_or_create_sso_user
    provider = db.session.get(SSOProvider, provider_id)
    with current_app.test_request_context():
        opened, _error = _get_or_create_sso_user(provider, 'gina', 'gina@per-type.test', 'Gina',
                                                 {'sub': subject})
        opened_id = opened.id if opened is not None else None
    db.session.rollback()
    return opened_id


def _one_row_per_subject_of_an_idp(username):
    keys = []
    for row in UserSSOIdentity.query.filter_by(user_id=User.query.filter_by(username=username).one().id):
        idp = db.session.get(SSOProvider, row.provider_id).idp_key() if row.provider_id else row.orphan_of
        if row.external_id is not None and idp is not None:
            keys.append((idp, row.external_id))
    assert len(keys) == len(set(keys)), keys


@pytest.mark.parametrize('idp, fmt, state, subject', MATRIX_CASES)
def test_a_merge_leaves_one_row_per_subject_of_an_idp(target, idp, fmt, state, subject):
    """One subject of one IdP is one row of an account, after the merge and after the sign-in that
    follows it (OIDC Core §5.7); the archive's identity joins corp only when gina holds no row of
    its IdP, never over one, and never across two IdPs."""
    issuer = 'https://same.example/' if idp == 'same' else 'https://okta.example'
    key = SSOProvider(provider_type='oauth2', oauth2_issuer=issuer).idp_key()
    corp = _here('corp', 'oauth2', 'https://same.example')
    symbols = {P: corp, K: key}
    gina = User(username='gina', email='gina@per-type.test', role='viewer', active=True,
                password_hash=NOPASS)
    db.session.add(gina)
    db.session.flush()
    for provider, external_id, orphan_of in STATES[state]:
        row = UserSSOIdentity(user_id=gina.id, provider_id=symbols.get(provider),
                              orphan_of=symbols.get(orphan_of))
        if external_id is not None:
            row.bind(external_id)
        db.session.add(row)
    db.session.commit()
    gina_id = gina.id
    after, warning, logins = MATRIX[(idp, fmt, state)]

    def resolved(rows):
        return sorted(((symbols.get(p), e, symbols.get(o)) for p, e, o in rows), key=repr)

    results = _restore({'sso_providers': [_archived_provider('okta', 'oauth2', issuer)],
                        **_archived_account(fmt, 'gina', 'okta', A)}, 'merge')
    db.session.commit()
    db.session.expire_all()
    assert sorted(_rows('gina'), key=repr) == resolved(after)
    identity_warnings = [w for w in results['warnings'] if w.startswith('user_sso_identities:')]
    assert len(identity_warnings) == (1 if warning else 0), identity_warnings
    if warning:
        assert WARNINGS[warning] in identity_warnings[0], identity_warnings
    _one_row_per_subject_of_an_idp('gina')

    opens, rows_after = logins[subject]
    assert (_sign_in(corp, subject) == gina_id) is opens
    db.session.expire_all()
    assert sorted(_rows('gina'), key=repr) == resolved(rows_after)
    _one_row_per_subject_of_an_idp('gina')
    _one_per_type_and_no_dangling_provider()

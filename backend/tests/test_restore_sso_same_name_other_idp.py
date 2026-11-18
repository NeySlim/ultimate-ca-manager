"""A restore never lets the accounts of one IdP answer to another IdP.

An archived provider with the name and the type of the one here but another IdP key (another
OIDC issuer, SAML entity ID or LDAP directory) is another provider: a replacement removes the
one here (its accounts keep its IdP as orphans), a merge keeps it and leaves the archived one
out (its accounts come back as orphans of their IdP). OIDC Core 1.0 §5.7: sub and iss, used
together, are the only claims an RP can rely upon as a stable identifier for the End-User.
The same IdP, written otherwise, is still updated in place.

Instance: kate bound by the IdP here (``kate-sub``), liam without identity. Archive: kate bound
by the archived provider, mona bound by it (``mona-sub``).
"""
import os

import pytest

from models import db, User, UserSSOIdentity
from models.sso import SSOProvider
from tests.test_restore_sso_one_per_type import FORMATS, NOPASS, target  # noqa: F401

# Per type: the IdP here (A), the same IdP written otherwise, another IdP (B)
IDPS = {
    'oauth2': ({'oauth2_issuer': 'https://a.example'},
               {'oauth2_issuer': 'https://A.Example/'},
               {'oauth2_issuer': 'https://b.example'}),
    'saml': ({'saml_entity_id': 'https://a.example/idp'},
             {'saml_entity_id': ' https://a.example/idp '},
             {'saml_entity_id': 'https://b.example/idp'}),
    'ldap': ({'ldap_server': 'ldap-a.example', 'ldap_base_dn': 'dc=a,dc=example'},
             {'ldap_server': 'LDAP-A.example', 'ldap_base_dn': 'DC=a,DC=example'},
             {'ldap_server': 'ldap-b.example', 'ldap_base_dn': 'dc=b,dc=example'}),
}
CASES = {'same': 0, 'respelled': 1, 'other': 2}


def _key(kind, fields):
    return SSOProvider(provider_type=kind, **fields).idp_key()


def _presented(kind, subject):
    return {'oauth2': {'sub': subject},
            'saml': {'name_id': subject, 'name_id_format': 'persistent'},
            'ldap': {'uid': subject}}[kind]


def _instance(kind):
    corp = SSOProvider(name='corp', provider_type=kind, enabled=True, auto_create_users=True,
                       default_role='viewer', **IDPS[kind][0])
    db.session.add(corp)
    db.session.flush()
    kate = User(username='kate', email='kate@idp.test', role='viewer', active=True,
                password_hash=NOPASS)
    liam = User(username='liam', email='liam@idp.test', role='viewer', active=True,
                password_hash='local-password-hash')
    db.session.add_all([kate, liam])
    db.session.flush()
    row = UserSSOIdentity(user_id=kate.id, provider_id=corp.id)
    row.bind('kate-sub')
    db.session.add(row)
    db.session.commit()
    return corp.id


def _archive(fmt, kind, idp, kate_subject):
    provider = {'name': 'corp', 'provider_type': kind, 'enabled': True, 'default_role': 'viewer',
                'auto_create_users': True, **idp}
    users, identities = [], []
    for number, (name, subject) in enumerate([('kate', kate_subject), ('mona', 'mona-sub')]):
        user = {'username': name, 'email': f'{name}@idp.test', 'role': 'viewer', 'active': True,
                'password_hash': NOPASS, 'force_password_change': False,
                'custom_role_id': None, 'custom_role_id_ref': None}
        if fmt == '2.254':
            user.update(auth_source=kind, sso_provider_id=41, sso_provider_id_ref={'name': 'corp'},
                        sso_external_id=subject, sso_orphan_of=None)
        else:
            identities.append({'user_id': 900 + number, 'user_id_ref': {'username': name},
                               'provider_id': 41, 'provider_id_ref': {'name': 'corp'},
                               'orphan_of': None, 'external_id': subject, 'created_by': None})
        users.append(user)
    data = {'sso_providers': [provider], 'users': users}
    if fmt == '3.0':
        data['user_sso_identities'] = identities
    return data


def _restore(data, mode):
    from services.backup_service import BackupService
    return BackupService()._restore_payload(data, os.urandom(32), mode)


def _rows(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        return None
    return [(row.provider_id, row.external_id, row.orphan_of)
            for row in UserSSOIdentity.query.filter_by(user_id=user.id).order_by(UserSSOIdentity.id)]


def _login(provider_id, username, subject):
    from api.v2.sso.ldap_routes import _get_or_create_sso_user
    from flask import current_app
    provider = db.session.get(SSOProvider, provider_id)
    with current_app.test_request_context():
        user, error = _get_or_create_sso_user(provider, username, f'{username}@idp.test', 'N',
                                              _presented(provider.provider_type, subject))
    db.session.rollback()
    return user.username if user is not None else None, error


def _expected(mode, fmt, kind, case, corp, after):
    """The table, once the restore is done: the provider of the type (its id and IdP fields),
    the identity rows (provider_id, external_id, orphan_of) of kate, liam (None: no account)
    and mona, and the line of the restore's report (None: no sso_providers line).

    ``after`` is the id of the provider of the type after the restore."""
    a, b = _key(kind, IDPS[kind][0]), _key(kind, IDPS[kind][2])
    if case != 'other':
        # Same IdP, even written otherwise: updated in place, its id and accounts kept
        return {'provider': (corp, IDPS[kind][CASES[case]]), 'kate': [(corp, 'kate-sub', None)],
                'liam': [] if mode == 'merge' else None, 'mona': [(corp, 'mona-sub', None)],
                'warning': None}
    if mode == 'replace':
        # The archive's provider takes the place. kate's row of A stays an orphan of A (3.0) or
        # gives way to the archive's account row (2.254); liam is not in the archive
        kate = [(None, 'kate-sub', a)] if fmt == '3.0' else []
        return {'provider': (after, IDPS[kind][2]), 'kate': kate + [(after, 'kate-sub-b', None)],
                'liam': None, 'mona': [(after, 'mona-sub', None)],
                'warning': "the {kind} provider 'corp' (#{corp}) is replaced by the archive's "
                           "{kind} provider 'corp': it signs in through another IdP"}
    # Merge: the provider here stays as it is; the archive's identities are orphans of B (a
    # merge keeps the rows of an account it holds when the archive is of 2.254)
    kate = [(corp, 'kate-sub', None)] + ([(None, 'kate-sub-b', b)] if fmt == '3.0' else [])
    return {'provider': (corp, IDPS[kind][0]), 'kate': kate, 'liam': [],
            'mona': [(None, 'mona-sub', b)],
            'warning': "the archive's {kind} provider 'corp' is not restored: the {kind} provider "
                       "of that name here signs in through another IdP (#{corp})"}


@pytest.mark.parametrize('kind', sorted(IDPS))
@pytest.mark.parametrize('case', sorted(CASES))
@pytest.mark.parametrize('fmt', FORMATS)
@pytest.mark.parametrize('mode', ['replace', 'merge'])
def test_a_restore_binds_no_account_of_one_idp_to_another(target, mode, fmt, case, kind):
    corp = _instance(kind)
    kate_subject = 'kate-sub-b' if case == 'other' else 'kate-sub'
    results = _restore(_archive(fmt, kind, IDPS[kind][CASES[case]], kate_subject), mode)
    db.session.expire_all()
    providers = SSOProvider.query.filter_by(provider_type=kind).all()
    assert len(providers) == 1
    after = providers[0]
    want = _expected(mode, fmt, kind, case, corp, after.id)

    provider_id, fields = want['provider']
    assert after.id == provider_id and after.name == 'corp'
    assert {f: getattr(after, f) for f in fields} == fields
    assert _rows('kate') == want['kate']
    assert _rows('liam') == want['liam']
    assert _rows('mona') == want['mona']
    sso = [w for w in results['warnings'] if w.startswith('sso_providers:')]
    if want['warning'] is None:
        assert sso == []
    else:
        text = want['warning'].format(kind=kind, corp=corp)
        assert any(text in w for w in sso), sso
    # Whatever the case: no identity row of A is bound to a provider of another IdP
    a = {_key(kind, IDPS[kind][0]), _key(kind, IDPS[kind][1])}
    for row in UserSSOIdentity.query.filter(UserSSOIdentity.provider_id.isnot(None)):
        holder = db.session.get(SSOProvider, row.provider_id)
        if row.external_id == 'kate-sub':
            assert holder.idp_key() in a, (row.provider_id, holder.idp_key())


@pytest.mark.parametrize('kind', sorted(IDPS))
@pytest.mark.parametrize('fmt', FORMATS)
def test_after_a_replacement_the_other_idp_does_not_open_kate(target, fmt, kind):
    corp = _instance(kind)
    _restore(_archive(fmt, kind, IDPS[kind][2], 'kate-sub-b'), 'replace')
    db.session.expire_all()
    b = SSOProvider.query.filter_by(provider_type=kind).one()
    assert b.idp_key() == _key(kind, IDPS[kind][2])
    # kate's subject at A, presented by B, opens no account of kate
    assert _login(b.id, 'kate', 'kate-sub')[0] != 'kate'
    assert _login(b.id, 'intruder', 'kate-sub')[0] != 'kate'
    # The archive's accounts sign in through B
    assert _login(b.id, 'mona', 'mona-sub') == ('mona', None)
    assert _login(b.id, 'kate', 'kate-sub-b') == ('kate', None)
    assert corp is not None


@pytest.mark.parametrize('kind', sorted(IDPS))
def test_a_replacement_of_the_provider_alone_leaves_kate_an_orphan_of_a(target, kind):
    """Section selection: the accounts here stay, and B never opens the one A bound."""
    corp = _instance(kind)
    archive = _archive('3.0', kind, IDPS[kind][2], 'kate-sub-b')
    results = _restore({'sso_providers': archive['sso_providers']}, 'replace')
    db.session.expire_all()
    b = SSOProvider.query.filter_by(provider_type=kind).one()
    assert b.idp_key() == _key(kind, IDPS[kind][2])
    assert _rows('kate') == [(None, 'kate-sub', _key(kind, IDPS[kind][0]))]
    assert _rows('liam') == []
    assert any(f"'corp' (#{corp}) is replaced" in w for w in results['warnings']), results['warnings']
    assert _login(b.id, 'kate', 'kate-sub')[0] != 'kate'
    assert _login(b.id, 'intruder', 'kate-sub')[0] != 'kate'


@pytest.mark.parametrize('kind', sorted(IDPS))
@pytest.mark.parametrize('fmt', FORMATS)
def test_after_a_merge_the_other_idp_does_not_open_kate(target, fmt, kind):
    corp = _instance(kind)
    _restore(_archive(fmt, kind, IDPS[kind][2], 'kate-sub-b'), 'merge')
    db.session.expire_all()
    here = db.session.get(SSOProvider, corp)
    assert here.idp_key() == _key(kind, IDPS[kind][0])
    # The provider here still opens kate by A's subject, and nobody by B's subjects
    assert _login(corp, 'kate', 'kate-sub') == ('kate', None)
    assert _login(corp, 'mona', 'mona-sub')[0] != 'mona'
    # A provider of B, set up later the way the API deletes and creates one, takes mona back
    UserSSOIdentity.query.filter_by(provider_id=corp).update(
        {UserSSOIdentity.provider_id: None, UserSSOIdentity.orphan_of: here.idp_key()},
        synchronize_session=False)
    db.session.delete(here)
    db.session.flush()
    b = SSOProvider(name='b', provider_type=kind, enabled=True, auto_create_users=True,
                    default_role='viewer', **IDPS[kind][2])
    db.session.add(b)
    db.session.commit()
    assert _login(b.id, 'kate', 'kate-sub')[0] != 'kate'
    assert _login(b.id, 'intruder', 'kate-sub')[0] != 'kate'
    assert _login(b.id, 'mona', 'mona-sub') == ('mona', None)


@pytest.mark.parametrize('mode', ['replace', 'merge'])
@pytest.mark.parametrize('archived, moved', [
    ({}, False),                                   # the archive does not carry the field: kept here
    ({'oauth2_issuer': None}, True),               # it carries no IdP: kate's is not trusted to it
    ({'oauth2_issuer': 'https://a.example/'}, False),
])
def test_an_idp_field_the_archive_does_not_carry_keeps_the_one_here(target, mode, archived, moved):
    corp = _instance('oauth2')
    provider = {'name': 'corp', 'provider_type': 'oauth2', 'enabled': True, 'default_role': 'viewer',
                **archived}
    results = _restore({'sso_providers': [provider]}, mode)
    db.session.expire_all()
    sso = [w for w in results['warnings'] if w.startswith('sso_providers:')]
    assert bool(sso) is moved, sso
    if not moved:
        assert db.session.get(SSOProvider, corp).oauth2_issuer.startswith('https://a.example')
        assert _rows('kate') == [(corp, 'kate-sub', None)]
    elif mode == 'replace':
        assert _rows('kate') == [(None, 'kate-sub', 'oauth2:https://a.example')]
    else:
        assert db.session.get(SSOProvider, corp).oauth2_issuer == 'https://a.example'
        assert _rows('kate') == [(corp, 'kate-sub', None)]


@pytest.mark.parametrize('mode', ['replace', 'merge'])
def test_a_provider_whose_idp_is_unknown_on_both_sides_is_updated_in_place(target, mode):
    corp = SSOProvider(name='corp', provider_type='saml', enabled=False, default_role='viewer')
    db.session.add(corp)
    db.session.commit()
    results = _restore({'sso_providers': [{'name': 'corp', 'provider_type': 'saml',
                                           'display_name': 'Corp', 'saml_entity_id': None}]}, mode)
    db.session.expire_all()
    assert not [w for w in results['warnings'] if w.startswith('sso_providers:')]
    assert SSOProvider.query.filter_by(provider_type='saml').one().id == corp.id


@pytest.mark.parametrize('kind', sorted(IDPS))
def test_an_identity_removed_with_its_provider_is_not_reported_as_unlinked(target, kind):
    """The report counts as unlinked the rows that stay, never one the replacement removes."""
    _instance(kind)
    archive = _archive('3.0', kind, IDPS[kind][2], 'kate-sub-b')
    mona = [user for user in archive['users'] if user['username'] == 'mona']
    results = _restore({'sso_providers': [], 'user_sso_identities': [], 'users': mona}, 'replace')
    db.session.expire_all()
    assert _rows('kate') is None and SSOProvider.query.filter_by(provider_type=kind).count() == 0
    assert 'user_sso_identities.provider_id' not in results['unlinked_dependents'], results


# The archived field that tells each provider's IdP, and the values that are not text
NOT_TEXT_FIELDS = [('oauth2', 'oauth2_issuer'), ('saml', 'saml_entity_id'),
                   ('ldap', 'ldap_server'), ('ldap', 'ldap_base_dn')]
NOT_TEXT = {'number': 12345, 'list': ['https://a.example'], 'object': {'url': 'https://a.example'}}


# A replacement writes the archived row: a list or an object then fails in the text column
# (another defect), so only a number goes that far
@pytest.mark.parametrize('value, mode', [(v, 'merge') for v in sorted(NOT_TEXT)]
                         + [('number', 'replace')])
@pytest.mark.parametrize('kind, field', NOT_TEXT_FIELDS)
def test_an_archived_idp_field_that_is_not_text_names_no_idp(target, kind, field, value, mode):
    corp = _instance(kind)
    archive = _archive('3.0', kind, {**IDPS[kind][0], field: NOT_TEXT[value]}, 'kate-sub-b')
    results = _restore(archive, mode)
    db.session.expire_all()
    # No IdP is never the IdP here: kate's account at A never follows the archived row
    sso = [w for w in results['warnings'] if w.startswith('sso_providers:')]
    assert len(sso) == 1 and 'another IdP' in sso[0], sso
    a = _key(kind, IDPS[kind][0])
    if mode == 'merge':
        assert {f: getattr(db.session.get(SSOProvider, corp), f) for f in IDPS[kind][0]} \
            == IDPS[kind][0]
        # The value is read as absent: an archived base DN alone left out keeps the server's key
        archived = _key(kind, {**IDPS[kind][0], field: None})
        assert _rows('kate') == [(corp, 'kate-sub', None), (None, 'kate-sub-b', archived)]
    else:
        assert (None, 'kate-sub', a) in _rows('kate')


@pytest.mark.parametrize('mode', ['merge', 'replace'])
@pytest.mark.parametrize('value', sorted(NOT_TEXT))
def test_an_archived_provider_type_that_is_not_text_is_refused(target, value, mode):
    from services.backup.errors import BackupSchemaError
    corp = _instance('oauth2')
    archive = _archive('3.0', 'oauth2', IDPS['oauth2'][1], 'kate-sub-b')
    archive['sso_providers'][0]['provider_type'] = NOT_TEXT[value]
    with pytest.raises(BackupSchemaError) as refused:
        _restore(archive, mode)
    assert "'corp'" in str(refused.value) and 'Nothing has been changed' in str(refused.value)
    db.session.rollback()
    assert _rows('kate') == [(corp, 'kate-sub', None)]


@pytest.mark.parametrize('kind, field', NOT_TEXT_FIELDS)
def test_a_field_here_that_is_not_text_names_no_idp(app, kind, field):
    from services.backup.restore.sso_providers import _another_idp
    with app.app_context():
        provider = SSOProvider(name='corp', provider_type=kind, **{**IDPS[kind][0], field: 12345})
        assert _another_idp(provider, {'name': 'corp', **IDPS[kind][0]}) is True
        assert _another_idp(provider, {'name': 'corp'}) is False


UNREADABLE = 'https://[idp.example.test/realms/x'


@pytest.mark.parametrize('here, archived, other', [
    (UNREADABLE, UNREADABLE, False),                              # compared as written
    ('https://idp.example.test/realms/x', UNREADABLE, True),
    (UNREADABLE, 'https://[other.example.test/realms/x', True),
])
def test_an_issuer_no_url_parser_reads_is_compared_as_written(app, here, archived, other):
    from services.backup.restore.sso_providers import _another_idp
    with app.app_context():
        provider = SSOProvider(name='corp', provider_type='oauth2', oauth2_issuer=here)
        assert _another_idp(provider, {'name': 'corp', 'oauth2_issuer': archived}) is other


@pytest.mark.parametrize('mode', ['replace', 'merge'])
def test_an_unreadable_issuer_on_both_sides_restores_in_place(target, mode):
    corp = SSOProvider(name='corp', provider_type='oauth2', enabled=False, default_role='viewer',
                       oauth2_issuer=UNREADABLE)
    db.session.add(corp)
    db.session.commit()
    results = _restore({'sso_providers': [{'name': 'corp', 'provider_type': 'oauth2',
                                           'display_name': 'Corp', 'oauth2_issuer': UNREADABLE}]},
                       mode)
    db.session.expire_all()
    assert not [w for w in results['warnings'] if w.startswith('sso_providers:')]
    assert SSOProvider.query.filter_by(provider_type='oauth2').one().id == corp.id


@pytest.mark.parametrize('kind', sorted(IDPS))
def test_a_merge_that_leaves_the_provider_out_still_carried_it(target, kind):
    from services.backup.restore_report import restore_audit_details
    _instance(kind)
    archive = _archive('3.0', kind, IDPS[kind][2], 'kate-sub-b')
    results = _restore({'sso_providers': archive['sso_providers']}, 'merge')
    # Carried: the job revokes the sessions and restarts, and never answers "carried no data"
    assert any('is not restored' in w for w in results['warnings']), results['warnings']
    assert results['sections_carried'] == ['sso_providers']
    assert 'carried no data' not in restore_audit_details('a.ucmbkp', results)

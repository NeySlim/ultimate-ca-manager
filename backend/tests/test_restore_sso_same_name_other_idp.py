"""A restore never leaves an account bound under one IdP answering to another IdP.

An archived SSO provider is found here by its name. When the provider of that
name here talks to another IdP (OIDC issuer, SAML entity ID, LDAP server and
base DN), rewriting it in place would hand the accounts it bound to that IdP's
subjects (OIDC Core 5.7: a `sub` is unique per issuer only). A replacement
therefore treats it as another provider, whose accounts here become orphans of
their IdP; a merge keeps the provider here and leaves the archived one out.
"""
import uuid

import pytest

from models import db
from tests.fresh_app import fresh_app_fixtures
from tests.test_backup_cross_installation import PASSWORD, _only, _service
from tests.test_restore_replace_dependents import ENGINES, _target

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

NAME = 'corp'

# The IdP here (A), the same IdP written otherwise, and another IdP (B), per type.
IDPS = {
    'oauth2': {
        'A': {'oauth2_issuer': 'https://idp-a.example.test/realms/corp'},
        'A_respelled': {'oauth2_issuer': 'HTTPS://IDP-A.Example.Test/realms/corp/ '},
        'B': {'oauth2_issuer': 'https://idp-b.example.test/realms/corp'},
    },
    'saml': {
        'A': {'saml_entity_id': 'https://idp-a.example.test/saml'},
        'A_respelled': {'saml_entity_id': '  https://idp-a.example.test/saml '},
        'B': {'saml_entity_id': 'https://idp-b.example.test/saml'},
    },
    'ldap': {
        'A': {'ldap_server': 'ldap://dc-a.example.test', 'ldap_base_dn': 'dc=a,dc=test'},
        'A_respelled': {'ldap_server': 'LDAP://DC-A.Example.Test',
                                'ldap_base_dn': 'DC=A,DC=TEST'},
        'B': {'ldap_server': 'ldap://dc-b.example.test', 'ldap_base_dn': 'dc=b,dc=test'},
    },
}

KEY_OF = {
    'oauth2': {'A': 'oauth2:https://idp-a.example.test/realms/corp',
               'B': 'oauth2:https://idp-b.example.test/realms/corp'},
    'saml': {'A': 'saml:https://idp-a.example.test/saml',
             'B': 'saml:https://idp-b.example.test/saml'},
    'ldap': {'A': 'ldap:ldap://dc-a.example.test|dc=a,dc=test',
             'B': 'ldap:ldap://dc-b.example.test|dc=b,dc=test'},
}


@pytest.fixture(params=ENGINES)
def target(request, app, tmp_path):
    schema = f'sso_other_idp_{uuid.uuid4().hex[:12]}'
    with _target(app, request.param, tmp_path, schema):
        yield request.param


def _provider(kind, idp):
    from models.sso import SSOProvider
    provider = SSOProvider(name=NAME, provider_type=kind, enabled=True, **IDPS[kind][idp])
    db.session.add(provider)
    db.session.flush()
    return provider


def _account(username, provider=None, subject=None):
    from models import User
    user = User(username=username, email=f'{username}@example.test', password_hash='x' * 32,
                role='viewer', active=True,
                auth_source=provider.provider_type if provider else 'local',
                sso_provider_id=provider.id if provider else None, sso_external_id=subject)
    db.session.add(user)
    db.session.flush()
    return user


def _archive(kind, idp, scope):
    """The archive: provider `corp` for `idp`, kate and mona bound by it."""
    provider = _provider(kind, idp)
    _account('kate', provider, 'kate-archived')
    _account('mona', provider, 'mona-archived')
    sections = ('users', 'sso_providers') if scope == 'accounts' else ('sso_providers',)
    db.session.commit()
    return _service().create_backup(PASSWORD, include=_only(*sections))


def _instance(kind):
    """This installation before the restore: `corp` for A, kate and nina bound by it, liam local."""
    from models import User
    from models.sso import SSOProvider
    User.query.filter(User.username.in_(['kate', 'mona'])).delete(synchronize_session=False)
    SSOProvider.query.delete()
    db.session.flush()
    provider = _provider(kind, 'A')
    _account('kate', provider, 'kate-a')
    _account('nina', provider, 'nina-a')
    _account('liam')
    db.session.commit()


def _restore(blob, mode):
    results = _service().restore_backup(blob, PASSWORD, mode=mode)
    db.session.expire_all()
    return results


def _bindings():
    """username -> (provider name, sso_external_id, sso_orphan_of), None when gone."""
    from models import User
    from models.sso import SSOProvider
    found = {}
    for username in ('kate', 'mona', 'nina', 'liam'):
        user = User.query.filter_by(username=username).first()
        if user is None:
            found[username] = None
            continue
        provider = db.session.get(SSOProvider, user.sso_provider_id) if user.sso_provider_id else None
        found[username] = (provider.name if provider else None, user.sso_external_id,
                           user.sso_orphan_of)
    return found


def _sso_warnings(results):
    return [w for w in results.get('warnings') or [] if w.startswith('sso_providers:')]


def _config(kind):
    from models.sso import SSOProvider
    provider = SSOProvider.query.filter_by(name=NAME).one()
    return {field: getattr(provider, field) for field in IDPS[kind]['A']}


def _expected(mode, scope, kind, relation):
    """(bindings, provider configuration, warned) a restore must leave."""
    other = relation == 'B'
    arch = IDPS[kind][relation]
    kate_here, nina_here = (NAME, 'kate-a', None), (NAME, 'nina-a', None)
    liam = (None, None, None)
    kate_arch, mona_arch = (NAME, 'kate-archived', None), (NAME, 'mona-archived', None)
    if mode == 'replace' and scope == 'accounts':
        # The archive is the accounts: nina and liam go, kate and mona as the archive binds them
        return ({'kate': kate_arch, 'mona': mona_arch, 'nina': None, 'liam': None}, arch, other)
    if mode == 'replace':
        # The provider alone: an account it bound under A is an orphan of A, never bound to B
        if other:
            a = KEY_OF[kind]['A']
            return ({'kate': (None, 'kate-a', a), 'mona': None, 'nina': (None, 'nina-a', a),
                     'liam': liam}, arch, True)
        return ({'kate': kate_here, 'mona': None, 'nina': nina_here, 'liam': liam}, arch, False)
    if scope == 'accounts':
        if other:
            # The provider here stays A; the archive's accounts come back as orphans of B
            b = KEY_OF[kind]['B']
            return ({'kate': (None, 'kate-archived', b), 'mona': (None, 'mona-archived', b),
                     'nina': nina_here, 'liam': liam}, IDPS[kind]['A'], True)
        return ({'kate': kate_arch, 'mona': mona_arch, 'nina': nina_here, 'liam': liam},
                arch, False)
    if other:
        return ({'kate': kate_here, 'mona': None, 'nina': nina_here, 'liam': liam},
                IDPS[kind]['A'], True)
    return ({'kate': kate_here, 'mona': None, 'nina': nina_here, 'liam': liam}, arch, False)


@pytest.mark.parametrize('relation', ['A', 'A_respelled', 'B'])
@pytest.mark.parametrize('kind', ['oauth2', 'saml', 'ldap'])
@pytest.mark.parametrize('scope', ['accounts', 'provider'])
@pytest.mark.parametrize('mode', ['replace', 'merge'])
def test_accounts_never_follow_their_provider_to_another_idp(target, mode, scope, kind, relation):
    blob = _archive(kind, relation, scope)
    _instance(kind)

    results = _restore(blob, mode)

    bindings, config, warned = _expected(mode, scope, kind, relation)
    assert _bindings() == bindings
    assert _config(kind) == config
    warnings = _sso_warnings(results)
    if warned:
        assert len(warnings) == 1 and repr(NAME) in warnings[0], warnings
    else:
        assert warnings == []


def _presented(kind, subject):
    if kind == 'oauth2':
        return {'sub': subject}
    if kind == 'saml':
        return {'name_id': subject,
                'name_id_format': 'urn:oasis:names:tc:SAML:2.0:nameid-format:persistent'}
    return {'uid': subject}


@pytest.mark.parametrize('kind', ['oauth2', 'saml', 'ldap'])
@pytest.mark.parametrize('scope', ['accounts', 'provider'])
def test_the_subject_of_kate_at_a_never_opens_her_account_through_b(target, scope, kind):
    from api.v2.sso.ldap_routes import _resolve_sso_account
    from models.sso import SSOProvider
    blob = _archive(kind, 'B', scope)
    _instance(kind)

    _restore(blob, 'replace')

    provider = SSOProvider.query.filter_by(name=NAME).one()
    assert provider.idp_key() == KEY_OF[kind]['B']
    for username in ('kate', 'nina'):
        account, _rebind, _conflict, _owner, _unverified = _resolve_sso_account(
            provider, username, f'{username}@example.test',
            _presented(kind, f'{username}-a'))
        assert account is None, f'{username} at A opened through B'


@pytest.mark.parametrize('here, archived, other', [
    ({'oauth2_issuer': 'https://Idp.Example.Test/realms/X'},
     {'oauth2_issuer': 'https://idp.example.test/realms/X/'}, False),
    # The path of an issuer is compared as written (RFC 3986 6.2.2.1 lowers scheme and host only)
    ({'oauth2_issuer': 'https://idp.example.test/realms/X'},
     {'oauth2_issuer': 'https://idp.example.test/realms/x'}, True),
    ({}, {}, False),                                            # unknown on both sides
    ({'oauth2_issuer': 'https://idp.example.test'}, {'oauth2_issuer': None}, True),
    ({'oauth2_issuer': 'https://idp.example.test'}, {}, False),  # not carried: kept here
    ({'oauth2_issuer': 'https://idp.example.test'}, {'provider_type': 'saml'}, True),
])
def test_what_counts_as_another_idp(app, here, archived, other):
    from models.sso import SSOProvider
    from services.backup.restore.sso_providers import another_idp
    with app.app_context():
        provider = SSOProvider(name=NAME, provider_type='oauth2', **here)
        assert another_idp(provider, {'name': NAME, **archived}) is other


@pytest.mark.parametrize('kind', ['oauth2', 'saml', 'ldap'])
@pytest.mark.parametrize('mode', ['replace', 'merge'])
def test_accounts_without_their_provider_in_the_archive_are_named(target, mode, kind):
    """Accounts restored without their provider bind by name to the one here: the report says so."""
    from models.sso import SSOProvider
    provider = _provider(kind, 'B')
    _account('kate', provider, 'kate-archived')
    _account('mona', provider, 'mona-archived')
    db.session.commit()
    blob = _service().create_backup(PASSWORD, include=_only('users'))
    _instance(kind)

    results = _restore(blob, mode)

    here = SSOProvider.query.filter_by(name=NAME).one()
    assert here.idp_key() == KEY_OF[kind]['A']
    warnings = _sso_warnings(results)
    assert len(warnings) == 1, warnings
    assert all(part in warnings[0] for part in (repr(NAME), 'kate', 'mona')), warnings


@pytest.mark.parametrize('kind', ['oauth2', 'saml', 'ldap'])
@pytest.mark.parametrize('mode', ['replace', 'merge'])
def test_accounts_of_another_installation_without_their_provider_are_unbound(target, mode, kind):
    """From another installation the provider of that name here is unchecked: nobody binds to it."""
    from api.v2.sso.ldap_routes import _resolve_sso_account
    from models import SystemConfig, User
    from models.sso import SSOProvider
    from services.backup import installation
    provider = _provider(kind, 'B')
    _account('kate', provider, 'kate-archived')
    _account('mona', provider, 'mona-archived')
    db.session.commit()
    blob = _service().create_backup(PASSWORD, include=_only('users'))
    _instance(kind)
    # This database is now another installation than the archive's
    SystemConfig.query.filter_by(key=installation.CONFIG_KEY).one().value = uuid.uuid4().hex
    db.session.commit()

    results = _restore(blob, mode)

    here = SSOProvider.query.filter_by(name=NAME).one()
    assert here.idp_key() == KEY_OF[kind]['A']
    mona = User.query.filter_by(username='mona').one()
    assert (mona.sso_provider_id, mona.sso_external_id) == (None, 'mona-archived')
    assert User.query.filter_by(sso_provider_id=here.id, sso_external_id='kate-archived').count() == 0
    account, _rebind, _conflict, _owner, _unverified = _resolve_sso_account(
        here, 'whoever', 'whoever@example.test', _presented(kind, 'mona-archived'))
    assert account is None, 'mona at B opened through A'
    warnings = _sso_warnings(results)
    assert len(warnings) == 1, warnings
    assert all(part in warnings[0] for part in (repr(NAME), 'kate', 'mona', 'without')), warnings

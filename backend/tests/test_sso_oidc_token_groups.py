"""OIDC role mapping reads the groups and roles of the ID token the login validated.

Microsoft Entra ID's UserInfo endpoint never returns ``groups`` nor ``roles``:
they only exist in the ID token. The groups of a login are those of its ID
token (same ``sub``, same nonce) and of its UserInfo response, nothing else.
"""
from tests.sso_identity_support import users_of
import base64
import json
import logging
import time
import uuid

import pytest

from models import db, User
from models.sso import SSOProvider, SSOSession


def _unsigned_token(claims):
    def seg(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b'=').decode()
    return f"{seg({'alg': 'RS256', 'kid': 'k'})}.{seg(claims)}.c2ln"


def _cleanup(names):
    from api.v2.users.crud import _purge_user_dependencies

    for (user_id,) in User.query.filter(User.username.in_(names)).with_entities(User.id).all():
        _purge_user_dependencies(user_id)
    User.query.filter(User.username.in_(names)).delete(synchronize_session=False)
    db.session.commit()


@pytest.fixture
def entra(app, monkeypatch):
    """The only enabled OAuth2 provider. With verification on, ``verify_id_token``
    returns ``claims`` as validated; off, the real decoder reads an unsigned token."""
    from api.v2.sso import login_routes

    with app.app_context():
        others = [(p.id, p.enabled) for p in SSOProvider.query.filter_by(provider_type='oauth2').all()]
        for pid, _ in others:
            db.session.get(SSOProvider, pid).enabled = False
        row = SSOProvider(
            name=f'entra-{uuid.uuid4().hex[:6]}', provider_type='oauth2', enabled=True,
            oauth2_client_id='ucm-client', oauth2_client_secret='secret',
            oauth2_auth_url='https://idp.example/authorize',
            oauth2_token_url='https://idp.example/token',
            oauth2_userinfo_url='https://idp.example/userinfo',
            oauth2_issuer='https://idp.example', id_token_verify=True,
            auto_create_users=True, default_role='viewer',
            role_mapping='{"grp-oid-admins": "admin", "UCM.Operator": "operator"}',
        )
        db.session.add(row)
        db.session.commit()
        pid = row.id

    state = {'userinfo': {}, 'claims': {}}

    class Resp:
        ok = True
        text = ''

        def __init__(self, body):
            self._body = body

        def json(self):
            return self._body

    monkeypatch.setattr(login_routes, 'safe_request_post', lambda *_a, **_k: Resp(
        {'access_token': 'at', 'id_token': _unsigned_token(state['claims'])}
        if state['claims'] is not None else {'access_token': 'at'}))
    monkeypatch.setattr(login_routes, 'safe_request_get', lambda *_a, **_k: Resp(state['userinfo']))
    real_verify = login_routes.verify_id_token

    def fake_verify(id_token, provider, nonce, verify=True, ssl_verify=True):
        if not verify:
            return real_verify(id_token, provider, nonce, verify=False, ssl_verify=ssl_verify)
        return dict(state['claims'])
    monkeypatch.setattr(login_routes, 'verify_id_token', fake_verify)

    def configure(**fields):
        with app.app_context():
            row = db.session.get(SSOProvider, pid)
            for key, val in fields.items():
                setattr(row, key, val)
            db.session.commit()

    def login(userinfo, claims, nonce='n'):
        state['userinfo'] = dict(userinfo)
        state['claims'] = None if claims is None else dict(claims, nonce='n')
        client = app.test_client()
        with client.session_transaction() as s:
            s['sso_state'] = 'st'
            s['sso_pkce_verifier'] = 'v'
            if nonce:
                s['sso_nonce'] = nonce
        r = client.get('/api/v2/sso/callback/oauth2?state=st&code=c')
        assert r.status_code == 302
        return r.headers['Location']

    def role_of(username):
        with app.app_context():
            user = User.query.filter_by(username=username).first()
            return user.role if user else None

    login.configure = configure
    login.role_of = role_of
    yield login
    with app.app_context():
        SSOSession.query.filter_by(provider_id=pid).delete()
        _cleanup([u.username for u in users_of(pid).all()])
        db.session.delete(db.session.get(SSOProvider, pid))
        for opid, enabled in others:
            db.session.get(SSOProvider, opid).enabled = enabled
        db.session.commit()


OK = '/login/sso-complete'
UNMAPPED = '/login?error=sso_unmapped'


def test_groups_of_the_id_token_admit_when_userinfo_has_none(entra):
    loc = entra({'sub': 's1', 'preferred_username': 'entra1'},
                {'sub': 's1', 'groups': ['grp-oid-admins']})
    assert loc.endswith(OK)
    assert entra.role_of('entra1') == 'admin'


def test_app_roles_of_the_id_token_admit(entra):
    loc = entra({'sub': 's2', 'preferred_username': 'entra2'},
                {'sub': 's2', 'roles': ['UCM.Operator']})
    assert loc.endswith(OK)
    assert entra.role_of('entra2') == 'operator'


def test_an_empty_roles_claim_does_not_hide_groups(entra):
    loc = entra({'sub': 's3', 'preferred_username': 'entra3'},
                {'sub': 's3', 'roles': [], 'groups': ['grp-oid-admins']})
    assert loc.endswith(OK)
    assert entra.role_of('entra3') == 'admin'


def test_userinfo_and_token_groups_are_joined(entra):
    loc = entra({'sub': 's4', 'preferred_username': 'entra4', 'groups': ['UCM.Operator']},
                {'sub': 's4', 'groups': ['unrelated']})
    assert loc.endswith(OK)
    assert entra.role_of('entra4') == 'operator'


def test_no_groups_anywhere_is_still_refused(entra):
    loc = entra({'sub': 's5', 'preferred_username': 'entra5'}, {'sub': 's5'})
    assert loc.endswith(UNMAPPED)
    assert entra.role_of('entra5') is None


def test_subject_mismatch_is_refused_before_anything_is_read(entra):
    loc = entra({'sub': 'userinfo-sub', 'preferred_username': 'entra6'},
                {'sub': 'token-sub', 'groups': ['grp-oid-admins']})
    assert '/login?error=' in loc and not loc.endswith(OK)
    assert entra.role_of('entra6') is None


def _valid_claims(sub, **extra):
    now = int(time.time())
    return dict({'sub': sub, 'iss': 'https://idp.example', 'aud': 'ucm-client',
                 'iat': now, 'exp': now + 300}, **extra)


def test_unverified_token_groups_are_read_when_its_claims_are_valid(entra):
    # OIDC Core §3.1.3.7 (6): only the signature may give way to TLS; steps 2, 3, 9 hold.
    entra.configure(id_token_verify=False)
    loc = entra({'sub': 's7', 'preferred_username': 'entra7'},
                _valid_claims('s7', groups=['grp-oid-admins']))
    assert loc.endswith(OK)
    assert entra.role_of('entra7') == 'admin'


@pytest.mark.parametrize('bad', [
    {'aud': 'another-client'},
    {'iss': 'https://evil.example'},
    {'exp': 1},
    {'aud': ['ucm-client', 'other'], 'azp': 'other'},
], ids=['aud', 'iss', 'exp', 'azp'])
def test_unverified_token_with_invalid_claims_gives_no_groups(entra, bad):
    entra.configure(id_token_verify=False)
    name = f"zz-{'-'.join(bad)}"
    loc = entra({'sub': 'z1', 'preferred_username': name},
                _valid_claims('z1', groups=['grp-oid-admins'], **bad))
    assert loc.endswith(UNMAPPED)
    assert entra.role_of(name) is None


@pytest.mark.parametrize('config, iss', [
    ({'oauth2_issuer': ''}, ''),
    ({'oauth2_issuer': None}, None),
    ({'oauth2_client_id': ''}, 'https://idp.example'),
    ({}, None),
], ids=['issuer-empty', 'issuer-none', 'client-id-empty', 'token-without-iss'])
def test_unverified_token_needs_issuer_and_client_id(entra, config, iss):
    # OIDC Core §3.1.3.7 step 2: the configured issuer MUST exactly match iss.
    entra.configure(id_token_verify=False, **config)
    name = f'zi-{uuid.uuid4().hex[:6]}'
    claims = _valid_claims('zi', groups=['grp-oid-admins'], iss=iss)
    if iss is None:
        claims.pop('iss')
    loc = entra({'sub': 'zi', 'preferred_username': name}, claims)
    assert loc.endswith(UNMAPPED)
    assert entra.role_of(name) is None


def test_unverified_claims_need_a_configured_issuer_and_client_id():
    from types import SimpleNamespace
    from services.oidc_id_token import unverified_claims_are_valid

    def check(issuer, client_id, **claims):
        provider = SimpleNamespace(oauth2_issuer=issuer, oauth2_client_id=client_id)
        token = dict(_valid_claims('u', nonce='n'), **claims)
        return unverified_claims_are_valid(token, provider, 'n')

    assert check('https://idp.example', 'ucm-client')
    assert not check(None, 'ucm-client', iss=None)
    assert not check('', 'ucm-client', iss='')
    assert not check('https://idp.example', '', aud='')
    assert not check('https://idp.example', None, aud=None)
    assert not check('https://idp.example', 'ucm-client', sub='')


def test_unverified_token_without_tls_verification_gives_no_groups(entra):
    entra.configure(id_token_verify=False, oauth2_verify_ssl=False)
    loc = entra({'sub': 's13', 'preferred_username': 'entra13'},
                _valid_claims('s13', groups=['grp-oid-admins']))
    assert loc.endswith(UNMAPPED)
    assert entra.role_of('entra13') is None


def test_unverified_token_from_a_plain_http_token_endpoint_gives_no_groups(entra):
    """OIDC Core 3.1.3.7 step 6: only TLS server validation stands in for the signature."""
    entra.configure(id_token_verify=False, oauth2_token_url='http://idp.example/token')
    loc = entra({'sub': 's15', 'preferred_username': 'entra15'},
                _valid_claims('s15', groups=['grp-oid-admins']))
    assert loc.endswith(UNMAPPED)
    assert entra.role_of('entra15') is None


def test_unverified_token_still_feeds_groups_from_userinfo(entra):
    entra.configure(id_token_verify=False, oauth2_verify_ssl=False)
    loc = entra({'sub': 's14', 'preferred_username': 'entra14', 'groups': ['UCM.Operator']},
                {'sub': 's14', 'aud': 'another-client', 'groups': ['grp-oid-admins']})
    assert loc.endswith(OK)
    assert entra.role_of('entra14') == 'operator'


def test_unverified_token_of_another_subject_gives_no_groups(entra):
    entra.configure(id_token_verify=False)
    loc = entra({'sub': 's8', 'preferred_username': 'entra8'},
                _valid_claims('someone-else', groups=['grp-oid-admins']))
    assert loc.endswith(UNMAPPED)
    assert entra.role_of('entra8') is None


def test_unverified_token_without_a_session_nonce_gives_no_groups(entra):
    entra.configure(id_token_verify=False)
    loc = entra({'sub': 's12', 'preferred_username': 'entra12'},
                _valid_claims('s12', groups=['grp-oid-admins']), nonce=None)
    assert loc.endswith(UNMAPPED)
    assert entra.role_of('entra12') is None


@pytest.mark.parametrize('verified', [True, False], ids=['verified', 'unverified'])
def test_token_and_userinfo_without_subject_give_no_token_groups(entra, verified):
    # None == None is no binding: the token groups need a subject equal to UserInfo's.
    entra.configure(id_token_verify=verified)
    name = f'nosub-{verified}'
    claims = _valid_claims('x', groups=['grp-oid-admins'])
    claims.pop('sub')
    loc = entra({'preferred_username': name}, claims)
    assert loc.endswith(UNMAPPED)
    assert entra.role_of(name) is None


def test_entra_groups_overage_is_reported_and_refused(entra, caplog):
    with caplog.at_level(logging.WARNING):
        loc = entra({'sub': 's9', 'preferred_username': 'entra9'},
                    {'sub': 's9', '_claim_names': {'groups': 'src1'},
                     '_claim_sources': {'src1': {'endpoint': 'https://graph.example/x'}}})
    assert loc.endswith(UNMAPPED)
    assert 'too many groups' in caplog.text


def test_source_and_count_are_logged_without_token_values(entra, caplog):
    with caplog.at_level(logging.INFO, logger='api.v2.sso.helpers'):
        loc = entra({'sub': 's10', 'preferred_username': 'entra10', 'groups': ['UCM.Operator']},
                    {'sub': 's10', 'groups': ['grp-oid-admins', 'grp-secret-x']})
    assert loc.endswith(OK)
    line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith('OIDC groups'))
    assert 'ID token (2' in line and 'UserInfo (1' in line
    assert 'grp-secret-x' not in line


def test_role_sync_on_login_follows_token_groups(entra):
    entra.configure(sync_role_on_login=True)
    assert entra({'sub': 's11', 'preferred_username': 'entra11'},
                 {'sub': 's11', 'roles': ['UCM.Operator']}).endswith(OK)
    assert entra.role_of('entra11') == 'operator'
    assert entra({'sub': 's11', 'preferred_username': 'entra11'},
                 {'sub': 's11', 'groups': ['grp-oid-admins']}).endswith(OK)
    assert entra.role_of('entra11') == 'admin'


def test_external_groups_join_roles_and_groups():
    from api.v2.sso.helpers import _external_groups

    assert _external_groups({'roles': [], 'groups': ['a']}) == ['a']
    assert _external_groups({'roles': ['r'], 'groups': ['a', 'r']}) == ['r', 'a']
    assert _external_groups({'groups': 'solo'}) == ['solo']
    assert _external_groups(None) == []


def _groups_line(caplog):
    return next(r.getMessage() for r in caplog.records
                if r.getMessage().startswith('OIDC groups'))


@pytest.mark.parametrize('config, userinfo, claims, nonce, reason', [
    ({}, {'sub': 'r1'}, None, 'n', 'no ID token'),
    ({}, {'sub': 'r2'}, _valid_claims('other'), 'n', 'subject does not match UserInfo'),
    ({}, {}, {k: v for k, v in _valid_claims('x').items() if k != 'sub'}, 'n',
     'subject does not match UserInfo'),
    ({'oauth2_verify_ssl': False}, {'sub': 'r4'}, _valid_claims('r4'), 'n',
     'unverified and TLS verification is off'),
    ({'oauth2_token_url': 'http://idp.example/token'}, {'sub': 'r8'}, _valid_claims('r8'), 'n',
     'unverified and the token endpoint is not HTTPS'),
    ({}, {'sub': 'r5'}, _valid_claims('r5', iss='https://evil.example'), 'n',
     'unverified token rejected (ID token issuer mismatch)'),
    ({'oauth2_issuer': None}, {'sub': 'r6'}, _valid_claims('r6'), 'n',
     'unverified token rejected (OIDC issuer is not configured)'),
    ({}, {'sub': 'r7'}, _valid_claims('r7'), None,
     'unverified token rejected (no session nonce)'),
], ids=['no-token', 'other-sub', 'no-sub', 'tls-off', 'http-token', 'bad-iss', 'no-issuer', 'no-nonce'])
def test_log_says_why_the_id_token_was_not_used(entra, caplog, config, userinfo, claims,
                                                nonce, reason):
    entra.configure(id_token_verify=False, **config)
    if claims is not None:
        # The cases are built at collection: their times are set when the test runs
        now = int(time.time())
        claims = dict(claims, groups=['grp-secret-x'], iat=now, exp=now + 300)
    with caplog.at_level(logging.INFO, logger='api.v2.sso.helpers'):
        entra(dict(userinfo, preferred_username=f'log-{uuid.uuid4().hex[:6]}',
                   groups=['UCM.Operator']), claims, nonce=nonce)
    line = _groups_line(caplog)
    assert line == f'OIDC groups read from UserInfo (1 value(s)); ID token not used: {reason}'


# ---- SSO-04: the refusal says what was read, a mapping row to groups is applied ------

REMEDY = 'add a role mapping rule for one of these values, or set a default role'


def _refusal(app, username):
    from models import AuditLog
    with app.app_context():
        row = AuditLog.query.filter_by(action='login_failure', resource_name=username).one()
        return row.details


def _name():
    return f'diag-{uuid.uuid4().hex[:8]}'


def test_refusal_names_the_groups_read_and_their_source(app, entra, caplog):
    name = _name()
    with caplog.at_level(logging.WARNING, logger='api.v2.sso'):
        loc = entra({'sub': 'd1', 'preferred_username': name, 'groups': ['ui-team']},
                    {'sub': 'd1', 'groups': ['tk-team']})
    assert loc.endswith(UNMAPPED)
    details = _refusal(app, name)
    assert "no role mapping rule matches it" in details
    assert "groups read from the ID token and UserInfo, claims 'roles', 'groups': " \
           "'tk-team', 'ui-team'" in details
    assert details.endswith(REMEDY)
    assert details in caplog.text  # the WARNING line says the same


def test_refusal_says_why_the_token_was_not_used(app, entra):
    entra.configure(id_token_verify=False)
    name = _name()
    loc = entra({'sub': 'd2', 'preferred_username': name}, None)
    assert loc.endswith(UNMAPPED)
    details = _refusal(app, name)
    assert "no group value was read from UserInfo, claims 'roles', 'groups' " \
           "(ID token not used: no ID token)" in details


def test_refusal_with_nothing_read_lists_the_claim_names_never_their_values(app, entra, caplog):
    """The 16/11/2026 case: groups where UCM does not look. Names only, bounded."""
    name = _name()
    with caplog.at_level(logging.DEBUG):
        loc = entra({'sub': 'd3', 'preferred_username': name, 'email': 'SENTINEL-MAIL@x',
                     'name': 'SENTINEL-NAME', 'phone_number': 'SENTINEL-PHONE'},
                    {'sub': 'd3', 'realm_access': {'roles': ['SENTINEL-REALM-ROLE']},
                     'entitlements': ['SENTINEL-LIST'], 'given_name': 'SENTINEL-GIVEN',
                     'x_member_of': 'SENTINEL-MEMBER'})
    assert loc.endswith(UNMAPPED)
    details = _refusal(app, name)
    assert ("received claims that may carry groups: 'realm_access.roles', 'entitlements', "
            "'x_member_of': map one of them to groups in the attribute mapping") in details
    assert 'SENTINEL' not in details
    assert 'SENTINEL' not in caplog.text


def test_refusal_without_rules_nor_default_role_carries_the_diagnosis(app, entra):
    entra.configure(role_mapping=None, default_role=None)
    name = _name()
    loc = entra({'sub': 'd4', 'preferred_username': name}, {'sub': 'd4', 'groups': ['g1']})
    assert loc.endswith('/login?error=sso_no_default_role')
    details = _refusal(app, name)
    assert 'no role mapping rule and no default role' in details
    assert "'g1'" in details and details.endswith(REMEDY)


def test_refusal_values_are_bounded_and_one_line(app, entra, caplog):
    name = _name()
    groups = [f'g{i:03d}\nforged' for i in range(200)]
    with caplog.at_level(logging.INFO):
        loc = entra({'sub': 'd5', 'preferred_username': name}, {'sub': 'd5', 'groups': groups})
    assert loc.endswith(UNMAPPED)
    details = _refusal(app, name)
    assert '\n' not in details and '(+180 more)' in details
    assert all('\nforged' not in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize('claim, claims', [
    ('realm_access.roles', {'realm_access': {'roles': ['grp-oid-admins']}}),
    ('resource_access.ucm-client.roles',
     {'resource_access': {'ucm-client': {'roles': ['grp-oid-admins']}}}),
    ('https://example.com/groups', {'https://example.com/groups': ['grp-oid-admins']}),
], ids=['keycloak-realm', 'keycloak-client', 'uri'])
def test_a_claim_mapped_to_groups_is_read(entra, claim, claims):
    entra.configure(attribute_mapping=json.dumps({claim: 'groups'}))
    name = _name()
    assert entra({'sub': 'm1', 'preferred_username': name}, dict(claims, sub='m1')).endswith(OK)
    assert entra.role_of(name) == 'admin'


def test_a_claim_mapped_to_groups_is_read_from_userinfo(entra):
    entra.configure(attribute_mapping=json.dumps({'realm_access.roles': 'groups'}),
                    id_token_verify=False)
    name = _name()
    assert entra({'sub': 'm2', 'preferred_username': name,
                  'realm_access': {'roles': ['UCM.Operator']}}, None).endswith(OK)
    assert entra.role_of(name) == 'operator'


def test_the_exact_claim_name_wins_over_the_dotted_path(entra):
    entra.configure(attribute_mapping=json.dumps({'a.b': 'groups'}))
    name = _name()
    assert entra({'sub': 'm3', 'preferred_username': name},
                 {'sub': 'm3', 'a.b': ['UCM.Operator'], 'a': {'b': ['grp-oid-admins']}}
                 ).endswith(OK)
    assert entra.role_of(name) == 'operator'


def test_a_claim_mapped_to_groups_replaces_roles_and_groups(app, entra):
    entra.configure(attribute_mapping=json.dumps({'team': 'groups'}))
    name = _name()
    loc = entra({'sub': 'm4', 'preferred_username': name, 'roles': ['UCM.Operator']},
                {'sub': 'm4', 'groups': ['grp-oid-admins'], 'roles': ['UCM.Operator']})
    assert loc.endswith(UNMAPPED)
    assert "no group value was read from the ID token and UserInfo, claim 'team'" \
        in _refusal(app, name)


def test_a_mapped_claim_that_is_no_string_list_gives_no_group(entra):
    entra.configure(attribute_mapping=json.dumps({'team': 'groups'}))
    name = _name()
    assert entra({'sub': 'm5', 'preferred_username': name},
                 {'sub': 'm5', 'team': ['grp-oid-admins', 7]}).endswith(UNMAPPED)


def test_a_mapped_claim_keeps_the_token_trust_rules(entra):
    """Rien ne s'assouplit: a token of another subject gives no group, mapped or not."""
    entra.configure(attribute_mapping=json.dumps({'realm_access.roles': 'groups'}),
                    id_token_verify=False)
    name = _name()
    assert entra({'sub': 'm6', 'preferred_username': name},
                 _valid_claims('other', realm_access={'roles': ['grp-oid-admins']})
                 ).endswith(UNMAPPED)


def test_without_a_row_to_groups_the_log_line_is_unchanged(entra, caplog):
    entra.configure(attribute_mapping=json.dumps({'preferred_username': 'username'}))
    with caplog.at_level(logging.INFO, logger='api.v2.sso.helpers'):
        loc = entra({'sub': 'm7', 'preferred_username': _name(), 'groups': ['UCM.Operator']},
                    {'sub': 'm7', 'roles': ['grp-oid-admins']})
    assert loc.endswith(OK)
    assert _groups_line(caplog) == 'OIDC groups read from ID token (1 value(s)), UserInfo (1 value(s))'

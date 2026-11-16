"""OIDC role mapping reads the groups and roles of the ID token the login validated.

Microsoft Entra ID's UserInfo endpoint never returns ``groups`` nor ``roles``:
they only exist in the ID token. The groups of a login are those of its ID
token (same ``sub``, same nonce) and of its UserInfo response, nothing else.
"""
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
        {'access_token': 'at', 'id_token': _unsigned_token(state['claims'])}))
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
        state['claims'] = dict(claims, nonce='n')
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
        _cleanup([u.username for u in User.query.filter_by(sso_provider_id=pid).all()])
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
        return unverified_claims_are_valid(_valid_claims('u', nonce='n', **claims), provider, 'n')

    assert check('https://idp.example', 'ucm-client')
    assert not check(None, 'ucm-client', iss=None)
    assert not check('', 'ucm-client', iss='')
    assert not check('https://idp.example', '', aud='')
    assert not check('https://idp.example', None, aud=None)


def test_unverified_token_without_tls_verification_gives_no_groups(entra):
    entra.configure(id_token_verify=False, oauth2_verify_ssl=False)
    loc = entra({'sub': 's13', 'preferred_username': 'entra13'},
                _valid_claims('s13', groups=['grp-oid-admins']))
    assert loc.endswith(UNMAPPED)
    assert entra.role_of('entra13') is None


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

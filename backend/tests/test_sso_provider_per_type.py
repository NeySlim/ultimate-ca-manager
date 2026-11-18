"""One SSO provider per type, and the defence when a database holds two anyway.

The schema holds the rule (uq_pro_sso_providers_provider_type, step 165). Each sign-in still picks
by id, and an OIDC return or a SAML ACS is answered by the provider its start noted, never by
another of the type. The cases with two providers of a type lift the index for their duration.
"""
import os
import threading
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from api.v2.sso import login_routes, saml_sp
from models import db
from models.sso import SAMLMessageId, SSOProvider, SSOSession
from tests.sso_identity_support import several_per_type, step_aside


def _add(provider_type, enabled=True, **fields):
    row = SSOProvider(name=f'per-type-{provider_type}-{uuid.uuid4().hex[:8]}', provider_type=provider_type,
                      enabled=enabled, oauth2_client_id='c', oauth2_auth_url='https://idp.example/authorize',
                      saml_sso_url='https://idp.example/sso', saml_entity_id='https://idp.example',
                      ldap_server='ldap.example.test', **fields)
    db.session.add(row)
    db.session.commit()
    return row.id


def _drop(*ids):
    for pid in ids:
        SSOSession.query.filter_by(provider_id=pid).delete()
        SAMLMessageId.query.filter_by(provider_id=pid).delete()
        row = db.session.get(SSOProvider, pid)
        if row is not None:
            db.session.delete(row)
    db.session.commit()


@pytest.fixture
def two_of_a_type(app):
    """``make(type, enabled)`` adds a provider; two of one type are allowed until the test ends."""
    made, asides = [], {}

    def make(provider_type, enabled=True, **fields):
        with app.app_context():
            if provider_type not in asides:
                asides[provider_type] = step_aside(provider_type)
            made.append(_add(provider_type, enabled, **fields))
            return made[-1]

    with several_per_type(app):
        yield make
        with app.app_context():
            _drop(*made)
            for aside in asides.values():
                aside.back()


def _enable(app, pid, enabled):
    with app.app_context():
        db.session.get(SSOProvider, pid).enabled = enabled
        db.session.commit()


# --- The schema ---------------------------------------------------------------------------------

def test_the_database_refuses_a_second_provider_of_a_type(app):
    with app.app_context():
        aside = step_aside('ldap')
        first = _add('ldap', enabled=False)
        try:
            with pytest.raises(IntegrityError):
                _add('ldap', enabled=False)
            db.session.rollback()
        finally:
            _drop(first)
            aside.back()


# --- Each sign-in picks by id -------------------------------------------------------------------

def test_the_provider_of_a_type_is_the_lowest_enabled_id(app, two_of_a_type):
    first, second = two_of_a_type('oauth2'), two_of_a_type('oauth2')
    with app.app_context():
        assert login_routes.login_provider('oauth2').id == first
        # An update does not move it: PostgreSQL may return rows in another order afterwards
        db.session.get(SSOProvider, first).display_name = 'touched'
        db.session.commit()
        assert login_routes.login_provider('oauth2').id == first
    _enable(app, first, False)
    with app.app_context():
        assert login_routes.login_provider('oauth2').id == second


# --- OIDC: the return is answered by the provider its start noted --------------------------------

@pytest.fixture
def answered_by(monkeypatch):
    """The provider ids the token exchange was reached with; the IdP's answer is then refused."""
    seen = []

    def sign_in(provider, *_args):
        seen.append(provider.id)
        return None, login_routes.Refusal('stop-here')

    monkeypatch.setattr(login_routes, 'oidc_sign_in', sign_in)
    return seen


def _start_oidc(client):
    response = client.get('/api/v2/sso/login/oauth2')
    assert response.status_code == 302, response.get_data(as_text=True)
    with client.session_transaction() as s:
        return s['sso_state'], s['sso_provider_id']


def _return_oidc(client, state):
    response = client.get('/api/v2/sso/callback/oauth2', query_string={'state': state, 'code': 'c'})
    assert response.status_code == 302
    return response.headers['Location']


def test_an_oidc_return_is_answered_by_the_provider_its_start_noted(app, two_of_a_type, answered_by):
    first = two_of_a_type('oauth2', enabled=False)
    second = two_of_a_type('oauth2')
    client = app.test_client()
    state, noted = _start_oidc(client)
    assert noted == second
    # The lower id is enabled meanwhile: a new login would take it, this return does not
    _enable(app, first, True)
    assert 'error=stop-here' in _return_oidc(client, state)
    assert answered_by == [second]


@pytest.mark.parametrize('change', ['deleted', 'disabled', 'retyped'])
def test_an_oidc_return_whose_provider_is_gone_is_refused_not_rerouted(app, two_of_a_type, answered_by,
                                                                      change):
    first = two_of_a_type('oauth2', enabled=False)
    second = two_of_a_type('oauth2')
    client = app.test_client()
    state, _noted = _start_oidc(client)
    _enable(app, first, True)
    with app.app_context():
        if change == 'deleted':
            _drop(second)
        elif change == 'disabled':
            db.session.get(SSOProvider, second).enabled = False
        else:
            db.session.get(SSOProvider, second).provider_type = 'saml'
        db.session.commit()
    assert _return_oidc(client, state).endswith('/login?error=provider_not_found')
    assert answered_by == []


def test_an_oidc_return_without_a_noted_provider_is_refused(app, two_of_a_type, answered_by):
    two_of_a_type('oauth2')
    client = app.test_client()
    state, _noted = _start_oidc(client)
    with client.session_transaction() as s:
        s.pop('sso_provider_id')
    assert _return_oidc(client, state).endswith('/login?error=provider_not_found')
    assert answered_by == []


# --- SAML: the ACS is answered by the provider of the AuthnRequest -------------------------------

@pytest.fixture
def saml_answered_by(monkeypatch):
    seen = []
    monkeypatch.setattr(login_routes, '_get_saml_auth', lambda _request, provider, *a, **k: provider)

    def validate(provider, _auth, _request_id):
        seen.append(provider.id)
        return login_routes.Refusal('stop-here')

    monkeypatch.setattr(login_routes, 'saml_validate', validate)
    return seen


def _acs(app, request_id):
    client = app.test_client()
    client.set_cookie(saml_sp.REQUEST_COOKIE, request_id)
    response = client.post('/api/v2/sso/callback/saml', data={'SAMLResponse': 'x'})
    assert response.status_code == 302
    return response.headers['Location']


def _authn_request(app, pid):
    request_id = f'id-{uuid.uuid4().hex}'
    with app.app_context():
        saml_sp.remember_request(request_id, pid)
    return request_id


def test_a_saml_response_is_answered_by_the_provider_of_its_request(app, two_of_a_type, saml_answered_by):
    first = two_of_a_type('saml')
    second = two_of_a_type('saml')
    assert 'error=stop-here' in _acs(app, _authn_request(app, second))
    assert saml_answered_by == [second]
    # A response with no request of this browser is the IdP's own: the provider of the type answers
    assert 'error=stop-here' in _acs(app, '')
    assert saml_answered_by == [second, first]


@pytest.mark.parametrize('change', ['deleted', 'disabled'])
def test_a_saml_response_whose_provider_is_gone_is_refused_not_rerouted(app, two_of_a_type, saml_answered_by,
                                                                       change):
    two_of_a_type('saml')
    second = two_of_a_type('saml')
    request_id = _authn_request(app, second)
    with app.app_context():
        if change == 'deleted':
            # The request row stays, as on a node that had not purged it yet
            row = db.session.get(SSOProvider, second)
            db.session.delete(row)
        else:
            db.session.get(SSOProvider, second).enabled = False
        db.session.commit()
    assert _acs(app, request_id).endswith('/login?error=provider_not_found')
    assert saml_answered_by == []


def _acs_response(app, request_id):
    client = app.test_client()
    if request_id:
        client.set_cookie(saml_sp.REQUEST_COOKIE, request_id)
    response = client.post('/api/v2/sso/callback/saml', data={'SAMLResponse': 'x'})
    assert response.status_code == 302
    cleared = any(h.startswith(f'{saml_sp.REQUEST_COOKIE}=;') and 'Max-Age=0' in h
                  for h in response.headers.getlist('Set-Cookie'))
    return response.headers['Location'], cleared


def test_a_refused_saml_response_of_a_gone_provider_drops_its_request_cookie(app, two_of_a_type,
                                                                              saml_answered_by):
    """The browser is not held to provider_not_found until the request expires."""
    first = two_of_a_type('saml')
    second = two_of_a_type('saml')
    request_id = _authn_request(app, second)
    with app.app_context():
        db.session.delete(db.session.get(SSOProvider, second))  # its request row stays
        db.session.commit()
    location, cleared = _acs_response(app, request_id)
    assert location.endswith('/login?error=provider_not_found') and cleared
    assert saml_answered_by == []
    # Without the cookie, the next response is the IdP's own, answered by the provider of the type
    assert 'error=stop-here' in _acs_response(app, None)[0]
    assert saml_answered_by == [first]


def test_a_deleted_saml_provider_takes_its_pending_requests_with_it(app, auth_client, saml_answered_by):
    """A provider created after it, under the same number or not, never answers its requests."""
    with app.app_context():
        aside = step_aside('saml')
        old = _add('saml')
    created = []
    try:
        request_id = _authn_request(app, old)
        assert auth_client.delete(f'/api/v2/sso/providers/{old}').status_code == 200
        with app.app_context():
            assert SAMLMessageId.query.filter_by(provider_id=old, kind=SAMLMessageId.KIND_REQUEST).count() == 0
            created.append(_add('saml'))
        location, cleared = _acs_response(app, request_id)
        assert 'error=saml_login_expired' in location and cleared
        assert saml_answered_by == []
    finally:
        with app.app_context():
            _drop(old, *created)
            aside.back()


# --- LDAP: a provider named by id is an LDAP provider -------------------------------------------

def test_an_ldap_login_naming_another_type_is_refused(app, two_of_a_type):
    oidc = two_of_a_type('oauth2')
    response = app.test_client().post('/api/v2/sso/ldap/login',
                                      json={'username': 'nobody', 'password': 'x', 'provider_id': oidc})
    assert response.status_code == 400
    assert 'No LDAP provider configured' in response.get_data(as_text=True)


# --- API ----------------------------------------------------------------------------------------

def test_an_update_never_changes_the_type(app, auth_client):
    with app.app_context():
        asides = [step_aside('oauth2'), step_aside('saml')]
        oidc = _add('oauth2', enabled=False)
        saml = _add('saml', enabled=False)
    try:
        response = auth_client.put(f'/api/v2/sso/providers/{oidc}', json={'provider_type': 'saml'})
        assert response.status_code == 200, response.get_data(as_text=True)
        with app.app_context():
            assert db.session.get(SSOProvider, oidc).provider_type == 'oauth2'
    finally:
        with app.app_context():
            _drop(oidc, saml)
            for aside in asides:
                aside.back()


def _concurrent_creations(app, monkeypatch):
    """Two creations of one type, both past the type check before either commits."""
    from api.v2.sso import providers as routes
    both = threading.Barrier(2, timeout=20)
    checked = routes._validate_sso_outbound_urls

    def after_the_check(data):
        both.wait()
        return checked(data)

    monkeypatch.setattr(routes, '_validate_sso_outbound_urls', after_the_check)
    monkeypatch.setattr(routes.AuditService, 'log_action', lambda **_kw: None)
    answers = []

    def create(name):
        try:
            with app.test_request_context('/api/v2/sso/providers', method='POST',
                                          json={'name': name, 'provider_type': 'ldap'}):
                response = app.make_response(routes.create_provider.__wrapped__())
                answers.append((response.status_code, response.get_json()))
                db.session.remove()
        except Exception as exc:  # noqa: BLE001
            answers.append(repr(exc))

    workers = [threading.Thread(target=create, args=(f'race-{n}',)) for n in 'ab']
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(60)
    assert sorted(a[0] for a in answers) == [200, 400], answers
    refused = next(body for code, body in answers if code == 400)
    assert 'A LDAP provider already exists. Only one provider per type is allowed.' in str(refused), refused
    with app.app_context():
        assert SSOProvider.query.filter_by(provider_type='ldap').count() == 1
        db.session.remove()


def test_two_concurrent_creations_of_a_type_on_sqlite(app, monkeypatch, tmp_path):
    from tests.test_backup_cross_installation import _bound_to
    with _bound_to(app, f"sqlite:///{tmp_path / 'race.db'}"):
        _concurrent_creations(app, monkeypatch)


@pytest.mark.postgres
@pytest.mark.skipif(not os.environ.get('UCM_TEST_PG_URL'), reason='UCM_TEST_PG_URL not set')
def test_two_concurrent_creations_of_a_type_on_postgresql(app, monkeypatch):
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own
    with _a_schema_of_our_own(f'sso_race_{uuid.uuid4().hex[:6]}') as url, \
            _bound_to(app, url, is_postgresql=True):
        _concurrent_creations(app, monkeypatch)

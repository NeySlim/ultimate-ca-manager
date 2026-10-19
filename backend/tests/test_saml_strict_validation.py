"""SAML responses go through the whole callback and are checked strictly.

Audience, Destination, validity window, InResponseTo against the AuthnRequest
this browser started, IdP-initiated opt-in and the replay cache.
"""
import base64
import os
import datetime
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from onelogin.saml2.constants import OneLogin_Saml2_Constants as K
from onelogin.saml2.utils import OneLogin_Saml2_Utils

from api.v2.sso import saml_sp
from models import db, User
from models.sso import SSOProvider, SSOSession

IDP_ENTITY = 'https://idp.example.test/saml'
SP_BASE = 'https://ucm.example.test'
ACS = saml_sp.ACS_PATH
OK = '/login/sso-complete'
REFUSED = '/login?error=saml_validation_failed'


@pytest.fixture(scope='module')
def idp_signer():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'idp.example.test')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(serialization.Encoding.PEM,
                                serialization.PrivateFormat.TraditionalOpenSSL,
                                serialization.NoEncryption()).decode()
    return key_pem, cert.public_bytes(serialization.Encoding.PEM).decode()


@pytest.fixture(scope='module')
def _module_provider(app, idp_signer):
    """The only enabled SAML provider while this module runs, removed afterwards."""
    with app.app_context():
        others = SSOProvider.query.filter_by(provider_type='saml', enabled=True).all()
        other_ids = [p.id for p in others]
        for p in others:
            p.enabled = False
        row = SSOProvider(
            name=f'strict-saml-{uuid.uuid4().hex[:8]}', provider_type='saml', enabled=True,
            saml_entity_id=IDP_ENTITY, saml_sso_url='https://idp.example.test/sso',
            saml_certificate=idp_signer[1], auto_create_users=True, default_role='viewer',
        )
        db.session.add(row)
        db.session.commit()
        provider_id = row.id
    yield provider_id
    with app.app_context():
        SSOSession.query.filter_by(provider_id=provider_id).delete()
        User.query.filter_by(sso_provider_id=provider_id).update({'sso_provider_id': None})
        db.session.delete(db.session.get(SSOProvider, provider_id))
        for pid in other_ids:
            db.session.get(SSOProvider, pid).enabled = True
        db.session.commit()


@pytest.fixture
def provider(app, _module_provider, monkeypatch):
    monkeypatch.setattr(saml_sp, 'get_admin_base_url', lambda: None)
    _set_idp_initiated(app, _module_provider, False)
    return _module_provider


def _set_idp_initiated(app, provider_id, allowed):
    with app.app_context():
        db.session.get(SSOProvider, provider_id).saml_allow_idp_initiated = allowed
        db.session.commit()


def _ts(delta_minutes=0):
    t = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=delta_minutes)
    return t.strftime('%Y-%m-%dT%H:%M:%SZ')


def _response(idp_signer, *, in_response_to=None, sp_base=SP_BASE, audience=None,
              destination=None, issued=0, expires=5, assertion_id=None, name_id=None,
              scd_expiry=True):
    irt = f' InResponseTo="{in_response_to}"' if in_response_to else ''
    destination = destination or f'{sp_base}{ACS}'
    audience = audience or f'{sp_base}{saml_sp.ENTITY_PATH}'
    assertion_id = assertion_id or f'_a{uuid.uuid4().hex}'
    name_id = name_id or f'saml-{uuid.uuid4().hex[:12]}'
    scd_nooa = f' NotOnOrAfter="{_ts(expires)}"' if scd_expiry else ''
    xml = f'''<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
 xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" ID="_r{uuid.uuid4().hex}" Version="2.0"
 IssueInstant="{_ts(issued)}" Destination="{destination}"{irt}>
 <saml:Issuer>{IDP_ENTITY}</saml:Issuer>
 <samlp:Status><samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>
 <saml:Assertion ID="{assertion_id}" Version="2.0" IssueInstant="{_ts(issued)}">
  <saml:Issuer>{IDP_ENTITY}</saml:Issuer>
  <saml:Subject>
   <saml:NameID Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">{name_id}</saml:NameID>
   <saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
    <saml:SubjectConfirmationData{scd_nooa} Recipient="{destination}"{irt}/>
   </saml:SubjectConfirmation>
  </saml:Subject>
  <saml:Conditions NotBefore="{_ts(issued)}" NotOnOrAfter="{_ts(expires)}">
   <saml:AudienceRestriction><saml:Audience>{audience}</saml:Audience></saml:AudienceRestriction>
  </saml:Conditions>
  <saml:AuthnStatement AuthnInstant="{_ts(issued)}" SessionIndex="_s1">
   <saml:AuthnContext><saml:AuthnContextClassRef>urn:oasis:names:tc:SAML:2.0:ac:classes:Password</saml:AuthnContextClassRef></saml:AuthnContext>
  </saml:AuthnStatement>
 </saml:Assertion>
</samlp:Response>'''
    signed = OneLogin_Saml2_Utils.add_sign(xml, idp_signer[0], idp_signer[1],
                                           sign_algorithm=K.RSA_SHA256, digest_algorithm=K.SHA256)
    return base64.b64encode(signed).decode()


def _start_login(client, base=SP_BASE):
    r = client.get('/api/v2/sso/login/saml', base_url=base)
    assert r.status_code == 302, r.get_data(as_text=True)
    assert 'SAMLRequest=' in r.headers['Location']
    host = base.split('://', 1)[1].split(':')[0]
    cookie = client.get_cookie(saml_sp.REQUEST_COOKIE, domain=host, path=ACS)
    assert cookie is not None
    return cookie.value


def _post(client, saml_response, base=SP_BASE):
    r = client.post(ACS, base_url=base, data={'SAMLResponse': saml_response})
    assert r.status_code == 302
    return r.headers['Location']


def _refused(caplog, client, saml_response, reason, base=SP_BASE):
    """Refused, and for the stated reason rather than an earlier one."""
    caplog.clear()
    with caplog.at_level('ERROR'):
        assert _post(client, saml_response, base) == REFUSED
    assert reason in caplog.text, caplog.text


def test_sp_initiated_login_is_accepted(app, provider, idp_signer):
    client = app.test_client()
    request_id = _start_login(client)
    assert _post(client, _response(idp_signer, in_response_to=request_id)) == OK


def test_request_cookie_is_cross_site_and_cleared(app, provider):
    client = app.test_client()
    r = client.get('/api/v2/sso/login/saml', base_url=SP_BASE)
    header = next(h for h in r.headers.getlist('Set-Cookie') if h.startswith(saml_sp.REQUEST_COOKIE))
    assert 'SameSite=None' in header and 'Secure' in header and 'HttpOnly' in header
    r = client.post(ACS, base_url=SP_BASE, data={'SAMLResponse': 'x'})
    cleared = [h for h in r.headers.getlist('Set-Cookie') if h.startswith(saml_sp.REQUEST_COOKIE)]
    assert cleared and 'Max-Age=0' in cleared[0]


def test_assertion_for_another_audience_is_refused(app, provider, idp_signer, caplog):
    client = app.test_client()
    request_id = _start_login(client)
    resp = _response(idp_signer, in_response_to=request_id,
                     audience='https://other-sp.example.test/saml')
    _refused(caplog, client, resp, 'is not a valid audience')


def test_wrong_destination_is_refused(app, provider, idp_signer, caplog):
    client = app.test_client()
    request_id = _start_login(client)
    resp = _response(idp_signer, in_response_to=request_id,
                     destination='https://other-sp.example.test/acs')
    _refused(caplog, client, resp, 'The response was received at')


def test_expired_assertion_is_refused(app, provider, idp_signer, caplog):
    client = app.test_client()
    request_id = _start_login(client)
    resp = _response(idp_signer, in_response_to=request_id, issued=-30, expires=-20)
    _refused(caplog, client, resp, 'Could not validate timestamp: expired')


def test_bearer_confirmation_without_expiry_is_refused(app, provider, idp_signer, caplog):
    # The replay cache needs an end date; the Web SSO profile makes it mandatory.
    client = app.test_client()
    request_id = _start_login(client)
    resp = _response(idp_signer, in_response_to=request_id, scd_expiry=False)
    _refused(caplog, client, resp, 'SubjectConfirmationData has no NotOnOrAfter')


def test_unknown_in_response_to_is_refused(app, provider, idp_signer, caplog):
    # Even with IdP-initiated login allowed: a solicited response needs the request.
    _set_idp_initiated(app, provider, True)
    resp = _response(idp_signer, in_response_to='_never_issued')
    _refused(caplog, app.test_client(), resp, 'InResponseTo matches no AuthnRequest')


def test_in_response_to_of_another_request_is_refused(app, provider, idp_signer, caplog):
    client = app.test_client()
    _start_login(client)
    other = app.test_client()
    other_id = _start_login(other)
    _refused(caplog, client, _response(idp_signer, in_response_to=other_id),
             'does not match the ID of the AuthNRequest')


def test_forged_request_cookie_is_refused(app, provider, idp_signer, caplog):
    client = app.test_client()
    client.set_cookie(saml_sp.REQUEST_COOKIE, '_forged', domain='ucm.example.test', path=ACS)
    _refused(caplog, client, _response(idp_signer, in_response_to='_forged'),
             'unknown, expired or already used AuthnRequest')


def test_sp_initiated_response_cannot_be_posted_twice(app, provider, idp_signer):
    client = app.test_client()
    request_id = _start_login(client)
    resp = _response(idp_signer, in_response_to=request_id)
    assert _post(client, resp) == OK
    client.set_cookie(saml_sp.REQUEST_COOKIE, request_id, domain='ucm.example.test', path=ACS)
    assert _post(client, resp) == REFUSED


def test_idp_initiated_is_refused_by_default(app, provider, idp_signer, caplog):
    _refused(caplog, app.test_client(), _response(idp_signer), 'IdP-initiated login is disabled')


def test_idp_initiated_opt_in_accepts_once(app, provider, idp_signer, caplog):
    _set_idp_initiated(app, provider, True)
    resp = _response(idp_signer)
    assert _post(app.test_client(), resp) == OK
    _refused(caplog, app.test_client(), resp, 'assertion already consumed')


def test_replay_cache_is_shared_through_the_database(app, provider):
    with app.app_context():
        later = (datetime.datetime.now(datetime.timezone.utc)
                 + datetime.timedelta(minutes=5)).timestamp()
        assertion_id = f'_a{uuid.uuid4().hex}'
        assert saml_sp.consume_assertion(assertion_id, provider, later)
        assert not saml_sp.consume_assertion(assertion_id, provider, later)


def test_destination_follows_configured_base_url_behind_proxy(app, provider, idp_signer, monkeypatch):
    # The request reaches UCM under an internal origin; the IdP knows the public one.
    monkeypatch.setattr(saml_sp, 'get_admin_base_url', lambda: SP_BASE)
    monkeypatch.setattr(saml_sp, 'get_admin_canonical_origin', lambda: SP_BASE)
    internal = 'https://ucm-backend.internal:8443'
    client = app.test_client()
    r = client.get('/api/v2/sso/login/saml', base_url=internal)
    assert r.status_code == 302
    request_id = client.get_cookie(saml_sp.REQUEST_COOKIE, domain='ucm-backend.internal', path=ACS)
    assert request_id is not None
    resp = _response(idp_signer, in_response_to=request_id.value, sp_base=SP_BASE)
    assert _post(client, resp, base=internal) == OK


def test_destination_keeps_the_path_prefix(app, provider, idp_signer):
    # X-Forwarded-Prefix (or a SCRIPT_NAME) puts UCM under a sub-path.
    base = f'{SP_BASE}/pki'
    client = app.test_client()
    r = client.get('/api/v2/sso/login/saml', base_url=base)
    cookie = client.get_cookie(saml_sp.REQUEST_COOKIE, domain='ucm.example.test', path=f'/pki{ACS}')
    assert r.status_code == 302 and cookie is not None
    resp = _response(idp_signer, in_response_to=cookie.value, sp_base=base)
    assert _post(client, resp, base=base) == OK


def test_sp_base_keeps_request_origin_on_the_canonical_host(app, monkeypatch):
    monkeypatch.setattr(saml_sp, 'get_admin_base_url', lambda: 'https://ucm.example.test')
    monkeypatch.setattr(saml_sp, 'get_admin_canonical_origin', lambda: 'https://ucm.example.test:8443')
    with app.test_request_context('/', base_url='https://ucm.example.test'):
        from flask import request
        assert saml_sp.sp_base_url(request) == 'https://ucm.example.test'
    with app.test_request_context('/', base_url='https://10.0.0.5:8443'):
        from flask import request
        assert saml_sp.sp_base_url(request) == 'https://ucm.example.test:8443'


def test_idp_initiated_option_is_saved_and_returned(auth_client, provider):
    for wanted in (True, False):
        r = auth_client.put(f'/api/v2/sso/providers/{provider}', json={'saml_allow_idp_initiated': wanted})
        assert r.status_code == 200, r.get_data(as_text=True)
        r = auth_client.get(f'/api/v2/sso/providers/{provider}')
        assert r.get_json()['data']['saml_allow_idp_initiated'] is wanted


@pytest.mark.postgres
@pytest.mark.skipif(not os.getenv('UCM_TEST_PG_URL'), reason='UCM_TEST_PG_URL not set')
def test_message_ids_on_postgresql(monkeypatch):
    from types import SimpleNamespace
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from models.sso import SAMLMessageId
    schema = f"saml_{os.getenv('PYTEST_XDIST_WORKER', 'main')}_{uuid.uuid4().hex[:6]}"
    admin = create_engine(os.environ['UCM_TEST_PG_URL'])
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(os.environ['UCM_TEST_PG_URL'],
                           connect_args={'options': f'-csearch_path={schema}'})
    session = Session(engine)
    try:
        SAMLMessageId.__table__.create(engine)
        monkeypatch.setattr(saml_sp, 'db', SimpleNamespace(session=session))
        later = (datetime.datetime.now(datetime.timezone.utc)
                 + datetime.timedelta(minutes=5)).timestamp()
        assert saml_sp.consume_assertion('_a1', 1, later)
        assert not saml_sp.consume_assertion('_a1', 1, later)
        saml_sp.remember_request('_r1', 1)
        assert not saml_sp.take_request('_r1', 2)
        assert saml_sp.take_request('_r1', 1)
        assert not saml_sp.take_request('_r1', 1)
        earlier = (datetime.datetime.now(datetime.timezone.utc)
                   - datetime.timedelta(hours=1)).timestamp()
        assert saml_sp.consume_assertion('_old', 1, earlier)
        saml_sp.remember_request('_r2', 1)  # purges what expired
        ids = {r[0] for r in session.execute(text('SELECT message_id FROM pro_sso_saml_message_ids'))}
        assert ids == {'_a1', '_r2'}
    finally:
        session.close()
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        admin.dispose()

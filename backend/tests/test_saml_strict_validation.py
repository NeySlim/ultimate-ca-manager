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
    # No configured origin: the SP origin follows each test's request.
    monkeypatch.setattr(saml_sp, 'get_admin_base_url', lambda: None)
    monkeypatch.setattr(saml_sp, 'get_admin_canonical_origin', lambda: None)
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


def _cookie_headers(r):
    return [h for h in r.headers.getlist('Set-Cookie') if h.startswith(saml_sp.REQUEST_COOKIE)]


def test_request_cookie_is_cross_site_and_cleared_by_the_login(app, provider, idp_signer):
    client = app.test_client()
    r = client.get('/api/v2/sso/login/saml', base_url=SP_BASE)
    header = _cookie_headers(r)[0]
    assert 'SameSite=None' in header and 'Secure' in header and 'HttpOnly' in header
    request_id = client.get_cookie(saml_sp.REQUEST_COOKIE, domain='ucm.example.test', path=ACS).value
    r = client.post(ACS, base_url=SP_BASE, data={'SAMLResponse': _response(idp_signer, in_response_to=request_id)})
    assert r.headers['Location'] == OK
    cleared = _cookie_headers(r)
    assert cleared and 'Max-Age=0' in cleared[0]


def test_a_forged_post_does_not_spoil_the_pending_login(app, provider, idp_signer):
    # A cross-site POST lands in the victim's browser before the IdP answers.
    client = app.test_client()
    request_id = _start_login(client)
    r = client.post(ACS, base_url=SP_BASE, data={'SAMLResponse': 'x'})
    assert r.headers['Location'] == REFUSED and not _cookie_headers(r)
    forged = _response(idp_signer, in_response_to=request_id, audience='https://other-sp.example.test/saml')
    assert _post(client, forged) == REFUSED
    assert _post(client, _response(idp_signer, in_response_to=request_id)) == OK


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


def _sp_base(app, base):
    from flask import request
    with app.test_request_context('/', base_url=base):
        return saml_sp.sp_base_url(request)


def test_sp_base_keeps_request_port_on_the_canonical_host(app, monkeypatch):
    monkeypatch.setattr(saml_sp, 'get_admin_base_url', lambda: 'https://ucm.example.test')
    monkeypatch.setattr(saml_sp, 'get_admin_canonical_origin', lambda: 'https://ucm.example.test:8443')
    assert _sp_base(app, 'https://ucm.example.test') == 'https://ucm.example.test'
    assert _sp_base(app, 'https://10.0.0.5:8443') == 'https://ucm.example.test:8443'


def test_sp_base_takes_the_scheme_of_the_base_url(app, monkeypatch):
    # A TLS proxy that keeps Host but is not declared: UCM sees http.
    monkeypatch.setattr(saml_sp, 'get_admin_base_url', lambda: 'https://ucm.example.test')
    monkeypatch.setattr(saml_sp, 'get_admin_canonical_origin', lambda: 'https://ucm.example.test:8443')
    assert _sp_base(app, 'http://ucm.example.test') == 'https://ucm.example.test'


def test_sp_base_follows_the_fqdn_without_base_url(app, monkeypatch):
    monkeypatch.setattr(saml_sp, 'get_admin_base_url', lambda: None)
    monkeypatch.setattr(saml_sp, 'get_admin_canonical_origin', lambda: 'https://ucm.example.test:8443')
    monkeypatch.delenv('UCM_FQDN', raising=False)
    monkeypatch.setenv('FQDN', 'ucm.example.test')
    assert _sp_base(app, 'https://forged.example') == 'https://ucm.example.test:8443'
    # A canonical host guessed from the machine name is not a configuration.
    monkeypatch.setenv('FQDN', 'other.example.test')
    assert _sp_base(app, 'https://forged.example') == 'https://forged.example'


def test_forged_host_cannot_borrow_another_sp_identity(app, provider, idp_signer, monkeypatch, caplog):
    # A response the IdP issued to another SP, posted with that SP's Host.
    monkeypatch.setattr(saml_sp, 'get_admin_canonical_origin', lambda: SP_BASE)
    monkeypatch.delenv('UCM_FQDN', raising=False)
    monkeypatch.setenv('FQDN', 'ucm.example.test')
    _set_idp_initiated(app, provider, True)
    other = 'https://other-sp.example.test'
    _refused(caplog, app.test_client(), _response(idp_signer, sp_base=other),
             'The response was received at', base=other)


def test_sp_info_reports_whether_the_origin_is_configured(app, auth_client, monkeypatch):
    monkeypatch.setattr(saml_sp, 'get_admin_base_url', lambda: None)
    monkeypatch.setattr(saml_sp, 'get_admin_canonical_origin', lambda: None)
    data = auth_client.get('/api/v2/sso/saml/sp-info').get_json()['data']
    assert data['origin_configured'] is False
    monkeypatch.setattr(saml_sp, 'get_admin_base_url', lambda: SP_BASE)
    monkeypatch.setattr(saml_sp, 'get_admin_canonical_origin', lambda: SP_BASE)
    data = auth_client.get('/api/v2/sso/saml/sp-info').get_json()['data']
    assert data['origin_configured'] is True
    assert data['entity_id'] == f'{SP_BASE}/api/v2/sso' and data['acs_url'] == f'{SP_BASE}{ACS}'


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
        assert saml_sp.request_pending('_r1', 1) and not saml_sp.request_pending('_r1', 2)
        assert not saml_sp.take_request('_r1', 2)
        assert saml_sp.take_request('_r1', 1)
        assert not saml_sp.take_request('_r1', 1)
        assert not saml_sp.request_pending('_r1', 1)
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


# ---- AuthnRequest signing (saml_sign_requests) ----

def _keypair(kind):
    from cryptography.hazmat.primitives.asymmetric import ec
    key = (rsa.generate_private_key(public_exponent=65537, key_size=2048) if kind == 'rsa'
           else ec.generate_private_key(ec.SECP256R1()))
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'ucm.example.test')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=1)).sign(key, hashes.SHA256()))
    return key, cert


@pytest.fixture
def https_identity(tmp_path, monkeypatch):
    """Point the HTTPS certificate and key at a fresh pair of the given kind."""
    from config.settings import Config

    def _install(kind='rsa'):
        key, cert = _keypair(kind)
        cert_path, key_path = tmp_path / f'{kind}.crt', tmp_path / f'{kind}.key'
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                               serialization.PrivateFormat.PKCS8,
                                               serialization.NoEncryption()))
        monkeypatch.setattr(Config, 'HTTPS_CERT_PATH', cert_path)
        monkeypatch.setattr(Config, 'HTTPS_KEY_PATH', key_path)
        return cert
    return _install


def _configure(app, provider_id, **fields):
    with app.app_context():
        row = db.session.get(SSOProvider, provider_id)
        for k, v in fields.items():
            setattr(row, k, v)
        db.session.commit()


def _redirect_query(app):
    r = app.test_client().get('/api/v2/sso/login/saml', base_url=SP_BASE)
    assert r.status_code == 302, r.get_data(as_text=True)
    return r.headers['Location'].split('?', 1)[1]


def _assert_signed_by(query, cert):
    import urllib.parse
    from cryptography.hazmat.primitives.asymmetric import padding
    parts = query.split('&')
    params = dict(p.split('=', 1) for p in parts)
    assert urllib.parse.unquote(params['SigAlg']) == K.RSA_SHA256
    signed = '&'.join(p for p in parts if not p.startswith('Signature='))
    signature = base64.b64decode(urllib.parse.unquote(params['Signature']))
    cert.public_key().verify(signature, signed.encode(), padding.PKCS1v15(), hashes.SHA256())


@pytest.fixture
def signing_off(app, provider):
    yield provider
    _configure(app, provider, saml_sign_requests=False, saml_sp_cert_source='https')


def test_request_is_signed_with_the_https_key(app, signing_off, https_identity):
    cert = https_identity('rsa')
    _configure(app, signing_off, saml_sign_requests=True, saml_sp_cert_source='https')
    _assert_signed_by(_redirect_query(app), cert)


def test_request_is_unsigned_when_the_option_is_off(app, signing_off, https_identity):
    https_identity('rsa')
    query = _redirect_query(app)
    assert 'Signature=' not in query and 'SigAlg=' not in query


def test_request_is_signed_with_a_certificate_held_by_ucm(app, signing_off, create_cert):
    from models import Certificate
    cert_id = create_cert(cn='saml-sp.example.test')['id']
    with app.app_context():
        pem = base64.b64decode(db.session.get(Certificate, cert_id).crt)
    _configure(app, signing_off, saml_sign_requests=True, saml_sp_cert_source=str(cert_id))
    _assert_signed_by(_redirect_query(app), x509.load_pem_x509_certificate(pem))


def test_metadata_advertises_what_the_login_does(app, signing_off, https_identity):
    cert = https_identity('rsa')
    body = ''.join(cert.public_bytes(serialization.Encoding.PEM).decode().splitlines()[1:-1])
    client = app.test_client()
    xml = client.get('/api/v2/sso/saml/metadata', base_url=SP_BASE).get_data(as_text=True)
    assert 'AuthnRequestsSigned="false"' in xml
    _configure(app, signing_off, saml_sign_requests=True)
    xml = client.get('/api/v2/sso/saml/metadata', base_url=SP_BASE).get_data(as_text=True)
    assert 'AuthnRequestsSigned="true"' in xml and body in xml
    assert f'entityID="{SP_BASE}/api/v2/sso"' in xml


def test_a_non_rsa_key_is_refused_when_signing_is_turned_on(app, auth_client, signing_off, https_identity):
    https_identity('ec')
    r = auth_client.put(f'/api/v2/sso/providers/{signing_off}', json={'saml_sign_requests': True})
    assert r.status_code == 400 and 'RSA' in r.get_json()['message']
    with app.app_context():
        assert db.session.get(SSOProvider, signing_off).saml_sign_requests is False


def test_a_key_that_does_not_match_the_certificate_is_refused(app, auth_client, signing_off,
                                                             https_identity, tmp_path, monkeypatch):
    from config.settings import Config
    https_identity('rsa')
    other_key, _ = _keypair('rsa')
    stray = tmp_path / 'stray.key'
    stray.write_bytes(other_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                              serialization.NoEncryption()))
    monkeypatch.setattr(Config, 'HTTPS_KEY_PATH', stray)
    r = auth_client.put(f'/api/v2/sso/providers/{signing_off}', json={'saml_sign_requests': True})
    assert r.status_code == 400 and 'does not match' in r.get_json()['message']


# ---- NameID format ----

PERSISTENT = 'urn:oasis:names:tc:SAML:2.0:nameid-format:persistent'


def _authn_request_xml(query):
    import urllib.parse
    import zlib
    params = dict(p.split('=', 1) for p in query.split('&'))
    raw = base64.b64decode(urllib.parse.unquote(params['SAMLRequest']))
    return zlib.decompress(raw, -15).decode()


@pytest.fixture
def name_id_reset(app, provider):
    yield provider
    _configure(app, provider, saml_name_id_format=None)


def test_the_chosen_name_id_format_is_requested_and_published(app, auth_client, name_id_reset):
    r = auth_client.put(f'/api/v2/sso/providers/{name_id_reset}', json={'saml_name_id_format': PERSISTENT})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()['data']['saml_name_id_format'] == PERSISTENT
    assert f'Format="{PERSISTENT}"' in _authn_request_xml(_redirect_query(app))
    xml = app.test_client().get('/api/v2/sso/saml/metadata', base_url=SP_BASE).get_data(as_text=True)
    assert f'<md:NameIDFormat>{PERSISTENT}</md:NameIDFormat>' in xml


def test_unspecified_is_stored_as_the_default(app, auth_client, name_id_reset):
    unspecified = saml_sp.NAMEID_UNSPECIFIED
    r = auth_client.put(f'/api/v2/sso/providers/{name_id_reset}', json={'saml_name_id_format': unspecified})
    assert r.status_code == 200 and r.get_json()['data']['saml_name_id_format'] == ''
    assert f'Format="{unspecified}"' in _authn_request_xml(_redirect_query(app))


def test_an_unknown_name_id_format_is_refused(app, auth_client, name_id_reset):
    r = auth_client.put(f'/api/v2/sso/providers/{name_id_reset}',
                        json={'saml_name_id_format': 'urn:example:not-a-format'})
    assert r.status_code == 400
    with app.app_context():
        assert db.session.get(SSOProvider, name_id_reset).saml_name_id_format is None


def test_fallback_metadata_says_the_same(app, name_id_reset, signing_off, https_identity, monkeypatch):
    from onelogin.saml2.settings import OneLogin_Saml2_Settings

    def _broken(self):
        raise RuntimeError('builder unavailable')
    monkeypatch.setattr(OneLogin_Saml2_Settings, 'get_sp_metadata', _broken)
    https_identity('rsa')
    _configure(app, name_id_reset, saml_name_id_format=PERSISTENT, saml_sign_requests=True)
    xml = app.test_client().get('/api/v2/sso/saml/metadata', base_url=SP_BASE).get_data(as_text=True)
    assert f'<md:NameIDFormat>{PERSISTENT}</md:NameIDFormat>' in xml
    assert 'AuthnRequestsSigned="true"' in xml and 'WantAssertionsSigned="false"' in xml
    assert f'entityID="{SP_BASE}/api/v2/sso"' in xml


def test_a_request_answers_one_login_only(app, provider, idp_signer, caplog):
    # A second, distinct assertion for the same AuthnRequest.
    client = app.test_client()
    request_id = _start_login(client)
    assert _post(client, _response(idp_signer, in_response_to=request_id)) == OK
    client.set_cookie(saml_sp.REQUEST_COOKIE, request_id, domain='ucm.example.test', path=ACS)
    _refused(caplog, client, _response(idp_signer, in_response_to=request_id),
             'unknown, expired or already used AuthnRequest')


def test_an_oversized_assertion_id_is_not_reported_as_a_replay(app, provider, idp_signer, caplog):
    client = app.test_client()
    request_id = _start_login(client)
    resp = _response(idp_signer, in_response_to=request_id, assertion_id='_' + 'a' * 300)
    _refused(caplog, client, resp, 'assertion ID missing or longer than 256 characters')
    assert 'replay' not in caplog.text

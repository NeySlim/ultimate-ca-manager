"""SAML sign-ins against accounts Link to SSO attaches: the remedy works end to end."""
import base64
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
from models.audit_log import AuditLog
from models.sso import SSOProvider, SSOSession

IDP_ENTITY = 'https://idp.review.test/saml'
SP_BASE = 'https://ucm.review.test'
ACS = saml_sp.ACS_PATH
OK = '/login/sso-complete'
NAMEID_PERSISTENT = 'urn:oasis:names:tc:SAML:2.0:nameid-format:persistent'
NAMEID_EMAIL = 'urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress'


@pytest.fixture(scope='module')
def idp_signer():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'idp.review.test')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=1)).sign(key, hashes.SHA256()))
    key_pem = key.private_bytes(serialization.Encoding.PEM,
                                serialization.PrivateFormat.TraditionalOpenSSL,
                                serialization.NoEncryption()).decode()
    return key_pem, cert.public_bytes(serialization.Encoding.PEM).decode()


@pytest.fixture(scope='module')
def provider_id(app, idp_signer):
    with app.app_context():
        others = SSOProvider.query.filter_by(provider_type='saml', enabled=True).all()
        other_ids = [p.id for p in others]
        for p in others:
            p.enabled = False
        row = SSOProvider(
            name=f'review-saml-{uuid.uuid4().hex[:8]}', provider_type='saml', enabled=True,
            saml_entity_id=IDP_ENTITY, saml_sso_url='https://idp.review.test/sso',
            saml_certificate=idp_signer[1], auto_create_users=True, default_role='viewer',
            saml_allow_idp_initiated=True)
        db.session.add(row)
        db.session.commit()
        pid = row.id
    yield pid
    with app.app_context():
        SSOSession.query.filter_by(provider_id=pid).delete()
        User.query.filter_by(sso_provider_id=pid).update({'sso_provider_id': None})
        db.session.delete(db.session.get(SSOProvider, pid))
        for o in other_ids:
            db.session.get(SSOProvider, o).enabled = True
        db.session.commit()


@pytest.fixture
def provider(app, provider_id, monkeypatch):
    monkeypatch.setattr(saml_sp, 'get_admin_base_url', lambda: None)
    monkeypatch.setattr(saml_sp, 'get_admin_canonical_origin', lambda: None)
    yield provider_id
    _configure(app, provider_id, role_mapping=None, attribute_mapping=None)


def _configure(app, pid, **fields):
    with app.app_context():
        row = db.session.get(SSOProvider, pid)
        for k, v in fields.items():
            setattr(row, k, v)
        db.session.commit()


def _ts(delta=0):
    t = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=delta)
    return t.strftime('%Y-%m-%dT%H:%M:%SZ')


def _response(idp_signer, *, in_response_to, name_id, attributes=None, fmt=NAMEID_PERSISTENT):
    irt = f' InResponseTo="{in_response_to}"'
    dest = f'{SP_BASE}{ACS}'
    stmt = ''
    if attributes:
        stmt = '<saml:AttributeStatement>' + ''.join(
            f'<saml:Attribute Name="{n}">'
            + ''.join(f'<saml:AttributeValue>{v}</saml:AttributeValue>' for v in vals)
            + '</saml:Attribute>' for n, vals in attributes.items()) + '</saml:AttributeStatement>'
    xml = f'''<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
 xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" ID="_r{uuid.uuid4().hex}" Version="2.0"
 IssueInstant="{_ts()}" Destination="{dest}"{irt}>
 <saml:Issuer>{IDP_ENTITY}</saml:Issuer>
 <samlp:Status><samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>
 <saml:Assertion ID="_a{uuid.uuid4().hex}" Version="2.0" IssueInstant="{_ts()}">
  <saml:Issuer>{IDP_ENTITY}</saml:Issuer>
  <saml:Subject>
   <saml:NameID Format="{fmt}">{name_id}</saml:NameID>
   <saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
    <saml:SubjectConfirmationData NotOnOrAfter="{_ts(5)}" Recipient="{dest}"{irt}/>
   </saml:SubjectConfirmation>
  </saml:Subject>
  <saml:Conditions NotBefore="{_ts()}" NotOnOrAfter="{_ts(5)}">
   <saml:AudienceRestriction><saml:Audience>{SP_BASE}{saml_sp.ENTITY_PATH}</saml:Audience></saml:AudienceRestriction>
  </saml:Conditions>
  <saml:AuthnStatement AuthnInstant="{_ts()}" SessionIndex="_s1">
   <saml:AuthnContext><saml:AuthnContextClassRef>urn:oasis:names:tc:SAML:2.0:ac:classes:Password</saml:AuthnContextClassRef></saml:AuthnContext>
  </saml:AuthnStatement>
  {stmt}
 </saml:Assertion>
</samlp:Response>'''
    signed = OneLogin_Saml2_Utils.add_sign(xml, idp_signer[0], idp_signer[1],
                                           sign_algorithm=K.RSA_SHA256, digest_algorithm=K.SHA256)
    return base64.b64encode(signed).decode()


def _login(app, idp_signer, name_id, attributes=None, fmt=NAMEID_PERSISTENT, client=None):
    client = client or app.test_client()
    r = client.get('/api/v2/sso/login/saml', base_url=SP_BASE)
    assert r.status_code == 302
    rid = client.get_cookie(saml_sp.REQUEST_COOKIE, domain='ucm.review.test', path=ACS).value
    r = client.post(ACS, base_url=SP_BASE, data={'SAMLResponse': _response(
        idp_signer, in_response_to=rid, name_id=name_id, attributes=attributes, fmt=fmt)})
    assert r.status_code == 302
    return r.headers['Location'], client


def _last_failure(app, username):
    with app.app_context():
        row = (AuditLog.query.filter_by(action='login_failure', resource_name=username)
               .order_by(AuditLog.id.desc()).first())
        return row.details if row else None


def _make_user(app, **fields):
    with app.app_context():
        fields.setdefault('email', f"{fields['username']}@corp.test")
        fields.setdefault('full_name', 'N')
        fields.setdefault('role', 'operator')
        fields.setdefault('active', True)
        fields.setdefault('password_hash', '!SSO_NO_PASSWORD!')
        u = User(**fields)
        db.session.add(u)
        db.session.commit()
        return u.id


def test_saml_account_of_an_unknown_idp_is_refused_with_its_state_and_remedy(app, provider, idp_signer):
    """Deleted provider whose IdP was never recorded: refused, the audit says why and what repairs it."""
    u = f'orph-{uuid.uuid4().hex[:8]}'
    uid = _make_user(app, username=u, auth_source='saml', sso_provider_id=None,
                     sso_external_id=f'nid-{u}', sso_orphan_of=None)
    location, _ = _login(app, idp_signer, f'nid-{u}', {'username': [u]})
    assert location == '/login?error=sso_username_conflict'
    details = _last_failure(app, u)
    assert 'has no provider (its IdP is unknown)' in details and 'Link to SSO attaches it' in details
    with app.app_context():
        assert db.session.get(User, uid).sso_external_id == f'nid-{u}'


def test_name_id_change_is_repaired_by_link_to_sso_alone(app, provider, idp_signer, auth_client):
    """NameID changed at the IdP: Link to SSO resets the identity, no password change is asked."""
    u = f'ren-{uuid.uuid4().hex[:8]}'
    uid = _make_user(app, username=u, auth_source='saml', sso_provider_id=provider,
                     sso_external_id=f'old-{u}@corp.test')
    location, _ = _login(app, idp_signer, f'new-{u}@corp.test', {'username': [u]}, fmt=NAMEID_EMAIL)
    assert location == '/login?error=sso_username_conflict'
    assert 'Link to SSO resets its identity' in _last_failure(app, u)
    r = auth_client.post(f'/api/v2/users/{uid}/link-sso', json={'provider_id': provider})
    assert r.status_code == 200, r.get_json()
    location, client = _login(app, idp_signer, f'new-{u}@corp.test', {'username': [u]}, fmt=NAMEID_EMAIL)
    assert location == OK
    with app.app_context():
        user = db.session.get(User, uid)
        assert user.sso_external_id == f'new-{u}@corp.test'
        assert user.force_password_change is False
    r = client.get('/api/v2/certificates', base_url=SP_BASE)
    assert r.status_code == 200, (r.status_code, r.get_data(as_text=True)[:200])

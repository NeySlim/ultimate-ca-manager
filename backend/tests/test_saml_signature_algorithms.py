"""SAML responses signed with SHA-1 are refused by the service provider."""
import base64
import datetime
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from flask import request
from onelogin.saml2.constants import OneLogin_Saml2_Constants as K
from onelogin.saml2.utils import OneLogin_Saml2_Utils

from api.v2.sso.ldap_routes import _get_saml_auth


IDP_ENTITY = 'https://idp.example.test/saml'
ACS_PATH = '/api/v2/sso/callback/saml'


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


def _response_xml(sp_base):
    now = datetime.datetime.now(datetime.timezone.utc)
    issued = now.strftime('%Y-%m-%dT%H:%M:%SZ')
    later = (now + datetime.timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%SZ')
    return f'''<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
 xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" ID="_resp1" Version="2.0"
 IssueInstant="{issued}" Destination="{sp_base}{ACS_PATH}">
 <saml:Issuer>{IDP_ENTITY}</saml:Issuer>
 <samlp:Status><samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>
 <saml:Assertion ID="_assert1" Version="2.0" IssueInstant="{issued}">
  <saml:Issuer>{IDP_ENTITY}</saml:Issuer>
  <saml:Subject>
   <saml:NameID Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">alice-stable-id</saml:NameID>
   <saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
    <saml:SubjectConfirmationData NotOnOrAfter="{later}" Recipient="{sp_base}{ACS_PATH}"/>
   </saml:SubjectConfirmation>
  </saml:Subject>
  <saml:Conditions NotBefore="{issued}" NotOnOrAfter="{later}">
   <saml:AudienceRestriction><saml:Audience>{sp_base}/api/v2/sso</saml:Audience></saml:AudienceRestriction>
  </saml:Conditions>
  <saml:AuthnStatement AuthnInstant="{issued}" SessionIndex="_s1">
   <saml:AuthnContext><saml:AuthnContextClassRef>urn:oasis:names:tc:SAML:2.0:ac:classes:Password</saml:AuthnContextClassRef></saml:AuthnContext>
  </saml:AuthnStatement>
 </saml:Assertion>
</samlp:Response>'''


def _process(app, idp_signer, sign_algorithm, digest_algorithm):
    key_pem, cert_pem = idp_signer
    sp_base = 'https://ucm.example.test'
    signed = OneLogin_Saml2_Utils.add_sign(_response_xml(sp_base), key_pem, cert_pem,
                                           sign_algorithm=sign_algorithm,
                                           digest_algorithm=digest_algorithm)
    provider = SimpleNamespace(
        saml_entity_id=IDP_ENTITY,
        saml_sso_url='https://idp.example.test/sso',
        saml_slo_url=None,
        saml_certificate=cert_pem,
        saml_name_id_format=None,
    )
    with app.test_request_context(ACS_PATH, base_url=sp_base, method='POST',
                                  data={'SAMLResponse': base64.b64encode(signed).decode()}):
        auth = _get_saml_auth(request, provider)
        auth.process_response()
    return auth


def test_sha256_signed_response_is_accepted(app, idp_signer):
    auth = _process(app, idp_signer, K.RSA_SHA256, K.SHA256)
    assert auth.get_errors() == [], auth.get_last_error_reason()
    assert auth.is_authenticated()
    assert auth.get_nameid() == 'alice-stable-id'


def test_rsa_sha1_signed_response_is_refused(app, idp_signer):
    auth = _process(app, idp_signer, K.RSA_SHA1, K.SHA256)
    assert not auth.is_authenticated()
    assert 'Deprecated signature algorithm' in (auth.get_last_error_reason() or '')


def test_sha1_digest_is_refused(app, idp_signer):
    auth = _process(app, idp_signer, K.RSA_SHA256, K.SHA1)
    assert not auth.is_authenticated()
    assert 'Deprecated digest algorithm' in (auth.get_last_error_reason() or '')


"""SAML service-provider side: public URLs, python3-saml settings, message ids."""

import base64
import logging
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from onelogin.saml2.constants import OneLogin_Saml2_Constants
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from config.settings import Config
from models import Certificate, db
from models.sso import SAMLMessageId
from utils.key_codec import load_pem_bytes
from utils.datetime_utils import utc_now
from utils.public_endpoints import get_admin_base_url, get_admin_canonical_origin

logger = logging.getLogger(__name__)

ENTITY_PATH = '/api/v2/sso'
ACS_PATH = '/api/v2/sso/callback/saml'
NAMEID_UNSPECIFIED = 'urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified'
NAMEID_FORMATS = (
    NAMEID_UNSPECIFIED,
    'urn:oasis:names:tc:SAML:2.0:nameid-format:persistent',
    'urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress',
    'urn:oasis:names:tc:SAML:2.0:nameid-format:transient',
)
BINDING_POST = 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST'
BINDING_REDIRECT = 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect'

REQUEST_COOKIE = 'ucm_saml_request'
REQUEST_TTL = timedelta(minutes=10)
MAX_MESSAGE_ID_LENGTH = 256


def configured_origin():
    """Public origin set by the operator: admin Base URL, else FQDN; None if neither."""
    canonical = get_admin_canonical_origin()
    if not canonical:
        return None
    if get_admin_base_url():
        return canonical.rstrip('/')
    fqdn = (os.getenv('UCM_FQDN') or os.getenv('FQDN') or '').strip().lower()
    return canonical.rstrip('/') if fqdn and urlsplit(canonical).hostname == fqdn else None


def sp_base_url(flask_request):
    """Origin the IdP knows UCM by.

    The configured origin; on its own host the request keeps its port and path
    prefix (a proxy on 443). Nothing configured: the request's origin.
    """
    origin = flask_request.url_root.rstrip('/')
    canonical = configured_origin()
    if not canonical:
        return origin
    want, got = urlsplit(canonical), urlsplit(origin)
    if got.hostname == want.hostname:
        return f'{want.scheme}://{got.netloc}{got.path}'.rstrip('/')
    return canonical


def sp_endpoints(base):
    return {
        'entity_id': f'{base}{ENTITY_PATH}',
        'acs_url': f'{base}{ACS_PATH}',
        'slo_url': f'{base}{ACS_PATH}',
    }


def request_data(flask_request, base):
    """python3-saml view of the request, rebuilt on the public origin so that
    Destination and Recipient are compared with the URL the IdP was given."""
    parts = urlsplit(base)
    https = parts.scheme == 'https'
    host = parts.hostname or ''
    if ':' in host:
        host = f'[{host}]'
    port = parts.port
    if port and port != (443 if https else 80):
        host = f'{host}:{port}'
    return {
        'https': 'on' if https else 'off',
        'http_host': host,
        'script_name': parts.path.rstrip('/') + flask_request.path,
        'get_data': flask_request.args.copy(),
        'post_data': flask_request.form.copy(),
    }


def _first_cert_pem(pem_bytes):
    cert = x509.load_pem_x509_certificate(pem_bytes)
    return cert, cert.public_bytes(serialization.Encoding.PEM).decode()


def load_sp_credentials(provider, with_key=False):
    """SP certificate and, when asked, its key (PEM), from `saml_sp_cert_source`.

    python3-saml signs redirect-binding requests with RSA only: any other key,
    or one that does not match the certificate, raises ValueError.
    """
    source = (getattr(provider, 'saml_sp_cert_source', None) or 'https') if provider else 'https'
    cert = key_pem = None
    if source != 'https':
        row = None
        try:
            row = Certificate.query.filter(
                Certificate.id == int(source),
                Certificate.revoked == False,  # noqa: E712
                Certificate.valid_to > utc_now(),
                Certificate.crt.isnot(None),
            ).first()
        except (TypeError, ValueError):
            pass
        if row is None:
            logger.warning("SAML SP certificate #%s unusable, falling back to the HTTPS certificate", source)
            source = 'https'
        else:
            cert, cert_pem = _first_cert_pem(base64.b64decode(row.crt))
            if with_key:
                if not row.prv:
                    raise ValueError(f'certificate #{row.id} has no private key in UCM')
                key_pem = load_pem_bytes(row.prv, context=f'certificate {row.id}')
    if source == 'https':
        with open(Config.HTTPS_CERT_PATH, 'rb') as f:
            cert, cert_pem = _first_cert_pem(f.read())
        if with_key:
            with open(Config.HTTPS_KEY_PATH, 'rb') as f:
                key_pem = f.read()
    if not with_key:
        return cert_pem, None
    key = serialization.load_pem_private_key(key_pem, password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError('signing SAML requests needs an RSA key; choose an RSA SP certificate')
    if key.public_key().public_numbers() != cert.public_key().public_numbers():
        raise ValueError('the SP private key does not match the SP certificate')
    return cert_pem, key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()).decode()


def build_settings(provider, base, sp_cert=None, sp_key=None):
    """python3-saml settings: strict validation, SHA-1 refused.

    Requests are signed when the provider asks for it and `sp_key` is given.
    """
    endpoints = sp_endpoints(base)
    settings = {
        'strict': True,
        'debug': False,
        'sp': {
            'entityId': endpoints['entity_id'],
            'assertionConsumerService': {'url': endpoints['acs_url'], 'binding': BINDING_POST},
            'singleLogoutService': {'url': endpoints['slo_url'], 'binding': BINDING_REDIRECT},
            'NameIDFormat': provider.saml_name_id_format or NAMEID_UNSPECIFIED,
        },
        'idp': {
            'entityId': provider.saml_entity_id,
            'singleSignOnService': {'url': provider.saml_sso_url, 'binding': BINDING_REDIRECT},
            'x509cert': provider.saml_certificate or '',
        },
        'security': {
            # A valid signature on the Response or on the Assertion is always
            # required; demanding one place would refuse IdPs that sign the other.
            'wantAssertionsSigned': False,
            'wantMessagesSigned': False,
            'authnRequestsSigned': bool(sp_key and provider.saml_sign_requests),
            'wantNameIdEncrypted': False,
            'wantAssertionsEncrypted': False,
            # The username falls back to the NameID when no attribute is sent.
            'wantAttributeStatement': False,
            'requestedAuthnContext': False,
            'allowSingleLabelDomains': True,
            # SHA-256 for anything the SP signs; IdP signatures or digests in SHA-1 are refused.
            'signatureAlgorithm': OneLogin_Saml2_Constants.RSA_SHA256,
            'digestAlgorithm': OneLogin_Saml2_Constants.SHA256,
            'rejectDeprecatedAlgorithm': True,
        },
    }
    if sp_cert:
        settings['sp']['x509cert'] = sp_cert
    if sp_key:
        settings['sp']['privateKey'] = sp_key
    if provider.saml_slo_url:
        settings['idp']['singleLogoutService'] = {'url': provider.saml_slo_url, 'binding': BINDING_REDIRECT}
    return settings


def _purge_expired():
    db.session.execute(delete(SAMLMessageId).where(SAMLMessageId.expires_at < utc_now()))


def remember_request(request_id, provider_id):
    """Record an AuthnRequest id until its response arrives or REQUEST_TTL passes."""
    _purge_expired()
    db.session.add(SAMLMessageId(
        kind=SAMLMessageId.KIND_REQUEST, message_id=request_id,
        provider_id=provider_id, expires_at=utc_now() + REQUEST_TTL))
    db.session.commit()


def take_request(request_id, provider_id):
    """Consume a pending AuthnRequest id; False when unknown, expired or already used."""
    if not request_id or len(request_id) > MAX_MESSAGE_ID_LENGTH:
        return False
    result = db.session.execute(delete(SAMLMessageId).where(
        SAMLMessageId.kind == SAMLMessageId.KIND_REQUEST,
        SAMLMessageId.message_id == request_id,
        SAMLMessageId.provider_id == provider_id,
        SAMLMessageId.expires_at >= utc_now(),
    ))
    db.session.commit()
    return result.rowcount == 1


def consume_assertion(assertion_id, provider_id, not_on_or_after):
    """Record an assertion id until it expires; False if it was already consumed."""
    if not assertion_id or len(assertion_id) > MAX_MESSAGE_ID_LENGTH:
        return False
    drift = timedelta(seconds=OneLogin_Saml2_Constants.ALLOWED_CLOCK_DRIFT)
    expires = datetime.fromtimestamp(not_on_or_after, timezone.utc).replace(tzinfo=None) + drift
    _purge_expired()
    db.session.add(SAMLMessageId(
        kind=SAMLMessageId.KIND_ASSERTION, message_id=assertion_id,
        provider_id=provider_id, expires_at=expires))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return False
    return True


def _cookie_path(base):
    return urlsplit(base).path.rstrip('/') + ACS_PATH


def set_request_cookie(response, request_id, base):
    """Bind the AuthnRequest to this browser. SameSite=None: the response
    comes back as a cross-site POST, which a Lax session cookie does not follow."""
    secure = urlsplit(base).scheme == 'https'
    response.set_cookie(
        REQUEST_COOKIE, request_id, max_age=int(REQUEST_TTL.total_seconds()),
        path=_cookie_path(base), secure=secure, httponly=True,
        samesite='None' if secure else 'Lax')


def clear_request_cookie(response, base):
    secure = urlsplit(base).scheme == 'https'
    response.delete_cookie(REQUEST_COOKIE, path=_cookie_path(base), secure=secure,
                           httponly=True, samesite='None' if secure else 'Lax')

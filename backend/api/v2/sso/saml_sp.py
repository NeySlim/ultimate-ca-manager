"""SAML service-provider side: public URLs, python3-saml settings, message ids."""

import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from onelogin.saml2.constants import OneLogin_Saml2_Constants
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from models import db
from models.sso import SAMLMessageId
from utils.datetime_utils import utc_now
from utils.public_endpoints import get_admin_base_url, get_admin_canonical_origin

logger = logging.getLogger(__name__)

ENTITY_PATH = '/api/v2/sso'
ACS_PATH = '/api/v2/sso/callback/saml'
NAMEID_UNSPECIFIED = 'urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified'
BINDING_POST = 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST'
BINDING_REDIRECT = 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect'

REQUEST_COOKIE = 'ucm_saml_request'
REQUEST_TTL = timedelta(minutes=10)
MAX_MESSAGE_ID_LENGTH = 256


def sp_base_url(flask_request):
    """Origin the IdP knows UCM by.

    The request's own origin (X-Forwarded-* applied by ProxyFix), unless it
    reached UCM under another host than the configured admin base URL.
    """
    origin = flask_request.url_root.rstrip('/')
    if get_admin_base_url():
        canonical = get_admin_canonical_origin()
        if canonical and urlsplit(origin).hostname != urlsplit(canonical).hostname:
            return canonical.rstrip('/')
    return origin


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


def build_settings(provider, base):
    """python3-saml settings: strict validation, SHA-1 refused."""
    endpoints = sp_endpoints(base)
    settings = {
        'strict': True,
        'debug': False,
        'sp': {
            'entityId': endpoints['entity_id'],
            'assertionConsumerService': {'url': endpoints['acs_url'], 'binding': BINDING_POST},
            'singleLogoutService': {'url': endpoints['slo_url'], 'binding': BINDING_REDIRECT},
            'NameIDFormat': getattr(provider, 'saml_name_id_format', None) or NAMEID_UNSPECIFIED,
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
            'authnRequestsSigned': False,
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

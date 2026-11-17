from . import bp, VALID_ROLES
from .helpers import (_get_ssl_verify, _cleanup_ssl_verify, _parse_json_field,
                      saml_groups, oidc_groups, mapped_attributes, oidc_identity,
                      saml_identity)
from .ldap_routes import _get_or_create_sso_user, _get_saml_auth
from . import return_path, saml_sp
from onelogin.saml2.constants import OneLogin_Saml2_Constants
from flask import request, redirect, session, Response, after_this_request
from auth.unified import require_auth
from auth.session_start import begin_session
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from models import db, User, UserSSOIdentity
from models.sso import SSOProvider, SSOSession
from services.audit_service import AuditService
from services.oidc_id_token import (OIDCValidationError, unverified_claims_error,
                                    verify_id_token)
from utils.datetime_utils import utc_now
from utils.ssrf_protection import (
    safe_request_get,
    safe_request_post,
    validate_url_not_cloud_metadata,
)
from dataclasses import dataclass, field
from datetime import timedelta
import secrets as py_secrets
import base64
import hashlib
import urllib.parse
import hmac
import logging
import traceback
import json


def _pkce_pair():
    """Generate a PKCE (RFC 7636) code_verifier + S256 code_challenge pair."""
    verifier = py_secrets.token_urlsafe(64)[:128]  # 43..128 chars per spec
    digest = hashlib.sha256(verifier.encode('ascii')).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')
    return verifier, challenge


logger = logging.getLogger(__name__)


def _login_error(error, next_path=None):
    """The login page showing *error*, carrying the page asked for while it is still valid."""
    query = {'error': error}
    next_path = return_path.safe_next(next_path)
    if next_path:
        query['next'] = next_path
    return '/login?' + urllib.parse.urlencode(query)


def _reject_oidc_login(provider, reason, next_path=None):
    """Fail closed with a generic client error and a clear internal audit trail."""
    logger.error("OIDC login rejected for provider %s: %s", provider.name, reason)
    try:
        AuditService.log_action(
            action='login_failure',
            resource_type='sso',
            resource_id=provider.id,
            resource_name=provider.name,
            details=f'OIDC ID token rejected: {reason}',
            success=False,
        )
    except Exception as audit_error:
        logger.error("Failed to audit OIDC login rejection: %s", audit_error)
    return redirect(_login_error('invalid_credentials', next_path))


def _sso_complete(next_path):
    """Landing of a successful SSO login, carrying the page to return to when it is still valid."""
    next_path = return_path.safe_next(next_path)
    if not next_path:
        return '/login/sso-complete'
    return '/login/sso-complete?' + urllib.parse.urlencode({'next': next_path})


# Shown as "the login expired or was started elsewhere, start again".
SAML_LOGIN_EXPIRED = 'saml_login_expired'


def _reject_saml_login(provider, reason, error='saml_validation_failed', next_path=None):
    """Refuse a SAML response with a generic client error and an audited reason."""
    logger.error("SAML login rejected for provider %s: %s", provider.name, reason)
    AuditService.log_action(
        action='login_failure',
        resource_type='sso',
        details=f'SAML response rejected for provider {provider.name}: {reason}',
        success=False
    )
    return redirect(_login_error(error, next_path))

def _saml_logout_request(provider):
    """IdP-initiated Single Logout over HTTP-Redirect (SAML Profiles §4.4).

    The LogoutRequest must carry a valid IdP signature; this browser's session is
    closed when it belongs to the NameID, and a LogoutResponse goes back to the
    IdP's SLO URL, signed whenever the SP has an RSA key (§4.4.4.2).
    """
    from onelogin.saml2.auth import OneLogin_Saml2_Auth
    from onelogin.saml2.logout_request import OneLogin_Saml2_Logout_Request
    from onelogin.saml2.logout_response import OneLogin_Saml2_Logout_Response
    from onelogin.saml2.utils import OneLogin_Saml2_Utils
    from onelogin.saml2.xml_utils import OneLogin_Saml2_XML

    base = saml_sp.sp_base_url(request)
    sp_cert = sp_key = None
    if provider.saml_slo_url:  # the responder MUST authenticate its LogoutResponse
        try:
            sp_cert, sp_key = saml_sp.load_sp_credentials(provider, with_key=True)
        except Exception as e:
            logger.warning("SAML LogoutResponse sent unsigned: SP key unusable (%s)", e)
    data = saml_sp.request_data(request, base)
    # The signature covers the query as the IdP encoded it (SAML Bindings §3.4.4.1).
    data['query_string'] = request.query_string.decode('ascii', 'replace')
    if not _slo_query_is_unambiguous(request.args, data['query_string']):
        return _reject_saml_logout(provider, 'repeated or re-encoded SAML parameter')
    data['validate_signature_from_qs'] = True
    try:
        auth = OneLogin_Saml2_Auth(
            data, saml_sp.build_settings(provider, base, sp_cert, sp_key, want_messages_signed=True))
        logout_request = OneLogin_Saml2_Logout_Request(auth.get_settings(), data['get_data']['SAMLRequest'])
        xml = logout_request.get_xml()
        if not auth.validate_request_signature(data['get_data']):
            return _reject_saml_logout(provider, 'invalid or missing signature')
        if not logout_request.is_valid(data):
            return _reject_saml_logout(provider, logout_request.get_error() or 'invalid LogoutRequest')
        # A signed message MUST name its Destination (SAML Bindings §3.4.5.2); the
        # library checks it only when present. Fresh and used once, or a replay ends a later session.
        root = OneLogin_Saml2_XML.to_etree(xml)
        if not root.get('Destination'):
            return _reject_saml_logout(provider, 'signed LogoutRequest without Destination')
        issued = OneLogin_Saml2_Utils.parse_SAML_to_time(root.get('IssueInstant'))
        if not saml_sp.logout_request_fresh(issued):
            return _reject_saml_logout(provider, 'IssueInstant outside the clock window')
        if not saml_sp.consume_logout_request(logout_request.id, provider.id, issued):
            return _reject_saml_logout(provider, 'LogoutRequest already used')
        name_id = OneLogin_Saml2_Logout_Request.get_nameid(xml)
        indexes = OneLogin_Saml2_Logout_Request.get_session_indexes(xml)
    except Exception as e:
        return _reject_saml_logout(provider, f'unreadable LogoutRequest ({e})')

    users = {u for (u,) in db.session.query(SSOSession.user_id).filter_by(
        provider_id=provider.id, sso_name_id=name_id)}
    users |= {u for (u,) in db.session.query(UserSSOIdentity.user_id).filter_by(
        provider_id=provider.id, external_id=name_id)}
    SSOSession.query.filter_by(provider_id=provider.id, sso_name_id=name_id).delete()
    db.session.commit()
    # With SessionIndex values only the sessions they name end (SAML Core §3.7.3.2);
    # a session opened before its index was kept counts as named.
    own_index = session.get('saml_session_index')
    closed = (session.get('auth_method') == 'sso' and session.get('user_id') in users
              and (not indexes or own_index is None or own_index in indexes))
    if closed:
        session.clear()
    AuditService.log_action(
        action='logout', resource_type='sso', resource_name=name_id,
        details=(f'SAML Single Logout from {provider.name}: '
                 f'{"session closed" if closed else "no session of this NameID in this browser"}'),
        success=True)

    if not provider.saml_slo_url:
        return redirect('/login')
    builder = OneLogin_Saml2_Logout_Response(auth.get_settings())
    builder.build(logout_request.id)
    params = {'SAMLResponse': builder.get_response()}
    if 'RelayState' in data['get_data']:
        params['RelayState'] = data['get_data']['RelayState']
    if sp_key:
        auth.add_response_signature(params, OneLogin_Saml2_Constants.RSA_SHA256)
    return redirect(OneLogin_Saml2_Utils.redirect(auth.get_slo_response_url(), params, request_data=data))


_SLO_PARAMS = ('SAMLRequest', 'RelayState', 'SigAlg', 'Signature')


def _slo_query_is_unambiguous(args, query_string):
    """Each parameter appears at most once and spelled as the signed query keeps it,
    so the values acted on are the bytes the signature covers."""
    parts = query_string.split('&')
    for key in _SLO_PARAMS:
        raw = sum(1 for part in parts if part.startswith(key + '='))
        if raw > 1 or len(args.getlist(key)) != raw:
            return False
    return True


def _reject_saml_logout(provider, reason):
    logger.error("SAML LogoutRequest rejected for provider %s: %s", provider.name, reason)
    AuditService.log_action(
        action='logout', resource_type='sso',
        details=f'SAML LogoutRequest from {provider.name} rejected: {reason}', success=False)
    return redirect('/login?error=saml_logout_rejected')


# ============ Public SSO Endpoints (no auth) ============

@bp.route('/api/v2/sso/available', methods=['GET'])
def get_available_providers():
    """Get list of enabled SSO providers for login page"""
    providers = SSOProvider.query.filter_by(enabled=True).all()

    return success_response(data=[{
        'id': p.id,
        'name': p.name,
        'display_name': p.display_name or p.name,
        'provider_type': p.provider_type,
        'icon': p.icon,
        'is_default': p.is_default,
        'login_url': f'/api/v2/sso/login/{p.provider_type}' if p.provider_type != 'ldap' else None
    } for p in providers])


@bp.route('/api/v2/sso/login/<provider_type>', methods=['GET'])
def initiate_sso_login(provider_type):
    """
    Initiate SSO login flow.
    For OAuth2: redirects to authorization URL
    For SAML: redirects to IdP SSO URL
    For LDAP: returns error (LDAP uses direct auth via /api/v2/sso/ldap/login)
    """
    if provider_type not in ('saml', 'oauth2'):
        return error_response("Use /api/v2/sso/ldap/login for LDAP authentication", 400)

    provider = SSOProvider.query.filter_by(provider_type=provider_type, enabled=True).first()
    if not provider:
        return error_response(f"No enabled {provider_type.upper()} provider found", 404)

    # Generate state token for CSRF protection
    state = py_secrets.token_urlsafe(32)
    session['sso_state'] = state
    session['sso_provider_id'] = provider.id
    # The page to return to stays server side with this login's transaction, never sent to the IdP.
    next_path = return_path.safe_next(request.args.get('next'))
    session.pop('sso_next', None)
    if next_path and provider.provider_type == 'oauth2':
        session['sso_next'] = next_path

    if provider.provider_type == 'oauth2':
        # Build OAuth2 / OIDC authorization URL with PKCE (RFC 7636) + nonce
        scopes = json.loads(provider.oauth2_scopes) if provider.oauth2_scopes else ['openid', 'profile', 'email']

        callback_url = request.url_root.rstrip('/') + '/api/v2/sso/callback/oauth2'

        code_verifier, code_challenge = _pkce_pair()
        nonce = py_secrets.token_urlsafe(32)
        session['sso_pkce_verifier'] = code_verifier
        session['sso_nonce'] = nonce

        params = {
            'client_id': provider.oauth2_client_id,
            'redirect_uri': callback_url,
            'response_type': 'code',
            'scope': ' '.join(scopes),
            'state': state,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'nonce': nonce,
        }

        auth_url = provider.oauth2_auth_url + '?' + urllib.parse.urlencode(params)
        return redirect(auth_url)

    elif provider.provider_type == 'saml':
        # For SAML, generate proper AuthnRequest
        if not provider.saml_sso_url:
            return error_response("SAML SSO URL not configured", 400)

        try:
            saml_auth = _get_saml_auth(request, provider, state, sign_request=True)
            redirect_url = saml_auth.login()
            request_id = saml_auth.get_last_request_id()
            saml_sp.remember_request(request_id, provider.id, next_path)
            response = redirect(redirect_url)
            saml_sp.set_request_cookie(response, request_id, saml_sp.sp_base_url(request))
            return response
        except Exception as e:
            db.session.rollback()
            logger.error(f"SAML login initiation error: {e}")
            return error_response("SAML login failed. Check SAML configuration.", 500)

    return error_response("Unknown provider type", 400)


@dataclass
class Refusal:
    """A callback the IdP's answer refuses, before any account is looked at."""
    code: str                   # what /login?error= says
    reason: str = None          # why, for the log, the audit and a sign-in test report
    audit: str = None           # how the login records it: None, 'oidc', 'saml' or 'detail'
    detail: str = None          # 'detail': the login_failure audit text


@dataclass
class SignInIdentity:
    """What a validated IdP answer says of the person signing in."""
    username: str
    email: str
    fullname: str
    external_data: dict
    group_source: object
    session_id: str             # the key of the SSO session a login records
    session_index: str = None   # SAML SessionIndex
    not_verified: list = field(default_factory=list)


def _login_refused(provider, refusal, next_path):
    """The login's answer to ``refusal``: its audit entry, then the login page."""
    if refusal.audit == 'oidc':
        return _reject_oidc_login(provider, refusal.reason, next_path)
    if refusal.audit == 'saml':
        return _reject_saml_login(provider, refusal.reason, refusal.code, next_path)
    if refusal.audit == 'detail':
        AuditService.log_action(action='login_failure', resource_type='sso',
                                details=refusal.detail, success=False)
    return redirect(_login_error(refusal.code, next_path))


def _oidc_refusal(reason):
    return Refusal('invalid_credentials', reason, 'oidc')


def oidc_sign_in(provider, code, code_verifier, expected_nonce):
    """Exchange ``code`` and read the identity it gives: (SignInIdentity, None) or (None, Refusal).

    PKCE (RFC 7636), the nonce and the ID token are checked as provider settings say;
    a sign-in test runs this same function. Writes nothing."""
    verify = True
    try:
        callback_url = request.url_root.rstrip('/') + '/api/v2/sso/callback/oauth2'
        from utils.encryption import SecretUnreadable, decrypt_required
        try:
            client_secret = decrypt_required(provider._oauth2_client_secret,
                                             f'SSO provider {provider.name} client secret')
        except SecretUnreadable as e:
            # Never a token request without the secret the provider was saved with
            logger.error(str(e))
            return None, Refusal('token_exchange_failed', 'the client secret cannot be read')
        token_data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': callback_url,
            'client_id': provider.oauth2_client_id,
            'client_secret': client_secret,
        }
        if code_verifier:
            token_data['code_verifier'] = code_verifier

        verify = _get_ssl_verify(provider, 'oauth2')
        try:
            validate_url_not_cloud_metadata(provider.oauth2_token_url)
            token_response = safe_request_post(
                provider.oauth2_token_url,
                data=token_data,
                timeout=10,
                verify=verify,
                allow_redirects=False,
            )
        except (ValueError, TypeError) as token_error:
            return None, _oidc_refusal(f'token endpoint rejected: {token_error}')

        if not token_response.ok:
            logger.error("OAuth2 token exchange failed for provider %s", provider.name)
            return None, Refusal('token_exchange_failed', 'the token endpoint refused the code')

        tokens = token_response.json()
        access_token = tokens.get('access_token')

        if not access_token:
            return None, Refusal('no_access_token', 'the token response has no access token')

        id_token = tokens.get('id_token')
        verification_enabled = provider.id_token_verify is not False
        trusted_id_claims = None
        if verification_enabled and (not id_token or not expected_nonce):
            return None, _oidc_refusal('missing ID token or session nonce')
        if id_token:
            try:
                trusted_id_claims = verify_id_token(
                    id_token,
                    provider,
                    expected_nonce,
                    verify=verification_enabled,
                    ssl_verify=verify,
                )
            except OIDCValidationError as validation_error:
                return None, _oidc_refusal(str(validation_error))

        # Get user info. Revalidate and pin the IdP URL for every fetch.
        try:
            validate_url_not_cloud_metadata(provider.oauth2_userinfo_url)
            userinfo_response = safe_request_get(
                provider.oauth2_userinfo_url,
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=10,
                verify=verify,
                allow_redirects=False,
            )
        except (ValueError, TypeError) as userinfo_error:
            return None, _oidc_refusal(f'userinfo endpoint rejected: {userinfo_error}')

        if not userinfo_response.ok:
            return None, Refusal('userinfo_failed', 'the UserInfo endpoint refused the access token')

        userinfo = userinfo_response.json()
        if trusted_id_claims is not None and verification_enabled:
            if userinfo.get('sub') != trusted_id_claims.get('sub'):
                return None, _oidc_refusal('userinfo subject mismatch')

        # Map attributes
        attr_mapping = _parse_json_field(provider.attribute_mapping)
        username, email, fullname = oidc_identity(userinfo, attr_mapping)

        if not username:
            return None, Refusal('no_username', 'no username was read from UserInfo')

        # Token groups count only from the token of this login (nonce checked, same subject as
        # UserInfo). Unverified (compatibility mode), only over an HTTPS token endpoint with
        # its certificate checked: OIDC Core §3.1.3.7 step 6; steps 2-5 and 9-11 still apply.
        token_sub = (trusted_id_claims or {}).get('sub')
        token_unused = None
        if trusted_id_claims is None:
            token_unused = 'no ID token'
        elif not (isinstance(token_sub, str) and token_sub
                  and userinfo.get('sub') == token_sub):
            token_unused = 'subject does not match UserInfo'
        elif not verification_enabled:
            if verify is False:
                token_unused = 'unverified and TLS verification is off'
            elif urllib.parse.urlsplit(provider.oauth2_token_url or '').scheme.lower() != 'https':
                token_unused = 'unverified and the token endpoint is not HTTPS'
            else:
                claims_error = unverified_claims_error(trusted_id_claims, provider,
                                                       expected_nonce)
                if claims_error:
                    token_unused = f'unverified token rejected ({claims_error})'
        bound_claims = trusted_id_claims if token_unused is None else None
        groups, group_source = oidc_groups(userinfo, bound_claims, token_unused, attr_mapping)
        external_data = dict(userinfo, groups=groups)
        if mapped_attributes(attr_mapping, 'groups', set(userinfo) | set(bound_claims or {})):
            # A claim mapped to groups replaces roles and groups: UserInfo's roles go too.
            external_data.pop('roles', None)

        not_verified = []
        if not verification_enabled:
            not_verified.append(
                'the ID token signature, issuer, audience and expiry (compatibility mode): '
                'they only decide whether the token groups are read')
            not_verified.append('that UserInfo names the subject of the ID token')
            if not id_token:
                not_verified.append('no ID token was returned: the identity rests on UserInfo alone')
        return SignInIdentity(username, email, fullname, external_data, group_source,
                              session_id=userinfo.get('sub', username),
                              not_verified=not_verified), None
    finally:
        _cleanup_ssl_verify(verify)


def saml_validate(provider, saml_auth, request_id):
    """Signature, audience, destination, validity window and InResponseTo against
    ``request_id`` (SAML Profiles §4.1.4.3), by python3-saml: a Refusal, or None."""
    # SECURITY: NEVER fall back to an unsigned XML parser here. If python3-saml
    # raises, the response is untrusted and is refused (an earlier fallback was a bypass).
    try:
        saml_auth.process_response(request_id=request_id)
    except Exception as saml_err:
        logger.error(f"SAML response processing failed: {saml_err}")
        return Refusal('saml_validation_failed', 'the response could not be processed', 'detail',
                       f'SAML response rejected (parse error) for provider {provider.name}')

    errors = saml_auth.get_errors()
    if errors:
        reason = saml_auth.get_last_error_reason() or ''
        logger.error(f"SAML errors: {errors}, reason: {reason}")
        # A response to another AuthnRequest: a second tab, or a login started elsewhere.
        code = SAML_LOGIN_EXPIRED if 'InResponseTo' in reason else 'saml_validation_failed'
        return Refusal(code, reason or ', '.join(errors), 'detail',
                       f'SAML validation errors for provider {provider.name}: {errors}')
    return None


def saml_assertion(provider, saml_auth):
    """The identity of a validated response: (SignInIdentity, None) or (None, Refusal).
    Its assertion id is recorded, so a second use is refused (replay)."""
    not_on_or_after = saml_auth.get_last_assertion_not_on_or_after()
    if not not_on_or_after:
        return None, Refusal('saml_validation_failed', 'SubjectConfirmationData has no NotOnOrAfter', 'saml')
    assertion_id = saml_auth.get_last_assertion_id()
    if not assertion_id or len(assertion_id) > saml_sp.MAX_MESSAGE_ID_LENGTH:
        return None, Refusal(
            'saml_validation_failed',
            f'assertion ID missing or longer than {saml_sp.MAX_MESSAGE_ID_LENGTH} characters', 'saml')
    if not saml_sp.consume_assertion(assertion_id, provider.id, not_on_or_after):
        return None, Refusal('saml_validation_failed', 'assertion already consumed (replay)', 'saml')

    # Only reached after signature + assertion verification succeeded
    attrs = saml_auth.get_attributes()
    name_id = saml_auth.get_nameid()
    try:
        name_id_format = saml_auth.get_nameid_format() or ''
    except Exception:
        name_id_format = ''

    attr_mapping = _parse_json_field(provider.attribute_mapping)
    username, email, fullname = saml_identity(attrs, name_id, attr_mapping)
    if not username:
        return None, Refusal('no_username', 'no username was read from the assertion')

    groups, group_source = saml_groups(attrs, attr_mapping,
                                       saml_sp.attribute_friendly_names(saml_auth))
    external_data = {'name_id': name_id, 'name_id_format': name_id_format,
                     'attributes': {k: v for k, v in attrs.items()},
                     # Role mapping reads a top-level 'groups' key (as OIDC/LDAP supply).
                     'groups': groups}
    return SignInIdentity(username, email, fullname, external_data, group_source,
                          session_id=name_id, session_index=saml_auth.get_session_index()), None


def _open_sso_session(provider, identity, next_url, error_url):
    """The login's last steps once an account is admitted: the account is synchronised,
    its SSO session recorded, and the browser's session opened under a new identifier."""
    user, error_code = _get_or_create_sso_user(provider, identity.username, identity.email,
                                               identity.fullname, identity.external_data,
                                               group_source=identity.group_source)
    if not user:
        return redirect(error_url(error_code or 'user_creation_failed'))

    protocol = 'OAuth2' if provider.provider_type == 'oauth2' else 'SAML'
    # SECURITY: Block disabled accounts (admin can disable SSO users locally)
    if not user.active:
        logger.warning(f"{protocol} login blocked: user {identity.username} is disabled")
        AuditService.log_action(
            action='login_failure',
            resource_type='user',
            resource_id=user.id,
            resource_name=identity.username,
            details=f'{protocol} SSO login blocked: user disabled (via {provider.name})',
            success=False,
            username=identity.username
        )
        return redirect(error_url('account_disabled'))

    # Create or update SSO session for audit
    sso_session = SSOSession.query.filter_by(session_id=identity.session_id).first()
    if sso_session:
        sso_session.expires_at = utc_now() + timedelta(hours=8)
    else:
        sso_session = SSOSession(
            user_id=user.id,
            provider_id=provider.id,
            session_id=identity.session_id,
            sso_name_id=identity.session_id,
            expires_at=utc_now() + timedelta(hours=8)
        )
        db.session.add(sso_session)
    ok, err = safe_commit(logger, "SSO login failed - session save error")
    if not ok:
        return redirect(error_url('callback_error'))

    # Establish Flask session under a new identifier (no session fixation)
    now = utc_now()
    begin_session(user)
    session['user_id'] = user.id
    session['username'] = user.username
    session['role'] = user.role
    session['auth_method'] = 'sso'
    if identity.session_index:
        session['saml_session_index'] = identity.session_index
    session['login_time'] = now.isoformat()
    session['last_activity'] = now.isoformat()
    session.permanent = True

    # Forced 2FA enrolment (#141): restrict the session until TOTP is
    # enrolled when this provider enforces 2FA. The frontend picks it up
    # via /auth/verify after the sso-complete redirect.
    from auth.twofa_enforcement import must_enroll_2fa, ENROLL_SESSION_KEY
    if must_enroll_2fa(user, auth_method='sso', provider=provider):
        session[ENROLL_SESSION_KEY] = True

    # SEC-07: Audit log SSO login
    AuditService.log_action(
        action='login_success',
        resource_type='user',
        resource_id=user.id,
        resource_name=user.username,
        details=f'{protocol} SSO login via {provider.name}',
        success=True,
        username=user.username
    )
    return redirect(next_url)


@bp.route('/api/v2/sso/callback/<provider_type>', methods=['GET', 'POST'])
def sso_callback(provider_type):
    """
    Handle SSO callback from OAuth2/SAML providers.
    Creates or updates user and establishes session.
    """
    if provider_type not in ('saml', 'oauth2'):
        return redirect('/login?error=invalid_provider_type')

    # Circular import: a sign-in test runs the stages above.
    from . import sign_in_tests
    # A callback whose server-side transaction is a sign-in test's never reaches the login.
    test = sign_in_tests.transaction_of(provider_type)
    if test is not None:
        return sign_in_tests.finish(test, provider_type)

    # Spent by any OAuth2 return, used only by a successful one.
    oauth2_next = session.pop('sso_next', None) if provider_type == 'oauth2' else None

    provider = SSOProvider.query.filter_by(provider_type=provider_type, enabled=True).first()
    if not provider:
        return redirect(_login_error('provider_not_found', oauth2_next))

    # Verify state for CSRF protection (OAuth2 only — SAML uses its own mechanisms)
    if provider_type == 'oauth2':
        state = request.args.get('state')
        stored_state = session.get('sso_state', '')
        if not state or not hmac.compare_digest(state, stored_state):
            return redirect(_login_error('invalid_state', oauth2_next))

    if provider.provider_type == 'oauth2':
        code = request.args.get('code')
        if not code:
            error = request.args.get('error', 'no_code')
            return redirect(_login_error(error, oauth2_next))

        try:
            # PKCE: pop the verifier so it can only be used once
            code_verifier = session.pop('sso_pkce_verifier', None)
            expected_nonce = session.pop('sso_nonce', None)

            identity, refusal = oidc_sign_in(provider, code, code_verifier, expected_nonce)
            if refusal is not None:
                return _login_refused(provider, refusal, oauth2_next)
            return _open_sso_session(provider, identity, _sso_complete(oauth2_next),
                                     lambda code: _login_error(code, oauth2_next))

        except Exception as e:
            logger.error(f"OAuth2 callback error: {e}\n{traceback.format_exc()}")
            # Before the audit. `_get_or_create_sso_user` leaves the account
            # it created or rebound staged when it cannot commit, and
            # `log_action` commits the session it is given: auditing this
            # failure is what would have written the half-made account, and
            # the identity binding with it, on a login that never completed.
            db.session.rollback()
            AuditService.log_action(
                action='login_failure',
                resource_type='sso',
                details=f'OAuth2 callback error for provider {provider.name}',
                success=False
            )
            return redirect(_login_error('callback_error', oauth2_next))

    elif provider.provider_type == 'saml':
        if request.method == 'GET' and 'SAMLRequest' in request.args:
            return _saml_logout_request(provider)
        sp_base = saml_sp.sp_base_url(request)

        # Dropped once the request is used up or gone, never by a refused POST.
        drop_cookie = []

        @after_this_request
        def _drop_request_cookie(response):
            if drop_cookie:
                saml_sp.clear_request_cookie(response, sp_base)
            return response

        # The page this browser's AuthnRequest asked for: a failed login sends it back too
        back = None
        try:
            saml_auth = _get_saml_auth(request, provider)

            # The AuthnRequest this browser started; consumed only by a valid response.
            request_id = request.cookies.get(saml_sp.REQUEST_COOKIE) or None
            back = saml_sp.request_next_path(request_id, provider.id)
            if request_id and not saml_sp.request_pending(request_id, provider.id):
                drop_cookie.append(True)
                return _reject_saml_login(provider, 'unknown, expired or already used AuthnRequest',
                                          SAML_LOGIN_EXPIRED, next_path=back)

            refusal = saml_validate(provider, saml_auth, request_id)
            if refusal is not None:
                return _login_refused(provider, refusal, back)

            # python3-saml matched InResponseTo against request_id when both exist.
            in_response_to = saml_auth.get_last_response_in_response_to()
            saml_next = None
            if in_response_to is None:
                if not provider.saml_allow_idp_initiated:
                    return _reject_saml_login(provider, 'unsolicited response (IdP-initiated login is disabled)',
                                              next_path=back)
            elif request_id is None:
                return _reject_saml_login(provider, 'InResponseTo matches no AuthnRequest from this browser',
                                          SAML_LOGIN_EXPIRED, next_path=back)
            else:
                # Read before the take: only the response that consumes the request uses it.
                saml_next = back
                if not saml_sp.take_request(request_id, provider.id):
                    drop_cookie.append(True)
                    return _reject_saml_login(provider, 'unknown, expired or already used AuthnRequest',
                                              SAML_LOGIN_EXPIRED, next_path=back)
                drop_cookie.append(True)

            identity, refusal = saml_assertion(provider, saml_auth)
            if refusal is not None:
                return _login_refused(provider, refusal, back)
            return _open_sso_session(provider, identity, _sso_complete(saml_next),
                                     lambda code: _login_error(code, back))

        except Exception as e:
            logger.error(f"SAML callback error: {e}\n{traceback.format_exc()}")
            # Before the audit. `_get_or_create_sso_user` leaves the account
            # it created or rebound staged when it cannot commit, and
            # `log_action` commits the session it is given: auditing this
            # failure is what would have written the half-made account, and
            # the identity binding with it, on a login that never completed.
            db.session.rollback()
            AuditService.log_action(
                action='login_failure',
                resource_type='sso',
                details=f'SAML callback error for provider {provider.name}',
                success=False
            )
            return redirect(_login_error('callback_error', back))

    return redirect('/login?error=unknown_provider_type')

"""OIDC and SAML sign-in tests: the real round trip through the IdP, with the identity the
administrator presents there, reporting what the login would have done and doing none of it.

The test returns by the login's own callback URLs (OIDC Core §3.1.2.1 and SAML Profiles
§4.1.3.5 tie them to the registration); a row of ``pro_sso_sign_in_tests``, found by the hash
of the ``state`` or of the AuthnRequest id, is what makes a callback a test's. The login keeps
its transactions elsewhere (the session, ``pro_sso_saml_message_ids``), so neither can end as
the other. A test opens no session, writes no account and no login audit entry.
"""
import hashlib
import hmac
import json
import logging
import secrets as py_secrets
import traceback
import urllib.parse
from datetime import timedelta
from urllib.parse import urlsplit

from flask import g, make_response, redirect, request
from sqlalchemy import update

from auth.unified import require_auth
from models import User, db
from models.sso import SSOProvider, SSOSignInTest
from services.audit_service import AuditService
from services.sso_sign_in_test_purge import purge_expired_sign_in_tests as _purge_expired
from utils.datetime_utils import utc_isoformat, utc_now
from utils.db_transaction import safe_commit
from utils.response import error_response, success_response

from . import bp, saml_sp
from .diagnostics import MAX_NAMES, MAX_VALUES, NAME_LENGTH, VALUE_LENGTH
from .ldap_routes import CREATE, DISABLED, OPEN, _get_saml_auth, decide_sso_account
from . import login_routes

logger = logging.getLogger(__name__)

TRANSACTION_TTL = timedelta(minutes=10)
REPORT_TTL = timedelta(minutes=10)
BROWSER_COOKIE = 'ucm_sso_test'
DONE_PAGE = '/sso-test-complete'
AUDIT_ACTION = 'sso_sign_in_test'
_PROTOCOLS = ('oauth2', 'saml')
_DETAIL_LENGTH = 2000
_MAX_SAML_RESPONSE = 1024 * 1024


def _digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _transaction_hash(protocol, value):
    return _digest(f'{protocol}:{value}')


def _callback_path(protocol):
    """Path of the callback this protocol returns to, where the browser cookie is sent."""
    if protocol == 'saml':
        base = saml_sp.sp_base_url(request)
        return urlsplit(base).path.rstrip('/') + saml_sp.ACS_PATH, base
    base = request.url_root.rstrip('/')
    return urlsplit(base).path.rstrip('/') + '/api/v2/sso/callback/oauth2', base


def _set_browser_cookie(response, protocol, value):
    """Binds the test to the browser that started it, as the login's own cookie does.
    SameSite=None: a SAML response comes back as a cross-site POST."""
    path, base = _callback_path(protocol)
    secure = urlsplit(base).scheme == 'https'
    response.set_cookie(BROWSER_COOKIE, value, max_age=int(TRANSACTION_TTL.total_seconds()),
                        path=path, secure=secure, httponly=True,
                        samesite='None' if secure else 'Lax')


def _clear_browser_cookie(response, protocol):
    path, base = _callback_path(protocol)
    secure = urlsplit(base).scheme == 'https'
    response.delete_cookie(BROWSER_COOKIE, path=path, secure=secure, httponly=True,
                           samesite='None' if secure else 'Lax')


@bp.route('/api/v2/sso/providers/<int:provider_id>/test-sign-in', methods=['POST'])
@require_auth(['write:sso'])
def start_sign_in_test(provider_id):
    """Start a sign-in test of the SAVED provider, enabled or not: the URL to open, and the
    id its report is read by."""
    provider = db.get_or_404(SSOProvider, provider_id)
    if provider.provider_type not in _PROTOCOLS:
        return error_response("Sign-in tests are for OIDC and SAML providers; "
                              "test an LDAP provider with its mapping test", 400)
    owner_id = getattr(g, 'user_id', None)
    if owner_id is None:
        return error_response("Sign-in tests need a user account", 403)

    secret = None
    if provider.provider_type == 'oauth2':
        if not provider.oauth2_auth_url or not provider.oauth2_client_id:
            return error_response("The provider has no authorization URL or client ID", 400)
        state = py_secrets.token_urlsafe(32)
        code_verifier, code_challenge = login_routes._pkce_pair()
        nonce = py_secrets.token_urlsafe(32)
        scopes = json.loads(provider.oauth2_scopes) if provider.oauth2_scopes else ['openid', 'profile', 'email']
        params = {
            'client_id': provider.oauth2_client_id,
            'redirect_uri': request.url_root.rstrip('/') + '/api/v2/sso/callback/oauth2',
            'response_type': 'code',
            'scope': ' '.join(scopes),
            'state': state,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'nonce': nonce,
        }
        url = provider.oauth2_auth_url + '?' + urllib.parse.urlencode(params)
        transaction = _transaction_hash('oauth2', state)
        from utils.encryption import encrypt_value
        secret = encrypt_value(json.dumps({'code_verifier': code_verifier, 'nonce': nonce}))
    else:
        if not provider.saml_sso_url:
            return error_response("SAML SSO URL not configured", 400)
        try:
            saml_auth = _get_saml_auth(request, provider, sign_request=True)
            url = saml_auth.login()
            request_id = saml_auth.get_last_request_id()
        except Exception as e:
            logger.error(f"SAML sign-in test not started for provider {provider.name}: {type(e).__name__}: {e}")
            return error_response("SAML sign-in test failed to start. Check SAML configuration.", 500)
        transaction = _transaction_hash('saml', request_id)

    browser = py_secrets.token_urlsafe(32)
    token = py_secrets.token_urlsafe(32)
    now = utc_now()
    _purge_expired()
    db.session.add(SSOSignInTest(
        token=token, provider_id=provider.id, user_id=owner_id,
        protocol=provider.provider_type, transaction_hash=transaction,
        browser_hash=_digest(browser), secret=secret, state=SSOSignInTest.PENDING,
        created_at=now, expires_at=now + TRANSACTION_TTL))
    ok, err = safe_commit(logger, "Failed to start the sign-in test")
    if not ok:
        return err
    response = make_response(success_response(data={
        'id': token, 'url': url, 'expires_at': utc_isoformat(now + TRANSACTION_TTL),
    }, message="Sign-in test started"))
    _set_browser_cookie(response, provider.provider_type, browser)
    return response


@bp.route('/api/v2/sso/sign-in-tests/<token>', methods=['GET'])
@require_auth(['write:sso'])
def get_sign_in_test(token):
    """A test's state and report, for the account that started it only."""
    try:  # a read still answers when the purge cannot write; the scheduled task retries it
        _purge_expired()
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.warning(f"Sign-in test purge on read failed: {type(e).__name__}")
    test = SSOSignInTest.query.filter_by(token=str(token)[:64]).first()
    # Another account's test, or one gone, answers as if it never existed.
    if (test is None or test.user_id != getattr(g, 'user_id', None)
            or test.expires_at < utc_now()):
        return error_response("Sign-in test not found or expired", 404)
    done = test.state == SSOSignInTest.DONE
    return success_response(data={
        'id': test.token,
        'provider_id': test.provider_id,
        'protocol': test.protocol,
        'state': test.state,
        'expires_at': utc_isoformat(test.expires_at),
        'report': json.loads(test.report) if done and test.report else None,
    })


# -- the callback side --------------------------------------------------------

def _saml_in_response_to():
    """InResponseTo of the posted SAML response, read before any validation, only to find
    the transaction it names; python3-saml then checks it against that one."""
    if request.method != 'POST':
        return None
    value = request.form.get('SAMLResponse')
    if not value or len(value) > _MAX_SAML_RESPONSE:
        return None
    try:
        from onelogin.saml2.utils import OneLogin_Saml2_Utils
        from onelogin.saml2.xml_utils import OneLogin_Saml2_XML
        root = OneLogin_Saml2_XML.to_etree(OneLogin_Saml2_Utils.b64decode(value))
        in_response_to = root.get('InResponseTo')
    except Exception:
        return None
    return in_response_to or None


def transaction_of(protocol):
    """The sign-in test this callback answers, or None for a login's callback. An unsolicited
    SAML response names no request (SAML Profiles §4.1.5), so it is never a test's."""
    if protocol == 'oauth2':
        key = request.args.get('state')
    else:
        key = _saml_in_response_to()
    if not key or len(key) > saml_sp.MAX_MESSAGE_ID_LENGTH:
        return None
    test = SSOSignInTest.query.filter_by(
        transaction_hash=_transaction_hash(protocol, key), protocol=protocol).first()
    if test is not None:
        test.callback_key = key  # the AuthnRequest id python3-saml compares InResponseTo with
    return test


def _done(result, protocol, clear=True):
    response = redirect(f'{DONE_PAGE}?' + urllib.parse.urlencode({'result': result}))
    if clear:
        _clear_browser_cookie(response, protocol)
    return response


def _audit(test, details, success):
    owner = db.session.get(User, test.user_id)
    provider = db.session.get(SSOProvider, test.provider_id)
    AuditService.log_action(
        action=AUDIT_ACTION, resource_type='sso_provider', resource_id=test.provider_id,
        resource_name=provider.name if provider else None, details=details, success=success,
        username=owner.username if owner else None, user_id=test.user_id)


def finish(test, protocol):
    """Run the returning test once, then purge what expired (this test too, when it had)."""
    response = _finish(test, protocol)
    _purge_expired()
    db.session.commit()
    return response


def _finish(test, protocol):
    """The login's checks, then its account decision alone."""
    now = utc_now()
    test_id, secret, callback_key = test.id, test.secret, getattr(test, 'callback_key', None)
    if test.state != SSOSignInTest.PENDING:
        _audit(test, 'Sign-in test return refused: the test was already used (replay)', False)
        return _done('used', protocol, clear=False)
    if test.expires_at < now:
        _audit(test, 'Sign-in test return refused: the test expired', False)
        return _done('expired', protocol)
    browser = request.cookies.get(BROWSER_COOKIE) or ''
    if not hmac.compare_digest(_digest(browser), test.browser_hash):
        _audit(test, 'Sign-in test return refused: it came back to another browser', False)
        return _done('other_browser', protocol, clear=False)

    # Claimed once: a second return of this state or request finds it used.
    claimed = db.session.execute(update(SSOSignInTest).where(
        SSOSignInTest.id == test_id, SSOSignInTest.state == SSOSignInTest.PENDING,
        SSOSignInTest.expires_at >= now).values(state=SSOSignInTest.RUNNING, secret=None)).rowcount
    db.session.commit()
    if claimed != 1:
        return _done('used', protocol, clear=False)

    try:
        report = _run(test_id, protocol, secret, callback_key)
    except Exception as e:
        logger.error(f"Sign-in test callback error: {e}\n{traceback.format_exc()}")
        db.session.rollback()
        report = {'verdict': 'refused', 'stage': 'protocol', 'code': 'callback_error',
                  'reason': 'unexpected error, see the server log'}

    finished = utc_now()
    db.session.execute(update(SSOSignInTest).where(SSOSignInTest.id == test_id).values(
        state=SSOSignInTest.DONE, report=json.dumps(report), finished_at=finished,
        expires_at=finished + REPORT_TTL))
    db.session.commit()
    test = db.session.get(SSOSignInTest, test_id)
    _audit(test, _audit_text(report), True)
    return _done('done', protocol)


def _cut(value, limit=NAME_LENGTH):
    text = '' if value is None else str(value)
    return text if len(text) <= limit else text[:limit - 1] + '…'


def _cut_list(values, count, limit):
    values = list(values or [])
    return [_cut(v, limit) for v in values[:count]], max(0, len(values) - count)


def _run(test_id, protocol, secret, callback_key):
    test = db.session.get(SSOSignInTest, test_id)
    provider = db.session.get(SSOProvider, test.provider_id)
    if provider is None or provider.provider_type != protocol:
        return {'verdict': 'refused', 'stage': 'protocol', 'code': 'provider_not_found',
                'reason': 'the provider was deleted or changed type'}
    base = {'protocol': protocol, 'provider_id': provider.id, 'provider_name': provider.name,
            'provider_enabled': bool(provider.enabled)}

    if protocol == 'oauth2':
        code = request.args.get('code')
        if not code:
            error = _cut(request.args.get('error', 'no_code'), VALUE_LENGTH)
            return dict(base, verdict='refused', stage='protocol', code=error,
                        reason='the IdP returned no authorization code')
        from utils.encryption import decrypt_required
        kept = json.loads(decrypt_required(secret, 'the sign-in test PKCE verifier') or '{}')
        identity, refusal = login_routes.oidc_sign_in(
            provider, code, kept.get('code_verifier'), kept.get('nonce'))
    else:
        saml_auth = _get_saml_auth(request, provider)
        refusal = login_routes.saml_validate(provider, saml_auth, callback_key)
        identity = None
        if refusal is None and saml_auth.get_last_response_in_response_to() != callback_key:
            refusal = login_routes.Refusal(login_routes.SAML_LOGIN_EXPIRED,
                                           'InResponseTo does not name this test')
        if refusal is None:
            identity, refusal = login_routes.saml_assertion(provider, saml_auth)
    if refusal is not None:
        return dict(base, verdict='refused', stage='protocol', code=refusal.code,
                    reason=_cut(refusal.reason, _DETAIL_LENGTH))

    decision = decide_sso_account(provider, identity.username, identity.email, identity.fullname,
                                  identity.external_data, group_source=identity.group_source)
    report = dict(base, **_identity_report(provider, identity))
    report.update(_decision_report(decision))
    return report


def _identity_report(provider, identity):
    from .ldap_routes import _extract_external_id
    from .helpers import _external_groups
    groups, more = _cut_list(_external_groups(identity.external_data), MAX_VALUES, VALUE_LENGTH)
    source = identity.group_source
    candidates, more_candidates = _cut_list(getattr(source, 'candidates', None) or [],
                                            MAX_NAMES, NAME_LENGTH)
    return {
        'identity': {
            'username': _cut(identity.username),
            'email': _cut(identity.email),
            'fullname': _cut(identity.fullname),
            'external_id': _cut(_extract_external_id(provider, identity.external_data)),
        },
        'groups': groups,
        'groups_more': more,
        'group_source': _cut(getattr(source, 'label', None), _DETAIL_LENGTH),
        'candidates': candidates,
        'candidates_more': more_candidates,
        'not_verified': list(identity.not_verified or []),
    }


def _decision_report(d):
    if d.outcome == OPEN:
        binds = bool(d.rebind or (not d.bind_refusal and d.external_id
                                  and (d.row is None or d.row.external_id != d.external_id)))
        return {
            'verdict': 'accepted', 'stage': None, 'code': None,
            'account': {'outcome': 'open', 'username': _cut(d.user.username),
                        'binds_identity': binds,
                        'takes_back_orphan': d.row is not None and d.row.provider_id is None,
                        'updates_email': d.email is not None, 'updates_name': bool(d.fullname)},
            'role': d.role, 'custom_role': d.custom_role_name,
            'role_change': list(d.role_change) if d.role_change else None,
            'custom_role_change': list(d.custom_change) if d.custom_change else None,
        }
    if d.outcome == CREATE:
        return {
            'verdict': 'accepted', 'stage': None, 'code': None,
            'account': {'outcome': 'create', 'username': _cut(d.username)},
            'role': d.role, 'custom_role': d.custom_role_name,
        }
    if d.outcome == DISABLED:
        return {'verdict': 'refused', 'stage': 'account', 'code': 'account_disabled',
                'account': {'outcome': 'disabled', 'username': _cut(d.user.username)}}
    return {
        'verdict': 'refused', 'stage': 'account', 'code': d.code,
        'detail': _cut(d.refusal, _DETAIL_LENGTH) if d.refusal else None,
        'diagnosis': _cut(d.diagnosis, _DETAIL_LENGTH) if d.diagnosis else None,
        'account': {'outcome': 'refused',
                    'username': _cut(d.user.username) if d.user is not None else None},
    }


def _audit_text(report):
    name = report.get('provider_name')
    head = f"Sign-in test of provider {name!r}" if name else "Sign-in test"
    if report.get('verdict') == 'accepted':
        account = report.get('account') or {}
        what = ('would open the account' if account.get('outcome') == 'open'
                else 'would create the account')
        return f"{head}: accepted, {what} {account.get('username')!r} with role {report.get('role')}"
    return f"{head}: refused ({report.get('code')})"

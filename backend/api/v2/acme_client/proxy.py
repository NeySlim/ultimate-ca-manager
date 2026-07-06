"""
ACME Client Proxy Routes
POST /api/v2/acme/client/proxy/test-connection
POST /api/v2/acme/client/proxy/register
POST /api/v2/acme/client/proxy/unregister
"""

import json
import logging
from flask import request

from api.v2.acme_client import bp, _set_config, _coerce_bool
from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.ssrf_protection import validate_url_not_cloud_metadata
from models import db, SystemConfig
from models.acme_client_account import AcmeClientAccount
from services.acme.acme_proxy_account import resolve_proxy_account
from services.audit_service import AuditService

logger = logging.getLogger(__name__)


def _resolve_test_url(data: dict) -> str:
    """Resolve upstream directory URL for connection test."""
    account_id = data.get('acme_account_id') or data.get('proxy_acme_account_id')
    if account_id is not None:
        try:
            acct = AcmeClientAccount.query.get(int(account_id))
        except (TypeError, ValueError):
            acct = None
        if not acct:
            raise ValueError('ACME CA account not found')
        return acct.directory_url

    url = (data.get('url') or '').strip()
    if url:
        return url

    try:
        return resolve_proxy_account().directory_url
    except RuntimeError:
        pass

    cfg = SystemConfig.query.filter_by(key='acme.proxy.upstream_url').first()
    url = (cfg.value if cfg else '').strip()
    if url:
        return url

    mode_cfg = SystemConfig.query.filter_by(key='acme.proxy.upstream_mode').first()
    mode = mode_cfg.value if mode_cfg else 'staging'
    if mode == 'production':
        return AcmeClientAccount.LE_PRODUCTION_URL
    if mode == 'staging':
        return AcmeClientAccount.LE_STAGING_URL
    raise ValueError('No upstream URL configured')


@bp.route('/api/v2/acme/client/proxy/test-connection', methods=['POST'])
@require_auth(['read:acme'])
def test_proxy_connection():
    """Test connection to upstream ACME directory"""
    import urllib.request
    import ssl

    data = request.json or {}
    try:
        url = _resolve_test_url(data)
    except ValueError as e:
        return error_response(str(e), 400)

    if not url.startswith('https://'):
        return error_response('URL must use HTTPS', 400)

    try:
        validate_url_not_cloud_metadata(url)
    except ValueError:
        return error_response('URL cannot target cloud metadata or loopback', 400)

    cfg = SystemConfig.query.filter_by(key='acme.proxy.verify_ssl').first()
    verify_ssl = _coerce_bool(cfg.value if cfg else None, True)

    try:
        ctx = ssl.create_default_context() if verify_ssl else ssl._create_unverified_context()
        req = urllib.request.Request(url, headers={'User-Agent': 'UCM-ACME-Proxy'})
        resp = urllib.request.urlopen(req, timeout=10, context=ctx)
        directory = json.loads(resp.read().decode('utf-8'))

        meta = directory.get('meta', {})
        ca_name = None
        if 'letsencrypt.org' in url:
            ca_name = "Let's Encrypt"
            if 'staging' in url:
                ca_name += " (Staging)"
        elif 'zerossl.com' in url:
            ca_name = 'ZeroSSL'
        elif 'buypass.com' in url:
            ca_name = 'Buypass'
        elif 'pki.goog' in url:
            ca_name = 'Google Trust Services'
        elif 'harica.gr' in url:
            ca_name = 'HARICA'

        return success_response(data={
            'connected': True,
            'verify_ssl': verify_ssl,
            'ca_name': ca_name,
            'directory_url': url,
            'terms_of_service': meta.get('termsOfService'),
            'website': meta.get('website'),
            'eab_required': meta.get('externalAccountRequired', False),
            'endpoints': list(directory.keys()),
        })
    except urllib.error.URLError as e:
        return error_response(f'Connection failed: {e.reason}', 502)
    except Exception as e:
        logger.error(f"Proxy connection test failed: {e}")
        return error_response('Connection test failed', 502)


@bp.route('/api/v2/acme/client/proxy/register', methods=['POST'])
@require_auth(['write:acme'])
def register_proxy_account():
    """Register the proxy upstream AcmeClientAccount with its CA.

    Uses the selected ``proxy_acme_account_id`` (or explicit ``acme_account_id``
    in the body). Registration credentials and EAB live on the CA account row.
    """
    import re
    from services.acme.acme_client_service import AcmeClientService
    from services.acme.acme_proxy_service import AcmeProxyService

    data = request.json or {}
    email = (data.get('email') or '').strip()
    account_id = data.get('acme_account_id') or data.get('proxy_acme_account_id')

    if data.get('email') == '':
        return error_response('Email is required', 400)

    try:
        account = resolve_proxy_account(
            int(account_id) if account_id is not None else None
        )
    except (TypeError, ValueError):
        return error_response('Invalid acme_account_id', 400)
    except RuntimeError as e:
        return error_response(str(e), 400)

    if not email:
        email = (account.email or '').strip()
    if not email:
        return error_response('Email is required', 400)
    if not isinstance(email, str) or len(email) > 254:
        return error_response('Email is invalid or too long (max 254 chars)', 400)
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return error_response('Invalid email format', 400)
    if not AcmeProxyService._is_public_email_domain(email):
        return error_response(
            'Email domain is not a public domain (LetsEncrypt requires a public TLD). '
            'Use a public email (e.g. @example.com), not .local/.lan/.internal.',
            400,
        )

    _set_config('acme.proxy.acme_account_id', str(account.id), 'AcmeClientAccount id used as ACME proxy upstream')
    _set_config('acme.proxy_email', email, 'Upstream ACME proxy contact email (legacy)')
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to persist proxy account selection: {e}")
        return error_response('Failed to save proxy settings', 500)

    try:
        client = AcmeClientService(account=account)
        success, message, account_url = client.register_account(email)
        if not success:
            AuditService.log_action(
                action='acme_proxy_register',
                resource_type='acme_client',
                resource_name='ACME Proxy',
                details=f'Upstream registration failed: {message}',
                success=False,
            )
            return error_response(message, 502)
    except Exception as e:
        logger.error(f"Unexpected error during proxy registration: {e}")
        return error_response('Registration failed', 500)

    AuditService.log_action(
        action='acme_proxy_register',
        resource_type='acme_client',
        resource_name='ACME Proxy',
        details=f'Registered proxy upstream account {account.label} ({account_url})',
        success=True,
    )

    return success_response(
        data={
            'registered': True,
            'email': email,
            'account_url': account_url,
            'acme_account_id': account.id,
            'account': account.to_dict(),
        },
        message='Proxy upstream account registered',
    )


@bp.route('/api/v2/acme/client/proxy/unregister', methods=['POST'])
@require_auth(['write:acme'])
def unregister_proxy_account():
    """Clear upstream registration on the linked CA account (keeps the account row)."""
    data = request.json or {}
    account_id = data.get('acme_account_id') or data.get('proxy_acme_account_id')

    try:
        account = resolve_proxy_account(
            int(account_id) if account_id is not None else None
        )
    except RuntimeError as e:
        return error_response(str(e), 400)

    account.account_url = None
    for key in ['acme.proxy_email']:
        cfg = SystemConfig.query.filter_by(key=key).first()
        if cfg:
            db.session.delete(cfg)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to clear proxy account: {e}")
        return error_response('Failed to unregister', 500)

    AuditService.log_action(
        action='acme_proxy_unregister',
        resource_type='acme_client',
        resource_name='ACME Proxy',
        details=f'Cleared upstream registration for CA account {account.label}',
        success=True,
    )

    return success_response(
        data={'registered': False, 'acme_account_id': account.id},
        message='Proxy upstream registration cleared',
    )

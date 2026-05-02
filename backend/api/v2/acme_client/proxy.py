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
from services.audit_service import AuditService

logger = logging.getLogger(__name__)


@bp.route('/api/v2/acme/client/proxy/test-connection', methods=['POST'])
@require_auth(['read:acme'])
def test_proxy_connection():
    """Test connection to upstream ACME directory"""
    import urllib.request
    import ssl

    data = request.json or {}
    url = (data.get('url') or '').strip()
    if not url:
        # Use configured upstream URL
        cfg = SystemConfig.query.filter_by(key='acme.proxy.upstream_url').first()
        url = (cfg.value if cfg else '').strip()

    if not url:
        # Also check mode — auto-resolve for staging/production
        mode_cfg = SystemConfig.query.filter_by(key='acme.proxy.upstream_mode').first()
        mode = mode_cfg.value if mode_cfg else 'staging'
        if mode == 'production':
            url = 'https://acme-v02.api.letsencrypt.org/directory'
        elif mode == 'staging':
            url = 'https://acme-staging-v02.api.letsencrypt.org/directory'
        else:
            return error_response('No upstream URL configured', 400)

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

        # Extract CA info from directory
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
    """Register ACME proxy account with configured upstream CA.

    Stores the admin contact email AND triggers actual upstream registration
    so errors (invalid email domain, EAB required, unreachable CA) surface
    immediately rather than on the first client order.
    """
    import re
    from services.acme.acme_proxy_service import AcmeProxyService

    data = request.json or {}
    email = (data.get('email') or '').strip()

    if not email:
        return error_response('Email is required', 400)

    # RFC-ish email format validation
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return error_response('Invalid email format', 400)

    # Reject obviously private/internal TLDs — LE rejects them at the PSL check
    if not AcmeProxyService._is_public_email_domain(email):
        return error_response(
            'Email domain is not a public domain (LetsEncrypt requires a public TLD). '
            'Use a public email (e.g. @example.com), not .local/.lan/.internal.',
            400
        )

    _set_config('acme.proxy_email', email, "Upstream ACME proxy contact email")

    # Clear any stale account so re-registration uses the new email
    for stale_key in ['acme.proxy.account_url']:
        cfg = SystemConfig.query.filter_by(key=stale_key).first()
        if cfg:
            db.session.delete(cfg)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to persist proxy email: {e}")
        return error_response('Failed to save proxy email', 500)

    # Trigger actual upstream registration so errors surface now
    try:
        base_url = request.host_url.rstrip('/')
        svc = AcmeProxyService(base_url)
        account_url = svc.account_url  # Lazy — triggers _register_upstream_account
    except RuntimeError as e:
        logger.error(f"Upstream account registration failed: {e}")
        AuditService.log_action(
            action='acme_proxy_register',
            resource_type='acme_client',
            resource_name='ACME Proxy',
            details=f'Upstream registration failed: {e}',
            success=False
        )
        return error_response(str(e), 502)
    except Exception as e:
        logger.error(f"Unexpected error during proxy registration: {e}")
        return error_response('Registration failed', 500)

    AuditService.log_action(
        action='acme_proxy_register',
        resource_type='acme_client',
        resource_name='ACME Proxy',
        details=f'Registered ACME proxy account: {email} ({account_url})',
        success=True
    )

    return success_response(
        data={'registered': True, 'email': email, 'account_url': account_url},
        message='Proxy account registered'
    )


@bp.route('/api/v2/acme/client/proxy/unregister', methods=['POST'])
@require_auth(['write:acme'])
def unregister_proxy_account():
    """Unregister ACME proxy account — clears email AND stale account URL/key."""
    for key in ['acme.proxy_email', 'acme.proxy.account_url']:
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
        details='Unregistered ACME proxy account',
        success=True
    )

    return success_response(
        data={'registered': False},
        message='Proxy account unregistered'
    )

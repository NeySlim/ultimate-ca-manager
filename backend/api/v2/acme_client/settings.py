"""
ACME Client Settings Routes
GET/PATCH /api/v2/acme/client/settings
"""

import logging
from flask import request

from api.v2.acme_client import bp, _set_config, _coerce_bool
from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from utils.ssrf_protection import validate_url_not_cloud_metadata
from models import db, SystemConfig
from services.audit_service import AuditService

logger = logging.getLogger(__name__)


@bp.route('/api/v2/acme/client/settings', methods=['GET'])
@require_auth(['read:acme'])
def get_settings():
    """Get ACME client settings"""
    # Get configured email
    email_cfg = SystemConfig.query.filter_by(key='acme.client.email').first()

    # Get default environment
    env_cfg = SystemConfig.query.filter_by(key='acme.client.environment').first()

    # Get auto-renewal settings
    renewal_enabled = SystemConfig.query.filter_by(key='acme.client.renewal_enabled').first()
    renewal_days = SystemConfig.query.filter_by(key='acme.client.renewal_days').first()

    # Check if accounts exist
    staging_account = SystemConfig.query.filter_by(key='acme.client.staging.account_url').first()
    production_account = SystemConfig.query.filter_by(key='acme.client.production.account_url').first()

    # LE Proxy settings
    proxy_email_cfg = SystemConfig.query.filter_by(key='acme.proxy_email').first()
    proxy_enabled_cfg = SystemConfig.query.filter_by(key='acme.proxy_enabled').first()

    # EAB settings
    eab_kid_cfg = SystemConfig.query.filter_by(key='acme.client.eab_kid').first()
    eab_hmac_cfg = SystemConfig.query.filter_by(key='acme.client.eab_hmac_key').first()

    # Custom directory URL
    directory_cfg = SystemConfig.query.filter_by(key='acme.client.directory_url').first()

    # Key type settings
    key_type_cfg = SystemConfig.query.filter_by(key='acme.client.key_type').first()
    acct_key_type_cfg = SystemConfig.query.filter_by(key='acme.client.account_key_type').first()

    # Proxy upstream URL and mode
    proxy_upstream_cfg = SystemConfig.query.filter_by(key='acme.proxy.upstream_url').first()
    proxy_mode_cfg = SystemConfig.query.filter_by(key='acme.proxy.upstream_mode').first()
    client_verify_ssl_cfg = SystemConfig.query.filter_by(key='acme.client.verify_ssl').first()
    proxy_verify_ssl_cfg = SystemConfig.query.filter_by(key='acme.proxy.verify_ssl').first()

    # Proxy account registration status
    proxy_account_url_cfg = SystemConfig.query.filter_by(key='acme.proxy.account_url').first()

    # Proxy EAB settings (separate from client EAB — these are for the upstream CA)
    proxy_eab_kid_cfg = SystemConfig.query.filter_by(key='acme.proxy.eab_kid').first()
    proxy_eab_hmac_cfg = SystemConfig.query.filter_by(key='acme.proxy.eab_hmac_key').first()

    # Derive proxy account info
    proxy_account_url = proxy_account_url_cfg.value if proxy_account_url_cfg else None
    proxy_upstream_url = proxy_upstream_cfg.value if proxy_upstream_cfg else None

    return success_response(data={
        'email': email_cfg.value if email_cfg else None,
        'environment': env_cfg.value if env_cfg else 'staging',
        'renewal_enabled': renewal_enabled.value == 'true' if renewal_enabled else True,
        'renewal_days': int(renewal_days.value) if renewal_days else 30,
        'has_staging_account': bool(staging_account),
        'has_production_account': bool(production_account),
        'proxy_enabled': proxy_enabled_cfg.value == 'true' if proxy_enabled_cfg else False,
        'verify_ssl': _coerce_bool(client_verify_ssl_cfg.value if client_verify_ssl_cfg else None, True),
        'proxy_email': proxy_email_cfg.value if proxy_email_cfg else None,
        'proxy_registered': bool(proxy_email_cfg),
        'proxy_upstream_url': proxy_upstream_url,
        'proxy_upstream_mode': proxy_mode_cfg.value if proxy_mode_cfg else 'staging',
        'proxy_verify_ssl': _coerce_bool(proxy_verify_ssl_cfg.value if proxy_verify_ssl_cfg else None, True),
        'proxy_account_url': proxy_account_url,
        'proxy_account_registered': bool(proxy_account_url),
        'proxy_eab_kid': proxy_eab_kid_cfg.value if proxy_eab_kid_cfg else None,
        'proxy_eab_hmac_key_set': bool(proxy_eab_hmac_cfg and proxy_eab_hmac_cfg.value),
        'directory_url': directory_cfg.value if directory_cfg else None,
        'eab_kid': eab_kid_cfg.value if eab_kid_cfg else None,
        'eab_hmac_key_set': bool(eab_hmac_cfg and eab_hmac_cfg.value),
        'key_type': key_type_cfg.value if key_type_cfg else 'RSA-2048',
        'account_key_type': acct_key_type_cfg.value if acct_key_type_cfg else 'ES256',
    })


@bp.route('/api/v2/acme/client/settings', methods=['PATCH'])
@require_auth(['write:acme'])
def update_settings():
    """Update ACME client settings"""
    data = request.json
    if not data:
        return error_response('Request body required', 400)

    updates = []

    if 'email' in data:
        _set_config('acme.client.email', data['email'], 'ACME client contact email')
        updates.append('email')

    if 'environment' in data:
        if data['environment'] not in ['staging', 'production']:
            return error_response('Environment must be staging or production', 400)
        _set_config('acme.client.environment', data['environment'], 'ACME client environment')
        updates.append('environment')

    if 'renewal_enabled' in data:
        _set_config('acme.client.renewal_enabled',
                   'true' if data['renewal_enabled'] else 'false',
                   'ACME auto-renewal enabled')
        updates.append('renewal_enabled')

    if 'renewal_days' in data:
        days = int(data['renewal_days'])
        if days < 1 or days > 60:
            return error_response('Renewal days must be between 1 and 60', 400)
        _set_config('acme.client.renewal_days', str(days), 'ACME renewal days before expiry')
        updates.append('renewal_days')

    if 'proxy_enabled' in data:
        _set_config('acme.proxy_enabled',
                    'true' if data['proxy_enabled'] else 'false',
                    'Let\'s Encrypt proxy enabled')
        updates.append('proxy_enabled')

    if 'verify_ssl' in data:
        try:
            verify_ssl = _coerce_bool(data.get('verify_ssl'), True, strict=True)
        except ValueError:
            return error_response('verify_ssl must be a boolean', 400)
        _set_config(
            'acme.client.verify_ssl',
            'true' if verify_ssl else 'false',
            'ACME client SSL certificate verification'
        )
        updates.append('verify_ssl')

    if 'proxy_verify_ssl' in data:
        try:
            proxy_verify_ssl = _coerce_bool(data.get('proxy_verify_ssl'), True, strict=True)
        except ValueError:
            return error_response('proxy_verify_ssl must be a boolean', 400)
        _set_config(
            'acme.proxy.verify_ssl',
            'true' if proxy_verify_ssl else 'false',
            'ACME proxy upstream SSL certificate verification'
        )
        updates.append('proxy_verify_ssl')

    if 'directory_url' in data:
        url_val = (data['directory_url'] or '').strip()
        if url_val and not url_val.startswith('https://'):
            return error_response('Directory URL must use HTTPS', 400)
        if url_val:
            try:
                validate_url_not_cloud_metadata(url_val)
            except ValueError:
                return error_response('Directory URL cannot target cloud metadata or loopback', 400)
        # Clear stale client account credentials when CA changes
        old_dir = SystemConfig.query.filter_by(key='acme.client.directory_url').first()
        old_val = old_dir.value if old_dir else ''
        if url_val != old_val:
            for stale_key in [
                'acme.client.staging.account_url', 'acme.client.staging.account_key',
                'acme.client.production.account_url', 'acme.client.production.account_key',
            ]:
                stale = SystemConfig.query.filter_by(key=stale_key).first()
                if stale:
                    db.session.delete(stale)
            logger.info(f"Cleared client account credentials due to directory URL change")
        _set_config('acme.client.directory_url', url_val, 'Custom ACME directory URL')
        updates.append('directory_url')

    if 'eab_kid' in data:
        _set_config('acme.client.eab_kid', data['eab_kid'] or '', 'ACME EAB Key ID')
        updates.append('eab_kid')

    if 'eab_hmac_key' in data:
        _set_config('acme.client.eab_hmac_key', data['eab_hmac_key'] or '', 'ACME EAB HMAC Key')
        updates.append('eab_hmac_key')

    if 'key_type' in data:
        valid_key_types = ['RSA-2048', 'RSA-4096', 'EC-P256', 'EC-P384']
        if data['key_type'] not in valid_key_types:
            return error_response(f'Key type must be one of: {", ".join(valid_key_types)}', 400)
        _set_config('acme.client.key_type', data['key_type'], 'Certificate key type')
        updates.append('key_type')

    if 'account_key_type' in data:
        valid_acct_types = ['RS256', 'ES256', 'ES384']
        if data['account_key_type'] not in valid_acct_types:
            return error_response(f'Account key type must be one of: {", ".join(valid_acct_types)}', 400)
        _set_config('acme.client.account_key_type', data['account_key_type'], 'Account key algorithm')
        updates.append('account_key_type')

    if 'proxy_upstream_url' in data:
        url_val = (data['proxy_upstream_url'] or '').strip()
        if url_val and not url_val.startswith('https://'):
            return error_response('Proxy upstream URL must use HTTPS', 400)
        if url_val:
            try:
                validate_url_not_cloud_metadata(url_val)
            except ValueError:
                return error_response('Proxy upstream URL cannot target cloud metadata or loopback', 400)
        # Clear stale proxy account credentials when upstream CA changes
        old_upstream = SystemConfig.query.filter_by(key='acme.proxy.upstream_url').first()
        old_val = old_upstream.value if old_upstream else ''
        if url_val != old_val:
            for stale_key in ['acme.proxy.account_url', 'acme.proxy.account_key']:
                stale = SystemConfig.query.filter_by(key=stale_key).first()
                if stale:
                    db.session.delete(stale)
            logger.info(f"Cleared proxy account credentials due to upstream URL change")
        _set_config('acme.proxy.upstream_url', url_val, 'ACME proxy upstream directory URL')
        updates.append('proxy_upstream_url')

    if 'proxy_upstream_mode' in data:
        mode = data['proxy_upstream_mode']
        if mode not in ['production', 'staging', 'custom']:
            return error_response('Proxy upstream mode must be production, staging, or custom', 400)
        _set_config('acme.proxy.upstream_mode', mode, 'ACME proxy upstream mode')
        # Auto-set upstream URL based on mode
        mode_urls = {
            'production': 'https://acme-v02.api.letsencrypt.org/directory',
            'staging': 'https://acme-staging-v02.api.letsencrypt.org/directory',
        }
        if mode in mode_urls:
            new_url = mode_urls[mode]
            old_upstream = SystemConfig.query.filter_by(key='acme.proxy.upstream_url').first()
            old_val = old_upstream.value if old_upstream else ''
            if new_url != old_val:
                for stale_key in ['acme.proxy.account_url', 'acme.proxy.account_key']:
                    stale = SystemConfig.query.filter_by(key=stale_key).first()
                    if stale:
                        db.session.delete(stale)
                logger.info(f"Cleared proxy account credentials due to mode change to {mode}")
            _set_config('acme.proxy.upstream_url', new_url, 'ACME proxy upstream directory URL')
        elif mode == 'custom':
            # Clear stale URL from previous staging/production mode
            _set_config('acme.proxy.upstream_url', '', 'ACME proxy upstream directory URL')
            for stale_key in ['acme.proxy.account_url', 'acme.proxy.account_key']:
                stale = SystemConfig.query.filter_by(key=stale_key).first()
                if stale:
                    db.session.delete(stale)
            logger.info("Cleared proxy upstream URL and account for custom mode")
        updates.append('proxy_upstream_mode')

    if 'reset_proxy_account' in data and data['reset_proxy_account']:
        for reset_key in ['acme.proxy.account_url', 'acme.proxy.account_key']:
            cfg = SystemConfig.query.filter_by(key=reset_key).first()
            if cfg:
                db.session.delete(cfg)
        logger.info("Proxy account credentials reset by user")
        updates.append('reset_proxy_account')

    if 'proxy_eab_kid' in data:
        _set_config('acme.proxy.eab_kid', data['proxy_eab_kid'] or '', 'ACME proxy EAB Key ID')
        updates.append('proxy_eab_kid')

    if 'proxy_eab_hmac_key' in data:
        _set_config('acme.proxy.eab_hmac_key', data['proxy_eab_hmac_key'] or '', 'ACME proxy EAB HMAC Key')
        updates.append('proxy_eab_hmac_key')

    ok, _err = safe_commit(logger, "Failed to update ACME client settings")
    if not ok:
        return _err

    AuditService.log_action(
        action='acme_client_settings_update',
        resource_type='acme_client',
        resource_name='ACME Client Settings',
        details=f'Updated ACME client settings: {", ".join(updates)}' if updates else 'No changes',
        success=True
    )

    return success_response(
        message=f'Settings updated: {", ".join(updates)}' if updates else 'No changes'
    )

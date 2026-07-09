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
from utils.acme_public_url import get_acme_public_base, get_acme_proxy_public_base
from models import db, SystemConfig
from utils.acme_debug import clear_acme_debug_cache
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
    from models import AcmeClientAccount
    staging_account = AcmeClientAccount.query.filter_by(
        directory_url=AcmeClientAccount.LE_STAGING_URL
    ).first()
    production_account = AcmeClientAccount.query.filter_by(
        directory_url=AcmeClientAccount.LE_PRODUCTION_URL
    ).first()

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
    proxy_account_id_cfg = SystemConfig.query.filter_by(key='acme.proxy.acme_account_id').first()
    client_verify_ssl_cfg = SystemConfig.query.filter_by(key='acme.client.verify_ssl').first()
    proxy_verify_ssl_cfg = SystemConfig.query.filter_by(key='acme.proxy.verify_ssl').first()

    # Proxy account registration status
    proxy_account_url_cfg = SystemConfig.query.filter_by(key='acme.proxy.account_url').first()

    # Proxy EAB settings (separate from client EAB — these are for the upstream CA)
    proxy_eab_kid_cfg = SystemConfig.query.filter_by(key='acme.proxy.eab_kid').first()
    proxy_eab_hmac_cfg = SystemConfig.query.filter_by(key='acme.proxy.eab_hmac_key').first()

    # Derive proxy account info from linked AcmeClientAccount when set
    proxy_acme_account_id = None
    proxy_account = None
    if proxy_account_id_cfg and proxy_account_id_cfg.value:
        try:
            proxy_acme_account_id = int(proxy_account_id_cfg.value)
            proxy_account = db.session.get(AcmeClientAccount, proxy_acme_account_id)
        except (TypeError, ValueError):
            proxy_acme_account_id = None

    if proxy_account:
        proxy_upstream_url = proxy_account.directory_url
        proxy_upstream_mode = proxy_account.derived_environment()
        proxy_account_url = proxy_account.account_url
        proxy_account_registered = proxy_account.is_registered()
        proxy_eab_kid = proxy_account.eab_kid
        proxy_eab_hmac_set = bool(proxy_account.eab_hmac_key)
    else:
        proxy_account_url = proxy_account_url_cfg.value if proxy_account_url_cfg else None
        proxy_upstream_url = proxy_upstream_cfg.value if proxy_upstream_cfg else None
        proxy_upstream_mode = proxy_mode_cfg.value if proxy_mode_cfg else 'staging'
        proxy_account_registered = bool(proxy_account_url)
        proxy_eab_kid = proxy_eab_kid_cfg.value if proxy_eab_kid_cfg else None
        proxy_eab_hmac_set = bool(proxy_eab_hmac_cfg and proxy_eab_hmac_cfg.value)
    dns_timeout_cfg = SystemConfig.query.filter_by(key='acme.client.dns_propagation_timeout').first()
    debug_logging_cfg = SystemConfig.query.filter_by(key='acme.client.debug_logging').first()
    try:
        dns_timeout = int(dns_timeout_cfg.value) if dns_timeout_cfg else 120
    except (ValueError, TypeError):
        dns_timeout = 120

    return success_response(data={
        'email': email_cfg.value if email_cfg else None,
        'environment': env_cfg.value if env_cfg else 'staging',
        'renewal_enabled': renewal_enabled.value == 'true' if renewal_enabled else True,
        'renewal_days': int(renewal_days.value) if renewal_days else 30,
        'dns_propagation_timeout': dns_timeout,
        'debug_logging': _coerce_bool(debug_logging_cfg.value if debug_logging_cfg else None, False),
        'has_staging_account': bool(staging_account and staging_account.is_registered()),
        'has_production_account': bool(production_account and production_account.is_registered()),
        'proxy_enabled': proxy_enabled_cfg.value == 'true' if proxy_enabled_cfg else False,
        'verify_ssl': _coerce_bool(client_verify_ssl_cfg.value if client_verify_ssl_cfg else None, True),
        'proxy_email': proxy_email_cfg.value if proxy_email_cfg else None,
        'proxy_registered': bool(proxy_email_cfg),
        'proxy_upstream_url': proxy_upstream_url,
        'proxy_upstream_mode': proxy_upstream_mode,
        'proxy_acme_account_id': proxy_acme_account_id,
        'proxy_verify_ssl': _coerce_bool(proxy_verify_ssl_cfg.value if proxy_verify_ssl_cfg else None, True),
        'proxy_account_url': proxy_account_url,
        'proxy_account_registered': proxy_account_registered,
        'proxy_eab_kid': proxy_eab_kid,
        'proxy_eab_hmac_key_set': proxy_eab_hmac_set,
        'directory_url': directory_cfg.value if directory_cfg else None,
        'eab_kid': eab_kid_cfg.value if eab_kid_cfg else None,
        'eab_hmac_key_set': bool(eab_hmac_cfg and eab_hmac_cfg.value),
        'key_type': key_type_cfg.value if key_type_cfg else 'RSA-2048',
        'account_key_type': acct_key_type_cfg.value if acct_key_type_cfg else 'ES256',
        'acme_public_base_url': get_acme_public_base(request),
        'acme_proxy_public_base_url': get_acme_proxy_public_base(request),
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

        # Update is_default flag on AcmeClientAccount rows
        from models import AcmeClientAccount
        target_url = (AcmeClientAccount.LE_STAGING_URL if data['environment'] == 'staging'
                      else AcmeClientAccount.LE_PRODUCTION_URL)
        # Clear all defaults, then set on target (creates row if missing)
        AcmeClientAccount.query.update({AcmeClientAccount.is_default: False})
        target = AcmeClientAccount.query.filter_by(directory_url=target_url).first()
        if target:
            target.is_default = True
        else:
            # Will be created by AcmeClientService on first use; nothing to set here
            pass

    if 'renewal_enabled' in data:
        _set_config('acme.client.renewal_enabled',
                   'true' if data['renewal_enabled'] else 'false',
                   'ACME auto-renewal enabled')
        updates.append('renewal_enabled')

    if 'renewal_days' in data:
        try:
            days = int(data['renewal_days'])
        except (TypeError, ValueError):
            return error_response('Renewal days must be an integer', 400)
        if days < 1 or days > 60:
            return error_response('Renewal days must be between 1 and 60', 400)
        _set_config('acme.client.renewal_days', str(days), 'ACME renewal days before expiry')
        updates.append('renewal_days')

    if 'dns_propagation_timeout' in data:
        try:
            dns_to = int(data['dns_propagation_timeout'])
        except (TypeError, ValueError):
            return error_response('DNS propagation timeout must be an integer', 400)
        if dns_to < 0 or dns_to > 3600:
            return error_response('DNS propagation timeout must be between 0 and 3600 seconds', 400)
        _set_config('acme.client.dns_propagation_timeout', str(dns_to),
                    'Seconds to self-check DNS-01 TXT propagation before submitting to the CA')
        updates.append('dns_propagation_timeout')

    if 'debug_logging' in data:
        try:
            debug_logging = _coerce_bool(data.get('debug_logging'), False, strict=True)
        except ValueError:
            return error_response('debug_logging must be a boolean', 400)
        _set_config(
            'acme.client.debug_logging',
            'true' if debug_logging else 'false',
            'Emit verbose ACME/DNS diagnostic logs at INFO level for troubleshooting',
        )
        clear_acme_debug_cache()
        updates.append('debug_logging')

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
            # Clear creds on any account row that targets the OLD directory URL
            from models import AcmeClientAccount
            if old_val:
                old_account = AcmeClientAccount.query.filter_by(directory_url=old_val).first()
                if old_account:
                    old_account.account_url = None
                    old_account.account_key = None
                    logger.info(f"Cleared AcmeClientAccount creds for {old_val} (URL changed)")
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

    if 'proxy_acme_account_id' in data:
        from models import AcmeClientAccount
        raw = data.get('proxy_acme_account_id')
        if raw is None or raw == '':
            cfg = SystemConfig.query.filter_by(key='acme.proxy.acme_account_id').first()
            if cfg:
                db.session.delete(cfg)
            updates.append('proxy_acme_account_id')
        else:
            try:
                account_id = int(raw)
            except (TypeError, ValueError):
                return error_response('proxy_acme_account_id must be an integer', 400)
            acct = db.session.get(AcmeClientAccount, account_id)
            if not acct:
                return error_response('ACME CA account not found', 404)
            _set_config(
                'acme.proxy.acme_account_id',
                str(account_id),
                'AcmeClientAccount id used as ACME proxy upstream',
            )
            # Keep legacy URL/mode in sync for older API consumers
            _set_config('acme.proxy.upstream_url', acct.directory_url, 'ACME proxy upstream directory URL')
            _set_config(
                'acme.proxy.upstream_mode',
                acct.derived_environment(),
                'ACME proxy upstream mode',
            )
            updates.append('proxy_acme_account_id')

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
        from models import AcmeClientAccount
        account_id_cfg = SystemConfig.query.filter_by(key='acme.proxy.acme_account_id').first()
        if account_id_cfg and account_id_cfg.value:
            try:
                acct = db.session.get(AcmeClientAccount, int(account_id_cfg.value))
                if acct:
                    acct.account_url = None
                    acct.account_key = None
            except (TypeError, ValueError):
                pass
        for reset_key in ['acme.proxy.account_url', 'acme.proxy.account_key']:
            cfg = SystemConfig.query.filter_by(key=reset_key).first()
            if cfg:
                db.session.delete(cfg)
        logger.info("Proxy upstream account credentials reset by user")
        updates.append('reset_proxy_account')

    if 'proxy_eab_kid' in data:
        kid_val = data['proxy_eab_kid'] or ''
        _set_config('acme.proxy.eab_kid', kid_val, 'ACME proxy EAB Key ID')
        account_id_cfg = SystemConfig.query.filter_by(key='acme.proxy.acme_account_id').first()
        if account_id_cfg and account_id_cfg.value:
            try:
                from models import AcmeClientAccount
                acct = db.session.get(AcmeClientAccount, int(account_id_cfg.value))
                if acct:
                    acct.eab_kid = kid_val or None
                    if not kid_val and 'proxy_eab_hmac_key' in data and not data.get('proxy_eab_hmac_key'):
                        acct.eab_hmac_key = None
            except (TypeError, ValueError):
                pass
        updates.append('proxy_eab_kid')

    if 'proxy_eab_hmac_key' in data:
        hmac_val = data['proxy_eab_hmac_key'] or ''
        _set_config('acme.proxy.eab_hmac_key', hmac_val, 'ACME proxy EAB HMAC Key')
        account_id_cfg = SystemConfig.query.filter_by(key='acme.proxy.acme_account_id').first()
        if account_id_cfg and account_id_cfg.value:
            try:
                from models import AcmeClientAccount
                acct = db.session.get(AcmeClientAccount, int(account_id_cfg.value))
                if acct:
                    acct.eab_hmac_key = hmac_val or None
                    if not hmac_val and 'proxy_eab_kid' in data and not data.get('proxy_eab_kid'):
                        acct.eab_kid = None
            except (TypeError, ValueError):
                pass
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

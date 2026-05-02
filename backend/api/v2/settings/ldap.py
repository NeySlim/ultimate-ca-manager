"""
Settings - LDAP integration routes
"""

from flask import request
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, SystemConfig
from services.audit_service import AuditService
import logging

from . import bp

logger = logging.getLogger(__name__)


# ============================================================================
# LDAP Integration
# ============================================================================

@bp.route('/api/v2/settings/ldap', methods=['GET'])
@require_auth(['read:settings'])
def get_ldap_settings():
    """Get LDAP configuration"""
    return success_response(
        data={
            'enabled': False,
            'server': None,
            'port': 389,
            'use_ssl': False,
            'base_dn': None,
            'bind_dn': None,
            'user_filter': '(uid={username})',
            'sync_enabled': False
        }
    )


@bp.route('/api/v2/settings/ldap', methods=['PATCH'])
@require_auth(['write:settings'])
def update_ldap_settings():
    """Update LDAP configuration"""
    data = request.json

    if not data:
        return error_response('No data provided', 400)

    # Save each LDAP setting — allowlist to prevent arbitrary key injection
    ALLOWED_LDAP_KEYS = {
        'server', 'port', 'use_ssl', 'use_starttls', 'base_dn', 'bind_dn',
        'bind_password', 'user_filter', 'username_attribute', 'email_attribute',
        'display_name_attribute', 'group_filter', 'group_attribute',
        'sync_enabled', 'sync_interval', 'default_role', 'enabled',
        'timeout', 'verify_ssl', 'ca_cert'
    }
    for key, value in data.items():
        if key not in ALLOWED_LDAP_KEYS:
            continue
        config = SystemConfig.query.filter_by(key=f'ldap_{key}').first()
        if config:
            config.value = str(value) if value is not None else ''
        else:
            config = SystemConfig(key=f'ldap_{key}', value=str(value) if value is not None else '')
            db.session.add(config)

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update LDAP settings: {e}")
        return error_response('Failed to update LDAP settings', 500)

    AuditService.log_action(
        action='settings_update',
        resource_type='settings',
        resource_name='LDAP Settings',
        details='Updated LDAP settings',
        success=True
    )

    return success_response(
        data=data,
        message='LDAP settings updated successfully'
    )


@bp.route('/api/v2/settings/ldap/test', methods=['POST'])
@require_auth(['write:settings'])
def test_ldap_connection():
    """Test LDAP connection"""
    data = request.json or {}

    # LDAP testing requires ldap3 library
    try:
        import ldap3
        from ldap3 import Server, Connection, ALL

        server_url = data.get('server', 'localhost')
        port = data.get('port', 389)
        use_ssl = data.get('use_ssl', False)
        bind_dn = data.get('bind_dn')
        bind_password = data.get('bind_password')

        server = Server(server_url, port=port, use_ssl=use_ssl, get_info=ALL)
        conn = Connection(server, bind_dn, bind_password, auto_bind=True)

        return success_response(
            data={'connected': True, 'server_info': str(server.info)},
            message='LDAP connection successful'
        )
    except ImportError:
        return error_response('LDAP support not installed (pip install ldap3)', 501)
    except Exception as e:
        logger.error(f"LDAP connection test failed: {e}")
        return error_response('LDAP connection failed', 400)

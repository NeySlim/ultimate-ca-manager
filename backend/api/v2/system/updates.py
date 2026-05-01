"""
System Updates Operations
"""

from . import bp
from flask import request
from auth.unified import require_auth
from utils.response import success_response, error_response
from services.audit_service import AuditService
import os
import logging

logger = logging.getLogger(__name__)


@bp.route('/api/v2/system/updates/check', methods=['GET'])
@require_auth(['admin:system'])
def check_updates():
    """Check for available updates"""
    try:
        from services.updates import check_for_updates
        
        include_prereleases = request.args.get('include_prereleases', 'false').lower() == 'true'
        include_dev = request.args.get('include_dev', 'false').lower() == 'true'
        force = request.args.get('force', 'false').lower() == 'true'
        result = check_for_updates(include_prereleases=include_prereleases, include_dev=include_dev, force=force)
        result['can_auto_update'] = os.getenv('UCM_DOCKER') != '1'
        
        return success_response(data=result)
    except Exception as e:
        logger.error(f"Failed to check for updates: {e}")
        return error_response("Failed to check for updates", 500)


@bp.route('/api/v2/system/updates/install', methods=['POST'])
@require_auth(['admin:system'])
def install_update():
    """Download and install an update"""
    if os.getenv('UCM_DOCKER') == '1':
        return error_response(
            "Auto-update is not available in Docker. Pull the new image instead: "
            "docker pull ghcr.io/neyslim/ultimate-ca-manager:latest", 400
        )
    
    try:
        from services.updates import check_for_updates, download_update, install_update as do_install
        
        # Get update info
        include_prereleases = request.json.get('include_prereleases', False)
        include_dev = request.json.get('include_dev', False)
        update_info = check_for_updates(include_prereleases=include_prereleases, include_dev=include_dev)
        
        if not update_info.get('update_available'):
            return error_response("No update available", 400)
        
        if not update_info.get('download_url'):
            return error_response("No download URL available for this platform", 400)
        
        # Download
        package_path = download_update(
            update_info['download_url'],
            update_info['package_name']
        )
        
        # Install (this will restart the service)
        do_install(package_path)
        
        # Log the update
        AuditService.log_action(
            action='settings_update',
            resource_type='system',
            resource_id='ucm',
            resource_name='UCM Update',
            details=f"Updated from {update_info['current_version']} to {update_info['latest_version']}"
        )
        
        return success_response(
            message=f"Update to {update_info['latest_version']} initiated. Service will restart shortly."
        )
    except Exception as e:
        logger.error(f"Update failed: {e}")
        return error_response("Update failed", 500)


@bp.route('/api/v2/system/updates/version', methods=['GET'])
def get_version():
    """Get current version info (public endpoint)"""
    from services.updates import get_current_version
    
    return success_response(data={
        'version': get_current_version()
    })

"""
System Updates Operations
"""

from . import bp
from flask import request, g
from auth.unified import require_auth
from utils.ha import ha_enabled
from utils.response import success_response, error_response
from services.audit_service import AuditService
import logging

logger = logging.getLogger(__name__)


def _actor():
    """Authenticated principal for update attribution (review S-04) — never
    hardcode 'admin': another admin user or an API key owner must be credited
    consistently in the manifest, the initiated event and the final result."""
    for attr in ('current_user', 'user'):
        obj = getattr(g, attr, None)
        if obj is not None:
            username = getattr(obj, 'username', None) or (
                obj.get('username') if isinstance(obj, dict) else None)
            if username:
                return username
    return 'admin'


def _with_update_state(data):
    """can_auto_update plus, in HA, the rolling update campaign the screen shows."""
    from services.updates import is_container_install
    data['can_auto_update'] = not is_container_install()
    data['ha_mode'] = ha_enabled()
    data['update_campaign'] = None
    if data['ha_mode']:
        from services.update_campaign import public_view, read_campaign
        data['update_campaign'] = public_view(read_campaign()[1])
    return data


@bp.route('/api/v2/system/updates/check', methods=['GET'])
@require_auth(['admin:system'])
def check_updates():
    """Check for available updates"""
    try:
        from services.updates import check_for_updates

        include_prereleases = request.args.get('include_prereleases', 'false').lower() == 'true'
        include_dev = request.args.get('include_dev', 'false').lower() == 'true'
        force = request.args.get('force', 'false').lower() == 'true'
        result = _with_update_state(
            check_for_updates(include_prereleases=include_prereleases, include_dev=include_dev, force=force))

        return success_response(data=result)
    except Exception as e:
        logger.error(f"Failed to check for updates: {e}")
        return error_response("Failed to check for updates", 500)


@bp.route('/api/v2/system/updates/install', methods=['POST'])
@require_auth(['admin:system'])
def install_update():
    """Download and install an update; in HA, start a rolling update of every node"""
    from services.updates import CONTAINER_HA_REFUSAL, is_container_install
    in_ha = ha_enabled()
    if is_container_install():
        if in_ha:
            return error_response(CONTAINER_HA_REFUSAL, 400)
        return error_response(
            "Auto-update is not available in Docker. Pull the new image instead: "
            "docker pull ghcr.io/neyslim/ultimate-ca-manager:latest", 400
        )

    try:
        from services.updates import (
            check_for_updates, download_update, fetch_expected_sha256,
            install_update as do_install,
        )

        # Get update info
        include_prereleases = request.json.get('include_prereleases', False)
        include_dev = request.json.get('include_dev', False)
        update_info = check_for_updates(include_prereleases=include_prereleases, include_dev=include_dev)

        if not update_info.get('update_available'):
            return error_response("No update available", 400)

        if not update_info.get('download_url'):
            return error_response("No download URL available for this platform", 400)

        # Resolve the published SHA256. A release that publishes one must
        # verify — a fetch failure or a missing entry refuses the install
        # rather than silently downgrading to unverified.
        expected_sha256 = None
        checksum_note = 'no checksum published for this release'
        if update_info.get('checksum_url'):
            try:
                expected_sha256 = fetch_expected_sha256(
                    update_info['checksum_url'], update_info['package_name']
                )
            except Exception as e:
                logger.error(f"Checksum fetch failed: {e}")
                return error_response(
                    "Could not retrieve the release checksum: install refused", 502
                )
            if not expected_sha256:
                return error_response(
                    "Release checksum does not cover this package: install refused", 502
                )
            checksum_note = 'SHA256 verified'

        if in_ha:
            return _start_rolling_update(update_info, expected_sha256)

        # Download (verifies the digest on the fly when one is expected)
        package_path = download_update(
            update_info['download_url'],
            update_info['package_name'],
            expected_sha256=expected_sha256,
        )

        # Install (this will restart the service). The truthful outcome —
        # system.update_installed / system.update_failed — is emitted after
        # the restart from the watcher's durable result.
        actor = _actor()
        do_install(
            package_path,
            to_version=update_info['latest_version'],
            initiated_by=actor,
        )
        from services.webhook_service import emit_update_initiated
        emit_update_initiated({
            'current_version': update_info['current_version'],
            'latest_version': update_info['latest_version'],
        }, actor=actor)

        # Log the update
        AuditService.log_action(
            action='settings_update',
            resource_type='system',
            resource_id='ucm',
            resource_name='UCM Update',
            details=(
                f"Update from {update_info['current_version']} to "
                f"{update_info['latest_version']} triggered ({checksum_note}), "
                f"performed by the update watcher on restart"
            )
        )

        return success_response(
            message=f"Update to {update_info['latest_version']} initiated. Service will restart shortly."
        )
    except Exception as e:
        logger.error(f"Update failed: {e}")
        return error_response("Update failed", 500)


def _start_rolling_update(update_info, expected_sha256):
    """HA: no local download here, each node fetches and verifies the package on its turn."""
    from services import update_campaign
    started, message, campaign = update_campaign.start_campaign(
        update_info['latest_version'], update_info['download_url'], update_info['package_name'],
        expected_sha256, _actor())
    if not started:
        return error_response(message, 409)
    update_campaign.campaign_tick()
    return success_response(data={'campaign': update_campaign.public_view(update_campaign.read_campaign()[1])},
                            message=message)


@bp.route('/api/v2/system/updates/campaign', methods=['GET'])
@require_auth(['admin:system'])
def get_update_campaign():
    """HA rolling update state: target, nodes done, node in progress, failure and its reason"""
    from services.update_campaign import public_view, read_campaign
    return success_response(data={'ha': ha_enabled(), 'campaign': public_view(read_campaign()[1])})


@bp.route('/api/v2/system/updates/campaign/resume', methods=['POST'])
@require_auth(['admin:system'])
def resume_update_campaign():
    """Resume a stopped rolling update once the failed node was fixed"""
    if not ha_enabled():
        return error_response("Rolling updates exist only in HA mode", 400)
    from services import update_campaign
    resumed, message, campaign = update_campaign.resume_campaign(_actor())
    if not resumed:
        return error_response(message, 409)
    update_campaign.campaign_tick()
    return success_response(data={'campaign': update_campaign.public_view(update_campaign.read_campaign()[1])},
                            message=message)


@bp.route('/api/v2/system/updates/settings', methods=['GET'])
@require_auth(['admin:system'])
def get_update_settings():
    """Get update automation settings (#301)"""
    from services.updates import get_update_settings as read_settings

    return success_response(data=_with_update_state(read_settings()))


@bp.route('/api/v2/system/updates/settings', methods=['PATCH'])
@require_auth(['admin:system'])
def update_update_settings():
    """Update the update automation settings (#301)"""
    from services.updates import (
        UPDATE_CHANNEL_KEY, AUTO_UPDATE_ENABLED_KEY, AUTO_UPDATE_HOUR_KEY,
        UPDATE_POPUP_ENABLED_KEY, UPDATE_POPUP_BASELINE_KEY, _cfg_set_many,
        get_current_version, get_update_settings as read_settings,
    )

    data = request.json or {}

    if 'channel' in data:
        if data['channel'] not in ('stable', 'rc'):
            return error_response("channel must be 'stable' or 'rc'", 400)
    if 'hour' in data:
        if not isinstance(data['hour'], int) or not 0 <= data['hour'] <= 23:
            return error_response("hour must be an integer between 0 and 23", 400)
    if 'auto_install' in data and not isinstance(data['auto_install'], bool):
        return error_response("auto_install must be a boolean", 400)
    if 'popup_enabled' in data and not isinstance(data['popup_enabled'], bool):
        return error_response("popup_enabled must be a boolean", 400)
    from services.updates import is_container_install
    if data.get('auto_install') and is_container_install():
        return error_response(
            "Auto-update is not available in Docker. Pull the new image instead.", 400
        )

    # All fields in one transaction: a commit failure must yield an error,
    # never a partially saved config with a success audit (review F-06)
    current_settings = read_settings()
    changes = {}
    if 'channel' in data:
        changes[UPDATE_CHANNEL_KEY] = data['channel']
    if 'hour' in data:
        changes[AUTO_UPDATE_HOUR_KEY] = str(data['hour'])
    if 'auto_install' in data:
        changes[AUTO_UPDATE_ENABLED_KEY] = 'true' if data['auto_install'] else 'false'
    if 'popup_enabled' in data:
        popup_enabled = data['popup_enabled']
        changes[UPDATE_POPUP_ENABLED_KEY] = 'true' if popup_enabled else 'false'
        if popup_enabled and not current_settings.get('popup_enabled'):
            changes[UPDATE_POPUP_BASELINE_KEY] = get_current_version()
        elif not popup_enabled:
            changes[UPDATE_POPUP_BASELINE_KEY] = ''
    try:
        _cfg_set_many(changes)
    except Exception as e:
        logger.error(f"Failed to persist update settings: {e}")
        return error_response("Failed to save update settings", 500)

    AuditService.log_action(
        action='settings_update', resource_type='system', resource_id='ucm',
        resource_name='UCM Update Settings',
        details=f"Update automation settings changed: {sorted(data.keys())}",
        success=True,
    )
    return success_response(data=_with_update_state(read_settings()), message='Update settings saved')


@bp.route('/api/v2/system/updates/whatsnew', methods=['GET'])
@require_auth()
def whats_new():
    """Payload for the optional post-update popup (#308).

    Any authenticated user may ask; with the popup disabled the answer is a
    fast {'enabled': False} with no external call. Release notes for the
    running version come from the cached GitHub release lookup and degrade
    to an empty string on hosts without egress.
    """
    from services.updates import (
        get_current_version, get_installed_at,
        get_update_settings as read_settings,
    )

    settings = read_settings()
    if not settings.get('popup_enabled'):
        return success_response(data={'enabled': False})

    data = {
        'enabled': True,
        'version': get_current_version(),
        'baseline_version': settings.get('popup_baseline_version') or '',
        'installed_at': get_installed_at(),
        'release_notes': '',
        'published_at': None,
    }
    try:
        from services.updates import check_for_updates
        result = check_for_updates() or {}
        data['release_notes'] = result.get('current_release_notes') or ''
        data['published_at'] = result.get('current_published_at')
    except Exception as e:
        logger.warning(f"whatsnew: release notes unavailable: {e}")
    return success_response(data=data)


@bp.route('/api/v2/system/updates/version', methods=['GET'])
def get_version():
    """Get current version info (public endpoint)"""
    from services.updates import get_current_version

    return success_response(data={
        'version': get_current_version()
    })

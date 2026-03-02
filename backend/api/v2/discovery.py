"""
Discovery API v2
Scan profiles, async scanning, results, history.
"""
import ipaddress
import logging

from flask import Blueprint, request, current_app, g
from auth.unified import require_auth
from utils.response import success_response, error_response, created_response, no_content_response

logger = logging.getLogger(__name__)

bp = Blueprint('discovery', __name__)

import re
_VALID_TARGET_RE = re.compile(r'^[a-zA-Z0-9._:\-\[\]/]+$')


def _safe_int(val, default, lo=None, hi=None):
    """Safely cast to int with bounds. Returns default on invalid input."""
    try:
        v = int(val)
    except (ValueError, TypeError):
        return default
    if lo is not None:
        v = max(v, lo)
    if hi is not None:
        v = min(v, hi)
    return v

_service = None


def _get_service():
    global _service
    if _service is None:
        from services.discovery_service import DiscoveryService
        _service = DiscoveryService()
    return _service


def _audit(action, resource_name='', resource_id=None, details=''):
    """Helper to log discovery audit events."""
    try:
        from services.audit_service import AuditService
        AuditService.log_action(
            action=action,
            resource_type='discovery',
            resource_id=resource_id,
            resource_name=resource_name,
            details=details,
            success=True,
        )
    except Exception:
        pass


# ==================== Scan Profiles ====================

@bp.route('/api/v2/discovery/profiles', methods=['GET'])
@require_auth(['read:certificates'])
def list_profiles():
    """List all scan profiles."""
    svc = _get_service()
    return success_response(data=svc.get_profiles())


@bp.route('/api/v2/discovery/profiles', methods=['POST'])
@require_auth(['admin:system'])
def create_profile():
    """Create a new scan profile."""
    data = request.get_json()
    if not data or not data.get('name'):
        return error_response("Profile name is required", 400)
    if not data.get('targets') or not isinstance(data['targets'], list):
        return error_response("Targets must be a non-empty list", 400)
    if len(data['targets']) > 1000:
        return error_response("Maximum 1000 targets per profile", 400)
    # SEC-10: Validate target format
    for t in data['targets']:
        if not isinstance(t, str) or not _VALID_TARGET_RE.match(t.strip()):
            return error_response(f"Invalid target format: targets must be hostnames, IPs, or CIDR notation", 400)
    svc = _get_service()
    try:
        profile = svc.create_profile(data)
        _audit('discovery_profile_created', resource_name=data['name'],
               resource_id=profile.get('id'), details=f"Targets: {', '.join(data['targets'][:5])}")
        return created_response(data=profile, message="Profile created")
    except Exception as e:
        if 'UNIQUE' in str(e):
            return error_response("A profile with this name already exists", 409)
        logger.error(f"Failed to create profile: {e}")
        return error_response("Failed to create profile", 500)


@bp.route('/api/v2/discovery/profiles/<int:profile_id>', methods=['GET'])
@require_auth(['read:certificates'])
def get_profile(profile_id):
    """Get a single scan profile."""
    svc = _get_service()
    profile = svc.get_profile(profile_id)
    if not profile:
        return error_response("Profile not found", 404)
    return success_response(data=profile)


@bp.route('/api/v2/discovery/profiles/<int:profile_id>', methods=['PUT'])
@require_auth(['admin:system'])
def update_profile(profile_id):
    """Update a scan profile."""
    data = request.get_json()
    if not data:
        return error_response("No data provided", 400)
    svc = _get_service()
    profile = svc.update_profile(profile_id, data)
    if not profile:
        return error_response("Profile not found", 404)
    _audit('discovery_profile_updated', resource_name=profile.get('name', ''),
           resource_id=profile_id, details=f"Updated fields: {', '.join(data.keys())}")
    return success_response(data=profile, message="Profile updated")


@bp.route('/api/v2/discovery/profiles/<int:profile_id>', methods=['DELETE'])
@require_auth(['admin:system'])
def delete_profile(profile_id):
    """Delete a scan profile."""
    svc = _get_service()
    if not svc.delete_profile(profile_id):
        return error_response("Profile not found", 404)
    _audit('discovery_profile_deleted', resource_id=profile_id,
           details=f"Profile {profile_id} deleted")
    return no_content_response()


# ==================== Scanning ====================

@bp.route('/api/v2/discovery/profiles/<int:profile_id>/scan', methods=['POST'])
@require_auth(['admin:system'])
def scan_profile(profile_id):
    """Trigger a scan for a profile. Returns scan run ID."""
    svc = _get_service()
    profile = svc.get_profile(profile_id)
    if not profile:
        return error_response("Profile not found", 404)

    username = g.current_user.username if hasattr(g, 'current_user') else 'unknown'

    run_id = svc.start_scan(
        targets=profile['targets'],
        ports=profile['ports'],
        profile_id=profile_id,
        triggered_by='manual',
        triggered_by_user=username,
        app=current_app._get_current_object(),
        timeout=profile.get('timeout', 5),
        max_workers=profile.get('max_workers', 20),
        resolve_dns=profile.get('resolve_dns', False),
    )
    _audit('discovery_scan_started', resource_name=profile.get('name', ''),
           resource_id=run_id, details=f"Profile scan: {profile.get('name')}, targets: {len(profile['targets'])}")
    return success_response(data={'scan_run_id': run_id}, message="Scan started")


@bp.route('/api/v2/discovery/scan', methods=['POST'])
@require_auth(['admin:system'])
def ad_hoc_scan():
    """Ad-hoc scan without a saved profile."""
    data = request.get_json()
    if not data:
        return error_response("No data provided", 400)

    targets = data.get('targets', [])
    subnet = data.get('subnet')
    ports = data.get('ports', [443])
    timeout = _safe_int(data.get('timeout', 5), 5, lo=1, hi=30)
    scan_max_workers = _safe_int(data.get('max_workers', 20), 20, lo=1, hi=50)
    resolve_dns = bool(data.get('resolve_dns', False))

    if not targets and not subnet:
        return error_response("Provide either 'targets' or 'subnet'", 400)
    if targets and len(targets) > 500:
        return error_response("Maximum 500 targets per ad-hoc scan", 400)
    # SEC-10: Validate target format
    for t in targets:
        if not isinstance(t, str) or not _VALID_TARGET_RE.match(t.strip()):
            return error_response("Invalid target format: targets must be hostnames, IPs, or CIDR notation", 400)

    if subnet:
        try:
            net = ipaddress.ip_network(subnet, strict=False)
            if net.prefixlen < 22:
                return error_response("Subnet too large (max /22)", 400)
        except ValueError:
            return error_response("Invalid subnet notation", 400)

    svc = _get_service()
    username = g.current_user.username if hasattr(g, 'current_user') else 'unknown'

    if subnet:
        run_id = svc.start_subnet_scan(
            cidr=subnet, ports=ports,
            triggered_by='manual', triggered_by_user=username,
            app=current_app._get_current_object(),
            timeout=timeout, max_workers=scan_max_workers,
            resolve_dns=resolve_dns,
        )
        _audit('discovery_scan_started', resource_id=run_id,
               details=f"Ad-hoc subnet scan: {subnet}")
    else:
        run_id = svc.start_scan(
            targets=targets, ports=ports,
            triggered_by='manual', triggered_by_user=username,
            app=current_app._get_current_object(),
            timeout=timeout, max_workers=scan_max_workers,
            resolve_dns=resolve_dns,
        )
        _audit('discovery_scan_started', resource_id=run_id,
               details=f"Ad-hoc scan: {len(targets)} targets")

    return success_response(data={'scan_run_id': run_id}, message="Scan started")


# ==================== Scan History ====================

@bp.route('/api/v2/discovery/runs', methods=['GET'])
@require_auth(['read:certificates'])
def list_runs():
    """List scan run history."""
    limit = _safe_int(request.args.get('limit', 50), 50, lo=1, hi=200)
    offset = _safe_int(request.args.get('offset', 0), 0, lo=0)
    profile_id = request.args.get('profile_id', type=int)
    svc = _get_service()
    items, total = svc.get_runs(limit=limit, offset=offset, profile_id=profile_id)
    return success_response(data={'items': items, 'total': total})


@bp.route('/api/v2/discovery/runs/<int:run_id>', methods=['GET'])
@require_auth(['read:certificates'])
def get_run(run_id):
    """Get details of a single scan run."""
    svc = _get_service()
    run = svc.get_run(run_id)
    if not run:
        return error_response("Scan run not found", 404)
    return success_response(data=run)


# ==================== Results ====================

@bp.route('/api/v2/discovery', methods=['GET'])
@require_auth(['read:certificates'])
def list_discovered():
    """List discovered certificates with pagination and filtering."""
    limit = _safe_int(request.args.get('limit', 50), 50, lo=1, hi=200)
    offset = _safe_int(request.args.get('offset', 0), 0, lo=0)
    profile_id = request.args.get('profile_id', type=int)
    status = request.args.get('status')
    svc = _get_service()
    items, total = svc.get_all(limit=limit, offset=offset,
                               profile_id=profile_id, status=status)
    return success_response(data={'items': items, 'total': total})


@bp.route('/api/v2/discovery/stats', methods=['GET'])
@require_auth(['read:certificates'])
def get_stats():
    """Get discovery statistics."""
    profile_id = request.args.get('profile_id', type=int)
    svc = _get_service()
    return success_response(data=svc.get_stats(profile_id=profile_id))


@bp.route('/api/v2/discovery/<int:disc_id>', methods=['DELETE'])
@require_auth(['delete:certificates'])
def delete_discovered(disc_id):
    """Delete a single discovered certificate."""
    svc = _get_service()
    if not svc.delete(disc_id):
        return error_response("Not found", 404)
    _audit('discovery_result_deleted', resource_id=disc_id,
           details=f"Discovered certificate {disc_id} deleted")
    return no_content_response()


@bp.route('/api/v2/discovery', methods=['DELETE'])
@require_auth(['admin:system'])
def delete_all_discovered():
    """Delete all discovered certificates."""
    profile_id = request.args.get('profile_id', type=int)
    svc = _get_service()
    count = svc.delete_all(profile_id=profile_id)
    _audit('discovery_results_purged', details=f"Deleted {count} discovered certificates"
           + (f" for profile {profile_id}" if profile_id else ""))
    return success_response(data={'deleted': count}, message=f"Deleted {count} records")


# ==================== Export ====================

@bp.route('/api/v2/discovery/export', methods=['GET'])
@require_auth(['read:certificates'])
def export_discovered():
    """Export discovered certificates as CSV or JSON."""
    import csv
    import io
    from flask import Response

    fmt = request.args.get('format', 'csv')
    profile_id = request.args.get('profile_id', type=int)
    status = request.args.get('status')
    svc = _get_service()
    items, total = svc.get_all(limit=10000, offset=0, profile_id=profile_id, status=status)

    if fmt == 'json':
        import json
        _audit('discovery_export', details=f"JSON export: {total} certificates")
        return Response(
            json.dumps(items, indent=2, default=str),
            mimetype='application/json',
            headers={'Content-Disposition': 'attachment; filename=discovered_certificates.json'}
        )

    # CSV export
    output = io.StringIO()
    fields = ['target', 'port', 'sni_hostname', 'dns_hostname', 'subject', 'issuer', 'serial_number',
              'not_before', 'not_after', 'fingerprint_sha256', 'status',
              'first_seen', 'last_seen', 'is_expired', 'days_until_expiry',
              'san_dns_names', 'san_ip_addresses', 'scan_error']
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    for item in items:
        row = dict(item)
        # Flatten SAN lists for CSV
        row['san_dns_names'] = ', '.join(row.get('san_dns_names') or [])
        row['san_ip_addresses'] = ', '.join(row.get('san_ip_addresses') or [])
        writer.writerow(row)

    _audit('discovery_export', details=f"CSV export: {total} certificates")
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=discovered_certificates.csv'}
    )


# ==================== Bulk Operations ====================

@bp.route('/api/v2/discovery/bulk-resolve-dns', methods=['POST'])
@require_auth(['admin:system'])
def bulk_resolve_dns():
    """Re-resolve reverse DNS for all discovered certificates."""
    svc = _get_service()
    result = svc.bulk_resolve_dns()
    _audit('discovery_bulk_dns', details=f"Resolved {result['updated']}/{result['total']} certificates")
    return success_response(data=result, message=f"Updated {result['updated']} DNS hostnames")

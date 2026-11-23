"""
Audit Logs API v2.0
View and manage audit logs
"""
from flask import Blueprint, request, jsonify, g, Response
from auth.unified import require_auth
from services.audit_service import AuditService
from services import jobs
from services.jobs import audit_verify
from api.v2.system.jobs import busy_response, started_response, suspended_response
from utils.pagination import parse_date_filter, parse_request_pagination, parse_request_limit, parse_request_sort
from models import AuditLog
from utils.response import success_response, error_response
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('audit_v2', __name__)


def _timestamp_order(descending):
    # Every row is stamped on insert: no NULLS clause, which would keep PostgreSQL off the index
    return [AuditLog.timestamp.desc() if descending else AuditLog.timestamp.asc()]


@bp.route('/api/v2/audit/logs', methods=['GET'])
@require_auth(['read:audit'])
def get_logs():
    """
    Get audit logs with filtering and pagination
    
    Query params:
        page: Page number (default: 1)
        per_page: Items per page (default: 50, max: 100)
        username: Filter by username
        action: Filter by action type
        category: Filter by category (auth, users, certificates, etc.)
        resource_type: Filter by resource type
        success: Filter by success (true/false)
        date_from: Filter from date (ISO format)
        date_to: Filter to date (ISO format)
        search: Search in username, action, details
        sort_by: timestamp (the only key: the filters do the rest); sort_order: desc (default) or asc
    """
    # Outside the try below: an unknown key is the client's 400, not a 500
    sort = parse_request_sort({'timestamp': _timestamp_order}, ('timestamp', 'desc'), tiebreak=AuditLog.id)
    try:
        # Parse query params (support multi-select: ?action=create&action=delete)
        # `min(..., 100)` bounded this from above only. A negative page size
        # reached the query untouched, and `LIMIT -1` means no limit at all on
        # SQLite, so one request returned the whole audit table; PostgreSQL
        # refuses a negative LIMIT outright, so the same request answered 500
        # there. This is the listing the audit page itself uses.
        page, per_page = parse_request_pagination(default_per_page=50)
        username = request.args.get('username')
        action_list = request.args.getlist('action')
        category = request.args.get('category')
        resource_type_list = request.args.getlist('resource_type')
        search = request.args.get('search')
        
        # Parse success filter
        success = None
        success_param = request.args.get('success')
        if success_param is not None:
            success = success_param.lower() == 'true'
        
        # Parse date filters
        date_from, date_to = parse_date_filter()
        
        # Get logs
        logs, total, total_pages = AuditService.get_logs(
            page=page,
            per_page=per_page,
            username=username,
            action=action_list if action_list else None,
            category=category,
            resource_type=resource_type_list if resource_type_list else None,
            success=success,
            date_from=date_from,
            date_to=date_to,
            search=search,
            order_by=sort.clauses,
        )
        
        return success_response(
            data=[log.to_dict() for log in logs],
            meta={
                'page': page,
                'per_page': per_page,
                'total': total,
                'total_pages': total_pages
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting audit logs: {e}")
        return error_response("Failed to get audit logs", 500)


@bp.route('/api/v2/audit/logs/<int:log_id>', methods=['GET'])
@require_auth(['read:audit'])
def get_log(log_id):
    """Get a single audit log by ID"""
    log = AuditService.get_log_by_id(log_id)
    
    if not log:
        return error_response('Audit log not found', 404)
    
    return success_response(data=log.to_dict())


@bp.route('/api/v2/audit/stats', methods=['GET'])
@require_auth(['read:audit'])
def get_stats():
    """
    Get audit log statistics
    
    Query params:
        days: Number of days to analyze (default: 30)
    """
    days = request.args.get('days', 30, type=int)
    days = min(days, 365)  # Max 1 year
    
    stats = AuditService.get_stats(days=days)
    return success_response(data=stats)


@bp.route('/api/v2/audit/actions', methods=['GET'])
@require_auth(['read:audit'])
def get_actions():
    """Get list of all action types and categories"""
    actions = AuditService.get_actions_list()
    categories = AuditService.CATEGORIES
    
    return success_response(data={
        'actions': actions,
        'categories': categories
    })


@bp.route('/api/v2/audit/export', methods=['GET'])
@require_auth(['read:audit'])
def export_logs():
    """
    Export audit logs
    
    Query params:
        format: Export format (json, csv) - default: json
        date_from: Start date (ISO format)
        date_to: End date (ISO format)
        limit: Max records (default: 10000)
        username, action (repeatable), category, resource_type (repeatable), success, search:
            the filters of the list
    """
    format = request.args.get('format', 'json')
    limit = parse_request_limit(10000, 50000)
    
    # Parse dates
    date_from, date_to = parse_date_filter()

    success_param = request.args.get('success')
    action_list = request.args.getlist('action')
    resource_type_list = request.args.getlist('resource_type')
    data = AuditService.export_logs(
        format=format,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        username=request.args.get('username'),
        action=action_list or None,
        category=request.args.get('category'),
        resource_type=resource_type_list or None,
        success=None if success_param is None else success_param.lower() == 'true',
        search=request.args.get('search'),
    )
    
    if format == 'csv':
        return Response(
            data,
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=audit_logs.csv'}
        )
    else:
        return Response(
            data,
            mimetype='application/json',
            headers={'Content-Disposition': 'attachment; filename=audit_logs.json'}
        )


@bp.route('/api/v2/audit/cleanup', methods=['POST'])
@require_auth(['delete:audit'])
def cleanup_logs():
    """
    Clean up old audit logs
    
    Body:
        retention_days: Days to keep (default: 90, raised to 30, at most 3650)
    """
    data = request.json or {}
    raw = data.get('retention_days', 90)
    try:
        retention_days = int(raw)
    except (TypeError, ValueError):
        return error_response("retention_days must be an integer", 400)
    # Floor: 30 days, raised to it (keeps more, never less). Ceiling: 3650 days, refused:
    # lowering a retention would delete logs the operator asked to keep.
    if retention_days > 3650:
        return error_response("retention_days must be at most 3650", 400)
    retention_days = max(30, retention_days)
    
    try:
        deleted = AuditService.cleanup_old_logs(retention_days=retention_days)
    except Exception:
        return error_response("Failed to clean up audit logs", 500)
    
    # The purge records itself, sealed, with the first batch it deletes
    return success_response(
        data={'deleted': deleted},
        message=f'Cleaned up {deleted} old audit logs'
    )


def _verify_params():
    source = request.args if request.method == 'GET' else (request.get_json(silent=True) or {})
    values = []
    for name in ('start_id', 'end_id'):
        value = source.get(name)
        if value in (None, ''):
            values.append(None)
            continue
        try:
            values.append(int(value))
        except (TypeError, ValueError):
            values.append(None)  # as request.args.get(type=int) has always read it
    return audit_verify.params_of(*values)


@bp.route('/api/v2/audit/verify', methods=['GET', 'POST'])
@require_auth(['read:audit'])
def verify_integrity():
    """
    Verify the audit log hash chain, as a background job.

    GET joins the verification already running with the same range, or starts one; POST
    starts one (409 when another is active). Either waits at most 25 s: a verification
    finished by then answers 200 as below, otherwise 202 with a Location to follow
    (``Prefer: respond-async`` answers 202 at once).

    Params (query for GET, JSON body for POST):
        start_id: First log ID to check (optional)
        end_id: Last log ID to check (optional)

    Returns:
        status: 'intact', 'broken' (first_error_id names the entry) or
            'unprotected' (no master key, or entries the key does not seal)
        valid: True when no entry fails its check
        protection: what the master key attests
        errors: integrity violations found
    """
    params = _verify_params()

    def joinable(row):
        # Joined only when it checks the same range: its report answers this request
        return (request.method == 'GET' and row is not None and row['kind'] == audit_verify.KIND
                and json.loads(row['params'] or '{}') == params)

    try:
        job_id = jobs.start_job(audit_verify.KIND, params=params)
    except jobs.JobsSuspended:
        return suspended_response()
    except jobs.SlotBusy as busy:
        if joinable(busy.job):
            return started_response(busy.job['id'])
        return busy_response(busy)
    return started_response(job_id)

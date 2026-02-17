"""
Audit Logs API v2.0
View and manage audit logs
"""
from flask import Blueprint, request, jsonify, g, Response
from auth.unified import require_auth
from services.audit_service import AuditService
from utils.response import success_response, error_response
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('audit_v2', __name__)


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
    """
    try:
        # Parse query params
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 50, type=int), 100)
        username = request.args.get('username')
        action = request.args.get('action')
        category = request.args.get('category')
        resource_type = request.args.get('resource_type')
        search = request.args.get('search')
        
        # Parse success filter
        success = None
        success_param = request.args.get('success')
        if success_param is not None:
            success = success_param.lower() == 'true'
        
        # Parse date filters
        date_from = None
        date_to = None
        if request.args.get('date_from'):
            try:
                date_from = datetime.fromisoformat(request.args.get('date_from').replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass
        if request.args.get('date_to'):
            try:
                date_to = datetime.fromisoformat(request.args.get('date_to').replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass
        
        # Get logs
        logs, total, total_pages = AuditService.get_logs(
            page=page,
            per_page=per_page,
            username=username,
            action=action,
            category=category,
            resource_type=resource_type,
            success=success,
            date_from=date_from,
            date_to=date_to,
            search=search
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
        return error_response(f"Failed to get audit logs: {str(e)}", 500)


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
    """
    format = request.args.get('format', 'json')
    limit = min(request.args.get('limit', 10000, type=int), 50000)
    
    # Parse dates
    date_from = None
    date_to = None
    if request.args.get('date_from'):
        try:
            date_from = datetime.fromisoformat(request.args.get('date_from').replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            pass
    if request.args.get('date_to'):
        try:
            date_to = datetime.fromisoformat(request.args.get('date_to').replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            pass
    
    data = AuditService.export_logs(
        format=format,
        date_from=date_from,
        date_to=date_to,
        limit=limit
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
        retention_days: Days to keep (default: 90, min: 30)
    """
    data = request.json or {}
    retention_days = max(data.get('retention_days', 90), 30)
    
    deleted = AuditService.cleanup_old_logs(retention_days=retention_days)
    
    # Log the cleanup action
    AuditService.log_action(
        action='audit_cleanup',
        resource_type='audit_log',
        details=f'Cleaned up {deleted} logs older than {retention_days} days',
        success=True
    )
    
    return success_response(
        data={'deleted': deleted},
        message=f'Cleaned up {deleted} old audit logs'
    )


@bp.route('/api/v2/audit/verify', methods=['GET'])
@require_auth(['read:audit'])
def verify_integrity():
    """
    Verify audit log integrity using hash chain.
    
    Query params:
        start_id: First log ID to check (optional)
        end_id: Last log ID to check (optional)
    
    Returns:
        valid: Boolean - True if all hashes are valid
        checked: Number of entries verified
        errors: List of any integrity violations found
    """
    start_id = request.args.get('start_id', type=int)
    end_id = request.args.get('end_id', type=int)
    
    result = AuditService.verify_integrity(start_id=start_id, end_id=end_id)
    
    return success_response(
        data=result,
        message='Integrity check passed' if result['valid'] else f"Found {len(result['errors'])} integrity violations"
    )

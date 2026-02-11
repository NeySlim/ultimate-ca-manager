"""
Report API - UCM
Endpoints for generating and scheduling reports.
"""
from flask import Blueprint, request, Response
from auth.unified import require_auth
from utils.response import success_response, error_response
from services.report_service import ReportService
from models import db, SystemConfig
import json

bp = Blueprint('reports_pro', __name__)


@bp.route('/api/v2/reports/types', methods=['GET'])
@require_auth(['read:audit'])
def list_report_types():
    """List available report types"""
    return success_response(data=ReportService.REPORT_TYPES)


@bp.route('/api/v2/reports/generate', methods=['POST'])
@require_auth(['read:audit', 'export:audit'])
def generate_report():
    """Generate a report on-demand"""
    data = request.get_json() or {}
    
    report_type = data.get('report_type')
    if not report_type:
        return error_response("report_type is required", 400)
    
    if report_type not in ReportService.REPORT_TYPES:
        return error_response(f"Unknown report type: {report_type}", 400)
    
    params = data.get('params', {})
    
    try:
        report = ReportService.generate_report(report_type, params)
        return success_response(data=report)
    except Exception as e:
        return error_response(f"Report generation failed: {str(e)}", 500)


@bp.route('/api/v2/reports/download/<report_type>', methods=['GET'])
@require_auth(['read:audit', 'export:audit'])
def download_report(report_type):
    """Download a report as CSV"""
    if report_type not in ReportService.REPORT_TYPES:
        return error_response(f"Unknown report type: {report_type}", 400)
    
    params = {
        'format': request.args.get('format', 'csv'),
        'days': int(request.args.get('days', 30)),
    }
    
    try:
        report = ReportService.generate_report(report_type, params)
        
        if params['format'] == 'csv':
            return Response(
                report['content'],
                mimetype='text/csv',
                headers={
                    'Content-Disposition': f'attachment; filename=ucm-report-{report_type}.csv'
                }
            )
        else:
            return Response(
                report['content'],
                mimetype='application/json',
                headers={
                    'Content-Disposition': f'attachment; filename=ucm-report-{report_type}.json'
                }
            )
    except Exception as e:
        return error_response(f"Report generation failed: {str(e)}", 500)


@bp.route('/api/v2/reports/schedule', methods=['GET'])
@require_auth(['read:settings'])
def get_schedule_settings():
    """Get report schedule settings"""
    settings = {
        'expiry_report': {
            'enabled': _get_config('report_expiry_enabled', 'false') == 'true',
            'recipients': json.loads(_get_config('report_expiry_recipients', '[]')),
            'schedule': 'daily',
        },
        'compliance_report': {
            'enabled': _get_config('report_compliance_enabled', 'false') == 'true',
            'recipients': json.loads(_get_config('report_compliance_recipients', '[]')),
            'schedule': 'weekly',
        },
    }
    return success_response(data=settings)


@bp.route('/api/v2/reports/schedule', methods=['PUT'])
@require_auth(['write:settings'])
def update_schedule_settings():
    """Update report schedule settings"""
    data = request.get_json() or {}
    
    if 'expiry_report' in data:
        exp = data['expiry_report']
        _set_config('report_expiry_enabled', 'true' if exp.get('enabled') else 'false')
        if 'recipients' in exp:
            _set_config('report_expiry_recipients', json.dumps(exp['recipients']))
    
    if 'compliance_report' in data:
        comp = data['compliance_report']
        _set_config('report_compliance_enabled', 'true' if comp.get('enabled') else 'false')
        if 'recipients' in comp:
            _set_config('report_compliance_recipients', json.dumps(comp['recipients']))
    
    db.session.commit()
    
    # Return updated settings
    return get_schedule_settings()


@bp.route('/api/v2/reports/send-test', methods=['POST'])
@require_auth(['write:settings'])
def send_test_report():
    """Send a test report to verify email configuration"""
    data = request.get_json() or {}
    
    report_type = data.get('report_type', 'expiring_certificates')
    recipient = data.get('recipient')
    
    if not recipient:
        return error_response("recipient email is required", 400)
    
    try:
        ReportService.send_scheduled_report(
            report_type,
            [recipient],
            {'days': 30}
        )
        return success_response(message=f"Test report sent to {recipient}")
    except Exception as e:
        return error_response(f"Failed to send test report: {str(e)}", 500)


def _get_config(key: str, default: str = '') -> str:
    """Get config value from database"""
    config = SystemConfig.query.filter_by(key=key).first()
    return config.value if config else default


def _set_config(key: str, value: str):
    """Set config value in database"""
    config = SystemConfig.query.filter_by(key=key).first()
    if config:
        config.value = value
    else:
        config = SystemConfig(key=key, value=value)
        db.session.add(config)

"""
Report Service - UCM
Generates and schedules compliance reports (certificates, CAs, audit, expiry).
"""
from datetime import datetime, timedelta
from flask import current_app
import json
import csv
import io
import base64
import html
from models import db, Certificate, CA, User, AuditLog, SystemConfig
from services.email_service import EmailService
import logging
from utils.datetime_utils import utc_now, utc_isoformat
from utils.days_remaining import days_remaining as compute_days_remaining

logger = logging.getLogger(__name__)


class ReportService:
    """Service for generating and scheduling reports"""
    
    # Available report types
    REPORT_TYPES = {
        'certificate_inventory': {
            'name': 'Certificate Inventory',
            'description': 'Complete list of all certificates with status',
        },
        'expiring_certificates': {
            'name': 'Expiring Certificates',
            'description': 'Certificates expiring within specified days',
        },
        'ca_hierarchy': {
            'name': 'CA Hierarchy',
            'description': 'Certificate Authority structure and statistics',
        },
        'audit_summary': {
            'name': 'Audit Summary',
            'description': 'Security events and user activity summary',
        },
        'compliance_status': {
            'name': 'Compliance Status',
            'description': 'Policy compliance and violation summary',
        },
        'revoked_certificates': {
            'name': 'Revoked Certificates',
            'description': 'Certificates revoked within the period, with date and reason',
        },
    }

    # Email attachment per data format; PDF schedules are 'pdf_<template>'.
    ATTACHMENT_TYPES = {'csv': 'text/csv', 'json': 'application/json'}

    @classmethod
    def attachment_format(cls, value) -> str:
        """The data format to attach: ``value`` when it is one, else CSV."""
        return value if isinstance(value, str) and value in cls.ATTACHMENT_TYPES else 'csv'
    
    @classmethod
    def generate_report(cls, report_type: str, params: dict = None) -> dict:
        """
        Generate a report of specified type.
        
        Args:
            report_type: One of REPORT_TYPES keys
            params: Optional parameters (days, format, etc.)
            
        Returns:
            Report data with metadata and content
        """
        params = params or {}
        format_type = params.get('format', 'json')
        
        generators = {
            'certificate_inventory': cls._generate_certificate_inventory,
            'expiring_certificates': cls._generate_expiring_certificates,
            'ca_hierarchy': cls._generate_ca_hierarchy,
            'audit_summary': cls._generate_audit_summary,
            'compliance_status': cls._generate_compliance_status,
            'revoked_certificates': cls._generate_revoked_certificates,
        }
        
        if report_type not in generators:
            raise ValueError(f"Unknown report type: {report_type}")
        
        # Generate report data
        data = generators[report_type](params)
        
        # Format output
        if format_type == 'csv':
            content = cls._to_csv(data['items'], data.get('columns', []))
        elif format_type == 'json':
            content = json.dumps(data, indent=2, default=str)
        else:
            content = data
        
        return {
            'report_type': report_type,
            'report_name': cls.REPORT_TYPES[report_type]['name'],
            'generated_at': utc_isoformat(utc_now()),
            'parameters': params,
            'format': format_type,
            'content': content,
            'summary': data.get('summary', {}),
        }
    
    @classmethod
    def _cert_status(cls, cert) -> str:
        """Calculate certificate status from model fields"""
        if cert.revoked:
            return 'revoked'
        if cert.valid_to:
            now = utc_now()
            if cert.valid_to < now:
                return 'expired'
            if cert.valid_to < now + timedelta(days=30):
                return 'expiring'
        return 'valid'

    @classmethod
    def _generate_certificate_inventory(cls, params: dict) -> dict:
        """Generate certificate inventory report"""
        certs = Certificate.query.all()
        
        items = []
        stats = {'total': 0, 'valid': 0, 'expired': 0, 'revoked': 0, 'expiring': 0}
        
        for cert in certs:
            status = cls._cert_status(cert)
            stats['total'] += 1
            if status in stats:
                stats[status] += 1
            
            items.append({
                'id': cert.id,
                'common_name': cert.common_name,
                'serial_number': cert.serial_number,
                'status': status,
                'issuer': cert.issuer,
                'valid_from': cert.valid_from,
                'valid_to': cert.valid_to,
                'key_type': cert.key_type,
                'source': cert.source,
                'created_at': cert.created_at,
            })
        
        return {
            'items': items,
            'columns': ['id', 'common_name', 'serial_number', 'status', 'issuer', 
                       'valid_from', 'valid_to', 'key_type', 'source'],
            'summary': stats,
        }
    
    @classmethod
    def _generate_expiring_certificates(cls, params: dict) -> dict:
        """Generate expiring certificates report"""
        days = params.get('days', 30)
        now = utc_now()
        threshold = now + timedelta(days=days)
        
        certs = Certificate.query.filter(
            Certificate.valid_to != None,
            Certificate.valid_to <= threshold,
            Certificate.valid_to > now,
            Certificate.revoked == False
        ).order_by(Certificate.valid_to).all()
        
        items = []
        for cert in certs:
            days_left = compute_days_remaining(cert.valid_to, now)
            items.append({
                'id': cert.id,
                'common_name': cert.common_name,
                'serial_number': cert.serial_number,
                'issuer': cert.issuer,
                'valid_to': cert.valid_to,
                'days_remaining': days_left,
                'source': cert.source,
            })
        
        return {
            'items': items,
            'columns': ['id', 'common_name', 'serial_number', 'issuer', 
                       'valid_to', 'days_remaining', 'source'],
            'summary': {
                'total_expiring': len(items),
                'threshold_days': days,
            },
        }
    
    @classmethod
    def _generate_revoked_certificates(cls, params: dict) -> dict:
        """Certificates revoked in the last ``days`` days, optionally for one ``reason``."""
        try:
            days = min(max(int(params.get('days', 30)), 1), 3650)
        except (TypeError, ValueError):
            days = 30
        since = utc_now() - timedelta(days=days)
        query = Certificate.query.filter(
            Certificate.revoked == True,  # noqa: E712
            Certificate.revoked_at != None,  # noqa: E711
            Certificate.revoked_at >= since,
        )
        reason = params.get('reason')
        if reason:
            query = query.filter(Certificate.revoke_reason == str(reason)[:100])

        items, by_reason = [], {}
        for cert in query.order_by(Certificate.revoked_at.desc()).all():
            cert_reason = cert.revoke_reason or 'unspecified'
            by_reason[cert_reason] = by_reason.get(cert_reason, 0) + 1
            items.append({
                'id': cert.id,
                'common_name': cert.common_name,
                'serial_number': cert.serial_number,
                'issuer': cert.issuer,
                'revoked_at': cert.revoked_at,
                'revoke_reason': cert_reason,
                'valid_to': cert.valid_to,
                'source': cert.source,
            })

        return {
            'items': items,
            'columns': ['id', 'common_name', 'serial_number', 'issuer',
                        'revoked_at', 'revoke_reason', 'valid_to', 'source'],
            'summary': {
                'total_revoked': len(items),
                'period_days': days,
                'by_reason': by_reason,
            },
        }

    @classmethod
    def _generate_ca_hierarchy(cls, params: dict) -> dict:
        """Generate CA hierarchy report"""
        cas = CA.query.all()
        
        items = []
        stats = {'total': 0, 'root': 0, 'intermediate': 0}
        
        # Batch query: count certificates per CA in one query (avoid N+1)
        from sqlalchemy import func
        cert_counts = dict(
            db.session.query(Certificate.caref, func.count(Certificate.id))
            .group_by(Certificate.caref)
            .all()
        )
        
        for ca in cas:
            stats['total'] += 1
            if ca.is_root:
                stats['root'] += 1
            else:
                stats['intermediate'] += 1
            
            cert_count = cert_counts.get(ca.refid, 0)
            
            items.append({
                'id': ca.id,
                'refid': ca.refid,
                'common_name': ca.common_name,
                'parent_refid': ca.caref,
                'is_root': ca.is_root,
                'valid_from': ca.valid_from,
                'valid_to': ca.valid_to,
                'key_type': ca.key_type,
                'issued_certificates': cert_count,
                'cdp_url': ca.get_primary_cdp_url(),
                'cdp_urls': ca.get_cdp_urls(),
                'ocsp_urls': ca.get_ocsp_urls(),
                'cps_uri': ca.cps_uri if ca.cps_enabled else None,
            })
        
        return {
            'items': items,
            'columns': ['id', 'refid', 'common_name', 'parent_refid', 'is_root',
                       'valid_from', 'valid_to', 'key_type', 'issued_certificates'],
            'summary': stats,
        }
    
    @classmethod
    def _generate_audit_summary(cls, params: dict) -> dict:
        """Generate audit log summary report"""
        days = params.get('days', 7)
        since = utc_now() - timedelta(days=days)
        
        from sqlalchemy import func, case
        
        # DB-level aggregations instead of loading all rows
        base_filter = AuditLog.timestamp >= since
        
        total_events = AuditLog.query.filter(base_filter).count()
        
        # Group by action
        action_counts = db.session.query(
            func.coalesce(AuditLog.action, 'unknown'),
            func.count(AuditLog.id)
        ).filter(base_filter).group_by(AuditLog.action).order_by(func.count(AuditLog.id).desc()).limit(10).all()
        
        # Group by user
        user_counts = db.session.query(
            func.coalesce(AuditLog.username, 'system'),
            func.count(AuditLog.id)
        ).filter(base_filter).group_by(AuditLog.username).order_by(func.count(AuditLog.id).desc()).limit(10).all()
        
        # Group by resource type
        resource_counts = db.session.query(
            func.coalesce(AuditLog.resource_type, 'unknown'),
            func.count(AuditLog.id)
        ).filter(base_filter).group_by(AuditLog.resource_type).order_by(func.count(AuditLog.id).desc()).limit(10).all()
        
        unique_users = db.session.query(func.count(func.distinct(AuditLog.username))).filter(base_filter).scalar() or 0
        unique_actions = db.session.query(func.count(func.distinct(AuditLog.action))).filter(base_filter).scalar() or 0
        
        return {
            'items': [
                {'category': 'actions', 'data': dict(action_counts)},
                {'category': 'users', 'data': dict(user_counts)},
                {'category': 'resources', 'data': dict(resource_counts)},
            ],
            'columns': ['category', 'data'],
            'summary': {
                'total_events': total_events,
                'period_days': days,
                'unique_users': unique_users,
                'unique_actions': unique_actions,
            },
        }
    
    @classmethod
    def _generate_compliance_status(cls, params: dict) -> dict:
        """Generate compliance status report"""
        # Check for policy violations
        items = []
        
        # Check certificates without proper extensions
        total_active = Certificate.query.filter(
            Certificate.revoked == False,
            Certificate.valid_to > utc_now()
        ).count()
        
        # Check expired CAs
        expired_cas = CA.query.filter(
            CA.valid_to < utc_now()
        ).count()
        
        # Check weak keys (RSA < 2048)
        # This is simplified - would need actual key analysis
        
        items.append({
            'check': 'Active Certificates',
            'status': 'pass',
            'count': total_active,
            'severity': 'none',
        })
        
        # Build compliance items
        items.append({
            'check': 'Expired CAs',
            'status': 'pass' if expired_cas == 0 else 'fail',
            'count': expired_cas,
            'severity': 'high' if expired_cas > 0 else 'none',
        })
        
        # Check for certificates expiring soon (< 30 days)
        threshold = utc_now() + timedelta(days=30)
        now = utc_now()
        expiring_soon = Certificate.query.filter(
            Certificate.valid_to != None,
            Certificate.valid_to <= threshold,
            Certificate.valid_to > now,
            Certificate.revoked == False
        ).count()
        
        items.append({
            'check': 'Certificates Expiring <30 Days',
            'status': 'warning' if expiring_soon > 0 else 'pass',
            'count': expiring_soon,
            'severity': 'medium' if expiring_soon > 0 else 'none',
        })
        
        # Calculate overall score
        failed_checks = sum(1 for i in items if i['status'] == 'fail')
        warning_checks = sum(1 for i in items if i['status'] == 'warning')
        total_checks = len(items)
        
        if failed_checks > 0:
            score = 'critical'
        elif warning_checks > 0:
            score = 'warning'
        else:
            score = 'healthy'
        
        return {
            'items': items,
            'columns': ['check', 'status', 'count', 'severity'],
            'summary': {
                'overall_score': score,
                'total_checks': total_checks,
                'passed': total_checks - failed_checks - warning_checks,
                'warnings': warning_checks,
                'failed': failed_checks,
            },
        }
    
    @classmethod
    def _to_csv(cls, items: list, columns: list) -> str:
        """Convert items to CSV string"""
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        for item in items:
            # Flatten nested dicts
            flat_item = {}
            for col in columns:
                val = item.get(col, '')
                if isinstance(val, (dict, list)):
                    val = json.dumps(val)
                flat_item[col] = val
            writer.writerow(flat_item)
        return output.getvalue()
    
    @classmethod
    def send_scheduled_report(cls, report_type: str, recipients: list, params: dict = None) -> bool:
        """Generate a data report and email it as a CSV or JSON attachment.

        Returns True when every recipient was sent the report.
        """
        try:
            params = dict(params or {})
            fmt = params['format'] = cls.attachment_format(params.get('format'))

            report = cls.generate_report(report_type, params)
            today = utc_now().strftime('%Y-%m-%d')
            subject = f"UCM Report: {report['report_name']} - {today}"
            body = f"""
UCM Scheduled Report: {report['report_name']}

Generated: {report['generated_at']}
Parameters: {json.dumps(report['parameters'])}

Summary:
{json.dumps(report['summary'], indent=2)}

The full report is attached as a {fmt.upper()} file.

--
Ultimate Certificate Manager
            """
            attachment = (
                f"ucm-report-{report_type}-{today}.{fmt}",
                report['content'].encode('utf-8'),
                cls.ATTACHMENT_TYPES[fmt],
            )
            return cls._mail_each(recipients, subject, body, attachment, report_type)
        except Exception as e:
            logger.error(f"Failed to generate scheduled report {report_type}: {e}")
            return False

    @classmethod
    def send_scheduled_pdf_report(cls, recipients: list, template: str = 'executive') -> bool:
        """Generate a PDF report from one of the PDF templates and email it attached."""
        try:
            from services.pdf_report_service import PDFReportService
            tpl = PDFReportService.TEMPLATES.get(template) or PDFReportService.TEMPLATES['executive']
            pdf_bytes = PDFReportService.generate_executive_report(sections=tpl['sections'])

            today = utc_now().strftime('%Y-%m-%d')
            subject = f"UCM {tpl['name']} Report - {today}"
            body = f"""
UCM {tpl['name']} Report

Please find the attached PDF report ({tpl['description']}).

--
Ultimate Certificate Manager
            """
            attachment = (f"ucm-report-{template}-{today}.pdf", pdf_bytes, 'application/pdf')
            return cls._mail_each(recipients, subject, body, attachment, f'pdf_{template}')
        except Exception as e:
            logger.error(f"Failed to generate scheduled PDF report: {e}")
            return False

    @staticmethod
    def _mail_each(recipients, subject, body, attachment, label) -> bool:
        all_sent = True
        for recipient in recipients:
            try:
                ok, message = EmailService.send_email(
                    recipients=[recipient],
                    subject=subject,
                    body_html=f"<pre>{html.escape(body)}</pre>",
                    body_text=body,
                    notification_type="report",
                    attachments=[attachment],
                )
            except Exception as e:
                ok, message = False, str(e)
            if ok:
                logger.info(f"Sent {label} report to {recipient}")
            else:
                all_sent = False
                logger.error(f"Failed to send {label} report to {recipient}: {message}")
        return all_sent


def schedulable_reports() -> list:
    """Schedule keys: every data report, then 'pdf_<template>' (and the legacy 'executive_pdf')."""
    from services.pdf_report_service import PDFReportService
    return (list(ReportService.REPORT_TYPES)
            + [f'pdf_{t}' for t in PDFReportService.TEMPLATES]
            + ['executive_pdf'])


def send_report(report_key: str, recipients: list, fmt: str = 'csv') -> bool:
    """Send one schedule key's report: a PDF template or a data report in ``fmt``."""
    if report_key == 'executive_pdf':
        return ReportService.send_scheduled_pdf_report(recipients, 'executive')
    if report_key.startswith('pdf_'):
        return ReportService.send_scheduled_pdf_report(recipients, report_key[len('pdf_'):])
    return ReportService.send_scheduled_report(report_key, recipients, {'days': 30, 'format': fmt})


def run_scheduled_reports():
    """Unified scheduler task — checks all report schedules and sends due reports."""
    from datetime import datetime
    now = utc_now()
    current_hour = now.strftime('%H:%M')
    current_dow = now.weekday()  # 0=Monday
    current_dom = now.day
    
    for report_key in schedulable_reports():
        config = SystemConfig.query.filter_by(key=f'report_schedule_{report_key}').first()
        if not config or not config.value:
            continue
        
        try:
            sched = json.loads(config.value)
        except (json.JSONDecodeError, ValueError):
            continue
        
        if not sched.get('enabled'):
            continue
        
        recipients = sched.get('recipients', [])
        if not recipients:
            continue
        
        # Check if this is the right time to run
        sched_time = sched.get('time', '08:00')
        if current_hour != sched_time:
            continue
        
        freq = sched.get('frequency', 'weekly')
        if freq == 'weekly' and current_dow != sched.get('day_of_week', 1):
            continue
        if freq == 'monthly' and current_dom != sched.get('day_of_month', 1):
            continue
        
        # Time matches — send the report
        logger.info(f"Running scheduled report: {report_key} ({freq} at {sched_time})")
        try:
            send_report(report_key, recipients, sched.get('format', 'csv'))
        except Exception as e:
            logger.error(f"Scheduled report {report_key} failed: {e}")


# Legacy functions kept for backward compatibility
def run_daily_expiry_report():
    """Run daily expiring certificates report (legacy)"""
    config = SystemConfig.query.filter_by(key='report_expiry_enabled').first()
    if not config or config.value != 'true':
        return
    
    recipients_config = SystemConfig.query.filter_by(key='report_expiry_recipients').first()
    if not recipients_config:
        return
    
    try:
        recipients = json.loads(recipients_config.value)
        ReportService.send_scheduled_report(
            'expiring_certificates',
            recipients,
            {'days': 30, 'format': 'csv'}
        )
    except Exception as e:
        logger.error(f"Daily expiry report failed: {e}")


def run_weekly_compliance_report():
    """Run weekly compliance status report (legacy)"""
    config = SystemConfig.query.filter_by(key='report_compliance_enabled').first()
    if not config or config.value != 'true':
        return
    
    recipients_config = SystemConfig.query.filter_by(key='report_compliance_recipients').first()
    if not recipients_config:
        return
    
    try:
        recipients = json.loads(recipients_config.value)
        ReportService.send_scheduled_report(
            'compliance_status',
            recipients,
            {'format': 'csv'}
        )
    except Exception as e:
        logger.error(f"Weekly compliance report failed: {e}")

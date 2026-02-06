"""
Report Service - UCM Pro
Generates and schedules compliance reports (certificates, CAs, audit, expiry).
"""
from datetime import datetime, timedelta
from flask import current_app
import json
import csv
import io
import base64
from models import db, Certificate, CA, User, AuditLog, SystemConfig
from services.email_service import EmailService
import logging

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
    }
    
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
            'generated_at': datetime.utcnow().isoformat(),
            'parameters': params,
            'format': format_type,
            'content': content,
            'summary': data.get('summary', {}),
        }
    
    @classmethod
    def _generate_certificate_inventory(cls, params: dict) -> dict:
        """Generate certificate inventory report"""
        certs = Certificate.query.all()
        
        items = []
        stats = {'total': 0, 'valid': 0, 'expired': 0, 'revoked': 0, 'pending': 0}
        
        for cert in certs:
            status = cert.status or 'unknown'
            stats['total'] += 1
            if status in stats:
                stats[status] += 1
            
            items.append({
                'id': cert.id,
                'common_name': cert.common_name,
                'serial_number': cert.serial_number,
                'status': status,
                'issuer': cert.issuer,
                'not_before': cert.not_before,
                'not_after': cert.not_after,
                'key_type': cert.get_key_type(),
                'source': cert.source,
                'created_at': cert.created_at,
            })
        
        return {
            'items': items,
            'columns': ['id', 'common_name', 'serial_number', 'status', 'issuer', 
                       'not_before', 'not_after', 'key_type', 'source'],
            'summary': stats,
        }
    
    @classmethod
    def _generate_expiring_certificates(cls, params: dict) -> dict:
        """Generate expiring certificates report"""
        days = params.get('days', 30)
        threshold = datetime.utcnow() + timedelta(days=days)
        
        certs = Certificate.query.filter(
            Certificate.not_after != None,
            Certificate.not_after <= threshold,
            Certificate.status.in_(['valid', 'active'])
        ).order_by(Certificate.not_after).all()
        
        items = []
        for cert in certs:
            days_remaining = (cert.not_after - datetime.utcnow()).days if cert.not_after else None
            items.append({
                'id': cert.id,
                'common_name': cert.common_name,
                'serial_number': cert.serial_number,
                'issuer': cert.issuer,
                'not_after': cert.not_after,
                'days_remaining': days_remaining,
                'source': cert.source,
            })
        
        return {
            'items': items,
            'columns': ['id', 'common_name', 'serial_number', 'issuer', 
                       'not_after', 'days_remaining', 'source'],
            'summary': {
                'total_expiring': len(items),
                'threshold_days': days,
            },
        }
    
    @classmethod
    def _generate_ca_hierarchy(cls, params: dict) -> dict:
        """Generate CA hierarchy report"""
        cas = CA.query.all()
        
        items = []
        stats = {'total': 0, 'root': 0, 'intermediate': 0}
        
        for ca in cas:
            is_root = ca.parent_refid is None
            stats['total'] += 1
            if is_root:
                stats['root'] += 1
            else:
                stats['intermediate'] += 1
            
            cert_count = Certificate.query.filter_by(ca_id=ca.id).count()
            
            items.append({
                'id': ca.id,
                'refid': ca.refid,
                'common_name': ca.common_name,
                'parent_refid': ca.parent_refid,
                'is_root': is_root,
                'not_before': ca.not_before,
                'not_after': ca.not_after,
                'key_type': ca.key_type,
                'issued_certificates': cert_count,
                'crl_url': ca.crl_url,
            })
        
        return {
            'items': items,
            'columns': ['id', 'refid', 'common_name', 'parent_refid', 'is_root',
                       'not_before', 'not_after', 'key_type', 'issued_certificates'],
            'summary': stats,
        }
    
    @classmethod
    def _generate_audit_summary(cls, params: dict) -> dict:
        """Generate audit log summary report"""
        days = params.get('days', 7)
        since = datetime.utcnow() - timedelta(days=days)
        
        logs = AuditLog.query.filter(
            AuditLog.timestamp >= since
        ).all()
        
        # Aggregate by action
        by_action = {}
        by_user = {}
        by_resource = {}
        
        for log in logs:
            action = log.action or 'unknown'
            user = log.username or 'system'
            resource = log.resource_type or 'unknown'
            
            by_action[action] = by_action.get(action, 0) + 1
            by_user[user] = by_user.get(user, 0) + 1
            by_resource[resource] = by_resource.get(resource, 0) + 1
        
        # Top 10 of each
        top_actions = sorted(by_action.items(), key=lambda x: x[1], reverse=True)[:10]
        top_users = sorted(by_user.items(), key=lambda x: x[1], reverse=True)[:10]
        top_resources = sorted(by_resource.items(), key=lambda x: x[1], reverse=True)[:10]
        
        return {
            'items': [
                {'category': 'actions', 'data': dict(top_actions)},
                {'category': 'users', 'data': dict(top_users)},
                {'category': 'resources', 'data': dict(top_resources)},
            ],
            'columns': ['category', 'data'],
            'summary': {
                'total_events': len(logs),
                'period_days': days,
                'unique_users': len(by_user),
                'unique_actions': len(by_action),
            },
        }
    
    @classmethod
    def _generate_compliance_status(cls, params: dict) -> dict:
        """Generate compliance status report"""
        # Check for policy violations
        items = []
        issues = []
        
        # Check certificates without proper extensions
        certs_no_key_usage = Certificate.query.filter(
            Certificate.status.in_(['valid', 'active'])
        ).count()  # Simplified - would need extension parsing
        
        # Check expired CAs
        expired_cas = CA.query.filter(
            CA.not_after < datetime.utcnow()
        ).count()
        
        # Check weak keys (RSA < 2048)
        # This is simplified - would need actual key analysis
        
        # Build compliance items
        items.append({
            'check': 'Expired CAs',
            'status': 'pass' if expired_cas == 0 else 'fail',
            'count': expired_cas,
            'severity': 'high' if expired_cas > 0 else 'none',
        })
        
        # Check for certificates expiring soon (< 30 days)
        threshold = datetime.utcnow() + timedelta(days=30)
        expiring_soon = Certificate.query.filter(
            Certificate.not_after <= threshold,
            Certificate.status.in_(['valid', 'active'])
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
    def send_scheduled_report(cls, report_type: str, recipients: list, params: dict = None):
        """
        Generate and email a scheduled report.
        
        Args:
            report_type: Type of report to generate
            recipients: List of email addresses
            params: Report parameters
        """
        try:
            params = params or {}
            params['format'] = 'csv'  # CSV for email attachments
            
            report = cls.generate_report(report_type, params)
            
            subject = f"UCM Report: {report['report_name']} - {datetime.utcnow().strftime('%Y-%m-%d')}"
            
            # Build email body
            body = f"""
UCM Scheduled Report: {report['report_name']}

Generated: {report['generated_at']}
Parameters: {json.dumps(report['parameters'])}

Summary:
{json.dumps(report['summary'], indent=2)}

The full report is attached as a CSV file.

--
Ultimate CA Manager
            """
            
            # Send to each recipient
            for recipient in recipients:
                try:
                    EmailService.send_email(
                        to=recipient,
                        subject=subject,
                        body=body,
                        html=f"<pre>{body}</pre>",
                    )
                    logger.info(f"Sent {report_type} report to {recipient}")
                except Exception as e:
                    logger.error(f"Failed to send report to {recipient}: {e}")
            
        except Exception as e:
            logger.error(f"Failed to generate scheduled report {report_type}: {e}")


# Scheduled task functions for scheduler service
def run_daily_expiry_report():
    """Run daily expiring certificates report"""
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
    """Run weekly compliance status report"""
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

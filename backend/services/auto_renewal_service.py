"""
Certificate Auto-Renewal Service
Automatically renews certificates before they expire.
"""
from datetime import datetime, timedelta
from models import db, Certificate, CA, SystemConfig, AuditLog
from services.ca_service import CAService
import logging
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class AutoRenewalService:
    """Service for automatic certificate renewal"""
    
    @staticmethod
    def get_renewal_config():
        """Get auto-renewal configuration"""
        config = {
            'enabled': False,
            'days_before_expiry': 30,
            'renewal_sources': ['scep', 'acme', 'est'],  # Which sources to auto-renew
            'notify_on_renewal': True,
            'notify_on_failure': True,
        }
        
        enabled = SystemConfig.query.filter_by(key='auto_renewal_enabled').first()
        if enabled:
            config['enabled'] = enabled.value == 'true'
        
        days = SystemConfig.query.filter_by(key='auto_renewal_days').first()
        if days:
            config['days_before_expiry'] = int(days.value)
        
        sources = SystemConfig.query.filter_by(key='auto_renewal_sources').first()
        if sources:
            import json
            config['renewal_sources'] = json.loads(sources.value)
        
        return config
    
    @staticmethod
    def set_renewal_config(config: dict):
        """Update auto-renewal configuration"""
        import json
        
        for key, value in config.items():
            db_key = f'auto_renewal_{key}'
            if key == 'enabled':
                db_value = 'true' if value else 'false'
            elif key == 'renewal_sources':
                db_value = json.dumps(value)
            else:
                db_value = str(value)
            
            existing = SystemConfig.query.filter_by(key=db_key).first()
            if existing:
                existing.value = db_value
            else:
                db.session.add(SystemConfig(key=db_key, value=db_value))
        
        db.session.commit()
    
    @staticmethod
    def get_certificates_for_renewal():
        """Get certificates eligible for auto-renewal"""
        config = AutoRenewalService.get_renewal_config()
        if not config['enabled']:
            return []

        threshold = utc_now() + timedelta(days=config['days_before_expiry'])

        # NOTE: Certificate has no `status` column — `revoked` boolean + `archived` instead.
        # Expiry uses `valid_to`, not `not_after`.
        certs = Certificate.query.filter(
            Certificate.revoked.is_(False),
            (Certificate.archived.is_(False)) | (Certificate.archived.is_(None)),
            Certificate.valid_to.isnot(None),
            Certificate.valid_to <= threshold,
            Certificate.valid_to >= utc_now(),  # don't try to renew already-expired
            Certificate.crt.isnot(None),  # only issued certs, not CSRs
            Certificate.source.in_(config['renewal_sources'])
        ).all()

        return certs

    @staticmethod
    def renew_certificate(cert: Certificate) -> tuple:
        """
        Renew a single certificate.

        Returns:
            (success: bool, new_cert_id or error_message: int|str)
        """
        try:
            # Get the CA that issued this certificate (join on refid, not id)
            ca = CA.query.filter_by(refid=cert.caref).first() if cert.caref else None
            if not ca:
                return False, "Issuing CA not found"

            # Check CA is still valid
            if ca.valid_to and ca.valid_to < utc_now():
                return False, "Issuing CA has expired"

            # Calculate new validity (same as original or default)
            if cert.valid_from and cert.valid_to:
                original_days = (cert.valid_to - cert.valid_from).days
            else:
                original_days = 365

            # Re-issue with same subject and SANs
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend

            if cert.csr:
                # Re-sign original CSR
                import base64
                csr_pem = base64.b64decode(cert.csr).decode()
                csr = x509.load_pem_x509_csr(csr_pem.encode(), default_backend())
            else:
                # Can't renew without CSR
                return False, "Original CSR not available for renewal"

            # Sign with new validity
            new_cert_pem, serial = CAService.sign_csr_from_crypto(
                ca=ca,
                csr=csr,
                validity_days=original_days,
                source=f'{cert.source}-renewal'
            )

            # Get new certificate ID — scope by caref to disambiguate across CAs (#85)
            new_cert = Certificate.query.filter_by(
                serial_number=serial, caref=ca.refid
            ).order_by(Certificate.id.desc()).first()

            # Archive old certificate (no `superseded` status column exists)
            cert.archived = True

            # Audit log
            log = AuditLog(
                action='certificate.auto_renewed',
                resource_type='certificate',
                resource_id=new_cert.id if new_cert else None,
                resource_name=cert.common_name,
                details=f'Auto-renewed cert {cert.id}, new cert {new_cert.id if new_cert else "unknown"}'
            )
            db.session.add(log)
            db.session.commit()

            logger.info(f"Auto-renewed certificate {cert.id} -> {new_cert.id if new_cert else 'unknown'}")
            return True, new_cert.id if new_cert else 0

        except Exception as e:
            db.session.rollback()
            logger.error(f"Auto-renewal failed for cert {cert.id}: {e}")
            return False, "Renewal failed"
    
    @staticmethod
    def run_auto_renewal():
        """
        Run auto-renewal for all eligible certificates.
        This is called by the scheduler service.
        """
        config = AutoRenewalService.get_renewal_config()
        if not config['enabled']:
            logger.debug("Auto-renewal is disabled")
            return {'renewed': 0, 'failed': 0, 'skipped': 0}
        
        certs = AutoRenewalService.get_certificates_for_renewal()
        
        stats = {'renewed': 0, 'failed': 0, 'skipped': 0, 'errors': []}

        for cert in certs:
            # Skip already-archived (already processed / superseded)
            if cert.archived:
                stats['skipped'] += 1
                continue

            success, result = AutoRenewalService.renew_certificate(cert)

            if success:
                stats['renewed'] += 1
            else:
                stats['failed'] += 1
                stats['errors'].append({
                    'cert_id': cert.id,
                    'common_name': cert.common_name,
                    'error': result
                })
        
        logger.info(f"Auto-renewal complete: {stats['renewed']} renewed, {stats['failed']} failed")
        
        # Send notifications if configured
        if config.get('notify_on_renewal') and stats['renewed'] > 0:
            AutoRenewalService._send_renewal_notification(stats)
        
        if config.get('notify_on_failure') and stats['failed'] > 0:
            AutoRenewalService._send_failure_notification(stats)
        
        return stats
    
    @staticmethod
    def _send_renewal_notification(stats: dict):
        """Send notification about successful renewals"""
        from services.email_service import EmailService
        
        recipients = SystemConfig.query.filter_by(key='auto_renewal_notify_emails').first()
        if not recipients:
            return
        
        import json
        emails = json.loads(recipients.value)
        
        for email in emails:
            try:
                EmailService.send_email(
                    to=email,
                    subject=f'UCM: {stats["renewed"]} certificates auto-renewed',
                    body=f'The following {stats["renewed"]} certificates were automatically renewed.',
                    html=f'<p>The following {stats["renewed"]} certificates were automatically renewed.</p>'
                )
            except Exception as e:
                logger.error(f"Failed to send renewal notification: {e}")
    
    @staticmethod
    def _send_failure_notification(stats: dict):
        """Send notification about failed renewals"""
        from services.email_service import EmailService
        
        recipients = SystemConfig.query.filter_by(key='auto_renewal_notify_emails').first()
        if not recipients:
            return
        
        import json
        emails = json.loads(recipients.value)
        
        error_list = '\n'.join([
            f"- {e['common_name']} (ID: {e['cert_id']}): {e['error']}"
            for e in stats.get('errors', [])
        ])
        
        for email in emails:
            try:
                EmailService.send_email(
                    to=email,
                    subject=f'UCM: {stats["failed"]} certificate renewals FAILED',
                    body=f'The following certificate renewals failed:\n\n{error_list}',
                    html=f'<p>The following certificate renewals failed:</p><pre>{error_list}</pre>'
                )
            except Exception as e:
                logger.error(f"Failed to send failure notification: {e}")


# Scheduler task function
def run_auto_renewal_task():
    """Scheduled task for auto-renewal"""
    return AutoRenewalService.run_auto_renewal()

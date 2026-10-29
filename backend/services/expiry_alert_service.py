"""
Certificate expiry helpers: expiring-certificate listing (dashboard) and the
daily certificate.expiring / certificate.expired webhook pass.

E-mail alerts themselves are sent by services.notification (the scheduled
``cert_expiry_alerts`` task), which reads the cert_expiring row saved from
Settings > Email; the former in-memory ``ExpiryAlertSettings`` was never read
by the scheduler (#324) and has been removed.
"""
import logging
from datetime import timedelta
from typing import Dict, Any, List
from models import db, Certificate
from utils.datetime_utils import utc_now, utc_isoformat
from utils.days_remaining import days_remaining as compute_days_remaining

logger = logging.getLogger(__name__)


def get_expiring_certificates(days: int = 30, include_revoked: bool = False) -> List[Dict[str, Any]]:
    """
    Get certificates expiring within specified days
    
    Args:
        days: Number of days to look ahead
        include_revoked: Include revoked certificates
        
    Returns:
        List of certificate info dicts
    """
    now = utc_now()
    cutoff = now + timedelta(days=days)
    
    query = Certificate.query.filter(
        Certificate.valid_to <= cutoff,
        Certificate.valid_to > now
    )
    
    if not include_revoked:
        query = query.filter(
            db.or_(Certificate.revoked == False, Certificate.revoked == None)
        )
    
    certs = query.order_by(Certificate.valid_to.asc()).all()
    
    result = []
    for cert in certs:
        days_until = compute_days_remaining(cert.valid_to, now)
        result.append({
            'id': cert.id,
            'serial_number': cert.serial_number,
            'common_name': cert.descr,  # descr is used as common name
            'subject': cert.subject,
            'valid_to': utc_isoformat(cert.valid_to),
            'days_until_expiry': days_until,
            'issuer_ca_id': cert.caref,
            'revoked': cert.revoked or False
        })
    
    return result


def _emit_expiry_webhooks():
    """Fire certificate.expiring / certificate.expired webhooks.

    Independent of SMTP config (webhooks must work even when email is off).
    Runs daily with the scheduled check; 'expiring' is a recurring reminder
    for the active window, 'expired' is bounded to certs that crossed expiry
    in the last 24h so each expiry emits roughly once.
    """
    try:
        from services.webhook_service import emit_cert_expiring, emit_cert_expired
        from models import Certificate
        from utils.datetime_utils import utc_now
        from datetime import timedelta

        for cert in get_expiring_certificates(days=30, include_revoked=False):
            d = cert.get('days_until_expiry', 0)
            if d > 0:
                emit_cert_expiring(cert, days_left=d, ca_refid=cert.get('issuer_ca_id'))

        now = utc_now()
        just_expired = Certificate.query.filter(
            Certificate.valid_to <= now,
            Certificate.valid_to > now - timedelta(days=1),
            Certificate.revoked.isnot(True),
        ).all()
        for cert in just_expired:
            emit_cert_expired(cert.to_dict(), ca_refid=cert.caref)

        from services.ca.cross_certs import expiring_alerts
        soon, gone = expiring_alerts(days=30)
        for ca_refid, payload in soon:
            emit_cert_expiring(payload, days_left=payload['days_until_expiry'], ca_refid=ca_refid)
        for ca_refid, payload in gone:
            emit_cert_expired(payload, ca_refid=ca_refid)
    except Exception as e:
        logger.error(f"Expiry webhook pass failed: {e}")

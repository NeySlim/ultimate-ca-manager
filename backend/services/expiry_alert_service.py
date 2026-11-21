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


def get_expiring_certificates(days: int = 30, include_revoked: bool = False,
                              now=None) -> List[Dict[str, Any]]:
    """
    Get certificates expiring within specified days
    
    Args:
        days: Number of days to look ahead
        include_revoked: Include revoked certificates
        now: Reference instant (default: this host's clock)
        
    Returns:
        List of certificate info dicts
    """
    now = now or utc_now()
    cutoff = now + timedelta(days=days)
    
    query = Certificate.query.filter(
        Certificate.valid_to <= cutoff,
        Certificate.valid_to > now,
        # EST key generators renew by themselves; a replaced one stays archived until it expires
        Certificate.source.is_distinct_from('est_key_generator'),
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


def count_expired_between(after, until) -> int:
    """Unrevoked certificates and cross-certificates whose expiry falls in (after, until].

    Same rows as the 'expired' announcements: a cross-certificate counts only with its CA, as in expiring_alerts.
    """
    from models import CA
    from models.ca_cross_certificate import CACrossCertificate
    certs = Certificate.query.filter(
        Certificate.valid_to <= until, Certificate.valid_to > after,
        Certificate.revoked.isnot(True)).count()
    cross = CACrossCertificate.query.join(CA, CA.id == CACrossCertificate.ca_id).filter(
        CACrossCertificate.valid_to <= until, CACrossCertificate.valid_to > after,
        CACrossCertificate.revoked.is_(False)).count()
    return certs + cross


def _emit_expiry_webhooks(expiring=True, expired_after=None, now=None):
    """Fire certificate.expiring / certificate.expired webhooks.

    Independent of SMTP config (webhooks must work even when email is off).
    'expiring' is a recurring reminder for the active window; 'expired' covers
    certificates whose expiry falls in (expired_after, now], the last 24h by default.
    Returns False when the pass failed: its window is not covered and the mark must stay.
    """
    try:
        from services.webhook_service import emit_cert_expiring, emit_cert_expired
        from models import Certificate

        now = now or utc_now()
        expired_after = expired_after or now - timedelta(days=1)
        if expiring:
            for cert in get_expiring_certificates(days=30, include_revoked=False, now=now):
                d = cert.get('days_until_expiry', 0)
                if d > 0:
                    emit_cert_expiring(cert, days_left=d, ca_refid=cert.get('issuer_ca_id'))

        just_expired = Certificate.query.filter(
            Certificate.valid_to <= now,
            Certificate.valid_to > expired_after,
            Certificate.revoked.isnot(True),
        ).all()
        for cert in just_expired:
            emit_cert_expired(cert.to_dict(), ca_refid=cert.caref)

        from services.ca.cross_certs import expiring_alerts
        soon, gone = expiring_alerts(days=30, now=now, expired_after=expired_after)
        if expiring:
            for ca_refid, payload in soon:
                emit_cert_expiring(payload, days_left=payload['days_until_expiry'], ca_refid=ca_refid)
        for ca_refid, payload in gone:
            emit_cert_expired(payload, ca_refid=ca_refid)
    except Exception as e:
        logger.error(f"Expiry webhook pass failed: {e}")
        return False
    return True

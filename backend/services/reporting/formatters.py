"""Data formatting helpers and report data collection for UCM PDF reports."""
import os
import logging
from datetime import timedelta
from collections import Counter

from models import Certificate, CA, AuditLog
from services.compliance_service import calculate_compliance_score
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

# UCM brand colors (RGB tuples)
C = {
    'primary': (59, 130, 246),
    'primary_dark': (37, 99, 235),
    'success': (34, 197, 94),
    'warning': (234, 179, 8),
    'danger': (239, 68, 68),
    'dark': (15, 23, 42),
    'slate700': (51, 65, 85),
    'slate600': (71, 85, 105),
    'slate500': (100, 116, 139),
    'slate400': (148, 163, 184),
    'slate200': (226, 232, 240),
    'slate100': (241, 245, 249),
    'white': (255, 255, 255),
    'grade_a': (34, 197, 94),
    'grade_b': (59, 130, 246),
    'grade_c': (234, 179, 8),
    'grade_d': (249, 115, 22),
    'grade_f': (239, 68, 68),
    'accent_teal': (20, 184, 166),
}


def cert_status(cert, now):
    """Determine the status of a certificate."""
    if cert.revoked:
        return 'revoked'
    if cert.valid_to:
        if cert.valid_to < now:
            return 'expired'
        if (cert.valid_to - now).days <= 30:
            return 'expiring'
    return 'valid'


def score_to_grade(score):
    """Convert a numeric compliance score to a letter grade."""
    if score >= 95:
        return 'A+'
    if score >= 85:
        return 'A'
    if score >= 70:
        return 'B'
    if score >= 55:
        return 'C'
    if score >= 40:
        return 'D'
    return 'F'


def collect_report_data():
    """Collect and aggregate all data needed for report generation."""
    now = utc_now()

    all_certs = Certificate.query.all()
    active, expired, expiring_30, expiring_7, revoked = [], [], [], [], []
    status_counts = Counter()
    algo_counts = Counter()
    source_counts = Counter()
    lifetime_days = []
    compliance_scores = []
    compliance_breakdowns = []
    grade_counts = Counter()

    for cert in all_certs:
        status = cert_status(cert, now)
        status_counts[status] += 1
        if cert.key_algo:
            algo_counts[cert.key_algo.upper()] += 1
        source_counts[cert.source or 'manual'] += 1

        if cert.valid_from and cert.valid_to:
            lt = (cert.valid_to - cert.valid_from).days
            if lt > 0:
                lifetime_days.append(lt)

        if status == 'valid':
            active.append(cert)
        elif status == 'expired':
            expired.append(cert)
        elif status == 'revoked':
            revoked.append(cert)

        if cert.valid_to and not cert.revoked:
            days_left = (cert.valid_to - now).days
            if 0 < days_left <= 30:
                expiring_30.append(cert)
            if 0 < days_left <= 7:
                expiring_7.append(cert)

        try:
            cd = cert.to_dict() if hasattr(cert, 'to_dict') else cert
            sd = calculate_compliance_score(cd)
            compliance_scores.append(sd['score'])
            compliance_breakdowns.append(sd.get('breakdown', {}))
            grade_counts[sd['grade']] += 1
        except Exception:
            grade_counts['F'] += 1
            compliance_scores.append(0)

    # CAs
    all_cas = CA.query.all()
    root_cas = [ca for ca in all_cas if not ca.caref]
    intermediate_cas = [ca for ca in all_cas if ca.caref]

    # Average compliance per category
    category_scores = {}
    for bd in compliance_breakdowns:
        for cat, info in bd.items():
            if isinstance(info, dict) and 'score' in info and 'max' in info:
                if cat not in category_scores:
                    category_scores[cat] = {'total': 0, 'max': 0, 'count': 0}
                category_scores[cat]['total'] += info['score']
                category_scores[cat]['max'] += info['max']
                category_scores[cat]['count'] += 1

    avg_score = round(sum(compliance_scores) / len(compliance_scores)) if compliance_scores else 0
    avg_grade = score_to_grade(avg_score)

    # Audit (30 days)
    thirty_days_ago = now - timedelta(days=30)
    recent_logs = AuditLog.query.filter(AuditLog.timestamp >= thirty_days_ago).all()
    action_counts = Counter()
    daily_activity = Counter()
    failed_logins = 0
    unique_users = set()
    for log in recent_logs:
        action_counts[log.action] += 1
        if log.timestamp:
            daily_activity[log.timestamp.strftime('%Y-%m-%d')] += 1
        if log.action == 'login_failed':
            failed_logins += 1
        if log.username:
            unique_users.add(log.username)

    # Discovery scan info
    last_scan = None
    try:
        from models import DiscoveryHistory
        scan = DiscoveryHistory.query.order_by(DiscoveryHistory.id.desc()).first()
        if scan:
            last_scan = {
                'date': scan.started_at if hasattr(scan, 'started_at') else None,
                'hosts': getattr(scan, 'hosts_scanned', None),
                'certs_found': getattr(scan, 'certificates_found', None),
            }
    except Exception:
        pass

    # Risk assessment
    risk_score = 0
    risk_items = []
    if len(expiring_7) > 0:
        risk_score += 30
        risk_items.append(('CRITICAL', '%d cert(s) expire within 7 days' % len(expiring_7)))
    if len(expiring_30) > 3:
        risk_score += 15
        risk_items.append(('HIGH', '%d cert(s) expire within 30 days' % len(expiring_30)))
    elif len(expiring_30) > 0:
        risk_score += 5
        risk_items.append(('MEDIUM', '%d cert(s) expire within 30 days' % len(expiring_30)))
    if len(expired) > 0:
        risk_score += 20
        risk_items.append(('HIGH', '%d expired cert(s) still in inventory' % len(expired)))
    if avg_score < 50:
        risk_score += 25
        risk_items.append(('HIGH', 'Low compliance score (%d/100)' % avg_score))
    elif avg_score < 70:
        risk_score += 10
        risk_items.append(('MEDIUM', 'Moderate compliance (%d/100)' % avg_score))
    if failed_logins > 20:
        risk_score += 15
        risk_items.append(('HIGH', '%d failed logins in 30 days' % failed_logins))
    elif failed_logins > 5:
        risk_score += 5
        risk_items.append(('LOW', '%d failed logins in 30 days' % failed_logins))

    if risk_score >= 40:
        risk_level = 'HIGH'
    elif risk_score >= 15:
        risk_level = 'MEDIUM'
    else:
        risk_level = 'LOW'

    # Version
    version = 'N/A'
    try:
        for p in ['/opt/ucm/VERSION',
                  os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'VERSION')]:
            if os.path.exists(p):
                with open(p, 'r') as f:
                    version = f.read().strip()
                break
    except Exception:
        pass

    return {
        'generated_at': now,
        'version': version,
        'total_certs': len(all_certs),
        'active_certs': len(active),
        'expired_certs': len(expired),
        'expiring_30': expiring_30,
        'expiring_7': expiring_7,
        'revoked_certs': len(revoked),
        'status_counts': dict(status_counts),
        'algo_counts': dict(algo_counts),
        'source_counts': dict(source_counts),
        'lifetime_days': lifetime_days,
        'total_cas': len(all_cas),
        'root_cas': len(root_cas),
        'intermediate_cas': len(intermediate_cas),
        'ca_list': all_cas,
        'avg_score': avg_score,
        'avg_grade': avg_grade,
        'grade_counts': dict(grade_counts),
        'category_scores': category_scores,
        'action_counts': dict(action_counts),
        'daily_activity': dict(daily_activity),
        'failed_logins': failed_logins,
        'unique_users': len(unique_users),
        'total_audit_events': len(recent_logs),
        'all_certs': all_certs,
        'risk_level': risk_level,
        'risk_score': risk_score,
        'risk_items': risk_items,
        'last_scan': last_scan,
    }

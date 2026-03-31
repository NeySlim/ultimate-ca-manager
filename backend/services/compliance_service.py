"""
Certificate Compliance Scoring Service

Scores certificates A+ to F based on cryptographic strength,
validity, SANs, and industry best practices.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# Grade thresholds
GRADE_THRESHOLDS = [
    (95, 'A+'),
    (85, 'A'),
    (70, 'B'),
    (55, 'C'),
    (40, 'D'),
    (0, 'F'),
]


def calculate_compliance_score(cert_dict):
    """
    Calculate compliance score for a certificate.

    Args:
        cert_dict: Certificate dictionary from to_dict()

    Returns:
        dict with score, grade, and per-category breakdown
    """
    breakdown = {}

    # 1. Key Strength (30 points)
    breakdown['key_strength'] = _score_key_strength(cert_dict)

    # 2. Signature Algorithm (25 points)
    breakdown['signature'] = _score_signature(cert_dict)

    # 3. Validity Status (25 points)
    breakdown['validity'] = _score_validity(cert_dict)

    # 4. SAN Presence (10 points)
    breakdown['san'] = _score_san(cert_dict)

    # 5. Certificate Lifetime (10 points)
    breakdown['lifetime'] = _score_lifetime(cert_dict)

    total = sum(item['score'] for item in breakdown.values())
    total = min(total, 100)

    grade = 'F'
    for threshold, g in GRADE_THRESHOLDS:
        if total >= threshold:
            grade = g
            break

    return {
        'score': total,
        'grade': grade,
        'breakdown': breakdown,
    }


def _score_key_strength(cert_dict):
    """Score key algorithm and size (max 30 points)."""
    max_points = 30
    key_algo = (cert_dict.get('key_algorithm') or cert_dict.get('key_algo') or '').upper()
    key_size = cert_dict.get('key_size') or 0

    # Parse combined key_type like "RSA 2048" or "EC P-256"
    key_type = (cert_dict.get('key_type') or '').upper()
    if not key_algo and key_type:
        key_algo = key_type

    # Normalize
    if 'EC' in key_algo or 'ECDSA' in key_algo or 'P-' in key_algo or 'PRIME256V1' in key_type or 'PRIME384V1' in key_type or 'PRIME521V1' in key_type:
        algo_family = 'EC'
        key_info = key_algo + ' ' + key_type
        if 'P-521' in key_info or 'SECP521' in key_info or 'SECP521R1' in key_info or 'PRIME521V1' in key_info or key_size >= 521:
            score, reason = max_points, 'ECDSA P-521'
        elif 'P-384' in key_info or 'SECP384' in key_info or 'SECP384R1' in key_info or 'PRIME384V1' in key_info or key_size >= 384:
            score, reason = max_points, 'ECDSA P-384'
        elif 'P-256' in key_info or 'SECP256' in key_info or 'SECP256R1' in key_info or 'PRIME256V1' in key_info or key_size >= 256:
            score, reason = 25, 'ECDSA P-256'
        else:
            curve_name = 'unknown'
            if key_type:
                parts = key_type.split()
                if len(parts) >= 2:
                    curve_name = parts[-1]
            if key_size and key_size > 0:
                score, reason = 15, f'ECDSA {key_size}-bit'
            else:
                score, reason = 15, f'ECDSA ({curve_name})'
    elif 'ED25519' in key_algo or 'ED448' in key_algo:
        score, reason = max_points, key_algo.strip()
    elif 'RSA' in key_algo:
        algo_family = 'RSA'
        if key_size >= 4096:
            score, reason = max_points, f'RSA {key_size}'
        elif key_size >= 3072:
            score, reason = 25, f'RSA {key_size}'
        elif key_size >= 2048:
            score, reason = 20, f'RSA {key_size}'
        elif key_size >= 1024:
            score, reason = 5, f'RSA {key_size} (weak)'
        else:
            score, reason = 0, f'RSA {key_size} (critical)'
    else:
        score, reason = 10, key_algo or 'Unknown'

    return {'score': score, 'max': max_points, 'reason': reason}


def _score_signature(cert_dict):
    """Score signature algorithm (max 25 points)."""
    max_points = 25
    sig_algo = (cert_dict.get('signature_algorithm') or '').upper()

    if not sig_algo:
        return {'score': 10, 'max': max_points, 'reason': 'Unknown'}

    if 'SHA512' in sig_algo or 'SHA-512' in sig_algo:
        score, reason = max_points, 'SHA-512'
    elif 'SHA384' in sig_algo or 'SHA-384' in sig_algo:
        score, reason = max_points, 'SHA-384'
    elif 'SHA256' in sig_algo or 'SHA-256' in sig_algo:
        score, reason = 22, 'SHA-256'
    elif 'ED25519' in sig_algo or 'ED448' in sig_algo or 'EDDSA' in sig_algo:
        score, reason = max_points, sig_algo.strip()
    elif 'SHA1' in sig_algo or 'SHA-1' in sig_algo:
        score, reason = 0, 'SHA-1 (deprecated)'
    elif 'MD5' in sig_algo:
        score, reason = 0, 'MD5 (broken)'
    else:
        score, reason = 10, sig_algo.strip()

    return {'score': score, 'max': max_points, 'reason': reason}


def _score_validity(cert_dict):
    """Score validity status (max 25 points)."""
    max_points = 25
    status = (cert_dict.get('status') or '').lower()
    days_remaining = cert_dict.get('days_remaining')

    if status == 'revoked':
        return {'score': 0, 'max': max_points, 'reason': 'revoked'}

    if status == 'expired':
        return {'score': 0, 'max': max_points, 'reason': 'expired'}

    if days_remaining is not None:
        if days_remaining <= 0:
            return {'score': 0, 'max': max_points, 'reason': 'expired'}
        elif days_remaining <= 7:
            return {'score': 5, 'max': max_points, 'reason': 'expires_week'}
        elif days_remaining <= 30:
            return {'score': 15, 'max': max_points, 'reason': 'expires_month'}
        else:
            return {'score': max_points, 'max': max_points, 'reason': 'valid'}

    if status == 'valid':
        return {'score': max_points, 'max': max_points, 'reason': 'valid'}

    return {'score': 15, 'max': max_points, 'reason': 'unknown'}


def _score_san(cert_dict):
    """Score SAN presence (max 10 points)."""
    max_points = 10

    san_combined = cert_dict.get('san_combined') or ''
    san_dns = cert_dict.get('san_dns') or '[]'
    san_ip = cert_dict.get('san_ip') or '[]'
    san_email = cert_dict.get('san_email') or '[]'

    has_sans = bool(san_combined.strip()) or any(
        s not in ('[]', '', 'null', None)
        for s in [san_dns, san_ip, san_email]
    )

    cert_type = (cert_dict.get('cert_type') or '').lower()

    if cert_type in ('ca', 'root', 'intermediate'):
        # CAs don't need SANs
        return {'score': max_points, 'max': max_points, 'reason': 'ca_exempt'}

    if has_sans:
        return {'score': max_points, 'max': max_points, 'reason': 'present'}

    return {'score': 0, 'max': max_points, 'reason': 'missing'}


def _score_lifetime(cert_dict):
    """Score certificate lifetime duration (max 10 points).

    Industry best practice: ≤398 days for server certs.
    CAs are exempt from this check.
    """
    max_points = 10
    cert_type = (cert_dict.get('cert_type') or '').lower()

    if cert_type in ('ca', 'root', 'intermediate'):
        return {'score': max_points, 'max': max_points, 'reason': 'ca_exempt'}

    valid_from = cert_dict.get('valid_from')
    valid_to = cert_dict.get('valid_to')

    if not valid_from or not valid_to:
        return {'score': 5, 'max': max_points, 'reason': 'unknown'}

    try:
        if isinstance(valid_from, str):
            valid_from = datetime.fromisoformat(valid_from.replace('Z', '+00:00'))
        if isinstance(valid_to, str):
            valid_to = datetime.fromisoformat(valid_to.replace('Z', '+00:00'))

        # Make timezone-aware if naive
        if valid_from.tzinfo is None:
            valid_from = valid_from.replace(tzinfo=timezone.utc)
        if valid_to.tzinfo is None:
            valid_to = valid_to.replace(tzinfo=timezone.utc)

        lifetime_days = (valid_to - valid_from).days

        if lifetime_days <= 398:
            return {'score': max_points, 'max': max_points, 'reason': 'short'}
        elif lifetime_days <= 825:
            return {'score': 7, 'max': max_points, 'reason': 'moderate'}
        else:
            return {'score': 3, 'max': max_points, 'reason': 'long'}
    except (ValueError, TypeError):
        return {'score': 5, 'max': max_points, 'reason': 'unknown'}


def score_certificates_batch(cert_dicts):
    """Score multiple certificates efficiently.

    Args:
        cert_dicts: List of certificate dictionaries

    Returns:
        dict mapping cert id to compliance result
    """
    results = {}
    for cert in cert_dicts:
        cert_id = cert.get('id')
        try:
            results[cert_id] = calculate_compliance_score(cert)
        except Exception as e:
            logger.warning(f"Failed to score cert {cert_id}: {e}")
            results[cert_id] = {
                'score': 0,
                'grade': 'F',
                'breakdown': {},
            }
    return results

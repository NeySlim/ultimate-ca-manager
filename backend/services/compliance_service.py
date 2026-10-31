"""
Certificate Compliance Scoring Service

Scores certificates A+ to F based on cryptographic strength,
validity, SANs, and industry best practices.
"""

import logging
from datetime import datetime, timezone

from utils import key_algorithms
from utils.key_algorithms import normalize_label

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

    pq = _post_quantum(cert_dict, ('key_algorithm', 'key_algo', 'key_type'))
    if pq:
        return {'score': _pq_key_points(pq), 'max': max_points, 'reason': pq.label}
    if 'EC' in key_algo or 'ECDSA' in key_algo or 'P-' in key_algo or 'PRIME' in key_type:
        score, reason = _score_ec_key(cert_dict, key_size)
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


def _post_quantum(cert_dict, fields):
    for field in fields:
        pq = key_algorithms.post_quantum_info(cert_dict.get(field))
        if pq:
            return pq
    return None


# ML-DSA scores like the NIST curve of its category: 44 as P-256, 65 as P-384, 87 as P-521
_ML_DSA_POINTS = {2: 25, 3: 30, 5: 30}


def _pq_key_points(pq):
    """SLH-DSA (hash-based) scores full; ML-DSA as the classical curve of its category."""
    return 30 if pq.family == 'SLH-DSA' else _ML_DSA_POINTS.get(pq.security_level, 25)


# Brainpool scores like the NIST curve of the same size (BSI TR-02102-1)
_EC_POINTS = {'EC-P256': (25, 'ECDSA P-256'), 'EC-P384': (30, 'ECDSA P-384'),
              'EC-P521': (30, 'ECDSA P-521'), 'EC-BP256': (25, 'ECDSA brainpoolP256r1'),
              'EC-BP384': (30, 'ECDSA brainpoolP384r1'), 'EC-BP512': (30, 'ECDSA brainpoolP512r1')}
_EC_LABEL_BY_SIZE = {256: 'EC-P256', 384: 'EC-P384', 521: 'EC-P521'}


def key_algo_sort_points():
    """``(key_algo spelling, points)`` of every registered key, plus RSA 8192
    and 1024, scored by ``_score_key_strength`` itself for the SQL sort."""
    spellings = [(a.legacy_key_algo, a.key_size) for a in key_algorithms.ALGORITHMS]
    spellings += [('RSA 8192', 8192), ('RSA 1024', 1024)]
    spellings += [(n.label, None) for n in key_algorithms.slh_dsa_names()]
    return [(s, _score_key_strength({'key_algo': s, 'key_size': n})['score']) for s, n in spellings]


def key_algo_sort_levels():
    """``(key_algo spelling, NIST category)`` of every post-quantum key, which
    breaks ties between equal key strength points in the SQL sort."""
    levels = [(a.legacy_key_algo, a.security_level) for a in key_algorithms.ALGORITHMS if a.security_level]
    return levels + [(n.label, n.security_level) for n in key_algorithms.slh_dsa_names()]


def _score_ec_key(cert_dict, key_size):
    """Points for an EC key from its actual curve; a curve outside the registry
    (secp256k1) is named as such and scored as an unrated EC key."""
    unregistered = None
    for field in ('key_type', 'key_algo', 'key_algorithm'):
        spelling = str(cert_dict.get(field) or '').strip()
        parts = spelling.split()
        curves = parts[1:] if parts and parts[0].upper() in ('EC', 'ECDSA') else []
        for candidate in (spelling, *curves):
            label = normalize_label(candidate)
            if label in _EC_POINTS:
                return _EC_POINTS[label]
        if unregistered is None and len(curves) == 1:
            unregistered = curves[0]
    if unregistered:
        return 15, f'ECDSA {unregistered}'
    label = _EC_LABEL_BY_SIZE.get(key_size)
    if label:
        return _EC_POINTS[label]
    return 15, f'ECDSA ({key_size}-bit)'


def _score_signature(cert_dict):
    """Score signature algorithm (max 25 points)."""
    max_points = 25
    sig_algo = (cert_dict.get('signature_algorithm') or '').upper()

    if not sig_algo:
        return {'score': 10, 'max': max_points, 'reason': 'Unknown'}

    pq = _post_quantum(cert_dict, ('signature_algorithm',))
    if pq:  # the scheme fixes its own hash (SHAKE256 or SHA-2 inside it)
        return {'score': max_points, 'max': max_points, 'reason': pq.label}

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

"""
TSA Management Routes v2.0
/api/v2/tsa/* - TSA configuration and statistics
"""

from utils.signing_ca import signing_ca_problem
from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, SystemConfig, CA, Certificate, AuditLog
from services.audit_service import AuditService
from services.tsa_service import describe_configured_signer
import logging
import re

logger = logging.getLogger(__name__)

bp = Blueprint('tsa_v2', __name__)

_POLICY_OID_RE = re.compile(r'^[0-2](?:\.(?:0|[1-9]\d*)){1,}$')
_MAX_POLICY_OID_LENGTH = 255

# RFC 5280 §4.2.1.12 id-kp-timeStamping
_TIME_STAMPING_OID = '1.3.6.1.5.5.7.3.8'

# Protocol-enrolled certificates keep their private key on the client, and
# AD CS-proxied certificates are issued by an external CA: UCM cannot sign
# with any of them, so they are never offered as a dedicated TSA signer.
_NON_LOCAL_KEY_SOURCES = {'acme', 'letsencrypt', 'scep', 'est', 'msca'}


def _signer_candidate_view(cert):
    """Shape a Certificate as a dedicated-signer candidate, or None if unusable.

    Only certificates whose private key UCM holds and can decrypt, that carry
    the timeStamping EKU, and that are not revoked / expired are offered.
    """
    if cert.revoked or cert.archived:
        return None
    if (cert.private_key_location or 'stored') != 'stored' or not cert.has_private_key:
        return None
    if (cert.source or 'manual') in _NON_LOCAL_KEY_SOURCES:
        return None

    try:
        import base64
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        from cryptography.x509.oid import ExtensionOID
        from utils.datetime_utils import utc_now

        parsed = x509.load_pem_x509_certificate(
            base64.b64decode(cert.crt), default_backend()
        )
        try:
            eku = parsed.extensions.get_extension_for_oid(ExtensionOID.EXTENDED_KEY_USAGE)
        except x509.ExtensionNotFound:
            return None
        eku_oids = {oid.dotted_string for oid in eku.value}
        if _TIME_STAMPING_OID not in eku_oids:
            return None

        now = utc_now()
        if cert.valid_to and cert.valid_to <= now:
            return None
        if cert.valid_from and cert.valid_from > now:
            return None

        critical_exclusive = bool(eku.critical) and eku_oids == {_TIME_STAMPING_OID}
    except Exception:
        return None

    return {
        'refid': cert.refid,
        'descr': cert.descr,
        'subject': cert.subject,
        'subject_cn': cert.subject_cn or cert.common_name,
        'serial_number': cert.serial_number,
        'key_type': cert.key_type,
        'valid_to': cert.valid_to.isoformat() if cert.valid_to else None,
        'ca_name': cert.ca.descr if cert.ca else None,
        'eku_critical_exclusive': critical_exclusive,
    }


def _validate_signer_refid(refid):
    """Return (error_message, None) or (None, cert). Empty refid is invalid here."""
    cert = Certificate.query.filter_by(refid=refid).first()
    if cert is None or not cert.crt:
        return 'signer_cert_refid does not match a known certificate', None
    view = _signer_candidate_view(cert)
    if view is None:
        return (
            'The selected certificate cannot be a TSA signer: it must be a '
            'non-revoked, unexpired certificate whose private key UCM holds '
            'and that carries the timeStamping EKU', None
        )
    # "Can decrypt" is the operative requirement — actually try it.
    try:
        import base64
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        try:
            from security.encryption import decrypt_private_key
            prv_pem = decrypt_private_key(cert.prv)
        except ImportError:
            prv_pem = cert.prv
        load_pem_private_key(base64.b64decode(prv_pem), password=None,
                             backend=default_backend())
    except Exception:
        return 'The selected certificate private key cannot be decrypted by UCM', None
    return None, cert


def normalize_policy_oid(value):
    """Return a canonical policy OID string, or None when malformed."""
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if len(candidate) > _MAX_POLICY_OID_LENGTH or not _POLICY_OID_RE.fullmatch(candidate):
        return None
    first, second = (int(arc) for arc in candidate.split('.', 2)[:2])
    if first < 2 and second > 39:
        return None
    return candidate


def get_config(key, default=None):
    """Get config value from database"""
    config = SystemConfig.query.filter_by(key=key).first()
    return config.value if config else default


def set_config(key, value):
    """Set config value in database"""
    config = SystemConfig.query.filter_by(key=key).first()
    if config:
        config.value = str(value) if value is not None else None
    else:
        config = SystemConfig(key=key, value=str(value) if value is not None else None)
        db.session.add(config)


@bp.route('/api/v2/tsa/config', methods=['GET'])
@require_auth(['read:settings'])
def get_tsa_config():
    """Get TSA configuration from database"""
    ca_refid = get_config('tsa_ca_refid', '')
    ca_id = None
    ca_name = None
    if ca_refid:
        ca = CA.query.filter_by(refid=ca_refid).first()
        if ca:
            ca_id = ca.id
            ca_name = ca.descr

    return success_response(data={
        'enabled': get_config('tsa_enabled', 'false') == 'true',
        'ca_refid': ca_refid,
        'ca_id': ca_id,
        'ca_name': ca_name,
        'policy_oid': get_config('tsa_policy_oid', '1.2.3.4.1'),
        # Off by default: pre-2.200 deployments sign with the CA certificate
        # itself and must keep working. TSAService reads this key at signing
        # time; before it was surfaced here the toggle was settable only by
        # editing the database row directly.
        'require_dedicated_cert':
            get_config('tsa_require_dedicated_cert', 'false') == 'true',
        # Dedicated end-entity signer (#312). Empty string = the historical
        # CA-certificate signer. `signer` describes the configured certificate
        # (subject / serial / notAfter / chain status / usability).
        'signer_cert_refid': get_config('tsa_signer_cert_refid', ''),
        'signer': describe_configured_signer(),
    })


@bp.route('/api/v2/tsa/config', methods=['PATCH'])
@require_auth(['write:settings'])
def update_tsa_config():
    """Update TSA configuration in database"""
    data = request.json or {}

    policy_oid = None
    if 'policy_oid' in data:
        policy_oid = normalize_policy_oid(data['policy_oid'])
        if policy_oid is None:
            return error_response('policy_oid must be a valid OID', 400)

    if 'signer_cert_refid' in data:
        raw = data['signer_cert_refid']
        refid = raw.strip() if isinstance(raw, str) else ''
        if refid:
            err, _cert = _validate_signer_refid(refid)
            if err:
                return error_response(err, 400)
        set_config('tsa_signer_cert_refid', refid)

    if 'enabled' in data:
        set_config('tsa_enabled', 'true' if data['enabled'] else 'false')
    if 'require_dedicated_cert' in data:
        set_config(
            'tsa_require_dedicated_cert',
            'true' if data['require_dedicated_cert'] else 'false',
        )
    if 'ca_refid' in data or 'ca_id' in data:
        # Either form names the signing CA; a CA that cannot sign is refused
        # when it is chosen (a saved setting is not re-judged on every save)
        if 'ca_refid' in data:
            new_refid = data['ca_refid'] or ''
            ca = CA.query.filter_by(refid=new_refid).first() if new_refid else None
        else:
            ca = db.session.get(CA, data['ca_id']) if data['ca_id'] else None
            new_refid = ca.refid if ca else ''
        if new_refid and new_refid != get_config('tsa_ca_refid', ''):
            problem = signing_ca_problem(ca)
            if problem:
                return error_response(problem, 400)
        set_config('tsa_ca_refid', new_refid)
    if policy_oid is not None:
        set_config('tsa_policy_oid', policy_oid)

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update TSA config: {e}")
        return error_response('Failed to update TSA configuration', 500)

    AuditService.log_action(
        action='tsa_config_update',
        resource_type='tsa',
        resource_name='TSA Configuration',
        details='Updated TSA configuration',
        success=True
    )

    return success_response(message='TSA configuration saved')


@bp.route('/api/v2/tsa/signer-candidates', methods=['GET'])
@require_auth(['read:settings'])
def list_signer_candidates():
    """Certificates eligible to be the dedicated TSA signer (#312).

    A candidate is a non-revoked, non-archived, unexpired certificate whose
    private key UCM holds locally and that carries the timeStamping EKU.
    """
    rows = (
        Certificate.query
        .filter(Certificate.crt.isnot(None), Certificate.prv.isnot(None))
        .filter(Certificate.revoked.isnot(True))
        .filter(Certificate.archived.isnot(True))
        .all()
    )
    candidates = [v for v in (_signer_candidate_view(c) for c in rows) if v]
    candidates.sort(key=lambda v: (v['subject_cn'] or v['descr'] or '').lower())
    return success_response(data=candidates)


@bp.route('/api/v2/tsa/signer-certificate', methods=['POST'])
@require_auth(['write:settings', 'write:certificates'])
def issue_signer_certificate():
    """One-click issuance of a dedicated RFC 3161 TSA signing certificate (#312).

    Builds an end-entity certificate with a critical, exclusive timeStamping EKU
    (the generic issue path cannot), stores its key encrypted, and — when no
    usable dedicated signer is configured yet — selects it as
    ``tsa_signer_cert_refid`` in the same transaction.
    """
    from services.tsa_signer_cert import (
        issue_tsa_signer_certificate, TsaSignerIssueError,
    )

    data = request.json or {}

    # Reject wrong-typed inputs before they reach the issuer. bool() / .strip()
    # on a coerced value is how {"select": "false"} swaps a healthy signer and
    # {"cn": 123} 500s (#314 review).
    if 'select' in data and not isinstance(data['select'], bool):
        return error_response('select must be a boolean', 400)
    if data.get('cn') is not None and not isinstance(data['cn'], str):
        return error_response('cn must be a string', 400)

    ca = None
    if data.get('ca_refid'):
        ca = CA.query.filter_by(refid=data['ca_refid']).first()
    elif data.get('ca_id'):
        ca = db.session.get(CA, data['ca_id'])
    else:
        default_refid = get_config('tsa_ca_refid', '')
        if default_refid:
            ca = CA.query.filter_by(refid=default_refid).first()
    if ca is None:
        return error_response(
            'No issuing CA: pass ca_id / ca_refid or configure the TSA signing CA first',
            400,
        )

    # Auto-select only when nothing usable is configured. An explicit boolean
    # from the caller always wins, so the live signer is never swapped silently.
    current = describe_configured_signer()
    if 'select' in data:
        want_select = data['select']  # validated bool above
    else:
        want_select = not current.get('usable', False)

    actor = getattr(g, 'current_user', None)
    try:
        cert = issue_tsa_signer_certificate(
            ca=ca,
            cn=data.get('cn'),
            validity_days=data.get('validity_days'),
            key_type=data.get('key_type'),
            key_size=data.get('key_size'),
            curve=data.get('curve'),
            actor=getattr(actor, 'username', 'system'),
            actor_user_id=getattr(actor, 'id', None),
        )
    except TsaSignerIssueError as exc:
        return error_response(exc.message, exc.status)

    selected = False
    if want_select:
        set_config('tsa_signer_cert_refid', cert.refid)
        try:
            db.session.commit()
            selected = True
        except Exception as e:
            db.session.rollback()
            logger.error(f"Issued TSA signer {cert.refid} but failed to select it: {e}")

    AuditService.log_action(
        action='tsa_config_update',
        resource_type='tsa',
        resource_name='TSA Configuration',
        details=(f'Issued TSA signing certificate {cert.refid}'
                 + (' and selected it as the dedicated signer' if selected else '')),
        success=True,
    )

    return success_response(
        data={
            'certificate': cert.to_dict(),
            'selected': selected,
            'signer': describe_configured_signer(),
        },
        message='TSA signing certificate issued',
    )


@bp.route('/api/v2/tsa/stats', methods=['GET'])
@require_auth(['read:settings'])
def get_tsa_stats():
    """Get TSA statistics from audit logs"""
    try:
        total = AuditLog.query.filter(
            AuditLog.action.like('tsa.%') | AuditLog.details.like('%TSA%timestamp%')
        ).count()
        successful = AuditLog.query.filter(
            (AuditLog.action.like('tsa.%') | AuditLog.details.like('%TSA%timestamp%')),
            AuditLog.success == True
        ).count()
        failed = AuditLog.query.filter(
            (AuditLog.action.like('tsa.%') | AuditLog.details.like('%TSA%timestamp%')),
            AuditLog.success == False
        ).count()

        return success_response(data={
            'total': total,
            'successful': successful,
            'failed': failed,
        })
    except Exception as e:
        logger.error(f"Failed to get TSA stats: {e}")
        return success_response(data={
            'total': 0,
            'successful': 0,
            'failed': 0,
        })

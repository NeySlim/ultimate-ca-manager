"""
System HTTPS Operations
"""

from . import bp
from flask import request, current_app, Response
from auth.unified import require_auth
from utils.ha import ha_enabled
from services.https_binding import restart_to_serve
from utils.response import success_response, error_response
from models import Certificate, db, SystemConfig
from services.audit_service import AuditService
from pathlib import Path
import os
from datetime import datetime, timedelta, timezone
import logging
from utils.datetime_utils import to_naive_utc, utc_now, utc_isoformat
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from utils import key_algorithms
from utils.issuance_defaults import BASELINE_ISSUE_KEY
from utils.key_codec import private_key_to_pem

logger = logging.getLogger(__name__)


def _actor():
    from flask import g
    user = getattr(g, 'current_user', None)
    return getattr(user, 'username', None)


def _https_attention():
    """The renewed certificate the HTTPS binding could not follow (no key in UCM), or None."""
    from services.binding_attention import REASON_SUCCESSOR_WITHOUT_KEY, https_left_behind_for
    refid = https_left_behind_for()
    if not refid:
        return None
    successor = Certificate.query.filter_by(refid=refid).first()
    return {
        'reason': REASON_SUCCESSOR_WITHOUT_KEY,
        'successor_id': successor.id if successor else None,
        'successor_refid': refid,
        'successor_descr': successor.descr if successor else None,
        'successor_has_key': bool(successor and successor.has_private_key),
        'successor_archived': bool(successor and successor.archived),
    }


@bp.route('/api/v2/system/https/cert-info', methods=['GET'])
@require_auth(['read:settings'])
def get_https_cert_info():
    """Get information about the current HTTPS certificate"""
    data_dir = os.environ.get('DATA_DIR', '/opt/ucm/data')
    cert_path = Path(os.environ.get('HTTPS_CERT_PATH', f'{data_dir}/https_cert.pem'))

    if not cert_path.exists():
        return success_response(data={
            'common_name': 'Not configured',
            'issuer': '-',
            'valid_from': None,
            'valid_to': None,
            'fingerprint': '-',
            'type': 'none'
        })

    try:
        cert_pem = cert_path.read_bytes()
        cert = x509.load_pem_x509_certificate(cert_pem)

        # Extract subject CN
        cn = None
        for attr in cert.subject:
            if attr.oid == x509.oid.NameOID.COMMON_NAME:
                cn = attr.value
                break

        # Extract issuer CN
        issuer_cn = None
        for attr in cert.issuer:
            if attr.oid == x509.oid.NameOID.COMMON_NAME:
                issuer_cn = attr.value
                break

        # Check if self-signed
        is_self_signed = cert.subject == cert.issuer

        # Calculate fingerprint
        fingerprint = cert.fingerprint(hashes.SHA256()).hex()
        fingerprint_formatted = ':'.join(fingerprint[i:i+2].upper() for i in range(0, len(fingerprint), 2))

        # Dedicated binding (#303 M1): which managed certificate follows
        # renewals automatically, surfaced so the UI can show it (#303 follow-up)
        bound = None
        try:
            from services.https_binding import get_bound_refid
            bound_refid = get_bound_refid()
            if bound_refid:
                from models import Certificate
                row = Certificate.query.filter_by(refid=bound_refid).first()
                bound = {
                    'refid': bound_refid,
                    'descr': row.descr if row else None,
                    'common_name': row.common_name if row else None,
                    'exists': bool(row and row.crt and row.prv),
                    'needs_attention': _https_attention(),
                }
        except Exception as e:
            logger.warning(f"Could not resolve HTTPS binding: {e}")

        return success_response(data={
            'bound_certificate': bound,
            'common_name': cn or 'Unknown',
            'issuer': issuer_cn or 'Unknown',
            'valid_from': utc_isoformat(cert.not_valid_before_utc),
            'valid_to': utc_isoformat(cert.not_valid_after_utc),
            'fingerprint': fingerprint_formatted[:47] + '...',
            'type': 'Self-Signed' if is_self_signed else 'CA-Signed',
            'serial': format(cert.serial_number, 'x').upper()
        })
    except Exception as e:
        logger.error(f"Failed to read HTTPS cert: {e}")
        return success_response(data={
            'common_name': 'Error reading certificate',
            'issuer': 'Unknown',
            'valid_from': None,
            'valid_to': None,
            'fingerprint': '-',
            'type': 'error'
        })


@bp.route('/api/v2/system/https/unbind', methods=['POST'])
@require_auth(['admin:system'])
def unbind_https_cert():
    """Stop following renewals of the bound HTTPS certificate (#303 M1).

    The files currently on disk are left untouched; only the automatic
    re-materialization on renewal stops.
    """
    from services.https_binding import get_bound_refid, set_bound_refid

    refid = get_bound_refid()
    if not refid:
        return error_response('No certificate is bound to HTTPS', 400)
    set_bound_refid('')
    AuditService.log_action(
        action='https_apply', resource_type='system', resource_id='ucm',
        resource_name='HTTPS binding',
        details=f'HTTPS certificate binding cleared (was {refid})', success=True,
    )
    return success_response(message='HTTPS certificate binding cleared')


@bp.route('/api/v2/system/https/regenerate', methods=['POST'])
@require_auth(['admin:system'])
def regenerate_https_cert():
    """Regenerate self-signed HTTPS certificate"""
    data = request.json or {}
    common_name = data.get('common_name', 'localhost')
    validity_days = data.get('validity_days', 365)

    try:
        # Generate private key
        private_key = key_algorithms.generate(BASELINE_ISSUE_KEY)

        # Build certificate
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "NL"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Ultimate Certificate Manager"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name[:64]),
        ])

        now = datetime.now(timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=validity_days))
            .add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName(common_name),
                    x509.DNSName("localhost"),
                ]),
                critical=False,
            )
            .sign(private_key, hashes.SHA256())
        )

        cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode('ascii')
        key_pem = private_key_to_pem(private_key).decode('ascii')
        from boot_config import write_https_pair
        from services.https_binding import _paths, set_bound_refid
        from services import shared_files
        cert_path, key_path = _paths()
        write_https_pair(cert_path, key_path, cert_pem, key_pem,
                         backup_suffix=utc_now().strftime('%Y%m%d_%H%M%S'))

        current_app.logger.info(f"Regenerated HTTPS certificate for {common_name}")

        # A regenerated self-signed certificate replaces any bound managed one (#303).
        # HA: the pair is kept for the other nodes, which write it as they restart.
        try:
            if ha_enabled():
                import json
                shared_files.store_file(shared_files.HTTPS_GENERATED,
                                 json.dumps({'crt': cert_pem, 'key': key_pem}).encode('utf-8'),
                                 actor=_actor())
            else:
                shared_files.drop_file(shared_files.HTTPS_GENERATED)
            set_bound_refid('')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Could not store the regenerated HTTPS certificate: {e}")
            # Not restarted: the next start writes the pair the database still names
            if ha_enabled():
                return error_response(
                    "Certificate regenerated on this node only: it could not be stored "
                    "for the other nodes", 500)
            return error_response(
                "Certificate written but not recorded: the service was not restarted, "
                "and its next start serves the previous certificate", 500)

        AuditService.log_action(
            action='https_regenerate',
            resource_type='system',
            resource_name='HTTPS Certificate',
            details=f'Regenerated self-signed HTTPS certificate for {common_name}',
            success=True
        )

        started, msg = restart_to_serve()
        if started is None:
            return success_response(
                message="Certificate regenerated. Restart the container to apply.",
                data={'requires_container_restart': True}
            )
        if not started:
            return success_response(
                message="Certificate regenerated but service restart failed. Please restart manually.",
                data={'restart_failed': True, 'error': msg}
            )

        return success_response(message="Certificate regenerated. Service restarting...")

    except Exception as e:
        current_app.logger.error(f"Failed to regenerate HTTPS cert: {e}")
        return error_response("Failed to regenerate certificate", 500)


@bp.route('/api/v2/system/https/apply', methods=['POST'])
@require_auth(['admin:system'])
def apply_https_cert():
    """Apply a managed certificate to HTTPS"""
    data = request.json
    cert_id = data.get('cert_id')

    if not cert_id:
        return error_response("Certificate ID required", 400)

    cert = db.session.get(Certificate, cert_id)
    if not cert:
        return error_response("Certificate not found", 404)

    # Verify cert has private key
    if not cert.prv:
        return error_response("Certificate has no private key - cannot use for HTTPS", 400)
    if not cert.crt:
        return error_response("Certificate has not been issued - cannot use for HTTPS", 400)
    if cert.revoked:
        return error_response("Certificate is revoked - cannot use for HTTPS", 400)
    if cert.valid_to is not None and to_naive_utc(cert.valid_to) <= utc_now():
        return error_response("Certificate has expired - cannot use for HTTPS", 400)

    try:
        from services.https_binding import https_key_pem, materialize_https_cert, set_bound_refid
        try:
            https_key_pem(cert)
        except ValueError as exc:
            logger.error(f"HTTPS apply: private key unreadable: {exc}")
            return error_response(
                "The private key of this certificate could not be read. "
                "The certificate and key in use were not replaced", 400)

        # Leaf, chain and key, written whole or not at all (also how every node writes it at start)
        full_cert = materialize_https_cert(cert)
        current_app.logger.info(f"Applied certificate {cert.refid} as HTTPS cert")

        # Remember the binding so a renewal re-materializes the files (#303), and so the
        # other nodes (HA) write the same files when they restart
        try:
            set_bound_refid(cert.refid, chain=full_cert)
        except Exception as e:
            current_app.logger.warning(f"Could not persist HTTPS binding: {e}")
            # Not restarted: the next start writes the certificate the database still names
            if ha_enabled():
                return error_response(
                    "Certificate applied on this node only: the binding could not be stored", 500)
            return error_response(
                "Certificate written but not recorded: the service was not restarted, "
                "and its next start serves the previous certificate", 500)

        AuditService.log_action(
            action='https_apply',
            resource_type='system',
            resource_id=str(cert_id),
            resource_name=cert.descr or cert.refid,
            details=f'Applied certificate {cert.refid} as HTTPS certificate',
            success=True
        )

        started, msg = restart_to_serve()
        if started is None:
            return success_response(
                message="Certificate applied. Restart the container to apply.",
                data={'requires_container_restart': True}
            )
        if not started:
            return success_response(
                message="Certificate applied but service restart failed. Please restart manually.",
                data={'restart_failed': True, 'error': msg}
            )

        return success_response(message="Certificate applied. Service restarting...")

    except Exception as e:
        current_app.logger.error(f"Failed to apply HTTPS cert: {e}")
        return error_response("Failed to apply certificate", 500)

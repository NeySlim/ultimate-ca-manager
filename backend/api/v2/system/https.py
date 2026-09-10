"""
System HTTPS Operations
"""

from . import bp
from flask import request, current_app, Response
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import Certificate, CA, db, SystemConfig
from services.audit_service import AuditService
from services.ca_service import CAService
from pathlib import Path
import os
import shutil
import base64
from datetime import datetime, timedelta, timezone
import logging
from utils.datetime_utils import utc_now, utc_isoformat
from config.settings import is_docker
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from utils.key_codec import private_key_to_pem

logger = logging.getLogger(__name__)


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
                    'exists': bool(row and row.crt and row.prv),
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
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )

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

        # Get cert paths dynamically - same logic as gunicorn.conf.py
        data_dir = os.environ.get('DATA_DIR', '/opt/ucm/data')
        cert_path = Path(os.environ.get('HTTPS_CERT_PATH', f'{data_dir}/https_cert.pem'))
        key_path = Path(os.environ.get('HTTPS_KEY_PATH', f'{data_dir}/https_key.pem'))

        # Backup existing
        if cert_path.exists():
            backup_suffix = utc_now().strftime('%Y%m%d_%H%M%S')
            shutil.copy(cert_path, f"{cert_path}.backup-{backup_suffix}")
        if key_path.exists():
            shutil.copy(key_path, f"{key_path}.backup-{backup_suffix}")

        # Write new cert and key
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(private_key_to_pem(private_key))
        os.chmod(key_path, 0o600)

        # Set ownership to the ucm service user (POSIX only; skipped elsewhere / if absent)
        try:
            import pwd  # POSIX-only; import lazily so this module loads on non-POSIX too
            ucm_user = pwd.getpwnam('ucm')
            os.chown(cert_path, ucm_user.pw_uid, ucm_user.pw_gid)
            os.chown(key_path, ucm_user.pw_uid, ucm_user.pw_gid)
        except (KeyError, ImportError):
            pass

        current_app.logger.info(f"Regenerated HTTPS certificate for {common_name}")

        # A regenerated self-signed certificate replaces any bound managed
        # certificate: drop the binding so renewals stop re-materializing (#303)
        try:
            from services.https_binding import set_bound_refid
            set_bound_refid('')
        except Exception as e:
            current_app.logger.warning(f"Could not clear HTTPS binding: {e}")

        AuditService.log_action(
            action='https_regenerate',
            resource_type='system',
            resource_name='HTTPS Certificate',
            details=f'Regenerated self-signed HTTPS certificate for {common_name}',
            success=True
        )

        # Restart service (skip in Docker - user must restart container)
        if is_docker():
            return success_response(
                message="Certificate regenerated. Restart the container to apply.",
                data={'requires_container_restart': True}
            )

        from utils.service_manager import restart_service as do_restart
        success, msg = do_restart()
        if not success:
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

    try:
        # Get cert paths dynamically - same logic as gunicorn.conf.py
        data_dir = os.environ.get('DATA_DIR', '/opt/ucm/data')
        cert_path = Path(os.environ.get('HTTPS_CERT_PATH', f'{data_dir}/https_cert.pem'))
        key_path = Path(os.environ.get('HTTPS_KEY_PATH', f'{data_dir}/https_key.pem'))

        # Backup existing certs
        if cert_path.exists():
            backup_suffix = utc_now().strftime('%Y%m%d_%H%M%S')
            shutil.copy(cert_path, f"{cert_path}.backup-{backup_suffix}")
        if key_path.exists():
            shutil.copy(key_path, f"{key_path}.backup-{backup_suffix}")

        # Decode cert/key - they may be base64 encoded or raw PEM
        cert_data = cert.crt
        key_data = cert.prv

        # Check if base64 encoded (doesn't start with -----BEGIN)
        if not cert_data.startswith('-----BEGIN'):
            try:
                cert_data = base64.b64decode(cert_data).decode('utf-8')
            except Exception:
                pass  # Already decoded or different format

        if not key_data.startswith('-----BEGIN'):
            try:
                key_data = base64.b64decode(key_data).decode('utf-8')
            except Exception:
                pass

        # Write new certificate with full chain (leaf + intermediates + root)
        full_cert = cert_data
        if cert.caref:
            ca = CA.query.filter_by(refid=cert.caref).first()
            if ca:
                chain_pems = CAService.get_ca_chain(ca.id)
                for chain_cert in chain_pems:
                    chain_str = chain_cert.decode('utf-8') if isinstance(chain_cert, bytes) else chain_cert
                    if not full_cert.endswith('\n'):
                        full_cert += '\n'
                    full_cert += chain_str

        cert_path.write_text(full_cert)

        # Write private key with restricted permissions
        key_path.write_text(key_data)
        os.chmod(key_path, 0o600)

        # Set ownership to ucm user (POSIX only; skipped on non-POSIX or if user absent)
        try:
            import pwd  # POSIX-only; import lazily so this module loads on non-POSIX too
            ucm_user = pwd.getpwnam('ucm')
            os.chown(cert_path, ucm_user.pw_uid, ucm_user.pw_gid)
            os.chown(key_path, ucm_user.pw_uid, ucm_user.pw_gid)
        except (KeyError, ImportError):
            pass  # ucm user doesn't exist (or non-POSIX), skip chown

        current_app.logger.info(f"Applied certificate {cert.refid} as HTTPS cert")

        # Remember the binding so a renewal re-materializes the files (#303)
        try:
            from services.https_binding import set_bound_refid
            set_bound_refid(cert.refid)
        except Exception as e:
            current_app.logger.warning(f"Could not persist HTTPS binding: {e}")

        AuditService.log_action(
            action='https_apply',
            resource_type='system',
            resource_id=str(cert_id),
            resource_name=cert.descr or cert.refid,
            details=f'Applied certificate {cert.refid} as HTTPS certificate',
            success=True
        )

        # Restart service (skip in Docker - user must restart container)
        if is_docker():
            return success_response(
                message="Certificate applied. Restart the container to apply.",
                data={'requires_container_restart': True}
            )

        from utils.service_manager import restart_service as do_restart
        success, msg = do_restart()
        if not success:
            return success_response(
                message="Certificate applied but service restart failed. Please restart manually.",
                data={'restart_failed': True, 'error': msg}
            )

        return success_response(message="Certificate applied. Service restarting...")

    except Exception as e:
        current_app.logger.error(f"Failed to apply HTTPS cert: {e}")
        return error_response("Failed to apply certificate", 500)

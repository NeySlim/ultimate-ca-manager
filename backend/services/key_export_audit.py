"""Audit trail for exports that hand out a private key."""
import logging

from flask import request

from services.audit_service import AuditService

logger = logging.getLogger(__name__)

KEY_FORMATS = ('key', 'pkcs12', 'p12', 'pfx', 'jks')


def audit_key_export(resource_type, resource_id, resource_name, export_format, password):
    """Record who exported which private key, in what format; never the key or password."""
    # Bundles always carry a password; a bare .key only when one was given; PEM never.
    encrypted = export_format in ('pkcs12', 'p12', 'pfx', 'jks') or (
        export_format == 'key' and bool(password))
    protection = 'password-protected' if encrypted else 'unencrypted'
    AuditService.log_action(
        action='private_key_exported',
        resource_type=resource_type,
        resource_id=str(resource_id),
        resource_name=resource_name,
        details=f'Private key exported as {export_format.upper()} ({protection})',
        success=True,
    )


def audit_ca_key_export(response):
    """after_request hook for the CA export route, which does not audit by itself."""
    try:
        if response.status_code != 200 or request.method != 'POST' or not request.is_json:
            return response  # key exports are POST-only on that route
        data = request.get_json(silent=True) or {}
        fmt = str(data.get('format') or 'pem').lower()
        from models import CA, db
        ca = db.session.get(CA, (request.view_args or {}).get('ca_id'))
        if ca is None or not ca.prv:
            return response
        if fmt in KEY_FORMATS or (fmt == 'pem' and bool(data.get('include_key'))):
            audit_key_export('ca', ca.id, ca.descr or ca.refid, fmt, data.get('password'))
    except Exception as e:
        logger.error(f"Failed to audit CA key export: {e}")
    return response


def register_ca_export_audit(bp, endpoint='export_ca'):
    """Attach the hook to the CA blueprint, limited to its single-CA export route."""
    full = f'{bp.name}.{endpoint}'

    @bp.after_request
    def _audit(response):
        if request.endpoint == full:
            return audit_ca_key_export(response)
        return response

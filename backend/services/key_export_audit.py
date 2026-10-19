"""Audit trail for exports that hand out a private key."""
from services.audit_service import AuditService


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


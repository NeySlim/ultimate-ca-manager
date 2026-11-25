"""Audit trail for exports that hand out a private key."""
from cryptography.hazmat.primitives import serialization

from services.audit_service import AuditService


def encrypt_key_pem(key_pem, password):
    """PKCS#8 PEM encrypted with *password*; the key unchanged when no password was given."""
    if not password:
        return key_pem
    key = serialization.load_pem_private_key(key_pem, password=None)
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(password.encode()))


def audit_key_export(resource_type, resource_id, resource_name, export_format, password, *, sealed=False):
    """Record who exported which private key, in what format; never the key or password.
    *sealed*: the key leaves already encrypted, as stored (an offline CA's)."""
    # Bundles always carry a password; key, PEM and hybrid zip only when one was given.
    encrypted = sealed or export_format in ('pkcs12', 'p12', 'pfx', 'jks') or (
        export_format in ('key', 'pem', 'hybrid-bundle') and bool(password))
    protection = 'password-protected' if encrypted else 'unencrypted'
    AuditService.log_action(
        action='private_key_exported',
        resource_type=resource_type,
        resource_id=str(resource_id),
        resource_name=resource_name,
        details=f'Private key exported as {export_format.upper()} ({protection})',
        success=True,
    )


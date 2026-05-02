"""Certificate private key upload route"""
import logging
import base64
from flask import request, g
from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from models import Certificate, db
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from cryptography.x509 import load_pem_x509_certificate
from services.audit_service import AuditService
from security.encryption import encrypt_private_key
from . import bp

logger = logging.getLogger(__name__)


@bp.route('/api/v2/certificates/<int:cert_id>/key', methods=['POST'])
@require_auth(['write:certificates'])
def upload_private_key(cert_id):
    """
    Upload/attach a private key to an existing certificate

    Request body:
    - key: Private key in PEM format (raw or base64 encoded)
    - passphrase: Optional passphrase if key is encrypted
    """

    cert = Certificate.query.get(cert_id)
    if not cert:
        return error_response('Certificate not found', 404)

    if cert.has_private_key:
        return error_response('Certificate already has a private key', 400)

    data = request.json
    if not data or not data.get('key'):
        return error_response('Private key is required', 400)

    key_data = data['key'].strip()
    passphrase = data.get('passphrase')

    try:
        # Decode key if base64 encoded
        if not key_data.startswith('-----BEGIN'):
            try:
                key_data = base64.b64decode(key_data).decode('utf-8')
            except Exception:
                return error_response('Invalid key format - must be PEM or base64-encoded PEM', 400)

        # Validate key format
        if 'PRIVATE KEY' not in key_data:
            return error_response('Invalid private key format', 400)

        # Try to load the key to validate it
        key_bytes = key_data.encode('utf-8')
        password = passphrase.encode('utf-8') if passphrase else None

        try:
            private_key = serialization.load_pem_private_key(
                key_bytes,
                password=password,
                backend=default_backend()
            )
        except Exception as e:
            if 'password' in str(e).lower() or 'decrypt' in str(e).lower():
                return error_response('Private key is encrypted - please provide passphrase', 400)
            logger.error(f"Invalid private key format: {e}")
            return error_response('Invalid private key format', 400)

        # Verify key matches certificate public key
        if cert.crt:
            try:
                cert_pem = base64.b64decode(cert.crt)
                certificate = load_pem_x509_certificate(cert_pem, default_backend())
                cert_public_key = certificate.public_key()
                key_public_key = private_key.public_key()

                # Compare public key bytes
                cert_pub_bytes = cert_public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo
                )
                key_pub_bytes = key_public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo
                )

                if cert_pub_bytes != key_pub_bytes:
                    return error_response('Private key does not match certificate public key', 400)
            except Exception as e:
                logger.error(f"Failed to verify key matches certificate: {e}")
                return error_response('Failed to verify key matches certificate', 400)

        # Store key (decrypt if needed, re-encode without password)
        unencrypted_key = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )

        # Encrypt with our key encryption if configured
        key_encoded = base64.b64encode(unencrypted_key).decode('utf-8')
        cert.prv = encrypt_private_key(key_encoded)

        ok, _err = safe_commit(logger, "Failed to upload private key")
        if not ok:
            return _err

        # Audit log
        username = g.current_user.username if hasattr(g, 'current_user') else 'system'
        AuditService.log_action(
            action='certificate_key_uploaded',
            resource_type='certificate',
            resource_id=cert_id,
            resource_name=cert.descr or f'Certificate #{cert_id}',
            details=f'Private key uploaded by {username}',
            success=True
        )

        return success_response(
            data=cert.to_dict(),
            message='Private key uploaded successfully'
        )

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to upload private key: {e}")
        return error_response('Failed to upload private key', 500)

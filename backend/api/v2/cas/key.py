"""
CA private key import (#348).

A CA created by signing an external request holds only its certificate: its
key lives on the system that made the request. Such a CA cannot sign, publish
a CRL or be taken offline until its key is imported here.
"""

from . import bp
from flask import request, g
import base64
import logging

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, ed448
from cryptography import x509

from auth.unified import require_auth
from utils.db_transaction import safe_commit
from utils.response import success_response, error_response
from utils.cert_issuer import private_key_matches
from utils.key_codec import private_key_to_pem
from services.audit_service import AuditService
from models import CA, db
try:
    from security.encryption import encrypt_private_key
except ImportError:  # pragma: no cover
    def encrypt_private_key(data):
        return data

logger = logging.getLogger(__name__)


@bp.route('/api/v2/cas/<int:ca_id>/key', methods=['POST'])
@require_auth(['write:cas'])
def import_ca_private_key(ca_id):
    """Attach a private key to a CA that holds only its certificate.

    Body (JSON): ``{key: PEM or base64 PEM, passphrase: optional}``.
    The key must be the certificate's own; Ed25519/Ed448 keys are refused,
    a CA could sign neither certificates nor CRLs with them.
    """
    ca = db.session.get(CA, ca_id)
    if not ca:
        return error_response('CA not found', 404)
    if ca.is_pending:
        return error_response('A pending CA already holds its own key; install its certificate instead', 409)
    if ca.hsm_key_id:
        return error_response('CA key lives in an HSM', 400)
    if ca.prv:
        return error_response('CA already has a private key', 400)

    data = request.get_json(silent=True) or {}
    key_data = (data.get('key') or '').strip()
    if not key_data:
        return error_response('Private key is required', 400)
    passphrase = data.get('passphrase')
    if not key_data.startswith('-----BEGIN'):
        try:
            key_data = base64.b64decode(key_data).decode('utf-8')
        except Exception:
            return error_response('Invalid key format - must be PEM or base64-encoded PEM', 400)
    if 'PRIVATE KEY' not in key_data:
        return error_response('Invalid private key format', 400)
    try:
        private_key = serialization.load_pem_private_key(
            key_data.encode('utf-8'), password=passphrase.encode('utf-8') if passphrase else None)
    except Exception as e:
        if 'password' in str(e).lower() or 'decrypt' in str(e).lower():
            return error_response('Private key is encrypted - please provide passphrase', 400)
        logger.warning(f"CA {ca_id} key import: invalid key: {e}")
        return error_response('Invalid private key format', 400)
    if isinstance(private_key, (ed25519.Ed25519PrivateKey, ed448.Ed448PrivateKey)):
        return error_response('Ed25519 and Ed448 CA keys are not supported: '
                              'such a CA could sign neither certificates nor CRLs', 400)
    try:
        cert = x509.load_pem_x509_certificate(base64.b64decode(ca.crt))
    except Exception:
        return error_response('CA certificate could not be parsed', 400)
    if not private_key_matches(private_key, cert):
        return error_response('Private key does not match the CA certificate', 400)

    key_pem = private_key_to_pem(private_key)
    ca.prv = encrypt_private_key(base64.b64encode(key_pem).decode('utf-8'))
    ok, err = safe_commit(logger, "Failed to import CA private key")
    if not ok:
        return err
    try:
        from services.ca.helpers import save_ca_key_file
        save_ca_key_file(ca, key_pem)
    except Exception as e:
        logger.warning(f"CA {ca_id} key file not written: {e}")

    username = getattr(getattr(g, 'current_user', None), 'username', None) or 'system'
    AuditService.log_action(
        action='ca_key_imported', resource_type='ca', resource_id=ca.id,
        resource_name=ca.descr, details=f'Private key imported for CA: {ca.descr}', success=True,
    )
    ca_dict = ca.to_dict()
    from services.webhook_service import emit_ca_updated
    emit_ca_updated(ca_dict, actor=username, changes={'private_key': 'imported'})
    return success_response(data=ca_dict, message=f'Private key imported; CA "{ca_dict["descr"]}" can now sign')

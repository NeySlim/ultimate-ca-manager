"""
External-CSR CA lifecycle routes (#298)

A CA created with type='external' holds its key pair (local or HSM) and a
CA-flavored CSR; the certificate is signed by an external CA (typically an
offline root) and installed here. The private key never leaves UCM.
"""

from . import bp
from flask import request, g, Response
import base64
import logging

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.file_validation import validate_upload, CERT_EXTENSIONS
from utils.sanitize import sanitize_filename
from services.ca_service import CAService
from services.crl import CRLService, ExternalCRLConflict
from models import CA, db

logger = logging.getLogger(__name__)

CRL_EXTENSIONS = {'.crl', '.pem', '.der'}


def _actor_username():
    if hasattr(g, 'user'):
        return g.user.username
    if hasattr(g, 'current_user'):
        return g.current_user.username
    return 'system'


def _load_certificate_pem(data: bytes):
    """Parse an uploaded certificate (PEM or DER) and return PEM bytes."""
    try:
        cert = x509.load_pem_x509_certificate(data, default_backend())
        return cert.public_bytes(serialization.Encoding.PEM)
    except Exception:
        pass
    cert = x509.load_der_x509_certificate(data, default_backend())
    return cert.public_bytes(serialization.Encoding.PEM)


@bp.route('/api/v2/cas/<int:ca_id>/csr', methods=['GET'])
@require_auth(['read:cas'])
def download_ca_csr(ca_id):
    """Download the CA's outstanding CSR (PEM)."""
    ca = db.session.get(CA, ca_id)
    if not ca:
        return error_response('CA not found', 404)
    if not ca.csr:
        return error_response('No CSR available for this CA', 404)

    csr_pem = base64.b64decode(ca.csr)
    return Response(
        csr_pem,
        mimetype='application/x-pem-file',
        headers={
            'Content-Disposition':
                f'attachment; filename="{sanitize_filename(ca.descr or ca.refid)}.csr"'
        },
    )


@bp.route('/api/v2/cas/<int:ca_id>/certificate', methods=['POST'])
@require_auth(['write:cas'])
def install_ca_certificate(ca_id):
    """
    Install the externally signed certificate on an external-CSR CA.

    Accepts multipart 'file' (PEM or DER) or 'pem_content' (form or JSON).
    Serves the first activation of a pending CA and same-key renewals — the
    certificate's public key must match the CA's stored private key.
    """
    ca = db.session.get(CA, ca_id)
    if not ca:
        return error_response('CA not found', 404)
    if ca.offline:
        return error_response('CA is offline; restore it before installing a certificate', 409)

    cert_data = None
    if 'file' in request.files and request.files['file'].filename:
        try:
            cert_data, _ = validate_upload(request.files['file'], CERT_EXTENSIONS)
        except ValueError as e:
            logger.warning(f"CA certificate upload validation error: {e}")
            return error_response('Invalid file upload', 400)
    elif request.form.get('pem_content'):
        cert_data = request.form.get('pem_content').encode('utf-8')
    elif request.is_json and (request.json or {}).get('pem_content'):
        cert_data = request.json['pem_content'].encode('utf-8')
    if not cert_data:
        return error_response('No certificate file or PEM content provided', 400)

    try:
        cert_pem = _load_certificate_pem(cert_data)
    except Exception:
        return error_response('Invalid certificate file', 400)

    username = _actor_username()
    try:
        ca, warnings, superseded = CAService.complete_external_ca(
            ca, cert_pem, username=username)
    except ValueError as e:
        db.session.rollback()
        logger.info(f"Certificate install refused for CA {ca_id}: {e}")
        return error_response(str(e), 400)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to install certificate on CA {ca_id}: {e}", exc_info=True)
        return error_response('Failed to install CA certificate', 500)

    # Snapshot before emit — subscribers may commit and expire the instance.
    ca_dict = ca.to_dict()
    from services.webhook_service import emit_ca_updated
    emit_ca_updated(ca_dict, actor=username, changes={'certificate': 'installed'})

    data = {**ca_dict, 'warnings': warnings}
    if superseded:
        # Renewal: the replaced certificate stays valid until its notAfter —
        # only the external root can revoke it, so surface what to revoke.
        data['superseded_serial'] = superseded['serial']
        data['superseded_valid_to'] = superseded['valid_to']

    return success_response(
        data=data,
        message='CA certificate installed'
    )


@bp.route('/api/v2/cas/<int:ca_id>/crl', methods=['POST'])
@require_auth(['write:crl'])
def upload_external_crl(ca_id):
    """
    Install an externally-generated CRL on a key-less/offline CA (#302).

    Accepts multipart 'file' (PEM or DER) or 'pem_content' (form or JSON).
    The CRL must verify against the CA certificate, match its subject, and
    be newer than the currently served one; it is then served at the CA's
    CDP path and consulted by OCSP for this issuer.
    """
    ca = db.session.get(CA, ca_id)
    if not ca:
        return error_response('CA not found', 404)

    crl_data = None
    if 'file' in request.files and request.files['file'].filename:
        try:
            crl_data, _ = validate_upload(request.files['file'], CRL_EXTENSIONS)
        except ValueError as e:
            logger.warning(f"CRL upload validation error: {e}")
            return error_response('Invalid file upload', 400)
    elif request.form.get('pem_content'):
        crl_data = request.form.get('pem_content').encode('utf-8')
    elif request.is_json and (request.json or {}).get('pem_content'):
        crl_data = request.json['pem_content'].encode('utf-8')
    if not crl_data:
        return error_response('No CRL file or PEM content provided', 400)

    username = _actor_username()
    try:
        crl_metadata = CRLService.install_external_crl(
            ca.id, crl_data, username=username)
    except ExternalCRLConflict as e:
        db.session.rollback()
        logger.info(f"External CRL refused for CA {ca_id}: {e}")
        return error_response(str(e), 409)
    except ValueError as e:
        db.session.rollback()
        logger.info(f"External CRL rejected for CA {ca_id}: {e}")
        return error_response(str(e), 400)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to install external CRL on CA {ca_id}: {e}", exc_info=True)
        return error_response('Failed to install CRL', 500)

    data = crl_metadata.to_dict()
    data['caref'] = ca.refid

    try:
        from websocket.emitters import on_crl_regenerated
        on_crl_regenerated(
            ca.id, ca.descr, data.get('next_update', ''), data.get('revoked_count', 0))
    except Exception:
        pass

    return success_response(data=data, message='External CRL installed')


@bp.route('/api/v2/cas/<int:ca_id>/renew-csr', methods=['POST'])
@require_auth(['write:cas'])
def renew_ca_csr(ca_id):
    """Re-issue a CA CSR from the existing key (same-key renewal)."""
    ca = db.session.get(CA, ca_id)
    if not ca:
        return error_response('CA not found', 404)
    if not ca.has_private_key:
        return error_response('CA has no private key', 400)
    if ca.offline:
        return error_response('CA is offline; restore it before renewing', 409)
    if ca.revoked:
        return error_response('CA is revoked; a revoked CA is not renewed', 409)

    data = request.get_json(silent=True) or {}
    digest = data.get('digest')
    if digest is not None and digest not in ('sha256', 'sha384', 'sha512'):
        return error_response('digest must be one of sha256, sha384, sha512', 400)

    username = _actor_username()
    try:
        CAService.regenerate_ca_csr(ca, digest=digest, username=username)
    except ValueError as e:
        db.session.rollback()
        logger.info(f"CSR renewal refused for CA {ca_id}: {e}")
        return error_response(str(e), 400)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to renew CSR for CA {ca_id}: {e}", exc_info=True)
        return error_response('Failed to generate CSR', 500)

    ca_dict = ca.to_dict()
    from services.webhook_service import emit_ca_updated
    emit_ca_updated(ca_dict, actor=username, changes={'csr': 'renewed'})

    return success_response(
        data=ca_dict,
        message='CSR generated — download and submit it to the external CA'
    )

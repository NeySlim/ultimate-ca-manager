"""
Microsoft AD CS API routes
CRUD for MS CA connections + CSR signing + request status tracking
"""

import logging
from flask import Blueprint, request
from auth.unified import require_auth
from utils.response import success_response, error_response, created_response, no_content_response
from models import db
from models.msca import MicrosoftCA, MSCARequest
from services.msca_service import MicrosoftCAService

logger = logging.getLogger(__name__)

bp = Blueprint('microsoft_cas', __name__, url_prefix='/api/v2/microsoft-cas')


# --- CRUD Endpoints ---

@bp.route('', methods=['GET'])
@require_auth(['read:settings'])
def list_connections():
    """List all Microsoft CA connections"""
    connections = MicrosoftCA.query.order_by(MicrosoftCA.name).all()
    return success_response(data=[c.to_dict() for c in connections])


@bp.route('/enabled', methods=['GET'])
@require_auth(['read:certificates'])
def list_enabled_connections():
    """List enabled MS CA connections (for sign modal dropdown)"""
    connections = MicrosoftCAService.get_enabled_connections()
    return success_response(data=connections)


@bp.route('', methods=['POST'])
@require_auth(['write:settings'])
def create_connection():
    """Create a new Microsoft CA connection"""
    data = request.get_json()
    if not data:
        return error_response("Request body required", 400)

    name = data.get('name', '').strip()
    server = data.get('server', '').strip()
    auth_method = data.get('auth_method', 'certificate')

    if not name:
        return error_response("Name is required", 400)
    if not server:
        return error_response("Server hostname is required", 400)
    if auth_method not in ('certificate', 'kerberos', 'basic'):
        return error_response("Invalid auth method", 400)

    if MicrosoftCA.query.filter_by(name=name).first():
        return error_response(f"Connection '{name}' already exists", 409)

    try:
        msca = MicrosoftCA(
            name=name,
            server=server,
            ca_name=data.get('ca_name', '').strip() or None,
            auth_method=auth_method,
            use_ssl=data.get('use_ssl', True),
            verify_ssl=data.get('verify_ssl', True),
            ca_bundle=data.get('ca_bundle', '').strip() or None,
            default_template=data.get('default_template', 'WebServer').strip(),
            enabled=data.get('enabled', True),
            created_by=request.current_user.username if hasattr(request, 'current_user') else None,
        )

        # Auth-specific fields
        if auth_method == 'basic':
            msca.username = data.get('username', '').strip()
            msca.password = data.get('password', '')
        elif auth_method == 'certificate':
            msca.client_cert_pem = data.get('client_cert_pem', '').strip() or None
            msca.client_key_pem = data.get('client_key_pem', '').strip() or None
        elif auth_method == 'kerberos':
            msca.kerberos_principal = data.get('kerberos_principal', '').strip() or None
            msca.kerberos_keytab_path = data.get('kerberos_keytab_path', '').strip() or None

        db.session.add(msca)
        db.session.commit()

        logger.info(f"Microsoft CA connection created: {name} ({auth_method})")
        return created_response(data=msca.to_dict(), message="Microsoft CA connection created")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to create MS CA connection: {e}")
        return error_response("Failed to create connection", 500)


@bp.route('/<int:msca_id>', methods=['GET'])
@require_auth(['read:settings'])
def get_connection(msca_id):
    """Get Microsoft CA connection details"""
    msca = MicrosoftCA.query.get(msca_id)
    if not msca:
        return error_response("Connection not found", 404)
    return success_response(data=msca.to_dict())


@bp.route('/<int:msca_id>', methods=['PUT'])
@require_auth(['write:settings'])
def update_connection(msca_id):
    """Update a Microsoft CA connection"""
    msca = MicrosoftCA.query.get(msca_id)
    if not msca:
        return error_response("Connection not found", 404)

    data = request.get_json()
    if not data:
        return error_response("Request body required", 400)

    try:
        # Update common fields
        if 'name' in data:
            new_name = data['name'].strip()
            existing = MicrosoftCA.query.filter_by(name=new_name).first()
            if existing and existing.id != msca_id:
                return error_response(f"Connection '{new_name}' already exists", 409)
            msca.name = new_name

        if 'server' in data:
            msca.server = data['server'].strip()
        if 'ca_name' in data:
            msca.ca_name = data['ca_name'].strip() or None
        if 'use_ssl' in data:
            msca.use_ssl = data['use_ssl']
        if 'verify_ssl' in data:
            msca.verify_ssl = data['verify_ssl']
        if 'ca_bundle' in data:
            msca.ca_bundle = data['ca_bundle'].strip() or None
        if 'default_template' in data:
            msca.default_template = data['default_template'].strip()
        if 'enabled' in data:
            msca.enabled = data['enabled']

        # Auth method change
        if 'auth_method' in data:
            new_method = data['auth_method']
            if new_method not in ('certificate', 'kerberos', 'basic'):
                return error_response("Invalid auth method", 400)
            msca.auth_method = new_method

        # Auth-specific fields
        auth = data.get('auth_method', msca.auth_method)
        if auth == 'basic':
            if 'username' in data:
                msca.username = data['username'].strip()
            if 'password' in data and data['password'] != '***':
                msca.password = data['password']
        elif auth == 'certificate':
            if 'client_cert_pem' in data:
                msca.client_cert_pem = data['client_cert_pem'].strip() or None
            if 'client_key_pem' in data and data['client_key_pem'] != '***':
                msca.client_key_pem = data['client_key_pem'].strip() or None
        elif auth == 'kerberos':
            if 'kerberos_principal' in data:
                msca.kerberos_principal = data['kerberos_principal'].strip() or None
            if 'kerberos_keytab_path' in data:
                msca.kerberos_keytab_path = data['kerberos_keytab_path'].strip() or None

        db.session.commit()
        logger.info(f"Microsoft CA connection updated: {msca.name}")
        return success_response(data=msca.to_dict(), message="Connection updated")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update MS CA connection: {e}")
        return error_response("Failed to update connection", 500)


@bp.route('/<int:msca_id>', methods=['DELETE'])
@require_auth(['delete:settings'])
def delete_connection(msca_id):
    """Delete a Microsoft CA connection"""
    msca = MicrosoftCA.query.get(msca_id)
    if not msca:
        return error_response("Connection not found", 404)

    pending = MSCARequest.query.filter_by(msca_id=msca_id, status='pending').count()
    if pending > 0:
        return error_response(
            f"Cannot delete: {pending} pending request(s). Resolve them first.", 409
        )

    try:
        name = msca.name
        db.session.delete(msca)
        db.session.commit()
        logger.info(f"Microsoft CA connection deleted: {name}")
        return no_content_response()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete MS CA connection: {e}")
        return error_response("Failed to delete connection", 500)


# --- Connection Testing ---

@bp.route('/<int:msca_id>/test', methods=['POST'])
@require_auth(['write:settings'])
def test_connection(msca_id):
    """Test connectivity to Microsoft CA"""
    result = MicrosoftCAService.test_connection(msca_id)
    if result.get('success'):
        return success_response(data=result, message="Connection successful")
    return error_response(result.get('error', 'Connection test failed'), 400)


# --- Templates ---

@bp.route('/<int:msca_id>/templates', methods=['GET'])
@require_auth(['read:certificates'])
def list_templates(msca_id):
    """List available certificate templates from MS CA"""
    msca = MicrosoftCA.query.get(msca_id)
    if not msca:
        return error_response("Connection not found", 404)

    try:
        templates = MicrosoftCAService.list_templates(msca_id)
        return success_response(data=templates)
    except Exception as e:
        logger.error(f"Failed to list templates: {e}")
        return error_response("Failed to retrieve templates", 500)


# --- CSR Signing ---

@bp.route('/<int:msca_id>/sign/<int:csr_id>', methods=['POST'])
@require_auth(['write:certificates'])
def sign_csr(msca_id, csr_id):
    """Submit a CSR to Microsoft CA for signing"""
    from models import CSR

    msca = MicrosoftCA.query.get(msca_id)
    if not msca:
        return error_response("Microsoft CA connection not found", 404)

    csr = CSR.query.get(csr_id)
    if not csr:
        return error_response("CSR not found", 404)

    data = request.get_json() or {}
    template = data.get('template', msca.default_template)

    if not template:
        return error_response("Certificate template is required", 400)

    # Get CSR PEM
    try:
        import base64
        csr_pem = base64.b64decode(csr.csr).decode('utf-8')
    except Exception:
        csr_pem = csr.csr

    username = request.current_user.username if hasattr(request, 'current_user') else None

    try:
        result = MicrosoftCAService.submit_csr(
            msca_id=msca_id,
            csr_pem=csr_pem,
            template=template,
            csr_id=csr_id,
            submitted_by=username,
        )

        if result['status'] == 'issued':
            # Import the signed cert into UCM
            _import_signed_cert(csr, result.get('cert_pem'), msca, template, result['request_id'])
            return success_response(data=result, message="Certificate issued by Microsoft CA")

        elif result['status'] == 'pending':
            return success_response(data=result, message="Request pending approval")

        return success_response(data=result)

    except ValueError as e:
        return error_response(str(e), 400)
    except Exception as e:
        logger.error(f"Failed to sign CSR via MS CA: {e}")
        return error_response("Failed to submit CSR to Microsoft CA", 500)


@bp.route('/<int:msca_id>/requests/<int:request_id>', methods=['GET'])
@require_auth(['read:certificates'])
def check_request_status(msca_id, request_id):
    """Check status of a pending signing request"""
    try:
        result = MicrosoftCAService.check_request(msca_id, request_id)

        # If just issued, import the cert
        if result.get('status') == 'issued' and result.get('cert_pem'):
            req = MSCARequest.query.get(request_id)
            if req and req.csr_id and not req.cert_id:
                from models import CSR
                csr = CSR.query.get(req.csr_id)
                msca = MicrosoftCA.query.get(msca_id)
                if csr and msca:
                    _import_signed_cert(csr, req.cert_pem, msca, req.template, request_id)
                    result = req.to_dict()

        return success_response(data=result)
    except ValueError as e:
        return error_response(str(e), 404)
    except Exception as e:
        logger.error(f"Failed to check request status: {e}")
        return error_response("Failed to check request status", 500)


@bp.route('/requests/pending', methods=['GET'])
@require_auth(['read:certificates'])
def list_pending_requests():
    """List all pending MS CA requests"""
    msca_id = request.args.get('msca_id', type=int)
    requests_list = MicrosoftCAService.get_pending_requests(msca_id)
    return success_response(data=requests_list)


# --- Helper ---

def _import_signed_cert(csr, cert_pem, msca, template, msca_request_id):
    """Import a signed certificate from MS CA into UCM's certificate store"""
    from models import Certificate
    import base64
    from datetime import datetime

    try:
        from cryptography import x509 as cx509
        cert_der = base64.b64decode(cert_pem) if cert_pem else None
        if not cert_der:
            return

        # Try PEM first, then DER
        try:
            cert_obj = cx509.load_pem_x509_certificate(cert_pem.encode() if isinstance(cert_pem, str) else cert_pem)
        except Exception:
            cert_obj = cx509.load_der_x509_certificate(cert_der)

        # Extract subject fields
        subject = cert_obj.subject
        cn = subject.get_attributes_for_oid(cx509.oid.NameOID.COMMON_NAME)
        org = subject.get_attributes_for_oid(cx509.oid.NameOID.ORGANIZATION_NAME)

        cert_pem_b64 = base64.b64encode(
            cert_obj.public_bytes(encoding=__import__('cryptography.hazmat.primitives.serialization', fromlist=['Encoding']).Encoding.PEM)
        ).decode('utf-8')

        cert = Certificate(
            cn=cn[0].value if cn else 'Unknown',
            org=org[0].value if org else None,
            crt=cert_pem_b64,
            status='valid',
            cert_type='server',
            issuer_cn=f"MSCA: {msca.name}",
            not_before=cert_obj.not_valid_before_utc,
            not_after=cert_obj.not_valid_after_utc,
            serial_number=format(cert_obj.serial_number, 'x'),
        )
        db.session.add(cert)
        db.session.flush()

        # Link the MSCA request to the new cert
        msca_req = MSCARequest.query.get(msca_request_id)
        if msca_req:
            msca_req.cert_id = cert.id
            msca_req.status = 'issued'
            msca_req.issued_at = datetime.utcnow()

        # Update CSR status
        csr.status = 'signed'
        csr.cert_id = cert.id

        db.session.commit()
        logger.info(f"Imported MS CA signed certificate: {cert.cn} (id={cert.id})")

    except Exception as e:
        logger.error(f"Failed to import MS CA signed certificate: {e}")
        db.session.rollback()

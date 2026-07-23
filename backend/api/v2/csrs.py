"""
CSR Management Routes v2.0
/api/csrs/* - Certificate Signing Request CRUD
"""

import re
import json
import logging
import datetime
import base64
import uuid
from flask import Blueprint, request, jsonify, g, Response
from auth.unified import require_auth
from utils.response import success_response, error_response, created_response, no_content_response
from utils.dn_validation import validate_dn_field
from utils.file_validation import validate_upload, CERT_EXTENSIONS
from utils.sanitize import sanitize_filename
from models import db, Certificate, CA
from services.cert_service import CertificateService
from services.audit_service import AuditService
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from security.encryption import encrypt_private_key
from utils.datetime_utils import utc_now
from utils.db_transaction import safe_commit

bp = Blueprint('csrs_v2', __name__)
logger = logging.getLogger(__name__)

@bp.route('/api/v2/csrs', methods=['GET'])
@require_auth(['read:csrs'])
def list_csrs():
    """List all pending CSRs (Certificates with no crt)"""
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(max(1, request.args.get('per_page', 20, type=int)), 100)
    
    # Filter for certificates that have a CSR but no signed certificate yet
    query = Certificate.query.filter(
        Certificate.csr.isnot(None),
        Certificate.crt.is_(None)
    ).order_by(Certificate.created_at.desc())
    
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    data = []
    for cert in pagination.items:
        # Convert DB model to frontend friendly format
        item = cert.to_dict()
        item['status'] = 'Pending'
        item['cn'] = cert.common_name
        item['department'] = cert.organizational_unit
        item['sans'] = cert.san_dns_list
        item['key_type'] = cert.key_type
        item['requester'] = cert.created_by
        data.append(item)
    
    return success_response(
        data=data,
        meta={
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        }
    )


@bp.route('/api/v2/csrs/history', methods=['GET'])
@require_auth(['read:csrs'])
def list_csrs_history():
    """List all signed CSRs (Certificates that had a CSR and now have crt)"""
    
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(max(1, request.args.get('per_page', 20, type=int)), 100)
    
    # Filter for certificates that have both CSR and signed certificate
    query = Certificate.query.filter(
        Certificate.csr.isnot(None),
        Certificate.crt.isnot(None)
    ).order_by(Certificate.created_at.desc())
    
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Build CA lookup for names
    cas = {ca.refid: ca for ca in CA.query.all()}
    
    data = []
    for cert in pagination.items:
        item = cert.to_dict()
        item['status'] = 'Signed'
        item['cn'] = cert.common_name
        item['department'] = cert.organizational_unit
        item['sans'] = cert.san_dns_list
        item['key_type'] = cert.key_type
        item['requester'] = cert.created_by
        
        # Add CA info
        if cert.caref and cert.caref in cas:
            ca = cas[cert.caref]
            item['signed_by'] = ca.descr
            item['signed_by_id'] = ca.id
        else:
            item['signed_by'] = cert.issuer_name or 'Unknown CA'
            
        item['signed_at'] = cert.valid_from
        data.append(item)
    
    return success_response(
        data=data,
        meta={
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        }
    )

@bp.route('/api/v2/csrs/<int:csr_id>', methods=['GET'])
@require_auth(['read:csrs'])
def get_csr(csr_id):
    """Get CSR details"""
    cert = db.session.get(Certificate, csr_id)
    if not cert or not cert.csr:
        return error_response('CSR not found', 404)
    
    data = cert.to_dict(include_private=False)
    # Decode CSR PEM for display
    if cert.csr:
        try:
            data['csr_pem'] = base64.b64decode(cert.csr).decode('utf-8')
        except Exception:
            data['csr_pem'] = cert.csr
    
    return success_response(data=data)

@bp.route('/api/v2/csrs', methods=['POST'])
@require_auth(['write:csrs'])
def create_csr():
    """Create a new CSR"""
    data = request.json
    if not data or not data.get('cn'):
        return error_response('Common Name (cn) is required', 400)
    
    try:
        # Map frontend data to service arguments
        country = (data.get('country') or '').upper() or None
        dn = {'CN': data['cn']}
        if data.get('department'):
            dn['OU'] = data['department']
        if data.get('organization'):
            dn['O'] = data['organization']
        if country:
            dn['C'] = country
        
        # Validate DN fields
        for field, value in dn.items():
            is_valid, error = validate_dn_field(field, value)
            if not is_valid:
                return error_response(error, 400)
            
        # Parse key type (Frontend: "RSA 2048", "EC P-256", etc.)
        from utils.key_type import parse_csr_key_type
        try:
            key_type = parse_csr_key_type(data.get('key_type', 'RSA 2048'))
        except ValueError as exc:
            return error_response(str(exc), 400)

        # Parse SANs - frontend sends ["DNS:example.com", "IP:1.2.3.4", ...]
        from utils.san_parse import parse_csr_san_entries
        san_buckets, san_error = parse_csr_san_entries(data.get('sans', []))
        if san_error:
            return error_response(san_error, 400)

        cert = CertificateService.generate_csr(
            descr=f"CSR for {data['cn']}",
            dn=dn,
            key_type=key_type,
            san_dns=san_buckets['san_dns'] or None,
            san_ip=san_buckets['san_ip'] or None,
            san_email=san_buckets['san_email'] or None,
            san_uri=san_buckets['san_uri'] or None,
            san_upn=san_buckets['san_upn'] or None,
            username=getattr(g, 'current_user', None) and g.current_user.username or 'system'
        )
        
        AuditService.log_action(
            action='csr_create',
            resource_type='csr',
            resource_id=str(cert.id),
            resource_name=data['cn'],
            details=f'Created CSR for: {data["cn"]}',
            success=True
        )
        
        cert_dict = cert.to_dict()
        from services.webhook_service import emit_csr_submitted
        emit_csr_submitted(cert_dict)

        return created_response(
            data=cert_dict,
            message='CSR created successfully'
        )
    except Exception as e:
        logger.error(f"Failed to create CSR: {e}")
        return error_response('Failed to create CSR', 500)


@bp.route('/api/v2/csrs/upload', methods=['POST'])
@require_auth(['write:csrs'])
def upload_csr():
    """
    Upload CSR from JSON body with PEM content
    
    JSON body:
        pem: PEM-encoded CSR content
        name: Optional display name
    """
    
    data = request.get_json(silent=True)
    if not data or not data.get('pem'):
        return error_response('PEM content required', 400)

    pem_raw = data['pem']
    if isinstance(pem_raw, str):
        if len(pem_raw) > 65536:
            return error_response('CSR PEM too large (max 64KB)', 413)
        csr_pem = pem_raw.encode('utf-8')
    else:
        csr_pem = pem_raw
    name = data.get('name', '')

    try:
        # Parse CSR
        try:
            csr = x509.load_pem_x509_csr(csr_pem, default_backend())
        except (ValueError, TypeError) as e:
            return error_response(f'Invalid CSR PEM: {e}', 400)

        # RFC 2986 §2.2: verify CSR signature
        if not csr.is_signature_valid:
            return error_response('CSR has invalid signature', 400)
        
        # Extract subject info
        subject = csr.subject
        cn = None
        org = None
        ou = None
        
        for attr in subject:
            if attr.oid == x509.oid.NameOID.COMMON_NAME:
                cn = attr.value
            elif attr.oid == x509.oid.NameOID.ORGANIZATION_NAME:
                org = attr.value
            elif attr.oid == x509.oid.NameOID.ORGANIZATIONAL_UNIT_NAME:
                ou = attr.value
        
        # Build subject string
        subject_parts = []
        if cn:
            subject_parts.append(f"CN={cn}")
        if org:
            subject_parts.append(f"O={org}")
        if ou:
            subject_parts.append(f"OU={ou}")
        subject_str = ", ".join(subject_parts) if subject_parts else "Unknown"
        
        # Extract SANs from CSR
        san_dns, san_ip, san_email, san_uri = [], [], [], []
        try:
            san_ext = csr.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
            for name_entry in san_ext.value:
                if isinstance(name_entry, x509.DNSName):
                    san_dns.append(name_entry.value)
                elif isinstance(name_entry, x509.IPAddress):
                    san_ip.append(str(name_entry.value))
                elif isinstance(name_entry, x509.RFC822Name):
                    san_email.append(name_entry.value)
                elif isinstance(name_entry, x509.UniformResourceIdentifier):
                    san_uri.append(name_entry.value)
        except x509.ExtensionNotFound:
            pass
        
        # Create Certificate record with CSR (pending)
        new_cert = Certificate(
            refid=str(uuid.uuid4()),
            descr=name or cn or 'Uploaded CSR',
            subject=subject_str,
            subject_cn=cn,
            csr=base64.b64encode(csr_pem).decode('utf-8'),
            crt=None,
            prv=None,
            san_dns=json.dumps(san_dns) if san_dns else None,
            san_ip=json.dumps(san_ip) if san_ip else None,
            san_email=json.dumps(san_email) if san_email else None,
            san_uri=json.dumps(san_uri) if san_uri else None,
            source='upload',
            created_by=getattr(g, 'username', 'system')
        )
        
        db.session.add(new_cert)
        ok, err = safe_commit(logger, "Failed to upload CSR")
        if not ok:
            return err

        # Audit log
        AuditService.log_action(
            action='csr_uploaded',
            resource_type='csr',
            resource_id=new_cert.id,
            resource_name=cn,
            details=f'CSR uploaded: {subject_str}'
        )

        # Return CSR-friendly format
        result = new_cert.to_dict()
        result['status'] = 'Pending'
        result['cn'] = cn
        result['department'] = ou

        return created_response(
            data=result,
            message='CSR uploaded successfully'
        )
    except Exception as e:
        logger.error(f"Failed to upload CSR: {e}")
        return error_response('Failed to upload CSR', 500)


@bp.route('/api/v2/csrs/import', methods=['POST'])
@require_auth(['write:csrs'])
def import_csr():
    """
    Import CSR from file OR pasted PEM content
    
    Form data:
        file: CSR file (optional if pem_content provided)
        pem_content: Pasted PEM content (optional if file provided)
        name: Optional display name
    """
    
    # Get CSR data from file or pasted content
    csr_pem = None
    
    if 'file' in request.files and request.files['file'].filename:
        file = request.files['file']
        try:
            csr_pem, _ = validate_upload(file, CERT_EXTENSIONS)
        except ValueError as e:
            logger.warning(f"CSR upload validation error: {e}")
            return error_response('Invalid file upload', 400)
    elif request.form.get('pem_content'):
        csr_pem = request.form.get('pem_content').encode('utf-8')
    else:
        return error_response('No file or PEM content provided', 400)
    
    name = request.form.get('name', '')
    
    try:
        # Parse CSR
        try:
            csr = x509.load_pem_x509_csr(csr_pem, default_backend())
        except (ValueError, TypeError) as e:
            return error_response(f'Invalid CSR PEM: {e}', 400)

        # RFC 2986 §2.2: verify CSR signature
        if not csr.is_signature_valid:
            return error_response('CSR has invalid signature', 400)
        
        # Extract subject info
        subject = csr.subject
        cn = None
        org = None
        ou = None
        
        for attr in subject:
            if attr.oid == x509.oid.NameOID.COMMON_NAME:
                cn = attr.value
            elif attr.oid == x509.oid.NameOID.ORGANIZATION_NAME:
                org = attr.value
            elif attr.oid == x509.oid.NameOID.ORGANIZATIONAL_UNIT_NAME:
                ou = attr.value
        
        # Build subject string
        subject_str = subject.rfc4514_string()
        
        # Extract SANs if present
        san_dns = []
        san_ip = []
        san_email = []
        san_uri = []
        try:
            san_ext = csr.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
            for name_entry in san_ext.value:
                if isinstance(name_entry, x509.DNSName):
                    san_dns.append(name_entry.value)
                elif isinstance(name_entry, x509.IPAddress):
                    san_ip.append(str(name_entry.value))
                elif isinstance(name_entry, x509.RFC822Name):
                    san_email.append(name_entry.value)
                elif isinstance(name_entry, x509.UniformResourceIdentifier):
                    san_uri.append(name_entry.value)
        except x509.ExtensionNotFound:
            pass
        
        # Create Certificate record with CSR
        refid = str(uuid.uuid4())
        cert = Certificate(
            refid=refid,
            descr=name or cn or 'Imported CSR',
            csr=base64.b64encode(csr_pem).decode('utf-8'),
            crt=None,  # Not signed yet
            subject=subject_str,
            subject_cn=cn,
            san_dns=json.dumps(san_dns) if san_dns else None,
            san_ip=json.dumps(san_ip) if san_ip else None,
            san_email=json.dumps(san_email) if san_email else None,
            san_uri=json.dumps(san_uri) if san_uri else None,
            created_by='import',
            created_at=utc_now()
        )
        
        db.session.add(cert)
        ok, err = safe_commit(logger, "Import failed")
        if not ok:
            return err

        # Audit log
        AuditService.log_action(
            action='csr_imported',
            resource_type='csr',
            resource_id=cert.id,
            resource_name=cert.descr,
            details=f'Imported CSR: {cert.descr}',
            success=True
        )

        return created_response(
            data=cert.to_dict(),
            message=f'CSR "{cert.descr}" imported successfully'
        )

    except Exception as e:
        logger.error(f"CSR Import Error: {e}", exc_info=True)
        return error_response('Import failed', 500)

@bp.route('/api/v2/csrs/<int:csr_id>/export', methods=['GET'])
@require_auth(['read:csrs'])
def export_csr(csr_id):
    """Export CSR as PEM file"""
    
    cert = db.session.get(Certificate, csr_id)
    if not cert or not cert.csr:
        return error_response('CSR not found', 404)
    
    try:
        csr_pem = base64.b64decode(cert.csr)
        return Response(
            csr_pem,
            mimetype='application/x-pem-file',
            headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(cert.descr or cert.refid)}.csr"'}
        )
    except Exception as e:
        logger.error(f"CSR export failed: {e}")
        return error_response('Export failed', 500)

@bp.route('/api/v2/csrs/<int:csr_id>', methods=['DELETE'])
@require_auth(['delete:csrs'])
def delete_csr(csr_id):
    """Delete a CSR"""
    try:
        if CertificateService.delete_certificate(csr_id):
            AuditService.log_action(
                action='csr_delete',
                resource_type='csr',
                resource_id=str(csr_id),
                resource_name=f'CSR {csr_id}',
                details=f'Deleted CSR {csr_id}',
                success=True
            )
            return no_content_response()
        else:
            return error_response("CSR not found", 404)
    except Exception as e:
        logger.error(f"Failed to delete CSR: {e}")
        return error_response('Failed to delete CSR', 500)


@bp.route('/api/v2/csrs/<int:csr_id>/key', methods=['POST'])
@require_auth(['write:csrs'])
def upload_csr_private_key(csr_id):
    """
    Upload/attach a private key to an existing CSR
    
    Request body:
    - key: Private key in PEM format (raw or base64 encoded)
    - passphrase: Optional passphrase if key is encrypted
    """
    
    csr = db.session.get(Certificate, csr_id)
    if not csr:
        return error_response('CSR not found', 404)
    
    # Verify it's a CSR (has csr but no crt)
    if not csr.csr or csr.crt:
        return error_response('Not a pending CSR', 400)
    
    if csr.has_private_key:
        return error_response('CSR already has a private key', 400)
    
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
            logger.error(f"Invalid private key for CSR: {e}")
            return error_response('Invalid private key format', 400)

        # Verify key matches CSR public key (RFC 2986 §4.1)
        try:
            csr_pem_bytes = base64.b64decode(csr.csr)
            csr_obj = x509.load_pem_x509_csr(csr_pem_bytes, default_backend())
            csr_pub = csr_obj.public_key().public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            key_pub = private_key.public_key().public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            if csr_pub != key_pub:
                return error_response('Private key does not match CSR public key', 400)
        except ValueError as e:
            return error_response(f'Could not verify key against CSR: {e}', 400)
        
        # Store key (decrypt if needed, re-encode without password)
        unencrypted_key = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        # Encrypt with our key encryption if configured
        key_encoded = base64.b64encode(unencrypted_key).decode('utf-8')
        csr.prv = encrypt_private_key(key_encoded)
        
        ok, err = safe_commit(logger, "Failed to upload private key")
        if not ok:
            return err

        # Audit log
        username = g.current_user.username if hasattr(g, 'current_user') else 'system'
        AuditService.log_action(
            action='csr_key_uploaded',
            resource_type='csr',
            resource_id=csr_id,
            resource_name=csr.descr or f'CSR #{csr_id}',
            details=f'Private key uploaded by {username}',
            success=True
        )

        return success_response(
            data=csr.to_dict(),
            message='Private key uploaded successfully'
        )

    except Exception as e:
        logger.error(f"Failed to upload private key: {e}")
        return error_response('Failed to upload private key', 500)


@bp.route('/api/v2/csrs/<int:csr_id>/sign', methods=['POST'])
@require_auth(['write:csrs', 'write:certificates'])
def sign_csr(csr_id):
    """
    Sign a CSR with a CA to issue a certificate
    
    JSON body:
        ca_id: ID of the CA to sign with
        validity_days: Number of days the certificate should be valid (default: 365)
    """
    
    cert = db.session.get(Certificate, csr_id)
    if not cert:
        return error_response('CSR not found', 404)
    
    if not cert.csr:
        return error_response('No CSR data found', 400)
    
    if cert.crt:
        return error_response('CSR already signed', 400)
    
    data = request.get_json(silent=True) or {}
    ca_id = data.get('ca_id')
    try:
        validity_days = int(data.get('validity_days', 365))
    except (TypeError, ValueError):
        return error_response('validity_days must be an integer', 400)
    if validity_days < 1 or validity_days > 3650:
        return error_response('validity_days must be between 1 and 3650', 400)
    cert_type = data.get('cert_type', 'server')
    extra_ekus = data.get('extra_ekus')

    # Validate extra_ekus early to surface a clean 400
    if extra_ekus is not None:
        from utils.eku_validation import normalize_extra_ekus
        _normalized, _err = normalize_extra_ekus(extra_ekus)
        if _err:
            return error_response(f'Invalid extra_ekus: {_err}', 400)
        extra_ekus = _normalized
    
    # Map frontend cert_type to backend cert_type format
    cert_type_map = {
        'server': 'server_cert',
        'client': 'client_cert', 
        'combined': 'combined_cert',
        'code_signing': 'code_signing',
        'email': 'email_cert',
        'intermediate_ca': 'intermediate_ca'
    }
    backend_cert_type = cert_type_map.get(cert_type, 'server_cert')
    
    if not ca_id:
        return error_response('CA ID required', 400)
    
    # Get the CA from CA table (not Certificate table)
    ca = db.session.get(CA, ca_id)
    if not ca:
        return error_response('CA not found', 404)
    
    if not ca.crt or not ca.has_private_key:
        return error_response('CA is not valid for signing', 400)

    # Check offline status
    if ca.offline:
        return error_response(
            f"CA is offline: {ca.offline_reason or 'no reason provided'}",
            400
        )

    # Clamp validity to CA expiration
    try:
        from cryptography import x509 as _x509
        ca_pem = base64.b64decode(ca.crt) if ca.crt else None
        if ca_pem:
            ca_cert = _x509.load_pem_x509_certificate(ca_pem)
            ca_exp = ca_cert.not_valid_after_utc.replace(tzinfo=None)
            max_days = (ca_exp - utc_now()).days
            if max_days < 1:
                return error_response('CA is expired', 400)
            if validity_days > max_days:
                validity_days = max_days
    except Exception as e:
        logger.warning(f"Could not clamp validity to CA expiration: {e}")

    try:
        # Sign the CSR - use CA refid
        signed_result = CertificateService.sign_csr(
            cert_id=csr_id,
            caref=ca.refid,
            validity_days=validity_days,
            cert_type=backend_cert_type,
            extra_ekus=extra_ekus,
            # An operator explicitly signing a CSR may issue delegated
            # OCSP/timestamping certs (the documented responder workflow);
            # protocol enrollees (ACME/EST) never get these EKUs
            allow_sensitive_ekus=True,
        )
        
        # Determine if result is a CA or Certificate
        is_ca_result = isinstance(signed_result, CA)
        
        # Audit log
        AuditService.log_action(
            action='csr_signed',
            resource_type='ca' if is_ca_result else 'certificate',
            resource_id=signed_result.id,
            resource_name=signed_result.descr if is_ca_result else cert.subject,
            details=f'CSR signed as {"Intermediate CA" if is_ca_result else "certificate"} by CA {ca.descr} (id={ca_id}), validity={validity_days} days'
        )
        
        msg = 'CSR signed as Intermediate CA' if is_ca_result else 'CSR signed successfully'
        return success_response(
            data=signed_result.to_dict(),
            message=msg
        )
    except Exception as e:
        logger.error(f"CSR Sign Error: {e}", exc_info=True)
        return error_response("Failed to sign CSR", 500)


# ============================================================
# Bulk Operations
# ============================================================

@bp.route('/api/v2/csrs/bulk/sign', methods=['POST'])
@require_auth(['write:csrs', 'write:certificates'])
def bulk_sign_csrs():
    """Bulk sign CSRs with a CA"""

    data = request.get_json()
    if not data or not data.get('ids'):
        return error_response('ids array required', 400)

    ca_id = data.get('ca_id')
    try:
        validity_days = int(data.get('validity_days', 365))
    except (TypeError, ValueError):
        return error_response('validity_days must be an integer', 400)
    if validity_days < 1 or validity_days > 3650:
        return error_response('validity_days must be between 1 and 3650', 400)

    if not ca_id:
        return error_response('ca_id required', 400)

    ca = db.session.get(CA, ca_id)
    if not ca or not ca.crt or not ca.has_private_key:
        return error_response('CA not found or not valid for signing', 404)

    # Clamp validity to CA expiration
    try:
        ca_pem = base64.b64decode(ca.crt)
        ca_cert = x509.load_pem_x509_certificate(ca_pem)
        ca_exp = ca_cert.not_valid_after_utc.replace(tzinfo=None)
        max_days = (ca_exp - utc_now()).days
        if max_days < 1:
            return error_response('CA is expired', 400)
        if validity_days > max_days:
            validity_days = max_days
    except Exception as e:
        logger.warning(f"Could not clamp validity to CA expiration: {e}")

    ids = data['ids']
    results = {'success': [], 'failed': []}

    for csr_id in ids:
        try:
            cert = db.session.get(Certificate, csr_id)
            if not cert:
                results['failed'].append({'id': csr_id, 'error': 'Not found'})
                continue
            if not cert.csr:
                results['failed'].append({'id': csr_id, 'error': 'No CSR data'})
                continue
            if cert.crt:
                results['failed'].append({'id': csr_id, 'error': 'Already signed'})
                continue

            signed_cert = CertificateService.sign_csr(
                cert_id=csr_id, caref=ca.refid, validity_days=validity_days,
                allow_sensitive_ekus=True)
            results['success'].append(csr_id)
        except Exception as e:
            results['failed'].append({'id': csr_id, 'error': 'Signing failed'})

    AuditService.log_action(
        action='csrs_bulk_signed',
        resource_type='csr',
        resource_id=','.join(str(i) for i in results['success']),
        resource_name=f'{len(results["success"])} CSRs',
        details=f'Bulk signed {len(results["success"])} CSRs with CA {ca.descr}',
        success=True
    )

    return success_response(data=results, message=f'{len(results["success"])} CSRs signed')


@bp.route('/api/v2/csrs/bulk/delete', methods=['POST'])
@require_auth(['delete:csrs'])
def bulk_delete_csrs():
    """Bulk delete CSRs"""

    data = request.get_json()
    if not data or not data.get('ids'):
        return error_response('ids array required', 400)

    ids = data['ids']
    results = {'success': [], 'failed': []}

    for csr_id in ids:
        try:
            if CertificateService.delete_certificate(csr_id):
                results['success'].append(csr_id)
            else:
                results['failed'].append({'id': csr_id, 'error': 'Not found'})
        except Exception as e:
            results['failed'].append({'id': csr_id, 'error': 'Deletion failed'})

    AuditService.log_action(
        action='csrs_bulk_deleted',
        resource_type='csr',
        resource_id=','.join(str(i) for i in results['success']),
        resource_name=f'{len(results["success"])} CSRs',
        details=f'Bulk deleted {len(results["success"])} CSRs',
        success=True
    )

    return success_response(data=results, message=f'{len(results["success"])} CSRs deleted')

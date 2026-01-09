"""
mTLS Authentication API
Manage client certificates and mTLS settings
"""
from flask import Blueprint, request, jsonify, session, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from middleware.auth_middleware import admin_required
from models import db, User, SystemConfig, AuditLog, CA
from models.auth_certificate import AuthCertificate
from services.mtls_auth_service import MTLSAuthService
from services.certificate_parser import CertificateParser
from services.cert_service import CertificateService
import logging
import io
import base64

logger = logging.getLogger(__name__)

mtls_bp = Blueprint('mtls', __name__)


def log_audit(action, username, details=None):
    """Helper to log mTLS actions"""
    log = AuditLog(
        username=username,
        action=action,
        resource_type='mtls_certificate',
        details=details,
        ip_address=request.remote_addr
    )
    db.session.add(log)
    db.session.commit()


# ==================== mTLS Settings ====================

@mtls_bp.route('/settings', methods=['GET'])
@jwt_required()
@admin_required
def get_mtls_settings():
    """
    Get mTLS configuration
    ---
    GET /api/v1/mtls/settings
    """
    enabled = SystemConfig.query.filter_by(key='mtls_enabled').first()
    required = SystemConfig.query.filter_by(key='mtls_required').first()
    trusted_ca_id = SystemConfig.query.filter_by(key='mtls_trusted_ca_id').first()
    
    return jsonify({
        'enabled': enabled.value.lower() in ('true', '1', 'yes') if enabled else False,
        'required': required.value.lower() in ('true', '1', 'yes') if required else False,
        'trusted_ca_id': trusted_ca_id.value if trusted_ca_id else ''
    }), 200


@mtls_bp.route('/settings', methods=['POST', 'PUT'])
@jwt_required()
@admin_required
def update_mtls_settings():
    """
    Update mTLS configuration
    ---
    POST /api/v1/mtls/settings
    Body: {
        "enabled": true,
        "required": false,
        "trusted_ca_id": "ca_refid_123" (optional)
    }
    """
    try:
        data = request.get_json()
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        username = user.username if user else None
        
        # Update or create settings
        settings = {
            'mtls_enabled': str(data.get('enabled', False)).lower(),
            'mtls_required': str(data.get('required', False)).lower(),
            'mtls_trusted_ca_id': data.get('trusted_ca_id', '')
        }
        
        for key, value in settings.items():
            config = SystemConfig.query.filter_by(key=key).first()
            if not config:
                config = SystemConfig(key=key)
                db.session.add(config)
            
            config.value = value
            config.updated_by = username
        
        db.session.commit()
        
        log_audit('update_mtls_settings', username, f"Updated mTLS settings")
        
        return jsonify({
            'success': True,
            'message': 'mTLS settings updated successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating mTLS settings: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== Certificate Management ====================

@mtls_bp.route('/certificates', methods=['GET'])
@jwt_required()
def get_user_certificates():
    """
    Get certificates for current user
    ---
    GET /api/v1/mtls/certificates
    """
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    certificates = MTLSAuthService.get_user_certificates(user.id)
    
    return jsonify({
        'certificates': [cert.to_dict() for cert in certificates]
    }), 200


@mtls_bp.route('/certificates/all', methods=['GET'])
@jwt_required()
@admin_required
def get_all_certificates():
    """
    Get all enrolled certificates (admin only)
    ---
    GET /api/v1/mtls/certificates/all
    """
    certificates = AuthCertificate.query.all()
    
    # Include user information
    result = []
    for cert in certificates:
        cert_dict = cert.to_dict()
        if cert.user:
            cert_dict['username'] = cert.user.username
            cert_dict['user_email'] = cert.user.email
        result.append(cert_dict)
    
    return jsonify({
        'total': len(result),
        'certificates': result
    }), 200


@mtls_bp.route('/certificates/create', methods=['POST'])
@jwt_required()
def create_certificate():
    """
    Create a new client certificate (managed or self-signed)
    ---
    POST /api/v1/mtls/certificates/create
    Body: {
        "cn": "john.doe",
        "email": "john@example.com",
        "validity_days": 365,
        "key_size": 4096,  # Only for self-signed
        "self_signed": false  # true = self-signed, false = signed by trusted CA
    }
    """
    try:
        data = request.get_json()
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        username = user.username if user else None
        
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        cn = data.get('cn')
        email = data.get('email', '')
        validity_days = data.get('validity_days', 365)
        self_signed = data.get('self_signed', False)
        key_size = data.get('key_size', 4096)
        
        if not cn:
            return jsonify({'success': False, 'error': 'Common Name (CN) required'}), 400
        
        # Get mTLS settings
        trusted_ca_config = SystemConfig.query.filter_by(key='mtls_trusted_ca_id').first()
        trusted_ca_id = trusted_ca_config.value if trusted_ca_config else None
        
        if self_signed:
            # Create self-signed certificate
            if trusted_ca_id:
                return jsonify({'success': False, 'error': 'Self-signed certificates not allowed when CA is configured'}), 400
            
            # Generate self-signed cert using TrustStoreService
            from services.trust_store import TrustStoreService
            from cryptography.hazmat.primitives import hashes
            
            dn = {
                'CN': cn,
                'O': 'UCM mTLS',
                'OU': 'Client Certificate'
            }
            if email:
                dn['emailAddress'] = email
            
            subject = TrustStoreService.build_subject(dn)
            cert_pem_bytes, key_pem_bytes = TrustStoreService.create_self_signed_cert(
                subject=subject,
                validity_days=validity_days,
                key_type=str(key_size),
                digest='sha256'
            )
            
            # Convert to string for parsing
            cert_pem = cert_pem_bytes.decode('utf-8') if isinstance(cert_pem_bytes, bytes) else cert_pem_bytes
            key_pem = key_pem_bytes.decode('utf-8') if isinstance(key_pem_bytes, bytes) else key_pem_bytes
            cert_name = f"Self-Signed - {cn}"
            
        else:
            # Create managed certificate signed by trusted CA
            if not trusted_ca_id:
                return jsonify({'success': False, 'error': 'No trusted CA configured. Use self-signed option instead.'}), 400
            
            ca = CA.query.filter_by(refid=trusted_ca_id).first()
            if not ca:
                return jsonify({'success': False, 'error': 'Configured CA not found'}), 404
            
            # Build DN
            dn = {
                'CN': cn,
                'O': 'UCM mTLS',
                'OU': 'Client Certificate'
            }
            if email:
                dn['emailAddress'] = email
            
            # Create certificate using CertificateService
            cert = CertificateService.create_certificate(
                descr=f"mTLS Client - {cn}",
                caref=trusted_ca_id,
                dn=dn,
                cert_type='usr_cert',
                key_type=str(key_size),
                validity_days=validity_days,
                digest='sha256',
                san_email=[email] if email else None,
                private_key_location='stored',
                username=username
            )
            
            # Decode certificate and key from base64
            cert_pem_bytes = base64.b64decode(cert.crt)
            cert_pem = cert_pem_bytes.decode('utf-8')
            key_pem = base64.b64decode(cert.prv).decode('utf-8') if cert.prv else None
            cert_name = f"Managed - {cn}"
        
        # Parse certificate to extract info (cert_pem is string here)
        cert_obj = CertificateParser.parse_pem_certificate(cert_pem)
        if not cert_obj:
            raise ValueError("Failed to parse generated certificate")
        
        cert_info = CertificateParser.extract_certificate_info(cert_obj)
        
        # Store cert_pem as bytes for database
        if isinstance(cert_pem, str):
            cert_pem_bytes = cert_pem.encode('utf-8')
        
        # Create AuthCertificate record (metadata only, cert will be presented by client)
        auth_cert = AuthCertificate(
            user_id=user.id,
            name=cert_name,
            cert_serial=cert_info['serial'],
            cert_fingerprint=cert_info['fingerprint_sha256'],
            cert_subject=cert_info['subject_dn'],
            cert_issuer=cert_info['issuer_dn'],
            valid_from=cert_info['valid_from'],
            valid_until=cert_info['valid_until'],
            enabled=True
        )
        
        db.session.add(auth_cert)
        db.session.commit()
        
        log_audit('create_certificate', username, f"Created {'self-signed' if self_signed else 'managed'} certificate: {cn}")
        
        # Return certificate and private key for download
        return jsonify({
            'success': True,
            'message': 'Certificate created successfully',
            'certificate': auth_cert.to_dict(),
            'cert_pem': cert_pem,  # Return PEM for user to download
            'key_pem': key_pem  # Return private key for download
        }), 200
        
    except Exception as e:
        logger.error(f"Error creating certificate: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@mtls_bp.route('/certificates/enroll', methods=['POST'])
@jwt_required()
def enroll_certificate():
    """
    Enroll a client certificate for current user
    ---
    POST /api/v1/mtls/certificates/enroll
    Body: {
        "certificate": "-----BEGIN CERTIFICATE-----...",
        "name": "My YubiKey Certificate"
    }
    """
    try:
        data = request.get_json()
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        username = user.username if user else None
        
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        cert_pem = data.get('certificate')
        name = data.get('name')
        
        if not cert_pem:
            return jsonify({'success': False, 'error': 'Certificate required'}), 400
        
        success, message, auth_cert = MTLSAuthService.enroll_certificate(
            user.id,
            cert_pem,
            name
        )
        
        if success:
            log_audit('enroll_certificate', username, f"Enrolled certificate: {auth_cert.cert_serial}")
            
            return jsonify({
                'success': True,
                'message': message,
                'certificate': auth_cert.to_dict()
            }), 200
        else:
            return jsonify({'success': False, 'error': message}), 400
            
    except Exception as e:
        logger.error(f"Error enrolling certificate: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@mtls_bp.route('/certificates/<int:cert_id>/revoke', methods=['POST'])
@jwt_required()
def revoke_certificate(cert_id):
    """
    Revoke (disable) a certificate
    ---
    POST /api/v1/mtls/certificates/<cert_id>/revoke
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        username = user.username if user else None
        
        success, message = MTLSAuthService.revoke_certificate(cert_id, user.id)
        
        if success:
            log_audit('revoke_certificate', username, f"Revoked certificate ID: {cert_id}")
            return jsonify({'success': True, 'message': message}), 200
        else:
            return jsonify({'success': False, 'error': message}), 400
            
    except Exception as e:
        logger.error(f"Error revoking certificate: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@mtls_bp.route('/certificates/<int:cert_id>/download', methods=['GET'])
@jwt_required()
def download_certificate(cert_id):
    """
    Download certificate PEM file
    ---
    GET /api/v1/mtls/certificates/<cert_id>/download
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        # Get certificate (user can only download their own, admin can download any)
        auth_cert = AuthCertificate.query.filter_by(id=cert_id).first()
        
        if not auth_cert:
            return jsonify({'error': 'Certificate not found'}), 404
        
        # Check ownership
        if auth_cert.user_id != user.id and user.role != 'admin':
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Create PEM file
        cert_data = auth_cert.cert_pem.encode('utf-8')
        
        return send_file(
            io.BytesIO(cert_data),
            mimetype='application/x-pem-file',
            as_attachment=True,
            download_name=f'client-cert-{auth_cert.cert_serial[:16]}.pem'
        )
        
    except Exception as e:
        logger.error(f"Error downloading certificate: {str(e)}")
        return jsonify({'error': str(e)}), 500


@mtls_bp.route('/certificates/<int:cert_id>', methods=['DELETE'])
@jwt_required()
def delete_certificate(cert_id):
    """
    Delete a certificate
    ---
    DELETE /api/v1/mtls/certificates/<cert_id>
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        username = user.username if user else None
        
        success, message = MTLSAuthService.delete_certificate(cert_id, user.id)
        
        if success:
            log_audit('delete_certificate', username, f"Deleted certificate ID: {cert_id}")
            return jsonify({'success': True, 'message': message}), 200
        else:
            return jsonify({'success': False, 'error': message}), 400
            
    except Exception as e:
        logger.error(f"Error deleting certificate: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@mtls_bp.route('/certificates/<int:cert_id>/enable', methods=['POST'])
@jwt_required()
def enable_certificate(cert_id):
    """
    Re-enable a disabled certificate
    ---
    POST /api/v1/mtls/certificates/<cert_id>/enable
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        username = user.username if user else None
        
        cert = AuthCertificate.query.get(cert_id)
        
        if not cert:
            return jsonify({'success': False, 'error': 'Certificate not found'}), 404
        
        # Check authorization
        if cert.user_id != user.id and user.role != 'admin':
            return jsonify({'success': False, 'error': 'Not authorized'}), 403
        
        cert.enabled = True
        db.session.commit()
        
        log_audit('enable_certificate', username, f"Enabled certificate ID: {cert_id}")
        
        return jsonify({
            'success': True,
            'message': 'Certificate enabled successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error enabling certificate: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== Certificate Info/Validation ====================

@mtls_bp.route('/validate-certificate', methods=['POST'])
@jwt_required()
def validate_certificate():
    """
    Validate a certificate without enrolling it
    ---
    POST /api/v1/mtls/validate-certificate
    Body: {"certificate": "-----BEGIN CERTIFICATE-----..."}
    """
    try:
        data = request.get_json()
        cert_pem = data.get('certificate')
        
        if not cert_pem:
            return jsonify({'success': False, 'error': 'Certificate required'}), 400
        
        cert = CertificateParser.parse_pem_certificate(cert_pem)
        
        if not cert:
            return jsonify({
                'success': False,
                'error': 'Invalid certificate format'
            }), 400
        
        cert_info = CertificateParser.extract_certificate_info(cert)
        
        # Check if already enrolled
        existing = AuthCertificate.query.filter_by(cert_serial=cert_info['serial']).first()
        
        return jsonify({
            'success': True,
            'valid': cert_info['is_valid'],
            'already_enrolled': existing is not None,
            'info': {
                'subject': cert_info['subject_dn'],
                'issuer': cert_info['issuer_dn'],
                'serial': cert_info['serial'],
                'common_name': cert_info['common_name'],
                'email': cert_info['email'],
                'valid_from': cert_info['valid_from'].isoformat() if cert_info['valid_from'] else None,
                'valid_until': cert_info['valid_until'].isoformat() if cert_info['valid_until'] else None,
                'fingerprint': cert_info['fingerprint']
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error validating certificate: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

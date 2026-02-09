"""
mTLS API
Manage client certificates for mutual TLS authentication
"""

from flask import Blueprint, jsonify, request, current_app, g, Response
from api.v2.auth import require_auth
from models import User, Certificate, CA, db
from services.audit_service import AuditService
import json
from datetime import datetime, timezone

bp = Blueprint('mtls', __name__, url_prefix='/api/v2/mtls')


@bp.route('/certificates', methods=['GET'])
@require_auth()
def list_mtls_certificates():
    """List user's mTLS certificates (certificates with clientAuth EKU)"""
    user = g.current_user
    
    # Get certificates issued for this user (CN contains username@mtls)
    mtls_certs = Certificate.query.filter(
        Certificate.subject.like(f'%CN={user.username}@mtls%')
    ).order_by(Certificate.created_at.desc()).all()
    
    result = []
    for cert in mtls_certs:
        result.append({
            'id': cert.id,
            'name': f'mTLS Certificate #{cert.id}',
            'serial': cert.serial_number,
            'subject': cert.subject,
            'created_at': cert.created_at.isoformat() if cert.created_at else None,
            'expires_at': cert.not_after.isoformat() if cert.not_after else None,
            'status': cert.status,
            'ca_id': cert.ca_id
        })
    
    return jsonify({'data': result})


@bp.route('/certificates', methods=['POST'])
@require_auth()
def create_mtls_certificate():
    """Issue a new mTLS certificate for the user"""
    user = g.current_user
    data = request.get_json() or {}
    
    # Get CA for issuing
    ca_id = data.get('ca_id')
    if not ca_id:
        # Use first available CA
        ca = CA.query.first()
        if not ca:
            return jsonify({'error': True, 'message': 'No CA available'}), 400
        ca_id = ca.id
    
    ca = CA.query.get(ca_id)
    if not ca:
        return jsonify({'error': True, 'message': 'CA not found'}), 404
    
    # Create client certificate
    from services.certificate_service import CertificateService
    cert_service = CertificateService()
    
    # Build subject
    subject = {
        'CN': f'{user.username}@mtls',
        'O': data.get('organization', 'UCM Users'),
        'OU': 'mTLS Clients'
    }
    
    validity_days = data.get('validity_days', 365)
    
    try:
        # Issue certificate
        cert_data = cert_service.issue_certificate(
            ca_id=ca_id,
            subject=subject,
            key_type='RSA',
            key_size=2048,
            validity_days=validity_days,
            key_usage=['digitalSignature', 'keyEncipherment'],
            extended_key_usage=['clientAuth']
        )
        
        AuditService.log_action(
            action='mtls_cert_create',
            resource_type='certificate',
            resource_id=str(cert_data['id']),
            resource_name=f'{user.username}@mtls',
            details=f'Created mTLS certificate for user: {user.username}',
            success=True
        )
        
        return jsonify({
            'data': {
                'id': cert_data['id'],
                'serial': cert_data.get('serial', ''),
                'certificate': cert_data.get('pem', ''),
                'private_key': cert_data.get('private_key', ''),
                'created_at': datetime.now(timezone.utc).isoformat(),
                'expires_at': cert_data.get('not_after', ''),
                'status': 'valid'
            },
            'message': 'mTLS certificate created'
        }), 201
        
    except Exception as e:
        return jsonify({'error': True, 'message': str(e)}), 500


@bp.route('/certificates/<int:cert_id>', methods=['DELETE'])
@require_auth()
def revoke_mtls_certificate(cert_id):
    """Revoke a mTLS certificate"""
    user = g.current_user
    
    # Find certificate and verify ownership
    cert = Certificate.query.get(cert_id)
    if not cert:
        return jsonify({'error': True, 'message': 'Certificate not found'}), 404
    
    # Verify ownership (CN should contain username@mtls)
    if f'{user.username}@mtls' not in (cert.subject or ''):
        return jsonify({'error': True, 'message': 'Not authorized to revoke this certificate'}), 403
    
    # Revoke the certificate
    cert.status = 'revoked'
    cert.revoked_at = datetime.now(timezone.utc)
    cert.revocation_reason = 'User requested'
    db.session.commit()
    
    AuditService.log_action(
        action='mtls_cert_revoke',
        resource_type='certificate',
        resource_id=str(cert_id),
        resource_name=f'{user.username}@mtls',
        details=f'Revoked mTLS certificate {cert_id} for user: {user.username}',
        success=True
    )
    
    return jsonify({'message': 'Certificate revoked'})


@bp.route('/certificates/<int:cert_id>/download', methods=['GET'])
@require_auth()
def download_mtls_certificate(cert_id):
    """Download mTLS certificate as PKCS12"""
    user = g.current_user
    
    # Find certificate
    cert = Certificate.query.get(cert_id)
    if not cert:
        return jsonify({'error': True, 'message': 'Certificate not found'}), 404
    
    # Verify ownership
    if f'{user.username}@mtls' not in (cert.subject or ''):
        return jsonify({'error': True, 'message': 'Not authorized'}), 403
    
    # Check if we have the certificate PEM
    if not cert.certificate_pem:
        return jsonify({'error': True, 'message': 'Certificate data not available'}), 404
    
    # For now, just return PEM format
    # TODO: Implement PKCS12 conversion if private key is stored
    return Response(
        cert.certificate_pem,
        mimetype='application/x-pem-file',
        headers={
            'Content-Disposition': f'attachment; filename=mtls-{cert_id}.pem'
        }
    )


@bp.route('/authenticate', methods=['POST'])
def authenticate():
    """Authenticate via mTLS client certificate"""
    # Get client certificate from request
    # This requires NGINX/Apache to pass the client cert in a header
    client_cert = request.headers.get('X-Client-Cert')
    client_cert_verify = request.headers.get('X-Client-Cert-Verify')
    
    if not client_cert or client_cert_verify != 'SUCCESS':
        return jsonify({'error': True, 'message': 'No valid client certificate'}), 401
    
    # Parse certificate to get username
    # The CN should be in format: username@mtls
    import re
    match = re.search(r'CN=([^@,]+)@mtls', client_cert)
    if not match:
        return jsonify({'error': True, 'message': 'Invalid certificate subject'}), 401
    
    username = match.group(1)
    
    # Find user
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'error': True, 'message': 'User not found'}), 401
    
    if not user.active:
        return jsonify({'error': True, 'message': 'Account disabled'}), 401
    
    # Create session
    from flask import session
    session['user_id'] = user.id
    session.permanent = True
    
    return jsonify({
        'data': user.to_dict(),
        'message': 'mTLS authentication successful'
    })

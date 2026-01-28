"""
mTLS API
Manage client certificates for mutual TLS authentication
"""

from flask import Blueprint, jsonify, request, current_app, g
from api.v2.auth import require_auth
from models import User, Certificate, CA, db
import json
from datetime import datetime, timezone

bp = Blueprint('mtls', __name__, url_prefix='/api/v2/mtls')


@bp.route('/certificates', methods=['GET'])
@require_auth()
def list_mtls_certificates():
    """List user's mTLS certificates"""
    user = g.current_user
    
    # Get certificates from user metadata
    metadata = json.loads(user.metadata or '{}')
    mtls_certs = metadata.get('mtls_certificates', [])
    
    return jsonify({'data': mtls_certs})


@bp.route('/certificates', methods=['POST'])
@require_auth()
def create_mtls_certificate():
    """Issue a new mTLS certificate for the user"""
    user = g.current_user
    data = request.get_json()
    
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
        
        # Store reference in user metadata
        metadata = json.loads(user.metadata or '{}')
        mtls_certs = metadata.get('mtls_certificates', [])
        
        mtls_cert_ref = {
            'id': cert_data['id'],
            'name': data.get('name', f'mTLS Certificate {len(mtls_certs) + 1}'),
            'serial': cert_data.get('serial', ''),
            'created_at': datetime.now(timezone.utc).isoformat(),
            'expires_at': cert_data.get('not_after', ''),
            'status': 'valid'
        }
        
        mtls_certs.append(mtls_cert_ref)
        metadata['mtls_certificates'] = mtls_certs
        user.metadata = json.dumps(metadata)
        db.session.commit()
        
        return jsonify({
            'data': {
                **mtls_cert_ref,
                'certificate': cert_data.get('pem', ''),
                'private_key': cert_data.get('private_key', '')
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
    
    # Find in user metadata
    metadata = json.loads(user.metadata or '{}')
    mtls_certs = metadata.get('mtls_certificates', [])
    
    cert_ref = None
    for c in mtls_certs:
        if c['id'] == cert_id:
            cert_ref = c
            break
    
    if not cert_ref:
        return jsonify({'error': True, 'message': 'Certificate not found'}), 404
    
    # Revoke the actual certificate
    cert = Certificate.query.get(cert_id)
    if cert:
        cert.status = 'revoked'
        cert.revoked_at = datetime.now(timezone.utc)
        cert.revocation_reason = 'User requested'
        db.session.commit()
    
    # Update reference
    cert_ref['status'] = 'revoked'
    cert_ref['revoked_at'] = datetime.now(timezone.utc).isoformat()
    user.metadata = json.dumps(metadata)
    db.session.commit()
    
    return jsonify({'message': 'Certificate revoked'})


@bp.route('/certificates/<int:cert_id>/download', methods=['GET'])
@require_auth()
def download_mtls_certificate(cert_id):
    """Download mTLS certificate as PKCS12"""
    user = g.current_user
    
    # Check if user owns this cert
    metadata = json.loads(user.metadata or '{}')
    mtls_certs = metadata.get('mtls_certificates', [])
    
    has_cert = any(c['id'] == cert_id for c in mtls_certs)
    if not has_cert:
        return jsonify({'error': True, 'message': 'Certificate not found'}), 404
    
    cert = Certificate.query.get(cert_id)
    if not cert:
        return jsonify({'error': True, 'message': 'Certificate not found'}), 404
    
    password = request.args.get('password', 'changeme')
    
    # Generate PKCS12
    from services.certificate_service import CertificateService
    cert_service = CertificateService()
    
    try:
        pkcs12_data = cert_service.export_pkcs12(cert_id, password)
        
        from flask import Response
        return Response(
            pkcs12_data,
            mimetype='application/x-pkcs12',
            headers={
                'Content-Disposition': f'attachment; filename=mtls_{user.username}.p12'
            }
        )
    except Exception as e:
        return jsonify({'error': True, 'message': str(e)}), 500


@bp.route('/authenticate', methods=['POST'])
def mtls_authenticate():
    """Authenticate using client certificate"""
    # Get client certificate from request (nginx/gunicorn passes via headers)
    client_cert = request.headers.get('X-Client-Cert')
    client_cn = request.headers.get('X-Client-CN')
    client_verified = request.headers.get('X-Client-Verify')
    
    if client_verified != 'SUCCESS':
        return jsonify({
            'error': True, 
            'message': 'Client certificate verification failed'
        }), 401
    
    if not client_cn:
        return jsonify({
            'error': True,
            'message': 'No client certificate provided'
        }), 401
    
    # Extract username from CN (format: username@mtls)
    username = client_cn.split('@')[0] if '@' in client_cn else client_cn
    
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'error': True, 'message': 'User not found'}), 404
    
    if not user.is_active:
        return jsonify({'error': True, 'message': 'User account is disabled'}), 403
    
    # Create session
    from flask import session
    session.clear()
    session['user_id'] = user.id
    session.permanent = True
    
    return jsonify({
        'data': user.to_dict(),
        'message': 'mTLS authentication successful'
    })

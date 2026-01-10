"""
CRL API - Certificate Revocation List Management
RFC 5280 compliant CRL generation and distribution
"""
from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from middleware.auth_middleware import operator_required
from io import BytesIO

from models import db, CA, AuditLog
from models.crl import CRLMetadata
from services.crl_service import CRLService

crl_bp = Blueprint('crl', __name__)


@crl_bp.route('/', methods=['GET'])
@jwt_required()
def list_crls():
    """List all CRLs with metadata"""
    try:
        # Get all CAs
        cas = CA.query.all()
        
        result = []
        for ca in cas:
            latest_crl = CRLService.get_latest_crl(ca.id)
            
            crl_info = {
                'ca_id': ca.id,
                'ca_refid': ca.refid,
                'ca_name': ca.descr,
                'ca_common_name': ca.common_name,
                'cdp_enabled': ca.cdp_enabled,
                'cdp_url': ca.cdp_url,
                'has_crl': latest_crl is not None,
            }
            
            if latest_crl:
                crl_info.update({
                    'crl_number': latest_crl.crl_number,
                    'this_update': latest_crl.this_update.isoformat() if latest_crl.this_update else None,
                    'next_update': latest_crl.next_update.isoformat() if latest_crl.next_update else None,
                    'revoked_count': latest_crl.revoked_count,
                    'is_stale': latest_crl.is_stale,
                    'days_until_expiry': latest_crl.days_until_expiry,
                    'generated_by': latest_crl.generated_by,
                })
            
            result.append(crl_info)
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@crl_bp.route('/<int:ca_id>', methods=['GET'])
@jwt_required()
def get_crl_metadata(ca_id):
    """Get CRL metadata for a specific CA"""
    try:
        ca = CA.query.get(ca_id)
        if not ca:
            return jsonify({'error': 'CA not found'}), 404
        
        latest_crl = CRLService.get_latest_crl(ca_id)
        
        if not latest_crl:
            return jsonify({
                'ca_id': ca_id,
                'ca_name': ca.descr,
                'has_crl': False,
                'message': 'No CRL generated yet for this CA'
            }), 200
        
        # Get all CRLs for this CA (history)
        all_crls = CRLMetadata.query.filter_by(ca_id=ca_id).order_by(
            CRLMetadata.crl_number.desc()
        ).all()
        
        return jsonify({
            'ca_id': ca_id,
            'ca_name': ca.descr,
            'ca_refid': ca.refid,
            'cdp_enabled': ca.cdp_enabled,
            'cdp_url': ca.cdp_url,
            'latest_crl': latest_crl.to_dict(),
            'history': [crl.to_dict() for crl in all_crls[:10]]  # Last 10 CRLs
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@crl_bp.route('/<int:ca_id>/generate', methods=['POST'])
@jwt_required()
@operator_required
def generate_crl(ca_id):
    """Force CRL generation for a CA"""
    try:
        username = get_jwt_identity()
        
        ca = CA.query.get(ca_id)
        if not ca:
            return jsonify({'error': 'CA not found'}), 404
        
        if not ca.has_private_key:
            return jsonify({'error': 'CA does not have a private key - cannot sign CRL'}), 400
        
        # Generate CRL
        crl_metadata = CRLService.generate_crl(ca_id, username=username)
        
        return jsonify({
            'message': f'CRL #{crl_metadata.crl_number} generated successfully',
            'crl': crl_metadata.to_dict()
        }), 201
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@crl_bp.route('/<int:ca_id>/download', methods=['GET'])
@jwt_required()
def download_crl(ca_id):
    """Download CRL in PEM or DER format"""
    try:
        format_type = request.args.get('format', 'pem').lower()
        
        ca = CA.query.get(ca_id)
        if not ca:
            return jsonify({'error': 'CA not found'}), 404
        
        latest_crl = CRLService.get_latest_crl(ca_id)
        if not latest_crl:
            return jsonify({'error': 'No CRL available for this CA'}), 404
        
        if format_type == 'der':
            # Send DER format
            return send_file(
                BytesIO(latest_crl.crl_der),
                mimetype='application/pkix-crl',
                as_attachment=True,
                download_name=f'{ca.refid}.crl'
            )
        else:
            # Send PEM format
            return send_file(
                BytesIO(latest_crl.crl_pem.encode('utf-8')),
                mimetype='application/x-pem-file',
                as_attachment=True,
                download_name=f'{ca.refid}.pem'
            )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@crl_bp.route('/<int:ca_id>/revoked', methods=['GET'])
@jwt_required()
def get_revoked_certificates(ca_id):
    """Get list of revoked certificates for a CA"""
    try:
        ca = CA.query.get(ca_id)
        if not ca:
            return jsonify({'error': 'CA not found'}), 404
        
        revoked_certs = CRLService.get_revoked_certificates(ca_id)
        
        result = []
        for cert in revoked_certs:
            result.append({
                'id': cert.id,
                'refid': cert.refid,
                'descr': cert.descr,
                'serial_number': cert.serial_number,
                'common_name': cert.common_name,
                'revoked_at': cert.revoked_at.isoformat() if cert.revoked_at else None,
                'revoke_reason': cert.revoke_reason,
            })
        
        return jsonify({
            'ca_id': ca_id,
            'ca_name': ca.descr,
            'revoked_count': len(result),
            'revoked_certificates': result
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


"""
CA API - Certificate Authority Management
"""
from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from io import BytesIO

from models import db, User
from services.ca_service import CAService
from middleware.auth_middleware import operator_required, admin_required

ca_bp = Blueprint('ca', __name__)


@ca_bp.route('/', methods=['GET'])
@jwt_required()
def list_cas():
    """
    List all Certificate Authorities
    ---
    GET /api/v1/ca
    """
    cas = CAService.list_cas()
    return jsonify([ca.to_dict() for ca in cas]), 200


@ca_bp.route('/', methods=['POST'])
@jwt_required()
@operator_required
def create_ca():
    """
    Create new Certificate Authority
    ---
    POST /api/v1/ca
    {
        "action": "internal" | "import",
        "descr": "My CA",
        "dn": {
            "CN": "My CA",
            "O": "My Organization",
            "C": "NL"
        },
        "key_type": "2048",
        "validity_days": 825,
        "digest": "sha256",
        "caref": "parent-ca-refid",  // optional for intermediate CA
        "ocsp_uri": "http://ocsp.example.com",  // optional
        "crt_payload": "-----BEGIN CERTIFICATE-----...",  // for import
        "prv_payload": "-----BEGIN PRIVATE KEY-----..."  // optional for import
    }
    """
    data = request.get_json()
    identity = get_jwt_identity()
    user = User.query.get(identity)
    
    action = data.get('action', 'internal')
    
    try:
        if action == 'internal':
            # Create internal CA
            ca = CAService.create_internal_ca(
                descr=data.get('descr', 'New CA'),
                dn=data.get('dn', {}),
                key_type=data.get('key_type', '2048'),
                validity_days=int(data.get('validity_days', 825)),
                digest=data.get('digest', 'sha256'),
                caref=data.get('caref'),
                ocsp_uri=data.get('ocsp_uri'),
                username=user.username
            )
            return jsonify(ca.to_dict()), 201
            
        elif action == 'import':
            # Import existing CA
            if not data.get('crt_payload'):
                return jsonify({"error": "Certificate required for import"}), 400
            
            ca = CAService.import_ca(
                descr=data.get('descr', 'Imported CA'),
                cert_pem=data.get('crt_payload'),
                key_pem=data.get('prv_payload'),
                username=user.username
            )
            return jsonify(ca.to_dict()), 201
            
        else:
            return jsonify({"error": f"Unknown action: {action}"}), 400
            
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to create CA: {str(e)}"}), 500


@ca_bp.route('/<int:ca_id>', methods=['GET'])
@jwt_required()
def get_ca(ca_id):
    """
    Get CA details
    ---
    GET /api/v1/ca/<id>
    """
    ca = CAService.get_ca(ca_id)
    if not ca:
        return jsonify({"error": "CA not found"}), 404
    
    return jsonify(ca.to_dict(include_private=False)), 200


@ca_bp.route('/<int:ca_id>', methods=['DELETE'])
@jwt_required()
@operator_required
def delete_ca(ca_id):
    """
    Delete CA
    ---
    DELETE /api/v1/ca/<id>
    """
    identity = get_jwt_identity()
    user = User.query.get(identity)
    
    try:
        if CAService.delete_ca(ca_id, user.username):
            return jsonify({"message": "CA deleted successfully"}), 200
        else:
            return jsonify({"error": "CA not found"}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to delete CA: {str(e)}"}), 500


@ca_bp.route('/<int:ca_id>/export', methods=['GET'])
@jwt_required()
def export_ca(ca_id):
    """
    Export CA certificate
    ---
    GET /api/v1/ca/<id>/export?format=pem|der
    """
    format = request.args.get('format', 'pem')
    
    try:
        cert_bytes = CAService.export_ca(ca_id, format)
        
        mimetype = 'application/x-pem-file' if format == 'pem' else 'application/x-x509-ca-cert'
        extension = 'pem' if format == 'pem' else 'crt'
        
        return send_file(
            BytesIO(cert_bytes),
            mimetype=mimetype,
            as_attachment=True,
            download_name=f'ca_{ca_id}.{extension}'
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": f"Export failed: {str(e)}"}), 500


@ca_bp.route('/<int:ca_id>/chain', methods=['GET'])
@jwt_required()
def get_ca_chain(ca_id):
    """
    Get CA certificate chain
    ---
    GET /api/v1/ca/<id>/chain
    """
    try:
        chain = CAService.get_ca_chain(ca_id)
        
        # Return as list of PEM strings
        chain_pem = [cert.decode('utf-8') for cert in chain]
        
        return jsonify({
            "chain": chain_pem,
            "count": len(chain_pem)
        }), 200
    except Exception as e:
        return jsonify({"error": f"Failed to get chain: {str(e)}"}), 500

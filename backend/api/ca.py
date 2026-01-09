"""
CA API - Certificate Authority Management
"""
from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from io import BytesIO

from models import db, CA, AuditLog, User
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
    Delete CA by ID
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


@ca_bp.route('/<string:refid>', methods=['DELETE'])
@jwt_required()
@operator_required
def delete_ca_by_refid(refid):
    """
    Delete CA by refid
    ---
    DELETE /api/v1/ca/<refid>
    """
    from models import CA
    identity = get_jwt_identity()
    user = User.query.get(identity)
    
    try:
        ca = CA.query.filter_by(refid=refid).first()
        if not ca:
            return jsonify({"error": "CA not found"}), 404
        
        if CAService.delete_ca(ca.id, user.username):
            return jsonify({"message": "CA deleted successfully"}), 200
        else:
            return jsonify({"error": "Failed to delete CA"}), 500
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


@ca_bp.route('/<int:ca_id>/crl', methods=['GET'])
@jwt_required()
def get_ca_crl(ca_id):
    """
    Generate and download Certificate Revocation List
    ---
    GET /api/v1/ca/<id>/crl?validity_days=30
    """
    validity_days = int(request.args.get('validity_days', 30))
    
    try:
        crl_pem = CAService.generate_crl(ca_id, validity_days)
        
        return send_file(
            BytesIO(crl_pem),
            mimetype='application/pkix-crl',
            as_attachment=True,
            download_name=f'ca_{ca_id}.crl'
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": f"CRL generation failed: {str(e)}"}), 500


@ca_bp.route('/<int:ca_id>/fingerprints', methods=['GET'])
@jwt_required()
def get_ca_fingerprints(ca_id):
    """
    Get CA certificate fingerprints
    ---
    GET /api/v1/ca/<id>/fingerprints
    """
    try:
        fingerprints = CAService.get_ca_fingerprints(ca_id)
        return jsonify(fingerprints), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": f"Failed to get fingerprints: {str(e)}"}), 500


@ca_bp.route('/<int:ca_id>/details', methods=['GET'])
@jwt_required()
def get_ca_details(ca_id):
    """
    Get detailed CA certificate information
    ---
    GET /api/v1/ca/<id>/details
    """
    try:
        details = CAService.get_ca_details(ca_id)
        return jsonify(details), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": f"Failed to get details: {str(e)}"}), 500


@ca_bp.route('/<int:ca_id>/export/advanced', methods=['GET'])
@jwt_required()
def export_ca_advanced(ca_id):
    """
    Export CA with advanced options
    ---
    GET /api/v1/ca/<id>/export/advanced?format=pem|der|pkcs12&key=true&chain=true&password=xxx
    """
    export_format = request.args.get('format', 'pem')
    include_key = request.args.get('key', 'false').lower() == 'true'
    include_chain = request.args.get('chain', 'false').lower() == 'true'
    password = request.args.get('password')
    
    try:
        cert_bytes = CAService.export_ca_with_options(
            ca_id=ca_id,
            export_format=export_format,
            include_key=include_key,
            include_chain=include_chain,
            password=password
        )
        
        # Determine mimetype and extension
        if export_format == 'pkcs12':
            mimetype = 'application/x-pkcs12'
            extension = 'p12'
        elif export_format == 'der':
            mimetype = 'application/x-x509-ca-cert'
            extension = 'crt'
        else:
            mimetype = 'application/x-pem-file'
            extension = 'pem'
        
        return send_file(
            BytesIO(cert_bytes),
            mimetype=mimetype,
            as_attachment=True,
            download_name=f'ca_{ca_id}.{extension}'
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Export failed: {str(e)}"}), 500


@ca_bp.route('/<int:ca_id>', methods=['PATCH'])
@jwt_required()
@operator_required
def update_ca(ca_id):
    """Update CA configuration (CDP settings)"""
    try:
        data = request.get_json()
        
        ca = CA.query.get(ca_id)
        if not ca:
            return jsonify({"error": "CA not found"}), 404
        
        # Update CDP configuration
        if 'cdp_enabled' in data:
            ca.cdp_enabled = bool(data['cdp_enabled'])
        
        if 'cdp_url' in data:
            cdp_url = data['cdp_url']
            if cdp_url:
                # Validate CDP URL format
                if '{ca_refid}' not in cdp_url:
                    return jsonify({"error": "CDP URL must contain {ca_refid} placeholder"}), 400
                ca.cdp_url = cdp_url
            else:
                ca.cdp_url = None
        
        # Update OCSP configuration
        if 'ocsp_enabled' in data:
            ca.ocsp_enabled = bool(data['ocsp_enabled'])
        
        if 'ocsp_url' in data:
            ocsp_url = data['ocsp_url']
            ca.ocsp_url = ocsp_url if ocsp_url else None
        
        # Validate: if CDP enabled, URL must be set
        if ca.cdp_enabled and not ca.cdp_url:
            return jsonify({"error": "CDP URL is required when CDP is enabled"}), 400
        
        # Validate: if OCSP enabled, URL must be set
        if ca.ocsp_enabled and not ca.ocsp_url:
            return jsonify({"error": "OCSP URL is required when OCSP is enabled"}), 400
        
        db.session.commit()
        
        # Audit log
        username = get_jwt_identity()
        audit = AuditLog(
            username=username,
            action='ca_updated',
            resource_type='ca',
            resource_id=ca.refid,
            details=f"Updated CA configuration: CDP={ca.cdp_enabled}, OCSP={ca.ocsp_enabled}",
            success=True
        )
        db.session.add(audit)
        db.session.commit()
        
        return jsonify({
            "message": "CA updated successfully",
            "ca": {
                "id": ca.id,
                "refid": ca.refid,
                "cdp_enabled": ca.cdp_enabled,
                "cdp_url": ca.cdp_url,
                "ocsp_enabled": ca.ocsp_enabled,
                "ocsp_url": ca.ocsp_url
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

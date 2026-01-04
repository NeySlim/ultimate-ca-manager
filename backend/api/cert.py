"""
Certificate API - Certificate Management
"""
from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from io import BytesIO

from models import db, User
from services.cert_service import CertificateService
from middleware.auth_middleware import operator_required

cert_bp = Blueprint('cert', __name__)


@cert_bp.route('/', methods=['GET'])
@jwt_required()
def list_certificates():
    """
    List all certificates
    ---
    GET /api/v1/certificates?caref=<ca-refid>
    """
    caref = request.args.get('caref')
    certificates = CertificateService.list_certificates(caref=caref)
    return jsonify([cert.to_dict() for cert in certificates]), 200


@cert_bp.route('/', methods=['POST'])
@jwt_required()
@operator_required
def create_certificate():
    """
    Create new certificate
    ---
    POST /api/v1/certificates
    {
        "action": "internal" | "csr" | "import",
        "descr": "My Certificate",
        "caref": "ca-refid",  // for internal action
        "dn": {
            "CN": "example.com",
            "O": "My Org",
            "C": "NL"
        },
        "cert_type": "server_cert",  // usr_cert, server_cert, combined_server_client, ca_cert
        "key_type": "2048",
        "validity_days": 397,
        "digest": "sha256",
        "san_dns": ["example.com", "*.example.com"],  // optional
        "san_ip": ["192.168.1.1"],  // optional
        "san_uri": ["https://example.com"],  // optional
        "san_email": ["admin@example.com"],  // optional
        "ocsp_uri": "http://ocsp.example.com",  // optional
        "private_key_location": "firewall" | "download_only",  // optional
        "crt_payload": "-----BEGIN CERTIFICATE-----...",  // for import
        "prv_payload": "-----BEGIN PRIVATE KEY-----..."  // optional for import
    }
    """
    data = request.get_json()
    identity = get_jwt_identity()
    user = User.query.get(int(identity))
    
    action = data.get('action', 'internal')
    
    try:
        if action == 'internal':
            # Create certificate signed by CA
            cert = CertificateService.create_certificate(
                descr=data.get('descr', 'New Certificate'),
                caref=data.get('caref'),
                dn=data.get('dn', {}),
                cert_type=data.get('cert_type', 'server_cert'),
                key_type=data.get('key_type', '2048'),
                validity_days=int(data.get('validity_days', 397)),
                digest=data.get('digest', 'sha256'),
                san_dns=data.get('san_dns'),
                san_ip=data.get('san_ip'),
                san_uri=data.get('san_uri'),
                san_email=data.get('san_email'),
                ocsp_uri=data.get('ocsp_uri'),
                private_key_location=data.get('private_key_location', 'firewall'),
                username=user.username
            )
            return jsonify(cert.to_dict()), 201
            
        elif action == 'csr':
            # Generate CSR
            cert = CertificateService.generate_csr(
                descr=data.get('descr', 'New CSR'),
                dn=data.get('dn', {}),
                key_type=data.get('key_type', '2048'),
                digest=data.get('digest', 'sha256'),
                san_dns=data.get('san_dns'),
                san_ip=data.get('san_ip'),
                username=user.username
            )
            return jsonify(cert.to_dict()), 201
            
        elif action == 'import':
            # Import existing certificate
            if not data.get('crt_payload'):
                return jsonify({"error": "Certificate required for import"}), 400
            
            cert = CertificateService.import_certificate(
                descr=data.get('descr', 'Imported Certificate'),
                cert_pem=data.get('crt_payload'),
                key_pem=data.get('prv_payload'),
                username=user.username
            )
            return jsonify(cert.to_dict()), 201
            
        else:
            return jsonify({"error": f"Unknown action: {action}"}), 400
            
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to create certificate: {str(e)}"}), 500


@cert_bp.route('/<int:cert_id>', methods=['GET'])
@jwt_required()
def get_certificate(cert_id):
    """
    Get certificate details
    ---
    GET /api/v1/certificates/<id>
    """
    cert = CertificateService.get_certificate(cert_id)
    if not cert:
        return jsonify({"error": "Certificate not found"}), 404
    
    return jsonify(cert.to_dict(include_private=False)), 200


@cert_bp.route('/<int:cert_id>/sign', methods=['POST'])
@jwt_required()
@operator_required
def sign_csr(cert_id):
    """
    Sign a CSR
    ---
    POST /api/v1/certificates/<id>/sign
    {
        "caref": "ca-refid",
        "cert_type": "server_cert",
        "validity_days": 397,
        "digest": "sha256"
    }
    """
    data = request.get_json()
    identity = get_jwt_identity()
    user = User.query.get(int(identity))
    
    try:
        cert = CertificateService.sign_csr(
            cert_id=cert_id,
            caref=data.get('caref'),
            cert_type=data.get('cert_type', 'server_cert'),
            validity_days=int(data.get('validity_days', 397)),
            digest=data.get('digest', 'sha256'),
            username=user.username
        )
        return jsonify(cert.to_dict()), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to sign CSR: {str(e)}"}), 500


@cert_bp.route('/<int:cert_id>/revoke', methods=['POST'])
@jwt_required()
@operator_required
def revoke_certificate(cert_id):
    """
    Revoke a certificate
    ---
    POST /api/v1/certificates/<id>/revoke
    {
        "reason": "compromised"
    }
    """
    data = request.get_json() or {}
    identity = get_jwt_identity()
    user = User.query.get(int(identity))
    
    try:
        cert = CertificateService.revoke_certificate(
            cert_id=cert_id,
            reason=data.get('reason', 'unspecified'),
            username=user.username
        )
        return jsonify(cert.to_dict()), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to revoke certificate: {str(e)}"}), 500


@cert_bp.route('/<int:cert_id>/export', methods=['GET'])
@jwt_required()
def export_certificate(cert_id):
    """
    Export certificate
    ---
    GET /api/v1/certificates/<id>/export?format=pem|der|pkcs12&password=xxx
    """
    format = request.args.get('format', 'pem')
    password = request.args.get('password')
    
    try:
        cert_bytes = CertificateService.export_certificate(
            cert_id=cert_id,
            format=format,
            password=password
        )
        
        # Determine mimetype and extension
        if format == 'pem':
            mimetype = 'application/x-pem-file'
            extension = 'pem'
        elif format == 'der':
            mimetype = 'application/x-x509-user-cert'
            extension = 'crt'
        elif format == 'pkcs12':
            mimetype = 'application/x-pkcs12'
            extension = 'p12'
        else:
            return jsonify({"error": "Invalid format"}), 400
        
        return send_file(
            BytesIO(cert_bytes),
            mimetype=mimetype,
            as_attachment=True,
            download_name=f'certificate_{cert_id}.{extension}'
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Export failed: {str(e)}"}), 500


@cert_bp.route('/<int:cert_id>', methods=['DELETE'])
@jwt_required()
@operator_required
def delete_certificate(cert_id):
    """
    Delete certificate by ID
    ---
    DELETE /api/v1/certificates/<id>
    """
    identity = get_jwt_identity()
    user = User.query.get(int(identity))
    
    try:
        if CertificateService.delete_certificate(cert_id, user.username):
            return jsonify({"message": "Certificate deleted successfully"}), 200
        else:
            return jsonify({"error": "Certificate not found"}), 404
    except Exception as e:
        return jsonify({"error": f"Failed to delete certificate: {str(e)}"}), 500


@cert_bp.route('/by-refid/<string:refid>', methods=['DELETE'])
@jwt_required()
@operator_required
def delete_certificate_by_refid(refid):
    """
    Delete certificate by refid
    ---
    DELETE /api/v1/certificates/by-refid/<refid>
    """
    from models import Certificate
    identity = get_jwt_identity()
    user = User.query.get(int(identity))
    
    try:
        cert = Certificate.query.filter_by(refid=refid).first()
        if not cert:
            return jsonify({"error": "Certificate not found"}), 404
        
        if CertificateService.delete_certificate(cert.id, user.username):
            return jsonify({"message": "Certificate deleted successfully"}), 200
        else:
            return jsonify({"error": "Failed to delete certificate"}), 500
    except Exception as e:
        return jsonify({"error": f"Failed to delete certificate: {str(e)}"}), 500


@cert_bp.route('/by-refid/<string:refid>/revoke', methods=['POST'])
@jwt_required()
@operator_required
def revoke_certificate_by_refid(refid):
    """
    Revoke certificate by refid
    ---
    POST /api/v1/certificates/by-refid/<refid>/revoke
    {
        "reason": "compromised"
    }
    """
    from models import Certificate
    data = request.get_json() or {}
    identity = get_jwt_identity()
    user = User.query.get(int(identity))
    
    try:
        cert = Certificate.query.filter_by(refid=refid).first()
        if not cert:
            return jsonify({"error": "Certificate not found"}), 404
        
        cert = CertificateService.revoke_certificate(
            cert_id=cert.id,
            reason=data.get('reason', 'unspecified'),
            username=user.username
        )
        return jsonify(cert.to_dict()), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to revoke certificate: {str(e)}"}), 500




@cert_bp.route('/<int:cert_id>/private', methods=['GET'])
@jwt_required()
def get_certificate_private_data(cert_id):
    """
    Get certificate with private key (ADMIN ONLY - for system operations)
    ---
    GET /api/v1/certificates/<id>/private
    
    Returns certificate PEM and private key PEM for system operations
    like configuring HTTPS. Admin only for security.
    """
    from middleware.auth_middleware import admin_required
    from models import Certificate, CA
    import base64
    
    identity = get_jwt_identity()
    user = User.query.get(identity)
    
    # Admin only
    if user.role != 'admin':
        return jsonify({"error": "Admin access required"}), 403
    
    cert = Certificate.query.get(cert_id)
    if not cert:
        return jsonify({"error": "Certificate not found"}), 404
    
    if not cert.crt:
        return jsonify({"error": "Certificate not issued yet"}), 400
    
    # Decode certificate
    try:
        cert_pem = base64.b64decode(cert.crt).decode('utf-8')
    except:
        return jsonify({"error": "Invalid certificate data"}), 500
    
    # Decode private key if exists
    key_pem = None
    if cert.prv:
        try:
            key_pem = base64.b64decode(cert.prv).decode('utf-8')
        except:
            pass
    
    # Get CA chain if available
    ca_chain_pem = None
    if cert.caref:
        ca = CA.query.filter_by(refid=cert.caref).first()
        if ca and ca.crt:
            try:
                ca_chain_pem = base64.b64decode(ca.crt).decode('utf-8')
            except:
                pass
    
    return jsonify({
        "id": cert.id,
        "descr": cert.descr,
        "certificate_pem": cert_pem,
        "private_key_pem": key_pem,
        "ca_chain_pem": ca_chain_pem,
        "has_private_key": key_pem is not None
    }), 200


@cert_bp.route('/<int:cert_id>/fingerprints', methods=['GET'])
@jwt_required()
def get_certificate_fingerprints(cert_id):
    """
    Get certificate fingerprints
    ---
    GET /api/v1/certificates/<id>/fingerprints
    """
    try:
        fingerprints = CertificateService.get_certificate_fingerprints(cert_id)
        return jsonify(fingerprints), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": f"Failed to get fingerprints: {str(e)}"}), 500


@cert_bp.route('/<int:cert_id>/details', methods=['GET'])
@jwt_required()
def get_certificate_details(cert_id):
    """
    Get detailed certificate information
    ---
    GET /api/v1/certificates/<id>/details
    """
    try:
        details = CertificateService.get_certificate_details(cert_id)
        return jsonify(details), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": f"Failed to get details: {str(e)}"}), 500


@cert_bp.route('/<int:cert_id>/export/advanced', methods=['GET'])
@jwt_required()
def export_certificate_advanced(cert_id):
    """
    Export certificate with advanced options
    ---
    GET /api/v1/certificates/<id>/export/advanced?format=pem|der|pkcs12&key=true&chain=true&password=xxx
    """
    export_format = request.args.get('format', 'pem')
    include_key = request.args.get('key', 'false').lower() == 'true'
    include_chain = request.args.get('chain', 'false').lower() == 'true'
    password = request.args.get('password')
    
    try:
        cert_bytes = CertificateService.export_certificate_with_options(
            cert_id=cert_id,
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
            mimetype = 'application/x-x509-user-cert'
            extension = 'crt'
        else:
            mimetype = 'application/x-pem-file'
            extension = 'pem'
        
        return send_file(
            BytesIO(cert_bytes),
            mimetype=mimetype,
            as_attachment=True,
            download_name=f'certificate_{cert_id}.{extension}'
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Export failed: {str(e)}"}), 500


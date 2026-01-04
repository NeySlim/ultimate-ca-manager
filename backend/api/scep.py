"""
SCEP API - Simple Certificate Enrollment Protocol
RFC 8894 Implementation
"""
from flask import Blueprint, request, jsonify, Response
from flask_jwt_extended import jwt_required

from models import db, SystemConfig, SCEPRequest
from services.scep_service import SCEPService

scep_bp = Blueprint('scep', __name__)


def get_scep_config():
    """Get SCEP configuration from system config"""
    config = SystemConfig.query.filter_by(key="scep_config").first()
    if not config:
        return None
    
    import json
    return json.loads(config.value)


def get_scep_service():
    """Get configured SCEP service instance"""
    config = get_scep_config()
    if not config or not config.get('enabled'):
        return None
    
    return SCEPService(
        ca_refid=config['ca_refid'],
        challenge_password=config.get('challenge_password'),
        auto_approve=config.get('auto_approve', False)
    )


@scep_bp.route('/pkiclient.exe', methods=['GET', 'POST'])
def scep_endpoint():
    """
    SCEP protocol endpoint
    GET: GetCACert, GetCACaps
    POST: PKCSReq, GetCRL
    """
    operation = request.args.get('operation', '')
    
    # Get SCEP service
    service = get_scep_service()
    if not service:
        return jsonify({"error": "SCEP not configured"}), 503
    
    if request.method == 'GET':
        if operation == 'GetCACert':
            # Return CA certificate in DER format
            try:
                cert_der = service.get_ca_cert()
                return Response(cert_der, mimetype='application/x-x509-ca-cert')
            except Exception as e:
                return jsonify({"error": str(e)}), 500
        
        elif operation == 'GetCACaps':
            # Return CA capabilities as plaintext
            try:
                caps = service.get_ca_caps()
                return Response(caps, mimetype='text/plain')
            except Exception as e:
                return jsonify({"error": str(e)}), 500
    
    elif request.method == 'POST':
        if operation == 'PKCSReq':
            # Process PKCS#7 enrollment request
            try:
                pkcs7_data = request.data
                client_ip = request.remote_addr
                
                response_data, status_code = service.process_pkcs_req(
                    pkcs7_data, client_ip
                )
                
                return Response(
                    response_data,
                    mimetype='application/x-pki-message',
                    status=status_code
                )
            except Exception as e:
                import traceback
                traceback.print_exc()
                return jsonify({"error": str(e)}), 500
        
        elif operation == 'GetCRL':
            # TODO: Implement CRL retrieval
            return jsonify({"error": "GetCRL not yet implemented"}), 501
    
    return jsonify({"error": "Invalid operation"}), 400


# Management API for SCEP configuration and pending requests

@scep_bp.route('/config', methods=['GET', 'PUT'])
@jwt_required()
def scep_config():
    """Get or update SCEP configuration"""
    if request.method == 'GET':
        config = get_scep_config()
        if not config:
            return jsonify({
                "enabled": False,
                "ca_refid": None,
                "challenge_password": None,
                "auto_approve": False
            })
        return jsonify(config)
    
    else:  # PUT
        data = request.get_json()
        
        # Validate CA exists if provided
        if data.get('ca_refid'):
            from models import CA
            ca = CA.query.filter_by(refid=data['ca_refid']).first()
            if not ca:
                return jsonify({"error": "CA not found"}), 404
        
        # Save configuration
        import json
        config = SystemConfig.query.filter_by(key="scep_config").first()
        if not config:
            config = SystemConfig(key="scep_config")
            db.session.add(config)
        
        config.value = json.dumps({
            "enabled": data.get('enabled', False),
            "ca_refid": data.get('ca_refid'),
            "challenge_password": data.get('challenge_password'),
            "auto_approve": data.get('auto_approve', False)
        })
        db.session.commit()
        
        return jsonify({"message": "SCEP configuration updated"})


@scep_bp.route('/requests', methods=['GET'])
@jwt_required()
def list_scep_requests():
    """List all SCEP enrollment requests"""
    requests = SCEPRequest.query.order_by(SCEPRequest.created_at.desc()).all()
    return jsonify([req.to_dict() for req in requests])


@scep_bp.route('/requests/<transaction_id>', methods=['GET'])
@jwt_required()
def get_scep_request(transaction_id):
    """Get details of a specific SCEP request"""
    req = SCEPRequest.query.filter_by(transaction_id=transaction_id).first()
    if not req:
        return jsonify({"error": "Request not found"}), 404
    
    # Include CSR in response
    result = req.to_dict()
    result['csr'] = req.csr
    return jsonify(result)


@scep_bp.route('/requests/<transaction_id>/approve', methods=['POST'])
@jwt_required()
def approve_scep_request(transaction_id):
    """Approve a pending SCEP request"""
    from flask_jwt_extended import get_jwt_identity
    
    data = request.get_json() or {}
    validity_days = data.get('validity_days', 365)
    
    service = get_scep_service()
    if not service:
        return jsonify({"error": "SCEP not configured"}), 503
    
    user_id = get_jwt_identity()
    cert_refid = service.approve_request(
        transaction_id,
        approved_by=f"user_{user_id}",
        validity_days=validity_days
    )
    
    if not cert_refid:
        return jsonify({"error": "Request not found or already processed"}), 404
    
    return jsonify({
        "message": "Request approved",
        "cert_refid": cert_refid
    })


@scep_bp.route('/requests/<transaction_id>/reject', methods=['POST'])
@jwt_required()
def reject_scep_request(transaction_id):
    """Reject a pending SCEP request"""
    data = request.get_json() or {}
    reason = data.get('reason', 'Rejected by administrator')
    
    service = get_scep_service()
    if not service:
        return jsonify({"error": "SCEP not configured"}), 503
    
    success = service.reject_request(transaction_id, reason)
    
    if not success:
        return jsonify({"error": "Request not found or already processed"}), 404
    
    return jsonify({"message": "Request rejected"})

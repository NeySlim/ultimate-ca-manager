"""
SCEP API - Simple Certificate Enrollment Protocol
Placeholder - Full implementation in Phase 3
"""
from flask import Blueprint, request, jsonify

scep_bp = Blueprint('scep', __name__)


@scep_bp.route('/pkiclient.exe', methods=['GET', 'POST'])
def scep_endpoint():
    """
    SCEP endpoint
    GET: GetCACert, GetCACaps
    POST: PKCSReq, GetCRL, RenewalReq
    """
    operation = request.args.get('operation', '')
    
    if request.method == 'GET':
        if operation == 'GetCACert':
            # TODO: Implement in Phase 3
            return jsonify({"message": "Not yet implemented"}), 501
        elif operation == 'GetCACaps':
            # TODO: Implement in Phase 3
            return jsonify({"message": "Not yet implemented"}), 501
    
    elif request.method == 'POST':
        if operation == 'PKCSReq':
            # TODO: Implement in Phase 3
            return jsonify({"message": "Not yet implemented"}), 501
        elif operation == 'GetCRL':
            # TODO: Implement in Phase 3
            return jsonify({"message": "Not yet implemented"}), 501
    
    return jsonify({"error": "Invalid operation"}), 400

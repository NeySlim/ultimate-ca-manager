"""
CRL API - Certificate Revocation List Management
Placeholder - Full implementation in next phase
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from middleware.auth_middleware import operator_required

crl_bp = Blueprint('crl', __name__)


@crl_bp.route('/', methods=['GET'])
@jwt_required()
def list_crls():
    """List all CRLs"""
    # TODO: Implement in Phase 2
    return jsonify([]), 200


@crl_bp.route('/', methods=['POST'])
@jwt_required()
@operator_required
def create_crl():
    """Create new CRL"""
    # TODO: Implement in Phase 2
    return jsonify({"message": "Not yet implemented"}), 501

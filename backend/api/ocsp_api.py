"""
OCSP API Endpoints (Authenticated)
Management and statistics for OCSP
"""
import logging
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required
from models import db, CA, OCSPResponse

logger = logging.getLogger(__name__)

ocsp_api_bp = Blueprint('ocsp_api', __name__)


@ocsp_api_bp.route('/stats', methods=['GET'])
@jwt_required()
def get_ocsp_stats():
    """
    Get OCSP statistics
    ---
    GET /api/v1/ocsp/stats
    """
    try:
        # Count CAs with OCSP enabled
        ocsp_enabled_cas = CA.query.filter_by(ocsp_enabled=True).count()
        
        # Count cached responses
        cached_responses = OCSPResponse.query.count()
        
        # Count by status
        good_count = OCSPResponse.query.filter_by(status='good').count()
        revoked_count = OCSPResponse.query.filter_by(status='revoked').count()
        unknown_count = OCSPResponse.query.filter_by(status='unknown').count()
        
        # Check if requesting specific stat via hx-select
        from flask import request
        if request.headers.get('HX-Request'):
            # Return HTML fragments for HTMX
            return f'''
            <span class="ocsp-enabled-count">{ocsp_enabled_cas}</span>
            <span class="cached-responses-count">{cached_responses}</span>
            '''
        
        # Return full JSON for regular requests
        return jsonify({
            'ocsp_enabled_cas': ocsp_enabled_cas,
            'cached_responses': cached_responses,
            'responses_by_status': {
                'good': good_count,
                'revoked': revoked_count,
                'unknown': unknown_count
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting OCSP stats: {e}")
        return jsonify({'error': str(e)}), 500


@ocsp_api_bp.route('/cache/cleanup', methods=['POST'])
@jwt_required()
def cleanup_cache():
    """
    Clean up expired OCSP responses
    ---
    POST /api/v1/ocsp/cache/cleanup
    """
    try:
        from services.ocsp_service import OCSPService
        
        ocsp_service = OCSPService()
        ocsp_service.cleanup_expired_responses()
        
        return jsonify({'message': 'Cache cleanup completed'}), 200
        
    except Exception as e:
        logger.error(f"Error cleaning up OCSP cache: {e}")
        return jsonify({'error': str(e)}), 500

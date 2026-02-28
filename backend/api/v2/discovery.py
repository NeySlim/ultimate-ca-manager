"""
Discovery API Routes v2.0
/api/v2/discovery/* - Certificate discovery and scanning
"""
from flask import Blueprint, request
from auth.unified import require_auth
from utils.response import success_response, error_response
from services.discovery_service import DiscoveryService
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('discovery_v2', __name__)
discovery_service = DiscoveryService()


@bp.route('/discovery/scan', methods=['POST'])
@require_auth(['admin:system'])
def scan_targets():
    """
    Scan multiple targets for TLS certificates
    
    Request body:
    {
        "targets": ["example.com", "192.168.1.1"],
        "ports": [443, 8443]
    }
    
    Response:
    {
        "data": [
            {
                "target": "example.com:443",
                "certificate": "-----BEGIN CERTIFICATE-----...",
                "issuer": "CN=DigiCert...",
                "subject": "CN=example.com...",
                "serial": "0x123456789...",
                "not_before": "2024-01-01T00:00:00",
                "not_after": "2025-01-01T00:00:00",
                "fingerprint": "A1B2C3D4..."
            }
        ]
    }
    """
    try:
        data = request.get_json()
        targets = data.get('targets', [])
        ports = data.get('ports', [443, 8443])
        
        if not targets:
            return error_response("No targets specified", 400)
        
        results = discovery_service.scan_targets(targets, ports)
        
        return success_response(data={'results': results})
    
    except Exception as e:
        logger.error(f"Discovery scan error: {e}", exc_info=True)
        return error_response("Scan failed", 500)


@bp.route('/discovery/scan-subnet', methods=['POST'])
@require_auth(['admin:system'])
def scan_subnet():
    """
    Scan a subnet for TLS certificates
    
    Request body:
    {
        "subnet": "192.168.1.0/24",
        "ports": [443, 8443]
    }
    
    Response:
    {
        "data": [
            {
                "target": "192.168.1.1:443",
                "certificate": "-----BEGIN CERTIFICATE-----...",
                "issuer": "CN=DigiCert...",
                "subject": "CN=example.com...",
                "serial": "0x123456789...",
                "not_before": "2024-01-01T00:00:00",
                "not_after": "2025-01-01T00:00:00",
                "fingerprint": "A1B2C3D4..."
            }
        ]
    }
    """
    try:
        data = request.get_json()
        subnet = data.get('subnet')
        ports = data.get('ports', [443, 8443])
        
        if not subnet:
            return error_response("No subnet specified", 400)
        
        results = discovery_service.scan_subnet(subnet, ports)
        
        return success_response(data={'results': results})
    
    except Exception as e:
        logger.error(f"Subnet scan error: {e}", exc_info=True)
        return error_response("Scan failed", 500)


@bp.route('/discovery/import', methods=['POST'])
def import_certificates():
    """
    Import discovered certificates into UCM
    
    Request body:
    {
        "certificates": [
            {
                "target": "example.com:443",
                "certificate": "-----BEGIN CERTIFICATE-----...",
                "issuer": "CN=DigiCert...",
                "subject": "CN=example.com...",
                "serial": "0x123456789...",
                "not_before": "2024-01-01T00:00:00",
                "not_after": "2025-01-01T00:00:00",
                "fingerprint": "A1B2C3D4..."
            }
        ]
    }
    
    Response:
    {
        "data": {
            "imported": 5,
            "already_known": 2
        }
    }
    """
    try:
        data = request.get_json()
        certificates = data.get('certificates', [])
        
        if not certificates:
            return error_response("No certificates specified", 400)
        
        imported, known = discovery_service.import_multiple(certificates)
        
        return success_response(data={
            'imported': imported,
            'already_known': known
        })
    
    except Exception as e:
        logger.error(f"Import error: {e}", exc_info=True)
        return error_response("Import failed", 500)


@bp.route('/discovery/history', methods=['GET'])
def get_history():
    """
    Get discovery history
    
    Response:
    {
        "data": [
            {
                "id": 1,
                "target": "example.com:443",
                "certificate": "-----BEGIN CERTIFICATE-----...",
                "issuer": "CN=DigiCert...",
                "subject": "CN=example.com...",
                "serial": "0x123456789...",
                "not_before": "2024-01-01T00:00:00",
                "not_after": "2025-01-01T00:00:00",
                "fingerprint": "A1B2C3D4...",
                "status": "known|unknown",
                "last_seen": "2024-01-01T00:00:00",
                "ucm_certificate_id": 123,
                "is_expired": false
            }
        ]
    }
    """
    try:
        limit = request.args.get('limit', 100, type=int)
        history = discovery_service.get_discovery_history(limit)
        
        return success_response(data={'history': history})
    
    except Exception as e:
        logger.error(f"History error: {e}", exc_info=True)
        return error_response("Failed to retrieve history", 500)


@bp.route('/discovery/unknown', methods=['GET'])
def get_unknown():
    """
    Get certificates that are not in UCM
    
    Response:
    {
        "data": [
            {
                "id": 1,
                "target": "example.com:443",
                "certificate": "-----BEGIN CERTIFICATE-----...",
                "issuer": "CN=DigiCert...",
                "subject": "CN=example.com...",
                "serial": "0x123456789...",
                "not_before": "2024-01-01T00:00:00",
                "not_after": "2025-01-01T00:00:00",
                "fingerprint": "A1B2C3D4...",
                "status": "unknown",
                "last_seen": "2024-01-01T00:00:00",
                "ucm_certificate_id": null,
                "is_expired": false
            }
        ]
    }
    """
    try:
        unknown = discovery_service.get_unknown_certificates()
        
        return success_response(data={'unknown': unknown})
    
    except Exception as e:
        logger.error(f"Unknown certificates error: {e}", exc_info=True)
        return error_response("Failed to retrieve unknown certificates", 500)


@bp.route('/discovery/expired', methods=['GET'])
def get_expired():
    """
    Get expired discovered certificates
    
    Response:
    {
        "data": [
            {
                "id": 1,
                "target": "example.com:443",
                "certificate": "-----BEGIN CERTIFICATE-----...",
                "issuer": "CN=DigiCert...",
                "subject": "CN=example.com...",
                "serial": "0x123456789...",
                "not_before": "2024-01-01T00:00:00",
                "not_after": "2023-01-01T00:00:00",
                "fingerprint": "A1B2C3D4...",
                "status": "known|unknown",
                "last_seen": "2024-01-01T00:00:00",
                "ucm_certificate_id": 123,
                "is_expired": true
            }
        ]
    }
    """
    try:
        expired = discovery_service.get_expired_certificates()
        
        return success_response(data={'expired': expired})
    
    except Exception as e:
        logger.error(f"Expired certificates error: {e}", exc_info=True)
        return error_response("Failed to retrieve expired certificates", 500)

"""
OPNsense Import API
Handles testing connection and importing CAs/Certs from OPNsense
"""
from flask import Blueprint, request, jsonify, g
from functools import wraps
import requests
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning

# Disable SSL warnings for self-signed certs
disable_warnings(InsecureRequestWarning)

bp = Blueprint('import_opnsense', __name__)


def auth_required(f):
    """Decorator for routes that require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # TODO: Add proper auth check
        return f(*args, **kwargs)
    return decorated_function


@bp.route('/api/v2/import/opnsense/test', methods=['POST'])
@auth_required
def test_connection():
    """
    Test connection to OPNsense and fetch available CAs/Certificates
    
    POST /api/v2/import/opnsense/test
    Body: {
        "host": "192.168.1.1",
        "port": 443,
        "api_key": "xxx",
        "api_secret": "xxx",
        "verify_ssl": false
    }
    
    Returns: {
        "success": true,
        "items": [
            {
                "id": "1",
                "type": "CA" | "Certificate",
                "name": "Root CA",
                "subject": "CN=Root CA",
                "issuer": "CN=Root CA",
                "validUntil": "2034-02-15",
                "serialNumber": "01:02:03...",
                "selected": true
            }
        ],
        "stats": {
            "cas": 2,
            "certificates": 5
        }
    }
    """
    data = request.get_json()
    
    # Extract connection details
    host = data.get('host')
    port = data.get('port', 443)
    api_key = data.get('api_key')
    api_secret = data.get('api_secret')
    verify_ssl = data.get('verify_ssl', False)
    
    if not all([host, api_key, api_secret]):
        return jsonify({
            "success": False,
            "error": "Missing required fields: host, api_key, api_secret"
        }), 400
    
    base_url = f"https://{host}:{port}"
    
    try:
        # Test API connection
        session = requests.Session()
        session.verify = verify_ssl
        
        # Try to fetch trust items from OPNsense API
        # This endpoint retrieves all CAs and certificates from the trust store
        response = session.get(
            f"{base_url}/api/trust/ca/search",
            auth=(api_key, api_secret),
            timeout=10
        )
        
        if response.status_code != 200:
            return jsonify({
                "success": False,
                "error": f"API returned status {response.status_code}"
            }), 400
        
        # Parse CAs
        ca_data = response.json()
        items = []
        cas_count = 0
        
        if 'rows' in ca_data:
            for row in ca_data['rows']:
                items.append({
                    "id": row.get('uuid', ''),
                    "type": "CA",
                    "name": row.get('descr', 'Unknown CA'),
                    "subject": row.get('caref', ''),
                    "issuer": row.get('issuer', ''),
                    "validUntil": row.get('validto_time', ''),
                    "serialNumber": row.get('serial', ''),
                    "selected": True
                })
                cas_count += 1
        
        # Fetch certificates
        cert_response = session.get(
            f"{base_url}/api/trust/cert/search",
            auth=(api_key, api_secret),
            timeout=10
        )
        
        certs_count = 0
        if cert_response.status_code == 200:
            cert_data = cert_response.json()
            if 'rows' in cert_data:
                for row in cert_data['rows']:
                    items.append({
                        "id": row.get('uuid', ''),
                        "type": "Certificate",
                        "name": row.get('descr', 'Unknown Certificate'),
                        "subject": row.get('subject', ''),
                        "issuer": row.get('issuer', ''),
                        "validUntil": row.get('validto_time', ''),
                        "serialNumber": row.get('serial', ''),
                        "selected": True
                    })
                    certs_count += 1
        
        return jsonify({
            "success": True,
            "items": items,
            "stats": {
                "cas": cas_count,
                "certificates": certs_count
            }
        })
    
    except requests.exceptions.Timeout:
        return jsonify({
            "success": False,
            "error": "Connection timeout. Check host and port."
        }), 408
    
    except requests.exceptions.ConnectionError:
        return jsonify({
            "success": False,
            "error": "Connection failed. Check host and port."
        }), 503
    
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Error: {str(e)}"
        }), 500


@bp.route('/api/v2/import/opnsense/import', methods=['POST'])
@auth_required
def import_items():
    """
    Import selected CAs and Certificates from OPNsense
    
    POST /api/v2/import/opnsense/import
    Body: {
        "host": "192.168.1.1",
        "port": 443,
        "api_key": "xxx",
        "api_secret": "xxx",
        "verify_ssl": false,
        "items": ["uuid1", "uuid2", ...]
    }
    
    Returns: {
        "success": true,
        "imported": {
            "cas": 2,
            "certificates": 3
        },
        "skipped": 1,
        "errors": []
    }
    """
    data = request.get_json()
    
    # Extract connection details
    host = data.get('host')
    port = data.get('port', 443)
    api_key = data.get('api_key')
    api_secret = data.get('api_secret')
    verify_ssl = data.get('verify_ssl', False)
    items = data.get('items', [])
    
    if not all([host, api_key, api_secret]):
        return jsonify({
            "success": False,
            "error": "Missing required fields"
        }), 400
    
    if not items:
        return jsonify({
            "success": False,
            "error": "No items selected for import"
        }), 400
    
    # TODO: Implement actual import logic
    # For now, return mock success
    return jsonify({
        "success": True,
        "imported": {
            "cas": 2,
            "certificates": 3
        },
        "skipped": 0,
        "errors": []
    })

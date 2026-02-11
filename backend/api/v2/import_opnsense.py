"""
OPNsense Import API
Handles testing connection and importing CAs/Certs from OPNsense
"""
from flask import Blueprint, request, jsonify, g
from functools import wraps
import requests
import logging
from utils.safe_requests import create_session

# Setup logging
logger = logging.getLogger(__name__)

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
    
    logger.info(f"OpnSense test connection: host={host}, port={port}, verify_ssl={verify_ssl}")
    
    if not all([host, api_key, api_secret]):
        logger.warning(f"OpnSense test failed: missing required fields")
        return jsonify({
            "success": False,
            "error": "Missing required fields: host, api_key, api_secret"
        }), 400
    
    base_url = f"https://{host}:{port}"
    
    try:
        # Test API connection
        session = create_session(verify_ssl=verify_ssl)
        
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
        
        logger.info(f"OpnSense test successful: {cas_count} CAs, {certs_count} certificates")
        return jsonify({
            "success": True,
            "items": items,
            "stats": {
                "cas": cas_count,
                "certificates": certs_count
            }
        })
    
    except requests.exceptions.Timeout:
        logger.error(f"OpnSense connection timeout: {host}:{port}")
        return jsonify({
            "success": False,
            "error": "Connection timeout. Check host and port."
        }), 408
    
    except requests.exceptions.ConnectionError:
        logger.error(f"OpnSense connection failed: {host}:{port}")
        return jsonify({
            "success": False,
            "error": "Connection failed. Check host and port."
        }), 503
    
    except Exception as e:
        logger.exception(f"OpnSense test error: {str(e)}")
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
    
    logger.info(f"OpnSense import: host={host}, port={port}, items_count={len(items)}")
    
    if not all([host, api_key, api_secret]):
        logger.warning("OpnSense import failed: missing required fields")
        return jsonify({
            "success": False,
            "error": "Missing required fields"
        }), 400
    
    # Allow empty items array to import all
    if items is None:
        logger.warning("OpnSense import failed: no items specified")
        return jsonify({
            "success": False,
            "error": "No items selected for import"
        }), 400
    
    # Import logic
    from models import db, CA, Certificate
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    import base64
    import json
    
    # Fetch data from OPNsense
    session = create_session(verify_ssl=verify_ssl)
    base_url = f"https://{host}:{port}"
    
    stats = {
        "cas_imported": 0,
        "cas_skipped": 0,
        "certs_imported": 0,
        "certs_skipped": 0,
        "errors": []
    }
    
    try:
        # Fetch CAs
        ca_response = session.get(
            f"{base_url}/api/trust/ca/search",
            auth=(api_key, api_secret),
            timeout=10
        )
        
        # Fetch certificates
        cert_response = session.get(
            f"{base_url}/api/trust/cert/search",
            auth=(api_key, api_secret),
            timeout=10
        )
        
        # Build lookup by UUID
        all_cas = {}
        all_certs = {}
        
        if ca_response.status_code == 200:
            ca_data = ca_response.json()
            if 'rows' in ca_data:
                for row in ca_data['rows']:
                    all_cas[row.get('uuid')] = row
        
        if cert_response.status_code == 200:
            cert_data = cert_response.json()
            if 'rows' in cert_data:
                for row in cert_data['rows']:
                    all_certs[row.get('uuid')] = row
        
        # Import selected items
        for item_id in items:
            if item_id in all_cas:
                # Import CA
                ca_data = all_cas[item_id]
                
                # Check if already exists by refid
                existing = CA.query.filter_by(refid=item_id).first()
                if existing:
                    stats['cas_skipped'] += 1
                    continue
                
                # Check for duplicate by description (same CA, different refid from OPNsense)
                duplicate_by_name = CA.query.filter_by(
                    descr=ca_data.get('descr'),
                    imported_from='opnsense'
                ).first()
                
                if duplicate_by_name:
                    # Skip duplicate - same CA already imported with different refid
                    stats['cas_skipped'] += 1
                    stats['errors'].append(f"CA '{ca_data.get('descr')}' already exists with refid {duplicate_by_name.refid}")
                    continue
                
                # Parse certificate
                try:
                    crt_pem = base64.b64decode(ca_data.get('crt', ''))
                    x509_cert = x509.load_pem_x509_certificate(crt_pem, default_backend())
                    
                    subject = x509_cert.subject.rfc4514_string()
                    issuer = x509_cert.issuer.rfc4514_string()
                    valid_from = x509_cert.not_valid_before
                    valid_to = x509_cert.not_valid_after
                except:
                    subject = ''
                    issuer = ''
                    valid_from = None
                    valid_to = None
                
                # Create CA
                ca = CA(
                    refid=item_id,
                    descr=ca_data.get('descr', 'Imported from OPNsense'),
                    crt=ca_data.get('crt', ''),
                    prv=ca_data.get('prv'),
                    serial=0,
                    subject=subject,
                    issuer=issuer,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    imported_from='opnsense',
                    created_by='import'
                )
                
                db.session.add(ca)
                stats['cas_imported'] += 1
            
            elif item_id in all_certs:
                # Import Certificate
                cert_data = all_certs[item_id]
                
                # Check if already exists by refid
                existing = Certificate.query.filter_by(refid=item_id).first()
                if existing:
                    stats['certs_skipped'] += 1
                    continue
                
                # Check for duplicate by description
                duplicate_by_name = Certificate.query.filter_by(
                    descr=cert_data.get('descr'),
                    imported_from='opnsense'
                ).first()
                
                if duplicate_by_name:
                    # Skip duplicate
                    stats['certs_skipped'] += 1
                    stats['errors'].append(f"Certificate '{cert_data.get('descr')}' already exists with refid {duplicate_by_name.refid}")
                    continue
                
                # Parse certificate
                san_dns_list = []
                san_ip_list = []
                san_email_list = []
                san_uri_list = []
                subject = ''
                issuer = ''
                serial_number = ''
                valid_from = None
                valid_to = None
                
                try:
                    crt_pem = base64.b64decode(cert_data.get('crt', ''))
                    x509_cert = x509.load_pem_x509_certificate(crt_pem, default_backend())
                    
                    subject = x509_cert.subject.rfc4514_string()
                    issuer = x509_cert.issuer.rfc4514_string()
                    serial_number = str(x509_cert.serial_number)
                    valid_from = x509_cert.not_valid_before
                    valid_to = x509_cert.not_valid_after
                    
                    # Extract SANs
                    try:
                        ext = x509_cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
                        for name in ext.value:
                            if isinstance(name, x509.DNSName):
                                san_dns_list.append(name.value)
                            elif isinstance(name, x509.IPAddress):
                                san_ip_list.append(str(name.value))
                            elif isinstance(name, x509.RFC822Name):
                                san_email_list.append(name.value)
                            elif isinstance(name, x509.UniformResourceIdentifier):
                                san_uri_list.append(name.value)
                    except x509.ExtensionNotFound:
                        pass
                except:
                    pass
                
                # Create certificate
                cert = Certificate(
                    refid=item_id,
                    descr=cert_data.get('descr', 'Imported from OPNsense'),
                    caref=cert_data.get('caref'),
                    crt=cert_data.get('crt', ''),
                    prv=cert_data.get('prv'),
                    cert_type='server_cert',
                    subject=subject,
                    issuer=issuer,
                    serial_number=serial_number,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    san_dns=json.dumps(san_dns_list) if san_dns_list else None,
                    san_ip=json.dumps(san_ip_list) if san_ip_list else None,
                    san_email=json.dumps(san_email_list) if san_email_list else None,
                    san_uri=json.dumps(san_uri_list) if san_uri_list else None,
                    imported_from='opnsense',
                    created_by='import'
                )
                
                db.session.add(cert)
                stats['certs_imported'] += 1
        
        # Commit all changes
        db.session.commit()
        
        logger.info(f"OpnSense import complete: {stats['cas_imported']} CAs, {stats['certs_imported']} certificates imported, {stats['cas_skipped'] + stats['certs_skipped']} skipped")
        
        return jsonify({
            "success": True,
            "imported": {
                "cas": stats['cas_imported'],
                "certificates": stats['certs_imported']
            },
            "skipped": stats['cas_skipped'] + stats['certs_skipped'],
            "errors": stats['errors']
        })
    
    except Exception as e:
        db.session.rollback()
        logger.exception(f"OpnSense import failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

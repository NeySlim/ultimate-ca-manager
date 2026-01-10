"""
OPNsense Import API
Generic API for importing Trust data from any OPNsense instance
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

from models import db
from services.opnsense_import import (
    OPNsenseImportService, 
    get_import_config, 
    save_import_config
)

import_bp = Blueprint('import', __name__)


@import_bp.route('/config', methods=['GET', 'PUT', 'DELETE'])
@jwt_required()
def import_config():
    """
    Manage OPNsense import configuration
    
    GET: Retrieve current configuration
    PUT: Save new configuration
    DELETE: Remove configuration
    """
    if request.method == 'GET':
        config = get_import_config()
        if not config:
            return jsonify({
                "configured": False,
                "base_url": None,
                "username": None,
                "verify_ssl": False
            })
        
        # Don't return password in GET
        return jsonify({
            "configured": True,
            "base_url": config.get('base_url'),
            "username": config.get('username'),
            "verify_ssl": config.get('verify_ssl', False)
        })
    
    elif request.method == 'PUT':
        data = request.get_json()
        
        # Validate required fields
        if not data.get('base_url'):
            return jsonify({"error": "base_url is required"}), 400
        
        # Check which auth method is being used
        has_api_keys = data.get('api_key') and data.get('api_secret')
        has_password = data.get('username') and data.get('password')
        
        if not has_api_keys and not has_password:
            return jsonify({"error": "Either api_key/api_secret or username/password is required"}), 400
        
        # Save configuration
        save_import_config(
            base_url=data['base_url'],
            username=data.get('username'),
            password=data.get('password'),
            api_key=data.get('api_key'),
            api_secret=data.get('api_secret'),
            verify_ssl=data.get('verify_ssl', False)
        )
        
        return jsonify({"message": "Configuration saved"})
    
    else:  # DELETE
        from models import SystemConfig
        config = SystemConfig.query.filter_by(key="opnsense_import_config").first()
        if config:
            db.session.delete(config)
            db.session.commit()
        
        return jsonify({"message": "Configuration deleted"})


@import_bp.route('/test-connection', methods=['POST'])
@jwt_required()
def test_connection():
    """
    Test connection to OPNsense instance
    Can use saved config or provide credentials in request
    Supports both username/password and api_key/secret authentication
    """
    import sys
    sys.stderr.write(f"DEBUG test_connection called\n")
    sys.stderr.flush()
    
    data = request.get_json(silent=True) or {}
    sys.stderr.write(f"DEBUG test_connection data: {list(data.keys())}\n")
    sys.stderr.flush()
    
    # Use provided credentials or saved config
    if 'base_url' in data:
        base_url = data['base_url']
        username = data.get('username')
        password = data.get('password')
        api_key = data.get('api_key')
        api_secret = data.get('api_secret')
        verify_ssl = data.get('verify_ssl', False)
        sys.stderr.write(f"DEBUG Using provided credentials: {base_url} (API: {bool(api_key)})\n")
        sys.stderr.flush()
    else:
        config = get_import_config()
        if not config:
            sys.stderr.write(f"DEBUG No config found, returning 400\n")
            sys.stderr.flush()
            return jsonify({"error": "No configuration found"}), 400
        
        base_url = config['base_url']
        username = config.get('username')
        password = config.get('password')
        api_key = config.get('api_key')
        api_secret = config.get('api_secret')
        verify_ssl = config.get('verify_ssl', False)
        sys.stderr.write(f"DEBUG Using saved config: {base_url} (API: {bool(api_key)})\n")
        sys.stderr.flush()
    
    # Test connection
    sys.stderr.write(f"DEBUG Creating service...\n")
    sys.stderr.flush()
    try:
        service = OPNsenseImportService(
            base_url=base_url, 
            username=username, 
            password=password,
            api_key=api_key,
            api_secret=api_secret,
            verify_ssl=verify_ssl
        )
    except ValueError as e:
        sys.stderr.write(f"ERROR Invalid credentials: {str(e)}\n")
        sys.stderr.flush()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
    
    sys.stderr.write(f"DEBUG Testing connection...\n")
    sys.stderr.flush()
    if service.connect():
        sys.stderr.write(f"DEBUG Connection successful!\n")
        sys.stderr.flush()
        return jsonify({
            "success": True,
            "message": "Connected successfully",
            "base_url": base_url
        })
    else:
        sys.stderr.write(f"DEBUG Connection failed\n")
        sys.stderr.flush()
        return jsonify({
            "success": False,
            "error": "Connection failed - check credentials and network"
        }), 400


@import_bp.route('/preview', methods=['POST'])
@jwt_required()
def preview_import():
    """
    Preview what would be imported without actually importing
    Retrieves and parses config.xml to show available items
    """
    data = request.get_json(silent=True) or {}
    
    # Get credentials
    if 'base_url' in data:
        base_url = data['base_url']
        username = data['username']
        password = data['password']
        verify_ssl = data.get('verify_ssl', False)
    else:
        config = get_import_config()
        if not config:
            return jsonify({"error": "No configuration found"}), 400
        
        base_url = config['base_url']
        username = config['username']
        password = config['password']
        verify_ssl = config.get('verify_ssl', False)
    
    # Connect and retrieve config
    service = OPNsenseImportService(base_url, username, password, verify_ssl)
    
    if not service.connect():
        return jsonify({"error": "Failed to connect"}), 400
    
    config_xml = service.get_config_xml()
    if not config_xml:
        return jsonify({"error": "Failed to retrieve configuration"}), 500
    
    # Parse
    trust_data = service.parse_trust_data(config_xml)
    
    # Check which items already exist
    from models import CA, Certificate
    
    cas_preview = []
    for ca in trust_data['cas']:
        existing = CA.query.filter_by(refid=ca['refid']).first()
        cas_preview.append({
            'refid': ca['refid'],
            'descr': ca.get('descr', ''),
            'subject': ca.get('subject', ''),
            'is_root': ca.get('is_root', False),
            'has_private_key': bool(ca.get('prv')),
            'already_exists': existing is not None
        })
    
    certs_preview = []
    for cert in trust_data['certs']:
        existing = Certificate.query.filter_by(refid=cert['refid']).first()
        certs_preview.append({
            'refid': cert['refid'],
            'descr': cert.get('descr', ''),
            'subject': cert.get('subject', ''),
            'caref': cert.get('caref'),
            'type': cert.get('type', 'server_cert'),
            'has_private_key': bool(cert.get('prv')),
            'already_exists': existing is not None
        })
    
    return jsonify({
        "success": True,
        "cas": {
            "total": len(cas_preview),
            "new": len([c for c in cas_preview if not c['already_exists']]),
            "existing": len([c for c in cas_preview if c['already_exists']]),
            "items": cas_preview
        },
        "certs": {
            "total": len(certs_preview),
            "new": len([c for c in certs_preview if not c['already_exists']]),
            "existing": len([c for c in certs_preview if c['already_exists']]),
            "items": certs_preview
        }
    })


@import_bp.route('/execute', methods=['POST'])
@jwt_required()
def execute_import():
    """
    Execute full import from OPNsense
    
    Body params:
        skip_existing: bool (default: true) - Skip items that already exist
        base_url: str (optional) - Override saved config
        username: str (optional) - Override saved config (web auth)
        password: str (optional) - Override saved config (web auth)
        api_key: str (optional) - Override saved config (API auth)
        api_secret: str (optional) - Override saved config (API auth)
        verify_ssl: bool (optional) - Override saved config
    """
    data = request.get_json(silent=True) or {}
    skip_existing = data.get('skip_existing', True)
    
    # Get credentials
    if 'base_url' in data:
        base_url = data['base_url']
        username = data.get('username')
        password = data.get('password')
        api_key = data.get('api_key')
        api_secret = data.get('api_secret')
        verify_ssl = data.get('verify_ssl', False)
    else:
        config = get_import_config()
        if not config:
            return jsonify({"error": "No configuration found"}), 400
        
        base_url = config['base_url']
        username = config.get('username')
        password = config.get('password')
        api_key = config.get('api_key')
        api_secret = config.get('api_secret')
        verify_ssl = config.get('verify_ssl', False)
    
    # Execute import
    try:
        service = OPNsenseImportService(
            base_url=base_url,
            username=username,
            password=password,
            api_key=api_key,
            api_secret=api_secret,
            verify_ssl=verify_ssl
        )
        result = service.full_import(skip_existing=skip_existing)
    except ValueError as e:
        return jsonify({"error": str(e), "success": False}), 400
    except Exception as e:
        import sys
        import traceback
        sys.stderr.write(f"ERROR execute_import: {str(e)}\n")
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        return jsonify({"error": str(e), "success": False}), 500
    
    if result['success']:
        return jsonify(result)
    else:
        return jsonify(result), 500


@import_bp.route('/upload', methods=['POST'])
@jwt_required()
def upload_config():
    """
    Import from uploaded config.xml file
    Useful when automatic retrieval fails
    
    Expects multipart/form-data with:
        file: config.xml file
        skip_existing: bool (default: true)
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    # Read XML content
    try:
        config_xml = file.read().decode('utf-8')
    except Exception as e:
        return jsonify({"error": f"Failed to read file: {str(e)}"}), 400
    
    # Parse and import
    from services.opnsense_import import OPNsenseImportService
    
    # Create a dummy service just for parsing
    service = OPNsenseImportService("http://dummy", "user", "pass")
    
    # Parse
    data = service.parse_trust_data(config_xml)
    
    # Import
    skip_existing = request.form.get('skip_existing', 'true').lower() == 'true'
    
    cas_result = service.import_cas(data['cas'], skip_existing)
    certs_result = service.import_certificates(data['certs'], skip_existing)
    
    return jsonify({
        "success": True,
        "cas": cas_result,
        "certs": certs_result
    })


@import_bp.route('/history', methods=['GET'])
@jwt_required()
def import_history():
    """
    Get list of imported items
    Shows all CAs and certificates that were imported from OPNsense
    """
    from models import CA, Certificate
    
    imported_cas = CA.query.filter_by(imported_from='opnsense').all()
    imported_certs = Certificate.query.filter_by(imported_from='opnsense').all()
    
    return jsonify({
        "cas": {
            "count": len(imported_cas),
            "items": [ca.to_dict(include_private=False) for ca in imported_cas]
        },
        "certs": {
            "count": len(imported_certs),
            "items": [cert.to_dict(include_private=False) for cert in imported_certs]
        }
    })

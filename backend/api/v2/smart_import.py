"""
Smart Import API - Intelligent certificate/key import endpoint

Endpoints:
- POST /api/v2/import/analyze - Analyze content without importing
- POST /api/v2/import/execute - Execute the import
"""

from flask import Blueprint, request, jsonify
from auth.unified import require_auth
from services.smart_import import SmartImporter

bp = Blueprint('smart_import', __name__)


@bp.route('/api/v2/import/analyze', methods=['POST'])
@require_auth(['read:certificates'])
def analyze_import():
    """
    Analyze content for import without actually importing.
    
    Request body:
    {
        "content": "-----BEGIN CERTIFICATE-----...",
        "password": "optional password for encrypted content"
    }
    
    Response:
    {
        "success": true,
        "data": {
            "objects": [...],
            "chains": [...],
            "matching": {...},
            "validation": {...},
            "summary": {...}
        }
    }
    """
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    content = data.get('content')
    if not content:
        return jsonify({"error": "No content to analyze"}), 400
    
    password = data.get('password')
    
    try:
        importer = SmartImporter()
        result = importer.analyze(content, password)
        
        return jsonify({
            "success": True,
            "data": result.to_dict()
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@bp.route('/api/v2/import/execute', methods=['POST'])
@require_auth(['write:certificates'])
def execute_import():
    """
    Execute the smart import.
    
    Request body:
    {
        "content": "-----BEGIN CERTIFICATE-----...",
        "password": "optional password",
        "options": {
            "import_cas": true,
            "import_certs": true,
            "import_csrs": true,
            "skip_duplicates": true,
            "description_prefix": "Imported: "
        }
    }
    
    Response:
    {
        "success": true,
        "data": {
            "certificates_imported": 1,
            "cas_imported": 2,
            "keys_matched": 1,
            "csrs_imported": 0,
            "errors": [],
            "warnings": [],
            "imported_ids": {...}
        }
    }
    """
    from flask import g
    
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    content = data.get('content')
    if not content:
        return jsonify({"error": "No content to import"}), 400
    
    password = data.get('password')
    options = data.get('options', {})
    username = g.current_user.username if hasattr(g, 'current_user') else 'system'
    
    try:
        importer = SmartImporter()
        result = importer.execute(content, password, options, username)
        
        return jsonify({
            "success": result.success,
            "data": result.to_dict()
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@bp.route('/api/v2/import/formats', methods=['GET'])
@require_auth()
def get_supported_formats():
    """
    Get list of supported import formats.
    """
    return jsonify({
        "success": True,
        "data": {
            "formats": [
                {
                    "name": "PEM",
                    "extensions": [".pem", ".crt", ".cer", ".key"],
                    "description": "Base64 encoded with header/footer markers"
                },
                {
                    "name": "DER",
                    "extensions": [".der", ".cer"],
                    "description": "Binary ASN.1 format"
                },
                {
                    "name": "PKCS#12/PFX",
                    "extensions": [".p12", ".pfx"],
                    "description": "Password-protected bundle (cert + key + chain)"
                },
                {
                    "name": "PKCS#7",
                    "extensions": [".p7b", ".p7c"],
                    "description": "Certificate chain without private key"
                }
            ],
            "object_types": [
                {"type": "certificate", "description": "X.509 Certificate"},
                {"type": "private_key", "description": "RSA, EC, or Ed25519 private key"},
                {"type": "csr", "description": "Certificate Signing Request"},
                {"type": "ca", "description": "Certificate Authority (CA certificate)"}
            ],
            "features": [
                "Automatic format detection",
                "Multi-object parsing (cert + key + chain)",
                "Chain reconstruction",
                "Key-to-certificate matching",
                "Duplicate detection",
                "Validation (signatures, dates, chains)"
            ]
        }
    })

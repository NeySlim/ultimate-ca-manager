"""
Smart Import API - Intelligent certificate/key import endpoint

Endpoints:
- POST /api/v2/import/analyze - Analyze content without importing
- POST /api/v2/import/execute - Execute the import
"""

from flask import Blueprint, request, g
from auth.unified import require_auth, has_permission
from fips_mode import FipsRestricted
from services.smart_import import SmartImporter
from services.audit_service import AuditService
from utils.response import success_response, error_response
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('smart_import', __name__)

# The parser runs several full-content regex passes plus per-block crypto
# parsing, so unbounded content is a CPU/memory DoS amplifier even under the
# 50 MB global cap. A real certificate bundle is far smaller; 5 MB matches the
# CSV-upload ceiling and is generous for any legitimate PEM/PKCS12 blob.
MAX_IMPORT_CONTENT_BYTES = 5 * 1024 * 1024


def _content_too_large(content) -> bool:
    """True if content exceeds the smart-import size cap (measured in bytes)."""
    if isinstance(content, str):
        return len(content.encode('utf-8', errors='ignore')) > MAX_IMPORT_CONTENT_BYTES
    return len(content) > MAX_IMPORT_CONTENT_BYTES


@bp.route('/api/v2/import/analyze', methods=['POST'])
@require_auth(['read:certificates'])
def analyze_import():
    """
    Analyze content for import without actually importing.

    Request body: `content` (PEM/PKCS#12/JKS text or base64) and an optional
    `password` for encrypted content.

    Response `data` carries `objects`, `chains`, `matching`, `validation`
    and `summary`.

    Written as prose, without a PEM header or a JSON example. flasgger
    builds /api/docs/apispec.json by treating a run of three dashes in a
    route docstring as the start of a YAML block, and a PEM header is such
    a run. What followed was not a YAML mapping, and the whole served API
    description answered 500. tests/test_one_api_description.py keeps it
    answering 200.
    """
    data = request.get_json()
    
    if not data:
        return error_response("No data provided", 400)
    
    content = data.get('content')
    if not content:
        return error_response("No content to analyze", 400)
    if _content_too_large(content):
        return error_response("Content exceeds maximum import size", 413)

    password = data.get('password')
    
    try:
        importer = SmartImporter()
        result = importer.analyze(content, password)
        
        return success_response(data=result.to_dict())

    except FipsRestricted:
        raise  # the app handler answers 400 with the FIPS problem type
    except Exception as e:
        logger.error(f'Smart import analysis failed: {e}')
        return error_response('Import analysis failed', 500)


@bp.route('/api/v2/import/execute', methods=['POST'])
@require_auth(['write:certificates'])
def execute_import():
    """
    Execute the smart import.

    Request body: `content`, an optional `password`, and `options` with
    `import_cas`, `import_certs`, `import_csrs`, `skip_duplicates` and
    `description_prefix`.

    Response `data` carries the counts (`certificates_imported`,
    `cas_imported`, `keys_matched`, `csrs_imported`), plus `errors`,
    `warnings` and `imported_ids`.

    Prose rather than a JSON example, for the reason given on
    `analyze_import` above.
    """
    data = request.get_json()
    
    if not data:
        return error_response("No data provided", 400)
    
    content = data.get('content')
    if not content:
        return error_response("No content to import", 400)
    if _content_too_large(content):
        return error_response("Content exceeds maximum import size", 413)

    password = data.get('password')
    options = data.get('options', {})
    username = g.current_user.username if hasattr(g, 'current_user') else 'system'

    try:
        importer = SmartImporter()
        import_cas = options.get('import_cas', True)
        if import_cas and not has_permission('write:cas', g.permissions):
            analysis = importer.analyze(content, password)
            if analysis.summary.get('cas', 0) > 0:
                return error_response('write:cas permission required to import CAs', 403)

        result = importer.execute(content, password, options, username)
        
        AuditService.log_action(
            action='smart_import',
            resource_type='import',
            resource_name='Smart Import',
            details=f'Smart import by {username}: {result.to_dict().get("summary", "")}',
            success=result.success
        )
        
        return success_response(data=result.to_dict())

    except FipsRestricted:
        raise  # the app handler answers 400 with the FIPS problem type
    except Exception as e:
        logger.error(f'Smart import execution failed: {e}')
        return error_response('Import execution failed', 500)


@bp.route('/api/v2/import/formats', methods=['GET'])
@require_auth()
def get_supported_formats():
    """
    Get list of supported import formats.
    """
    return success_response(data={
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
    })

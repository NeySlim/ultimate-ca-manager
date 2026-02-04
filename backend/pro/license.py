"""
License API - UCM Pro
Handles license validation and activation with signature verification
"""

from flask import Blueprint, current_app, request
from pathlib import Path
from utils.response import success_response, error_response
from auth.unified import require_auth
import json
import hashlib
import hmac
import base64
from datetime import datetime

bp = Blueprint('license_pro', __name__)

# License signing key (in production, this would be an RSA public key)
# This is used to verify license signatures
LICENSE_PUBLIC_KEY = b'UCM-PRO-LICENSE-SIGNING-KEY-2026'


def verify_license_signature(license_data: dict) -> bool:
    """
    Verify the license signature to prevent tampering.
    Uses HMAC-SHA256 for signature verification.
    """
    signature = license_data.get('signature')
    if not signature:
        return False
    
    # Create payload without signature
    payload = {k: v for k, v in license_data.items() if k != 'signature'}
    payload_str = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    
    # Verify HMAC signature
    expected_sig = hmac.new(
        LICENSE_PUBLIC_KEY,
        payload_str.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected_sig)


def check_license_expiry(license_data: dict) -> bool:
    """Check if license is still valid (not expired)"""
    expires_at = license_data.get('expires_at')
    if not expires_at:
        return True  # No expiry = perpetual
    
    try:
        expiry_date = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
        return datetime.now(expiry_date.tzinfo) < expiry_date
    except:
        return False


@bp.route('/api/v2/license', methods=['GET'])
@require_auth(['read:settings'])
def get_license():
    """Get current license information"""
    license_path = Path('/opt/ucm/data/license.key')
    
    if not license_path.exists():
        return success_response(data={
            'type': 'community',
            'valid': True,
            'features': [],
            'pro_enabled': current_app.config.get('PRO_ENABLED', False)
        })
    
    try:
        license_data = json.loads(license_path.read_text())
        
        # Verify signature
        if not verify_license_signature(license_data):
            current_app.logger.warning("Invalid license signature detected")
            return success_response(data={
                'type': 'invalid',
                'valid': False,
                'error': 'License signature verification failed',
                'pro_enabled': False
            })
        
        # Check expiry
        is_valid = check_license_expiry(license_data)
        
        return success_response(data={
            'type': license_data.get('type', 'pro'),
            'valid': is_valid,
            'features': license_data.get('features', ['groups', 'rbac', 'sso', 'hsm']),
            'expires_at': license_data.get('expires_at'),
            'licensed_to': license_data.get('company'),
            'licensed_email': license_data.get('email'),
            'max_cas': license_data.get('max_cas', 100),
            'max_certs': license_data.get('max_certs', 10000),
            'pro_enabled': is_valid
        })
    except json.JSONDecodeError:
        return success_response(data={
            'type': 'invalid',
            'valid': False,
            'error': 'Invalid license file format',
            'pro_enabled': False
        })
    except Exception as e:
        current_app.logger.error(f"License check error: {e}")
        return success_response(data={
            'type': 'community',
            'valid': True,
            'features': [],
            'error': 'License check failed, running in community mode'
        })


@bp.route('/api/v2/license/activate', methods=['POST'])
@require_auth(['write:settings'])
def activate_license():
    """Activate a license key"""
    data = request.get_json()
    
    if not data or not data.get('license_key'):
        return error_response("License key is required", 400)
    
    license_key = data['license_key'].strip()
    
    try:
        # Decode and parse license (base64 encoded JSON)
        try:
            license_json = base64.b64decode(license_key).decode('utf-8')
            license_data = json.loads(license_json)
        except:
            return error_response("Invalid license key format", 400)
        
        # Verify signature
        if not verify_license_signature(license_data):
            return error_response("Invalid license signature", 400)
        
        # Check expiry
        if not check_license_expiry(license_data):
            return error_response("License has expired", 400)
        
        # Save license
        license_path = Path('/opt/ucm/data/license.key')
        license_path.write_text(json.dumps(license_data, indent=2))
        
        current_app.logger.info(f"License activated for: {license_data.get('company')}")
        
        return success_response(
            data={
                'type': license_data.get('type', 'pro'),
                'licensed_to': license_data.get('company'),
                'features': license_data.get('features', []),
                'expires_at': license_data.get('expires_at')
            },
            message="License activated successfully"
        )
    except Exception as e:
        current_app.logger.error(f"License activation error: {e}")
        return error_response("Failed to activate license", 500)


@bp.route('/api/v2/license/deactivate', methods=['POST'])
@require_auth(['write:settings'])
def deactivate_license():
    """Deactivate current license (revert to community)"""
    license_path = Path('/opt/ucm/data/license.key')
    
    if license_path.exists():
        license_path.unlink()
        current_app.logger.info("License deactivated")
    
    return success_response(message="License deactivated, running in community mode")

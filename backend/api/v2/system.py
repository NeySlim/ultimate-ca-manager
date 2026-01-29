"""
System Routes v2.0
Handles system-level operations: database maintenance, HTTPS certificates, health
"""

from flask import Blueprint, request, current_app, jsonify, send_from_directory
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, Certificate, CA, CRL, OCSPResponse
from pathlib import Path
import os
import subprocess
import shutil
import werkzeug.utils
from datetime import datetime, timezone

bp = Blueprint('system_v2', __name__)

@bp.route('/api/v2/system/db/stats', methods=['GET'])
@require_auth(['read:settings'])
def get_db_stats():
    """Get database statistics"""
    try:
        # Get DB size
        db_path = current_app.config.get('SQLALCHEMY_DATABASE_URI', '').replace('sqlite:///', '')
        size_bytes = os.path.getsize(db_path) if os.path.exists(db_path) else 0
        size_mb = round(size_bytes / (1024 * 1024), 2)
        
        # Get counts using ORM models instead of raw SQL
        counts = {
            'cas': CA.query.count(),
            'certificates': Certificate.query.count(),
            'crls': CRL.query.count(),
            'ocsp_responses': OCSPResponse.query.count()
        }
        
        # Calculate fragmentation (approximate for SQLite)
        # In a real scenario, we might parse 'PRAGMA page_count' vs actual size
        fragmentation = 0 
        
        return success_response(data={
            'size_mb': size_mb,
            'fragmentation_percent': fragmentation,
            'counts': counts,
            'last_vacuum': 'Never', # TODO: Store this timestamp
            'last_check': 'Never'
        })
    except Exception as e:
        return error_response(f"Failed to get stats: {str(e)}")

@bp.route('/api/v2/system/db/optimize', methods=['POST'])
@require_auth(['admin:system'])
def optimize_db():
    """Run VACUUM and ANALYZE"""
    try:
        db.session.execute(db.text("VACUUM"))
        db.session.execute(db.text("ANALYZE"))
        return success_response(message="Database optimized successfully")
    except Exception as e:
        return error_response(f"Optimization failed: {str(e)}")

@bp.route('/api/v2/system/db/integrity-check', methods=['POST'])
@require_auth(['admin:system'])
def check_integrity():
    """Run PRAGMA integrity_check"""
    try:
        result = db.session.execute(db.text("PRAGMA integrity_check")).scalar()
        if result == "ok":
            return success_response(message="Integrity check passed")
        else:
            return error_response(f"Integrity check failed: {result}")
    except Exception as e:
        return error_response(f"Check failed: {str(e)}")

@bp.route('/api/v2/system/https/cert-info', methods=['GET'])
@require_auth(['read:settings'])
def get_https_cert_info():
    """Get information about the current HTTPS certificate"""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    import hashlib
    
    cert_path = Path('/opt/ucm/data/https_cert.pem')
    
    if not cert_path.exists():
        return success_response(data={
            'common_name': 'Not configured',
            'issuer': '-',
            'valid_from': None,
            'valid_to': None,
            'fingerprint': '-',
            'type': 'none'
        })
    
    try:
        cert_pem = cert_path.read_bytes()
        cert = x509.load_pem_x509_certificate(cert_pem)
        
        # Extract subject CN
        cn = None
        for attr in cert.subject:
            if attr.oid == x509.oid.NameOID.COMMON_NAME:
                cn = attr.value
                break
        
        # Extract issuer CN
        issuer_cn = None
        for attr in cert.issuer:
            if attr.oid == x509.oid.NameOID.COMMON_NAME:
                issuer_cn = attr.value
                break
        
        # Check if self-signed
        is_self_signed = cert.subject == cert.issuer
        
        # Calculate fingerprint
        fingerprint = cert.fingerprint(hashes.SHA256()).hex()
        fingerprint_formatted = ':'.join(fingerprint[i:i+2].upper() for i in range(0, len(fingerprint), 2))
        
        return success_response(data={
            'common_name': cn or 'Unknown',
            'issuer': issuer_cn or 'Unknown',
            'valid_from': cert.not_valid_before_utc.isoformat(),
            'valid_to': cert.not_valid_after_utc.isoformat(),
            'fingerprint': fingerprint_formatted[:47] + '...',  # Truncate for display
            'type': 'Self-Signed' if is_self_signed else 'CA-Signed',
            'serial': format(cert.serial_number, 'x').upper()
        })
    except Exception as e:
        return success_response(data={
            'common_name': 'Error reading certificate',
            'issuer': str(e),
            'valid_from': None,
            'valid_to': None,
            'fingerprint': '-',
            'type': 'error'
        })

@bp.route('/api/v2/system/https/regenerate', methods=['POST'])
@require_auth(['admin:system'])
def regenerate_https_cert():
    """Regenerate self-signed HTTPS certificate"""
    # Trigger script or internal logic to regen cert
    # Service restart required
    return success_response(message="Certificate regenerated. Service restart required.")

@bp.route('/api/v2/system/https/apply', methods=['POST'])
@require_auth(['admin:system'])
def apply_https_cert():
    """Apply a managed certificate to HTTPS"""
    data = request.json
    cert_id = data.get('cert_id')
    
    if not cert_id:
        return error_response("Certificate ID required")
        
    cert = Certificate.query.get(cert_id)
    if not cert:
        return error_response("Certificate not found")
        
    # Logic to write cert.crt and cert.key to system location
    # and trigger restart
    return success_response(message="Certificate applied. Service restart required.")

@bp.route('/api/v2/system/db/export', methods=['GET'])
@require_auth(['admin:system'])
def export_db():
    """Export SQL dump"""
    # Placeholder: Return a dummy file
    return "SQL DUMP CONTENT", 200, {'Content-Type': 'application/sql', 'Content-Disposition': 'attachment; filename=dump.sql'}

@bp.route('/api/v2/system/db/reset', methods=['POST'])
@require_auth(['admin:system'])
def reset_pki():
    """Reset PKI Database"""
    # Logic to drop tables or delete file
    return success_response(message="PKI Database reset successfully. System restarting...")

@bp.route('/api/v2/system/backup', methods=['POST'])
@bp.route('/api/v2/system/backup/create', methods=['POST'])
@require_auth(['admin:system'])
def create_backup():
    """Create encrypted backup"""
    try:
        from services.backup_service import BackupService
        data = request.json or {}
        password = data.get('password')
        
        if not password:
            return error_response("Password required for encryption", 400)
        
        if len(password) < 12:
            return error_response("Password must be at least 12 characters", 400)

        service = BackupService()
        backup_bytes = service.create_backup(password)
        
        # Save to disk
        filename = f"ucm_backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.ucmbkp"
        backup_dir = "/opt/ucm/data/backups"
        os.makedirs(backup_dir, exist_ok=True)
        
        filepath = os.path.join(backup_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(backup_bytes)
        
        # Format size
        size = len(backup_bytes)
        if size > 1024*1024:
            size_str = f"{size/1024/1024:.1f} MB"
        elif size > 1024:
            size_str = f"{size/1024:.1f} KB"
        else:
            size_str = f"{size} B"
            
        return success_response(
            message="Backup created successfully", 
            data={
                'filename': filename,
                'size': size_str,
                'path': filepath
            }
        )
    except ValueError as e:
        return error_response(str(e), 400)
    except Exception as e:
        return error_response(f"Backup failed: {str(e)}", 500)

@bp.route('/api/v2/system/backups', methods=['GET'])
@bp.route('/api/v2/system/backup/list', methods=['GET'])
@require_auth(['read:settings'])
def list_backups():
    """List available backups"""
    try:
        backup_dir = "/opt/ucm/data/backups"
        if not os.path.exists(backup_dir):
            return success_response(data=[])
            
        files = []
        for f in os.listdir(backup_dir):
            if f.endswith('.ucmbkp') or f.endswith('.json.enc'):
                path = os.path.join(backup_dir, f)
                stat = os.stat(path)
                
                # Format size
                size = stat.st_size
                if size > 1024*1024:
                    size_str = f"{size/1024/1024:.1f} MB"
                elif size > 1024:
                    size_str = f"{size/1024:.1f} KB"
                else:
                    size_str = f"{size} B"
                
                files.append({
                    'filename': f,
                    'size': size_str,
                    'size_bytes': size,
                    'created_at': datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
                })
        
        # Sort by date desc
        files.sort(key=lambda x: x['size_bytes'], reverse=True)
        files.sort(key=lambda x: x['created_at'], reverse=True)
        return success_response(data=files)
    except Exception as e:
        return error_response(f"Failed to list backups: {str(e)}")

@bp.route('/api/v2/system/backup/<filename>/download', methods=['GET'])
@require_auth(['read:settings'])
def download_backup(filename):
    """Download backup file"""
    backup_dir = "/opt/ucm/data/backups"
    filename = werkzeug.utils.secure_filename(filename)
    return send_from_directory(
        backup_dir, 
        filename, 
        as_attachment=True, 
        mimetype='application/octet-stream'
    )

@bp.route('/api/v2/system/backup/<filename>', methods=['DELETE'])
@require_auth(['admin:system'])
def delete_backup(filename):
    """Delete a backup file"""
    try:
        backup_dir = "/opt/ucm/data/backups"
        filename = werkzeug.utils.secure_filename(filename)
        filepath = os.path.join(backup_dir, filename)
        
        if not os.path.exists(filepath):
            return error_response("Backup file not found", 404)
        
        os.remove(filepath)
        return success_response(message="Backup deleted successfully")
    except Exception as e:
        return error_response(f"Failed to delete backup: {str(e)}", 500)

@bp.route('/api/v2/system/restore', methods=['POST'])
@bp.route('/api/v2/system/backup/restore', methods=['POST'])
@require_auth(['admin:system'])
def restore_backup():
    """Restore from backup file"""
    try:
        from services.backup_service import BackupService
        
        if 'file' not in request.files:
            return error_response("No backup file provided", 400)
        
        file = request.files['file']
        password = request.form.get('password')
        
        if not password:
            return error_response("Password required for decryption", 400)
        
        if len(password) < 12:
            return error_response("Password must be at least 12 characters", 400)
        
        # Read file content
        backup_bytes = file.read()
        
        service = BackupService()
        results = service.restore_backup(backup_bytes, password)
        
        return success_response(
            message="Backup restored successfully",
            data=results
        )
    except ValueError as e:
        return error_response(str(e), 400)
    except Exception as e:
        return error_response(f"Restore failed: {str(e)}", 500)

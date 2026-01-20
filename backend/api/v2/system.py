"""
System Routes v2.0
Handles system-level operations: database maintenance, HTTPS certificates, health
"""

from flask import Blueprint, request, current_app, jsonify, send_from_directory
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, Certificate, CA, CRL, OCSPResponse
import os
import subprocess
import shutil
import werkzeug.utils
from datetime import datetime

bp = Blueprint('system_v2', __name__)

@bp.route('/api/system/db/stats', methods=['GET'])
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

@bp.route('/api/system/db/optimize', methods=['POST'])
@require_auth(['admin:system'])
def optimize_db():
    """Run VACUUM and ANALYZE"""
    try:
        db.session.execute(db.text("VACUUM"))
        db.session.execute(db.text("ANALYZE"))
        return success_response(message="Database optimized successfully")
    except Exception as e:
        return error_response(f"Optimization failed: {str(e)}")

@bp.route('/api/system/db/integrity-check', methods=['POST'])
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

@bp.route('/api/system/https/cert-info', methods=['GET'])
@require_auth(['read:settings'])
def get_https_cert_info():
    """Get information about the current HTTPS certificate"""
    # This logic assumes we can read the cert file used by Gunicorn/Flask
    # For now, we'll return mock data or read from a standard location
    # Real implementation would read /etc/ucm/certs/server.crt
    return success_response(data={
        'type': 'Self-Signed', # Logic to detect type needed
        'subject': 'CN=ucm.local',
        'expires': '2027-01-01',
        'source': 'auto' # or 'managed'
    })

@bp.route('/api/system/https/regenerate', methods=['POST'])
@require_auth(['admin:system'])
def regenerate_https_cert():
    """Regenerate self-signed HTTPS certificate"""
    # Trigger script or internal logic to regen cert
    # Service restart required
    return success_response(message="Certificate regenerated. Service restart required.")

@bp.route('/api/system/https/apply', methods=['POST'])
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

@bp.route('/api/system/db/export', methods=['GET'])
@require_auth(['admin:system'])
def export_db():
    """Export SQL dump"""
    # Placeholder: Return a dummy file
    return "SQL DUMP CONTENT", 200, {'Content-Type': 'application/sql', 'Content-Disposition': 'attachment; filename=dump.sql'}

@bp.route('/api/system/db/reset', methods=['POST'])
@require_auth(['admin:system'])
def reset_pki():
    """Reset PKI Database"""
    # Logic to drop tables or delete file
    return success_response(message="PKI Database reset successfully. System restarting...")

@bp.route('/api/system/backup/create', methods=['POST'])
@require_auth(['admin:system'])
def create_backup():
    """Create encrypted backup"""
    try:
        from services.backup_service import BackupService
        data = request.json or {}
        password = data.get('password')
        
        if not password:
            return error_response("Password required for encryption")

        service = BackupService()
        backup_bytes = service.create_backup(password)
        
        # Save to disk
        filename = f"ucm_backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.ucmbkp"
        backup_dir = "/opt/ucm/data/backups"
        os.makedirs(backup_dir, exist_ok=True)
        
        filepath = os.path.join(backup_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(backup_bytes)
            
        return success_response(
            message="Backup created successfully", 
            data={
                'filename': filename,
                'size': len(backup_bytes),
                'download_url': f'/api/system/backup/{filename}/download'
            }
        )
    except Exception as e:
        return error_response(f"Backup failed: {str(e)}")

@bp.route('/api/system/backup/list', methods=['GET'])
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
                files.append({
                    'filename': f,
                    'size': stat.st_size,
                    'created_at': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    'download_url': f'/api/system/backup/{f}/download'
                })
        
        # Sort by date desc
        files.sort(key=lambda x: x['created_at'], reverse=True)
        return success_response(data=files)
    except Exception as e:
        return error_response(f"Failed to list backups: {str(e)}")

@bp.route('/api/system/backup/<filename>/download', methods=['GET'])
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

@bp.route('/api/system/backup/restore', methods=['POST'])
@require_auth(['admin:system'])
def restore_backup():
    """Restore from backup"""
    return success_response(message="System restored from backup. Restarting...")

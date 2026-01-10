"""
Backup and Restore API Routes
"""
from flask import Blueprint, request, jsonify, send_file, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from functools import wraps
from datetime import datetime
import io
import os
import json

from models import User
from services.backup_service import BackupService

backup_bp = Blueprint('backup', __name__, url_prefix='/api/v1/backup')


def admin_required(fn):
    """Decorator to require admin role"""
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user or user.role != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        
        return fn(*args, **kwargs)
    return wrapper


@backup_bp.route('/create', methods=['POST'])
@admin_required
def create_backup():
    """
    Create encrypted backup and download
    
    POST /api/v1/backup/create
    {
        "password": "secure_password",
        "type": "full|database|certificates",
        "include": {
            "cas": true,
            "certificates": true,
            "users": true,
            "configuration": true,
            "acme_accounts": true,
            "email_password": false
        }
    }
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data or 'password' not in data:
            return jsonify({'error': 'Password is required'}), 400
        
        password = data['password']
        backup_type = data.get('type', 'full')
        include = data.get('include', {})
        
        # Validate backup type
        if backup_type not in ['full', 'database', 'certificates']:
            return jsonify({'error': 'Invalid backup type'}), 400
        
        # Create backup
        backup_service = BackupService()
        encrypted_data = backup_service.create_backup(
            password=password,
            backup_type=backup_type,
            include=include
        )
        
        # Generate filename
        timestamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
        filename = f"ucm-backup-{timestamp}.ucm-backup"
        
        # Create in-memory file
        backup_file = io.BytesIO(encrypted_data)
        backup_file.seek(0)
        
        current_app.logger.info(f"Backup created: {filename} ({len(encrypted_data)} bytes)")
        
        return send_file(
            backup_file,
            mimetype='application/octet-stream',
            as_attachment=True,
            download_name=filename
        )
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"Backup creation failed: {e}")
        return jsonify({'error': 'Backup creation failed'}), 500


@backup_bp.route('/list', methods=['GET'])
@admin_required
def list_backups():
    """
    List available backups (if stored on server)
    
    GET /api/v1/backup/list
    """
    # TODO: Implement if we store backups server-side
    return jsonify({
        'backups': [],
        'message': 'Server-side backup storage not yet implemented'
    })


@backup_bp.route('/restore', methods=['POST'])
@admin_required
def restore_backup():
    """
    Restore from encrypted backup
    
    POST /api/v1/backup/restore
    FormData:
        - file: backup file
        - password: decryption password
        - options: JSON string with restore options
    """
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        if 'password' not in request.form:
            return jsonify({'error': 'Password required'}), 400
        
        backup_file = request.files['file']
        password = request.form['password']
        
        # Parse options
        options = {}
        if 'options' in request.form:
            try:
                options = json.loads(request.form['options'])
            except:
                return jsonify({'error': 'Invalid options format'}), 400
        
        # Read file
        file_data = backup_file.read()
        
        # Restore
        from services.restore_service import RestoreService
        restore_service = RestoreService()
        
        stats = restore_service.restore_backup(
            encrypted_data=file_data,
            password=password,
            options=options
        )
        
        current_app.logger.info(f"Restore completed: {stats}")
        
        return jsonify({
            'success': True,
            'message': 'Restore completed. Service will restart in 3 seconds.',
            'restored': stats
        })
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"Restore failed: {e}")
        return jsonify({'error': f'Restore failed: {str(e)}'}), 500


@backup_bp.route('/validate', methods=['POST'])
@admin_required
def validate_backup():
    """
    Validate backup file without restoring
    
    POST /api/v1/backup/validate
    FormData:
        - file: backup file
        - password: decryption password
    """
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        if 'password' not in request.form:
            return jsonify({'error': 'Password required'}), 400
        
        backup_file = request.files['file']
        password = request.form['password']
        
        # Read file data
        file_data = backup_file.read()
        
        # Validate
        from services.restore_service import RestoreService
        restore_service = RestoreService()
        
        result = restore_service.validate_backup(file_data, password)
        
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f"Backup validation failed: {e}")
        return jsonify({
            'valid': False,
            'error': str(e)
        }), 500

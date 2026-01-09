"""
Email Notification API
Settings and management for email notifications
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from middleware.auth_middleware import admin_required
from models import db, AuditLog
from models.email_notification import SMTPConfig, NotificationConfig, NotificationLog
from services.email_service import EmailService
from services.notification_service import NotificationService
import json
import logging

logger = logging.getLogger(__name__)

notification_bp = Blueprint('notifications', __name__)


def log_audit(action, username, details=None):
    """Helper to log notification config changes"""
    log = AuditLog(
        username=username,
        action=action,
        resource_type='notification_config',
        details=details,
        ip_address=request.remote_addr
    )
    db.session.add(log)
    db.session.commit()


# ==================== SMTP Configuration ====================

@notification_bp.route('/smtp/config', methods=['GET'])
@jwt_required()
@admin_required
def get_smtp_config():
    """
    Get SMTP configuration
    ---
    GET /api/v1/notifications/smtp/config
    """
    config = SMTPConfig.query.first()
    
    if not config:
        # Return default config
        return jsonify({
            "smtp_host": "",
            "smtp_port": 587,
            "smtp_user": "",
            "smtp_from": "",
            "smtp_from_name": "UCM Notifications",
            "smtp_use_tls": True,
            "smtp_use_ssl": False,
            "enabled": False
        }), 200
    
    return jsonify(config.to_dict(include_password=False)), 200


@notification_bp.route('/smtp/config', methods=['POST', 'PUT'])
@jwt_required()
@admin_required
def update_smtp_config():
    """
    Update SMTP configuration
    ---
    POST /api/v1/notifications/smtp/config
    Body: {
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_user": "user@gmail.com",
        "smtp_password": "password",
        "smtp_from": "noreply@ucm.local",
        "smtp_from_name": "UCM Notifications",
        "smtp_use_tls": true,
        "smtp_use_ssl": false,
        "enabled": true
    }
    """
    try:
        data = request.get_json()
        username = get_jwt_identity()
        
        config = SMTPConfig.query.first()
        
        if not config:
            # Create new config
            config = SMTPConfig()
            db.session.add(config)
        
        # Update fields
        if 'smtp_host' in data:
            config.smtp_host = data['smtp_host']
        if 'smtp_port' in data:
            config.smtp_port = int(data['smtp_port'])
        if 'smtp_user' in data:
            config.smtp_user = data['smtp_user']
        if 'smtp_password' in data and data['smtp_password']:  # Only update if provided
            config.smtp_password = data['smtp_password']  # TODO: Encrypt this
        if 'smtp_from' in data:
            config.smtp_from = data['smtp_from']
        if 'smtp_from_name' in data:
            config.smtp_from_name = data['smtp_from_name']
        if 'smtp_use_tls' in data:
            config.smtp_use_tls = bool(data['smtp_use_tls'])
        if 'smtp_use_ssl' in data:
            config.smtp_use_ssl = bool(data['smtp_use_ssl'])
        if 'enabled' in data:
            config.enabled = bool(data['enabled'])
        
        config.updated_by = username
        
        db.session.commit()
        
        log_audit('update_smtp_config', username, f"Updated SMTP configuration")
        
        return jsonify({
            "success": True,
            "message": "SMTP configuration updated successfully",
            "config": config.to_dict(include_password=False)
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating SMTP config: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@notification_bp.route('/smtp/test', methods=['POST'])
@jwt_required()
@admin_required
def test_smtp():
    """
    Test SMTP connection
    ---
    POST /api/v1/notifications/smtp/test
    Body: {"email": "test@example.com"}
    """
    try:
        data = request.get_json()
        recipient = data.get('email')
        
        if not recipient:
            return jsonify({"success": False, "error": "Email address required"}), 400
        
        # Test connection first
        success, message = EmailService.test_connection()
        
        if not success:
            return jsonify({"success": False, "error": message}), 400
        
        # Send test email
        success, message = EmailService.send_test_email(recipient)
        
        if success:
            return jsonify({
                "success": True,
                "message": f"Test email sent successfully to {recipient}"
            }), 200
        else:
            return jsonify({"success": False, "error": message}), 400
            
    except Exception as e:
        logger.error(f"Error testing SMTP: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== Notification Configuration ====================

@notification_bp.route('/config', methods=['GET'])
@jwt_required()
def get_notification_configs():
    """
    Get all notification configurations
    ---
    GET /api/v1/notifications/config
    """
    configs = NotificationConfig.query.all()
    
    # If no configs exist, return defaults
    if not configs:
        default_configs = [
            {
                "type": "cert_expiring",
                "enabled": False,
                "days_before": 30,
                "recipients": [],
                "subject_template": "Certificate Expiring in {days} days - {description}",
                "description": "Alert when certificates are expiring soon"
            },
            {
                "type": "crl_expiring",
                "enabled": False,
                "days_before": 7,
                "recipients": [],
                "subject_template": "CRL Expiring in {days} days - {ca_name}",
                "description": "Alert when CRLs need regeneration"
            }
        ]
        return jsonify(default_configs), 200
    
    return jsonify([c.to_dict() for c in configs]), 200


@notification_bp.route('/config/<notification_type>', methods=['POST', 'PUT'])
@jwt_required()
@admin_required
def update_notification_config(notification_type):
    """
    Update notification configuration for a specific type
    ---
    POST /api/v1/notifications/config/cert_expiring
    Body: {
        "enabled": true,
        "days_before": 30,
        "recipients": ["admin@example.com", "ops@example.com"]
    }
    """
    try:
        data = request.get_json()
        username = get_jwt_identity()
        
        config = NotificationConfig.query.filter_by(type=notification_type).first()
        
        if not config:
            # Create new config
            config = NotificationConfig(type=notification_type)
            db.session.add(config)
        
        # Update fields
        if 'enabled' in data:
            config.enabled = bool(data['enabled'])
        if 'days_before' in data:
            config.days_before = int(data['days_before'])
        if 'recipients' in data:
            # Convert list to JSON string
            config.recipients = json.dumps(data['recipients'])
        if 'subject_template' in data:
            config.subject_template = data['subject_template']
        if 'description' in data:
            config.description = data['description']
        
        db.session.commit()
        
        log_audit('update_notification_config', username, f"Updated notification config: {notification_type}")
        
        return jsonify({
            "success": True,
            "message": f"Notification configuration updated for {notification_type}",
            "config": config.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating notification config: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== Notification History/Logs ====================

@notification_bp.route('/history', methods=['GET'])
@jwt_required()
def get_notification_history():
    """
    Get notification history
    ---
    GET /api/v1/notifications/history?limit=50&status=sent&type=cert_expiring
    """
    limit = request.args.get('limit', 50, type=int)
    status = request.args.get('status')  # sent, failed
    notification_type = request.args.get('type')
    
    query = NotificationLog.query
    
    if status:
        query = query.filter_by(status=status)
    if notification_type:
        query = query.filter_by(type=notification_type)
    
    logs = query.order_by(NotificationLog.sent_at.desc()).limit(limit).all()
    
    return jsonify({
        "total": len(logs),
        "logs": [log.to_dict() for log in logs]
    }), 200


@notification_bp.route('/stats', methods=['GET'])
@jwt_required()
def get_notification_stats():
    """
    Get notification statistics
    ---
    GET /api/v1/notifications/stats
    """
    from sqlalchemy import func
    from datetime import datetime, timedelta
    
    # Last 30 days
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    total_sent = NotificationLog.query.filter_by(status='sent').count()
    total_failed = NotificationLog.query.filter_by(status='failed').count()
    
    recent_sent = NotificationLog.query.filter(
        NotificationLog.status == 'sent',
        NotificationLog.sent_at >= thirty_days_ago
    ).count()
    
    recent_failed = NotificationLog.query.filter(
        NotificationLog.status == 'failed',
        NotificationLog.sent_at >= thirty_days_ago
    ).count()
    
    # By type
    by_type = db.session.query(
        NotificationLog.type,
        NotificationLog.status,
        func.count(NotificationLog.id).label('count')
    ).group_by(NotificationLog.type, NotificationLog.status).all()
    
    type_stats = {}
    for row in by_type:
        if row.type not in type_stats:
            type_stats[row.type] = {'sent': 0, 'failed': 0}
        type_stats[row.type][row.status] = row.count
    
    return jsonify({
        "total_sent": total_sent,
        "total_failed": total_failed,
        "recent_sent_30d": recent_sent,
        "recent_failed_30d": recent_failed,
        "by_type": type_stats
    }), 200


# ==================== Manual Notification Triggers ====================

@notification_bp.route('/check', methods=['POST'])
@jwt_required()
@admin_required
def manual_notification_check():
    """
    Manually trigger notification check
    ---
    POST /api/v1/notifications/check
    """
    try:
        username = get_jwt_identity()
        
        NotificationService.run_notification_check()
        
        log_audit('manual_notification_check', username, "Triggered manual notification check")
        
        return jsonify({
            "success": True,
            "message": "Notification check completed successfully"
        }), 200
        
    except Exception as e:
        logger.error(f"Error running notification check: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== User Notification Settings ====================

@notification_bp.route('/user/settings', methods=['GET'])
@jwt_required()
def get_user_notification_settings():
    """
    Get current user's notification settings
    ---
    GET /api/v1/notifications/user/settings
    """
    try:
        from models import User
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({
            'email': user.email or '',
            'enabled': user.notifications_enabled if hasattr(user, 'notifications_enabled') else True
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting user notification settings: {str(e)}")
        return jsonify({'error': str(e)}), 500


@notification_bp.route('/user/settings', methods=['POST'])
@jwt_required()
def update_user_notification_settings():
    """
    Update current user's notification settings
    ---
    POST /api/v1/notifications/user/settings
    Body: {"email": "user@example.com", "enabled": true}
    """
    try:
        from models import User
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json()
        
        if 'email' in data:
            user.email = data['email']
        
        if 'enabled' in data and hasattr(user, 'notifications_enabled'):
            user.notifications_enabled = data['enabled']
        
        db.session.commit()
        
        log_audit('update_notification_settings', user.username, 
                 f"Updated notification settings: email={user.email}")
        
        return jsonify({
            'success': True,
            'message': 'Notification settings updated successfully',
            'email': user.email,
            'enabled': user.notifications_enabled if hasattr(user, 'notifications_enabled') else True
        }), 200
        
    except Exception as e:
        logger.error(f"Error updating user notification settings: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

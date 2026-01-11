"""
Health Check API
Provides system health and monitoring endpoints
"""

from flask import Blueprint, jsonify, current_app
from datetime import datetime
import os
import psutil
from models import db, CA, Certificate, User, AcmeAccount

health_bp = Blueprint('health', __name__)


@health_bp.route('/api/health', methods=['GET'])
def health_check():
    """
    Basic health check endpoint
    Returns 200 if service is healthy
    """
    try:
        # Check database connectivity
        db.session.execute(db.text('SELECT 1'))
        
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'version': '1.9.0'
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'timestamp': datetime.utcnow().isoformat(),
            'error': str(e)
        }), 503


@health_bp.route('/api/health/detailed', methods=['GET'])
def health_detailed():
    """
    Detailed health check with system metrics
    No auth required for monitoring tools
    """
    try:
        # Database check
        db_healthy = False
        db_error = None
        try:
            db.session.execute(db.text('SELECT 1'))
            db_healthy = True
        except Exception as e:
            db_error = str(e)
        
        # Get database size
        db_path = db.engine.url.database
        db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
        
        # Count records
        ca_count = CA.query.count() if db_healthy else 0
        cert_count = Certificate.query.count() if db_healthy else 0
        user_count = User.query.count() if db_healthy else 0
        acme_count = AcmeAccount.query.count() if db_healthy else 0
        
        # System metrics
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        health_data = {
            'status': 'healthy' if db_healthy else 'degraded',
            'timestamp': datetime.utcnow().isoformat(),
            'version': '1.9.0',
            'database': {
                'healthy': db_healthy,
                'error': db_error,
                'size_bytes': db_size,
                'size_mb': round(db_size / (1024 * 1024), 2),
                'records': {
                    'certificate_authorities': ca_count,
                    'certificates': cert_count,
                    'users': user_count,
                    'acme_accounts': acme_count
                }
            },
            'system': {
                'cpu_percent': cpu_percent,
                'memory': {
                    'total_mb': round(memory.total / (1024 * 1024), 2),
                    'available_mb': round(memory.available / (1024 * 1024), 2),
                    'percent': memory.percent
                },
                'disk': {
                    'total_gb': round(disk.total / (1024 * 1024 * 1024), 2),
                    'used_gb': round(disk.used / (1024 * 1024 * 1024), 2),
                    'free_gb': round(disk.free / (1024 * 1024 * 1024), 2),
                    'percent': disk.percent
                }
            }
        }
        
        status_code = 200 if db_healthy else 503
        return jsonify(health_data), status_code
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'timestamp': datetime.utcnow().isoformat(),
            'error': str(e)
        }), 500


@health_bp.route('/api/health/readiness', methods=['GET'])
def readiness_check():
    """
    Kubernetes-style readiness probe
    Checks if service is ready to accept traffic
    """
    try:
        # Check database connectivity
        db.session.execute(db.text('SELECT 1'))
        
        # Check if at least one user exists (system initialized)
        user_count = User.query.count()
        
        if user_count == 0:
            return jsonify({
                'ready': False,
                'reason': 'System not initialized - no users found'
            }), 503
        
        return jsonify({
            'ready': True,
            'timestamp': datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        return jsonify({
            'ready': False,
            'reason': str(e)
        }), 503


@health_bp.route('/api/health/liveness', methods=['GET'])
def liveness_check():
    """
    Kubernetes-style liveness probe
    Simple check if application is running
    """
    return jsonify({
        'alive': True,
        'timestamp': datetime.utcnow().isoformat()
    }), 200

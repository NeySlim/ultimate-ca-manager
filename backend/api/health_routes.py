"""
Health Check Routes
Endpoints for load balancers, monitoring, and readiness checks.
"""
import time
from flask import Blueprint, jsonify, current_app
from models import db
import os

health_bp = Blueprint('health', __name__)

_started_at = time.time()


@health_bp.route('/health')
@health_bp.route('/api/health')
def health():
    """
    Basic health check - fast response for load balancers.
    Always returns 200 if the application is running.
    Includes started_at for restart detection by frontend.
    """
    return jsonify({
        'status': 'ok',
        'service': 'ucm',
        'started_at': _started_at
    })


@health_bp.route('/health/ready')
@health_bp.route('/api/health/ready')
def readiness():
    """
    Readiness check - verifies the app can serve traffic.
    Checks database connectivity and required services.
    Returns 200 if ready, 503 if not.
    """
    checks = {
        'database': _check_database(),
        'filesystem': _check_filesystem(),
    }
    
    # Optional: check Redis if configured
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        checks['redis'] = _check_redis(redis_url)
    
    all_ok = all(c.get('status') == 'ok' for c in checks.values())
    
    return jsonify({
        'status': 'ready' if all_ok else 'not_ready',
        'checks': checks
    }), 200 if all_ok else 503


@health_bp.route('/health/live')
@health_bp.route('/api/health/live')
def liveness():
    """
    Liveness check - verifies the app is not deadlocked.
    Returns 200 if alive, regardless of dependency status.
    """
    return jsonify({
        'status': 'alive',
        'service': 'ucm'
    })


def _check_database():
    """Check database connectivity"""
    try:
        # Execute simple query to verify connection
        db.session.execute(db.text('SELECT 1'))
        return {'status': 'ok'}
    except Exception as e:
        current_app.logger.error(f"Database health check failed: {e}")
        return {'status': 'error', 'message': str(e)[:100]}


def _check_filesystem():
    """Check filesystem access for data directory"""
    try:
        from config.settings import DATA_DIR
        if DATA_DIR.exists() and os.access(DATA_DIR, os.W_OK):
            return {'status': 'ok'}
        return {'status': 'error', 'message': 'Data directory not writable'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)[:100]}


def _check_redis(redis_url):
    """Check Redis connectivity"""
    try:
        import redis
        r = redis.from_url(redis_url, socket_timeout=2)
        r.ping()
        return {'status': 'ok'}
    except ImportError:
        return {'status': 'skipped', 'message': 'redis library not installed'}
    except Exception as e:
        current_app.logger.error(f"Redis health check failed: {e}")
        return {'status': 'error', 'message': str(e)[:100]}

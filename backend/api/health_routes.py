"""
Health Check Routes
Endpoints for load balancers, monitoring, and readiness checks.
"""
import time
from flask import Blueprint, jsonify, current_app
from models import db
from config.settings import redis_url as config_redis_url
import os

health_bp = Blueprint('health', __name__)

_started_at = time.time()


@health_bp.route('/api/v2/health')
@health_bp.route('/api/health')
@health_bp.route('/health')
def health():
    """
    Basic health check - fast response for load balancers.
    Always returns 200 if the application is running.
    Includes started_at for restart detection by frontend.
    """
    from config.settings import get_config
    _config = get_config()

    # Check WebSocket readiness
    ws_ready = False
    try:
        from websocket import socketio
        ws_ready = socketio.server is not None
    except Exception:
        pass

    result = {
        'status': 'ok',
        'service': 'ucm',
        'version': _config.APP_VERSION,
        'started_at': _started_at,
        'websocket': ws_ready
    }
    if current_app.config.get('SAFE_MODE'):
        result['safe_mode'] = True
        result['safe_mode_reason'] = 'encryption_key_missing'
    return jsonify(result)


@health_bp.route('/api/v2/health/ready')
@health_bp.route('/api/health/ready')
@health_bp.route('/health/ready')
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
    redis_url = config_redis_url()
    if redis_url:
        checks['redis'] = _check_redis(redis_url)
    
    all_ok = all(c.get('status') in ('ok', 'skipped') for c in checks.values())
    
    return jsonify({
        'status': 'ready' if all_ok else 'not_ready',
        'checks': checks
    }), 200 if all_ok else 503


@health_bp.route('/api/v2/health/live')
@health_bp.route('/api/health/live')
@health_bp.route('/health/live')
def liveness():
    """
    Liveness check - verifies the app is not deadlocked.
    Returns 200 if alive, regardless of dependency status.
    """
    return jsonify({
        'status': 'alive',
        'service': 'ucm'
    })


@health_bp.route('/metrics')
@health_bp.route('/api/v2/metrics')
def metrics():
    """Prometheus metrics endpoint (opt-in).

    Disabled (404) until a ``metrics_token`` is configured. When set, a
    matching ``Authorization: Bearer <token>`` is required — Prometheus
    scrapes with a static bearer token.
    """
    import hmac
    from flask import request, Response
    from models import SystemConfig

    cfg = SystemConfig.query.filter_by(key='metrics_token').first()
    token = cfg.value if cfg and cfg.value else None
    if not token:
        return Response('Metrics disabled', status=404, mimetype='text/plain')

    auth = request.headers.get('Authorization', '')
    presented = auth[7:] if auth.startswith('Bearer ') else ''
    if not presented or not hmac.compare_digest(presented, token):
        return Response('Unauthorized', status=401, mimetype='text/plain')

    from services.metrics_service import render_metrics
    body = render_metrics()
    return Response(body, status=200, mimetype='text/plain; version=0.0.4; charset=utf-8')


def _check_database():
    """Check database connectivity"""
    try:
        # Execute simple query to verify connection
        db.session.execute(db.text('SELECT 1'))
        return {'status': 'ok'}
    except Exception as e:
        current_app.logger.error(f"Database health check failed: {e}")
        return {'status': 'error', 'message': 'Database connection failed'}


def _check_filesystem():
    """Check filesystem access for data directory"""
    try:
        from config.settings import DATA_DIR
        if DATA_DIR.exists() and os.access(DATA_DIR, os.W_OK):
            return {'status': 'ok'}
        return {'status': 'error', 'message': 'Data directory not writable'}
    except Exception as e:
        return {'status': 'error', 'message': 'Filesystem check failed'}


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
        return {'status': 'error', 'message': 'Redis connection failed'}

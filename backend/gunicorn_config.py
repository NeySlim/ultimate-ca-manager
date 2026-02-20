# Gunicorn configuration file for UCM
# Single config for all deployments (DEB, RPM, Docker)

# Monkey-patch BEFORE any other imports to avoid gevent + Python 3.13
# SSLContext/SSLSocket recursion bugs (super() closure captures wrong class)
from gevent import monkey
monkey.patch_all()

import os
import sys

# Detect environment
base_path = os.getenv('UCM_BASE_PATH', '/opt/ucm')
data_path = os.getenv('DATA_DIR', f'{base_path}/data')
is_docker = os.path.exists('/.dockerenv')

# Server socket
bind = f"0.0.0.0:{os.getenv('HTTPS_PORT', '8443')}"
backlog = 2048

# Worker processes
workers = int(os.getenv('GUNICORN_WORKERS', 2))
worker_class = 'geventwebsocket.gunicorn.workers.GeventWebSocketWorker'
worker_connections = 1000
timeout = 120
keepalive = 5

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# SSL/TLS
certfile = os.getenv('HTTPS_CERT_PATH', f'{data_path}/https_cert.pem')
keyfile = os.getenv('HTTPS_KEY_PATH', f'{data_path}/https_key.pem')
cert_reqs = 0
ca_certs = None
do_handshake_on_connect = True


def _load_mtls_config():
    """Read mTLS settings from database at startup and configure client cert verification.
    Uses raw sqlite3 to avoid Flask/SQLAlchemy dependency at config load time.
    """
    global cert_reqs, ca_certs

    db_path = os.path.join(data_path, 'ucm.db')
    if not os.path.exists(db_path):
        return

    import sqlite3
    import base64
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT key, value FROM system_config "
            "WHERE key IN ('mtls_enabled', 'mtls_required', 'mtls_trusted_ca_id')"
        )
        config = dict(cursor.fetchall())

        if config.get('mtls_enabled') != 'true':
            conn.close()
            return

        ca_refid = config.get('mtls_trusted_ca_id')
        if not ca_refid:
            conn.close()
            return

        cursor.execute(
            "SELECT crt, descr FROM certificate_authorities WHERE refid = ?",
            (ca_refid,)
        )
        row = cursor.fetchone()
        conn.close()

        if not row or not row[0]:
            print("mTLS: trusted CA not found in database", file=sys.stderr)
            return

        # Decode CA cert (base64 encoded in DB)
        try:
            ca_pem = base64.b64decode(row[0]).decode('utf-8')
        except Exception:
            ca_pem = row[0]

        # Write CA cert to a stable file (overwritten on each restart)
        ca_file_path = os.path.join(data_path, 'mtls_ca.pem')
        with open(ca_file_path, 'w') as f:
            f.write(ca_pem)

        ca_certs = ca_file_path
        cert_reqs = 2 if config.get('mtls_required') == 'true' else 1

        mode = "REQUIRED" if cert_reqs == 2 else "OPTIONAL"
        ca_name = row[1] or ca_refid
        print(f"mTLS: {mode} — trusted CA: {ca_name}", file=sys.stderr)

    except Exception as e:
        print(f"mTLS: config load failed: {e}", file=sys.stderr)


_load_mtls_config()

# Logging: stdout in Docker, files in native installs
if is_docker:
    accesslog = '-'
    errorlog = '-'
else:
    accesslog = os.getenv('ACCESS_LOG', '/var/log/ucm/access.log')
    errorlog = os.getenv('ERROR_LOG', '/var/log/ucm/error.log')
loglevel = os.getenv('LOG_LEVEL', 'info')
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = 'ucm'

# Preload app so DB init runs once in master process
preload_app = True

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# Server hooks
def on_starting(server):
    server.log.info("Starting UCM with Gunicorn")

def on_reload(server):
    server.log.info("Reloading UCM")

def worker_int(worker):
    worker.log.info("Worker received INT or QUIT signal")

def worker_abort(worker):
    worker.log.info("Worker received SIGABRT signal")

def post_worker_init(worker):
    """Suppress noisy SSL/connection tracebacks from gevent.

    Reverse proxy health checks and port scanners cause SSL handshake
    failures that produce ~20-line tracebacks every few minutes.
    This replaces the default gevent hub error handler with one that
    logs these as single-line DEBUG messages instead.
    """
    import ssl
    import gevent

    hub = gevent.get_hub()
    _original_handle_error = hub.handle_error

    def _quiet_handle_error(context, type, value, tb):
        if type and issubclass(type, (ssl.SSLError, ConnectionResetError, BrokenPipeError, OSError)):
            worker.log.debug("Connection error suppressed: %s", value)
            return
        _original_handle_error(context, type, value, tb)

    hub.handle_error = _quiet_handle_error

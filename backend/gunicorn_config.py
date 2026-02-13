# Gunicorn configuration file for UCM
# Single config for all deployments (DEB, RPM, Docker)

# Monkey-patch BEFORE any other imports to avoid gevent + Python 3.13
# SSLContext/SSLSocket recursion bugs (super() closure captures wrong class)
from gevent import monkey
monkey.patch_all()

import os

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
do_handshake_on_connect = True

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

# Gunicorn configuration file
# UCM Production WSGI Server

import multiprocessing
import os
import sys

# Server socket
bind = f"0.0.0.0:{os.getenv('UCM_HTTPS_PORT', '8443')}"
backlog = 2048

# Worker processes
workers = int(os.getenv('GUNICORN_WORKERS', multiprocessing.cpu_count() * 2 + 1))
worker_class = 'geventwebsocket.gunicorn.workers.GeventWebSocketWorker'
worker_connections = 1000
timeout = 120
keepalive = 5

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# SSL/TLS
# Support both Docker (/app) and production (/opt/ucm) paths
base_path = os.getenv('UCM_BASE_PATH', '/opt/ucm')
data_path = os.getenv('DATA_DIR', f'{base_path}/data')
certfile = f'{data_path}/https_cert.pem'
keyfile = f'{data_path}/https_key.pem'
ssl_version = 'TLSv1_2'
cert_reqs = 0  # Don't require client certificate
do_handshake_on_connect = True

# Logging
accesslog = '-'  # stdout
errorlog = '-'   # stderr
loglevel = os.getenv('LOG_LEVEL', 'info')
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = 'ucm'

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# Preload application to initialize DB before forking workers
# This ensures DB tables are created ONCE by the master process
preload_app = True

# Server hooks
def on_starting(server):
    """Called just before the master process is initialized."""
    server.log.info("Starting UCM with Gunicorn")

def post_worker_init(worker):
    """Called just after a worker has initialized the application.
    
    Fix gevent + Python 3.13 SSLContext.minimum_version recursion bug.
    gevent monkey-patches ssl.SSLContext, causing the property setter
    to infinitely recurse through super() between gevent and stdlib classes.
    """
    import ssl
    if hasattr(ssl, '_SSLContext') and ssl.SSLContext is not ssl._SSLContext:
        _CBase = ssl._SSLContext
        _min_desc = _CBase.__dict__.get('minimum_version')
        _max_desc = _CBase.__dict__.get('maximum_version')
        
        if _min_desc is not None:
            def _safe_set_min(self, value):
                _min_desc.__set__(self, value)
            
            cur = type.__dict__['__dict__'].__get__(ssl.SSLContext).get('minimum_version')
            if cur and hasattr(cur, 'fget'):
                ssl.SSLContext.minimum_version = cur.setter(_safe_set_min)
        
        if _max_desc is not None:
            def _safe_set_max(self, value):
                _max_desc.__set__(self, value)
            
            cur = type.__dict__['__dict__'].__get__(ssl.SSLContext).get('maximum_version')
            if cur and hasattr(cur, 'fget'):
                ssl.SSLContext.maximum_version = cur.setter(_safe_set_max)
        
        worker.log.info("Applied SSL recursion workaround for gevent + Python 3.13")

def on_reload(server):
    """Called to recycle workers during a reload via SIGHUP."""
    server.log.info("Reloading UCM")

def worker_int(worker):
    """Called just after a worker exited on SIGINT or SIGQUIT."""
    worker.log.info("Worker received INT or QUIT signal")

def worker_abort(worker):
    """Called when a worker received the SIGABRT signal."""
    worker.log.info("Worker received SIGABRT signal")

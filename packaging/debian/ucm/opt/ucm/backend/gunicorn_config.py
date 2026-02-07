# Gunicorn configuration file for UCM (native installation)
# This file is used when gunicorn is started with -c gunicorn_config.py
# For systemd service, configuration is in /etc/systemd/system/ucm.service

import multiprocessing
import os

# Server socket
bind = f"0.0.0.0:{os.getenv('HTTPS_PORT', '8443')}"
backlog = 2048

# Worker processes - Use gevent for WebSocket support
workers = int(os.getenv('GUNICORN_WORKERS', 4))
worker_class = 'geventwebsocket.gunicorn.workers.GeventWebSocketWorker'
worker_connections = 1000
timeout = 120
keepalive = 5

# WebSocket support
websocket_ping_interval = 25
websocket_ping_timeout = 60

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# SSL/TLS - paths for native installation
certfile = os.getenv('HTTPS_CERT_PATH', '/opt/ucm/data/https_cert.pem')
keyfile = os.getenv('HTTPS_KEY_PATH', '/opt/ucm/data/https_key.pem')
ssl_version = 'TLSv1_2'
cert_reqs = 0  # Don't require client certificate
do_handshake_on_connect = True

# Logging
accesslog = os.getenv('ACCESS_LOG', '/var/log/ucm/access.log')
errorlog = os.getenv('ERROR_LOG', '/var/log/ucm/error.log')
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

# Server hooks
def on_starting(server):
    """Called just before the master process is initialized."""
    server.log.info("Starting UCM with Gunicorn")

def on_reload(server):
    """Called to recycle workers during a reload via SIGHUP."""
    server.log.info("Reloading UCM")

def worker_int(worker):
    """Called just after a worker exited on SIGINT or SIGQUIT."""
    worker.log.info("Worker received INT or QUIT signal")

def worker_abort(worker):
    """Called when a worker received SIGABRT signal."""
    worker.log.info("Worker received SIGABRT signal")

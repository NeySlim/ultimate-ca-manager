#!/bin/bash
# UCM Start Wrapper - Loads environment and starts Gunicorn
# This script is executed by systemd to properly load environment variables
# before starting the Gunicorn WSGI server with WebSocket support.

# Load environment variables from config file
set -a
[ -f /etc/ucm/ucm.env ] && source /etc/ucm/ucm.env
set +a

# Set defaults if not defined
: ${HTTPS_PORT:=8443}
: ${HTTPS_CERT_PATH:=/opt/ucm/data/https_cert.pem}
: ${HTTPS_KEY_PATH:=/opt/ucm/data/https_key.pem}
: ${LOG_LEVEL:=info}

# Start Gunicorn with SSL and WebSocket support (gevent worker)
cd /opt/ucm/backend
exec /opt/ucm/venv/bin/gunicorn \
    --bind "0.0.0.0:${HTTPS_PORT}" \
    --workers 4 \
    --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker \
    --timeout 120 \
    --access-logfile /var/log/ucm/access.log \
    --error-logfile /var/log/ucm/error.log \
    --log-level "${LOG_LEVEL}" \
    --certfile "${HTTPS_CERT_PATH}" \
    --keyfile "${HTTPS_KEY_PATH}" \
    --chdir /opt/ucm/backend \
    wsgi:app

#!/bin/bash
# UCM Start Wrapper - Loads environment and starts Gunicorn
# This script is executed by systemd to properly load environment variables
# before starting the Gunicorn WSGI server with WebSocket support.

# Load environment variables from config file
set -a
[ -f /etc/ucm/ucm.env ] && source /etc/ucm/ucm.env
set +a

# Start Gunicorn using Python config file (all settings in gunicorn_config.py)
cd /opt/ucm/backend
exec /opt/ucm/venv/bin/gunicorn -c gunicorn_config.py wsgi:app

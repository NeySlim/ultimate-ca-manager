#!/bin/bash
# UCM Start Wrapper for RPM - Loads environment and starts Gunicorn
# RPM paths differ from DEB: /usr/share/ucm vs /opt/ucm

# Load environment variables from config file
set -a
[ -f /etc/ucm/ucm.env ] && source /etc/ucm/ucm.env
set +a

# Set defaults - RPM uses /var/lib/ucm for data
: ${HTTPS_PORT:=8443}
: ${UCM_DATA:=/var/lib/ucm}
: ${HTTPS_CERT_PATH:=$UCM_DATA/https_cert.pem}
: ${HTTPS_KEY_PATH:=$UCM_DATA/https_key.pem}
: ${LOG_LEVEL:=info}

export DATABASE_PATH="${DATABASE_PATH:-$UCM_DATA/ucm.db}"
export DATA_DIR="$UCM_DATA"

# Generate self-signed HTTPS cert if not exists
if [ ! -f "$HTTPS_CERT_PATH" ] || [ ! -f "$HTTPS_KEY_PATH" ]; then
    echo "Generating self-signed HTTPS certificate..."
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
        -keyout "$HTTPS_KEY_PATH" \
        -out "$HTTPS_CERT_PATH" \
        -subj "/CN=ucm/O=UCM/OU=PKI" 2>/dev/null
    chmod 600 "$HTTPS_KEY_PATH"
    chmod 644 "$HTTPS_CERT_PATH"
    echo "Certificate generated: $HTTPS_CERT_PATH"
fi

# Start Gunicorn with SSL
cd /usr/share/ucm/backend
exec /usr/share/ucm/venv/bin/gunicorn \
    --bind "0.0.0.0:${HTTPS_PORT}" \
    --workers 4 \
    --worker-class sync \
    --timeout 120 \
    --access-logfile /var/log/ucm/access.log \
    --error-logfile /var/log/ucm/error.log \
    --log-level "${LOG_LEVEL}" \
    --certfile "${HTTPS_CERT_PATH}" \
    --keyfile "${HTTPS_KEY_PATH}" \
    --chdir /usr/share/ucm/backend \
    wsgi:app

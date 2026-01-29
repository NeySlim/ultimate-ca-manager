#!/bin/bash
# Extract mTLS CA certificate from database
cd /opt/ucm
CA_ID=$(sqlite3 backend/data/ucm.db "SELECT value FROM system_config WHERE key='mtls_trusted_ca_id';" 2>/dev/null)

if [ -n "$CA_ID" ]; then
    sqlite3 backend/data/ucm.db "SELECT crt FROM certificate_authorities WHERE refid='$CA_ID';" 2>/dev/null | base64 -d > /tmp/ucm_mtls_ca.pem
    if [ -s /tmp/ucm_mtls_ca.pem ]; then
        chmod 644 /tmp/ucm_mtls_ca.pem
        exit 0
    fi
fi

# If extraction failed, create empty file so Gunicorn doesn't fail
touch /tmp/ucm_mtls_ca.pem
exit 0

#!/bin/bash
set -e

# Create ucm user if not exists
if ! id -u ucm > /dev/null 2>&1; then
    useradd -r -s /bin/bash -d /opt/ucm -m ucm
fi

# Set permissions
chown -R ucm:ucm /opt/ucm
chmod 755 /opt/ucm

# Create virtual environment
cd /opt/ucm
python3 -m venv venv
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r backend/requirements.txt

# Create data directories
mkdir -p /opt/ucm/backend/data/{ca,certs,crl,ocsp,scep}
mkdir -p /var/lib/ucm
mkdir -p /var/log/ucm
mkdir -p /etc/ucm
chown -R ucm:ucm /opt/ucm/backend/data
chown -R ucm:ucm /var/lib/ucm
chown -R ucm:ucm /var/log/ucm
chmod 755 /var/log/ucm

# Generate self-signed HTTPS certificate compatible with modern browsers
if [ ! -f /etc/ucm/https_cert.pem ]; then
    FQDN=$(hostname -f 2>/dev/null || hostname)
    IP=$(hostname -I | awk '{print $1}')
    FQDN_BASE=$(echo $FQDN | cut -d. -f2-)
    
    cat > /tmp/ucm-ssl.cnf << SSLEOF
[req]
distinguished_name = req_distinguished_name
x509_extensions = v3_req
prompt = no

[req_distinguished_name]
C = US
ST = State
L = City
O = Ultimate CA Manager
OU = IT
CN = ${FQDN}

[v3_req]
# Key Usage - critical for modern browsers
keyUsage = critical, digitalSignature, keyEncipherment, keyAgreement
# Extended Key Usage - TLS Server Authentication
extendedKeyUsage = serverAuth
# Subject Alternative Name - required by modern browsers
subjectAltName = @alt_names
# Basic Constraints - not a CA
basicConstraints = critical, CA:FALSE
# Subject Key Identifier
subjectKeyIdentifier = hash

[alt_names]
DNS.1 = ${FQDN}
DNS.2 = localhost
DNS.3 = *.${FQDN_BASE}
IP.1 = ${IP}
IP.2 = 127.0.0.1
SSLEOF
    
    openssl req -x509 -newkey rsa:4096 -sha256 -nodes \
        -keyout /etc/ucm/https_key.pem \
        -out /etc/ucm/https_cert.pem \
        -days 365 \
        -config /tmp/ucm-ssl.cnf \
        -extensions v3_req \
        2>/dev/null
    
    rm -f /tmp/ucm-ssl.cnf
    chmod 600 /etc/ucm/https_key.pem
    chmod 644 /etc/ucm/https_cert.pem
    chown ucm:ucm /etc/ucm/https_key.pem
    chown ucm:ucm /etc/ucm/https_cert.pem
fi

# Create environment file if not exists
if [ ! -f /etc/ucm/ucm.env ]; then
    FQDN_VALUE=$(hostname -f 2>/dev/null || hostname)
    
    # Generate security keys
    SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
    JWT_SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
    
    cat > /etc/ucm/ucm.env << ENVEOF
# UCM Configuration
FQDN=${FQDN_VALUE}
HTTPS_PORT=8443
DEBUG=false
LOG_LEVEL=INFO

# Security
SECRET_KEY=${SECRET_KEY}
JWT_SECRET_KEY=${JWT_SECRET}
SESSION_TIMEOUT=3600
JWT_EXPIRATION=86400

# Database
DATABASE_PATH=/var/lib/ucm/ucm.db

# HTTPS Certificate
HTTPS_CERT_PATH=/etc/ucm/https_cert.pem
HTTPS_KEY_PATH=/etc/ucm/https_key.pem
HTTPS_AUTO_GENERATE=true

# Logging
LOG_FILE=/var/log/ucm/ucm.log
AUDIT_LOG_FILE=/var/log/ucm/audit.log
ENVEOF
    chmod 600 /etc/ucm/ucm.env
    chown ucm:ucm /etc/ucm/ucm.env
fi

# Initialize database if not exists
if [ ! -f /opt/ucm/backend/data/ucm.db ]; then
    cd /opt/ucm
    sudo -u ucm venv/bin/python backend/init_db.py
fi

# Enable and start service
systemctl daemon-reload
systemctl enable ucm.service
systemctl start ucm.service

echo "✅ UCM installed successfully!"
echo "   Access: https://$(hostname -I | awk '{print $1}'):8443"
echo "   Config: /etc/ucm/ucm.env"
echo "   Logs: journalctl -u ucm -f"
echo ""
echo "⚠️  Note: Self-signed certificate generated."
echo "   Add to trusted certificates or replace with your own."

exit 0

Name:           ucm
Version:        %{?_version}%{!?_version:2.0.0}
Release:        %{?_release}%{!?_release:1}%{?dist}
Summary:        Ultimate CA Manager - Complete PKI Management Platform

License:        Proprietary
URL:            https://github.com/NeySlim/ultimate-ca-manager
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3 >= 3.9
BuildRequires:  python3-pip
BuildRequires:  systemd-rpm-macros

Requires:       python3 >= 3.9
Requires:       python3-pip
Requires:       systemd
Requires:       openssl >= 1.1.1

# Installation paths - same as Debian for consistency
%define ucm_home /opt/ucm
%define ucm_data /opt/ucm/data
%define ucm_config /etc/ucm
%define ucm_log /var/log/ucm

%description
Ultimate CA Manager (UCM) is a comprehensive Public Key Infrastructure (PKI)
management platform providing:
- Root and Intermediate Certificate Authorities
- Certificate lifecycle management (create, renew, revoke, export)
- OCSP Responder and CRL Distribution Points
- SCEP enrollment (iOS, Android, Windows, macOS MDM)
- ACME protocol support (Let's Encrypt compatible)
- WebAuthn/FIDO2 passwordless authentication
- REST API with JWT authentication
- Email notifications for certificate expiration

%prep
%setup -q

%build
# Nothing to build - pure Python application

%install
# Create directory structure
install -d %{buildroot}%{ucm_home}
install -d %{buildroot}%{ucm_data}/{ca,certs,private,crl,scep,backups,sessions}
install -d %{buildroot}%{ucm_config}
install -d %{buildroot}%{ucm_log}
install -d %{buildroot}%{_unitdir}
install -d %{buildroot}%{_bindir}

# Install application files to /opt/ucm
cp -r backend %{buildroot}%{ucm_home}/
cp -r frontend %{buildroot}%{ucm_home}/
cp -r scripts %{buildroot}%{ucm_home}/

# Remove .env files (configuration created by postinst)
find %{buildroot}%{ucm_home} -name ".env*" -delete

# Install root files
install -m 644 backend/requirements.txt %{buildroot}%{ucm_home}/
install -m 644 backend/gunicorn.conf.py %{buildroot}%{ucm_home}/
install -m 755 backend/wsgi.py %{buildroot}%{ucm_home}/

# Install systemd service
install -m 644 packaging/rpm/ucm.service %{buildroot}%{_unitdir}/%{name}.service

# Install configuration helper
install -m 755 packaging/scripts/ucm-configure %{buildroot}%{_bindir}/ucm-configure

%pre
# Create ucm user and group
getent group %{name} >/dev/null || groupadd -r %{name}
getent passwd %{name} >/dev/null || \
    useradd -r -g %{name} -d %{ucm_home} \
    -s /sbin/nologin -c "UCM Service Account" %{name}

# Backup existing data on upgrade
if [ $1 -eq 2 ]; then
    BACKUP_DIR="/var/backups/ucm/upgrade-$(date +%%Y%%m%%d-%%H%%M%%S)"
    mkdir -p "$BACKUP_DIR"
    if [ -d "%{ucm_data}" ]; then
        cp -r %{ucm_data} "$BACKUP_DIR/"
        echo "Backup created at: $BACKUP_DIR"
    fi
fi

%post
# Generate configuration if not present
ENV_FILE="%{ucm_config}/ucm.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "Generating initial configuration..."
    
    # Generate secrets
    SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
    JWT_SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
    ADMIN_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_urlsafe(16))')
    FQDN=$(hostname -f 2>/dev/null || hostname)
    
    cat > "$ENV_FILE" << EOF
# UCM Configuration - Generated on $(date)
# Directory paths
BASE_DIR=%{ucm_home}
DATA_DIR=%{ucm_data}

# Network
FQDN=${FQDN}
HTTPS_PORT=8443

# Security (DO NOT SHARE!)
SECRET_KEY=${SECRET_KEY}
JWT_SECRET_KEY=${JWT_SECRET}

# Database
DATABASE_PATH=%{ucm_data}/ucm.db

# Initial Admin (CHANGE PASSWORD AFTER LOGIN!)
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=${ADMIN_PASSWORD}
INITIAL_ADMIN_EMAIL=admin@${FQDN}

# HTTPS
HTTPS_CERT_PATH=%{ucm_data}/https_cert.pem
HTTPS_KEY_PATH=%{ucm_data}/https_key.pem

# Features
SCEP_ENABLED=true
ACME_ENABLED=true
EOF

    chmod 600 "$ENV_FILE"
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo " UCM INSTALLED!"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo " Admin: admin / ${ADMIN_PASSWORD}"
    echo " ⚠️  CHANGE PASSWORD AFTER FIRST LOGIN!"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
fi

# Set ownership
chown -R %{name}:%{name} %{ucm_home}
chown -R %{name}:%{name} %{ucm_data}
chown -R %{name}:%{name} %{ucm_config}
chown -R %{name}:%{name} %{ucm_log}
chmod 700 %{ucm_data}/{ca,certs,private,backups}

# Generate HTTPS certificate if missing
CERT_PATH="%{ucm_data}/https_cert.pem"
KEY_PATH="%{ucm_data}/https_key.pem"

if [ ! -f "$CERT_PATH" ]; then
    echo "Generating HTTPS certificate..."
    FQDN=$(hostname -f 2>/dev/null || hostname)
    IP=$(hostname -I | awk '{print $1}')
    
    cat > /tmp/ucm-ssl.cnf << SSLEOF
[req]
distinguished_name = req_distinguished_name
x509_extensions = v3_req
prompt = no

[req_distinguished_name]
CN = ${FQDN}
O = Ultimate CA Manager

[v3_req]
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = DNS:${FQDN},DNS:localhost,IP:${IP},IP:127.0.0.1
basicConstraints = critical, CA:FALSE
SSLEOF
    
    openssl req -x509 -newkey rsa:4096 -sha256 -nodes \
        -keyout "$KEY_PATH" -out "$CERT_PATH" -days 365 \
        -config /tmp/ucm-ssl.cnf -extensions v3_req 2>/dev/null
    
    rm -f /tmp/ucm-ssl.cnf
    chmod 600 "$KEY_PATH"
    chmod 644 "$CERT_PATH"
    chown %{name}:%{name} "$KEY_PATH" "$CERT_PATH"
    echo "✓ Certificate generated"
fi

# Create Python venv
if [ ! -d "%{ucm_home}/venv" ]; then
    echo "Creating Python environment..."
    cd %{ucm_home}
    python3 -m venv venv
    venv/bin/pip install --quiet --upgrade pip
    venv/bin/pip install --quiet -r requirements.txt
    chown -R %{name}:%{name} venv
    echo "✓ Python environment ready"
fi

# Initialize database
if [ ! -f "%{ucm_data}/ucm.db" ]; then
    echo "Initializing database..."
    cd %{ucm_home}/backend
    set -a; [ -f "$ENV_FILE" ] && . "$ENV_FILE"; set +a
    ../venv/bin/python init_db.py
    chown %{name}:%{name} %{ucm_data}/ucm.db
    echo "✓ Database initialized"
fi

systemctl daemon-reload >/dev/null 2>&1 || true
%systemd_post %{name}.service

FQDN=$(hostname -f 2>/dev/null || hostname)
echo ""
echo " Access: https://${FQDN}:8443"
echo " Start:  systemctl start ucm"
echo " Status: systemctl status ucm"
echo ""

%preun
%systemd_preun %{name}.service

%postun
%systemd_postun_with_restart %{name}.service
if [ $1 -eq 0 ]; then
    userdel %{name} 2>/dev/null || true
    groupdel %{name} 2>/dev/null || true
fi

%files
%{ucm_home}/
%{ucm_data}/
%dir %{ucm_config}/
%dir %{ucm_log}/
%{_unitdir}/%{name}.service
%{_bindir}/ucm-configure

%changelog
* Sun Feb 02 2026 UCM Team <dev@ucm.local> - 2.0.0-1
- Major v2.0.0 release
- Unified installation paths (/opt/ucm)
- Improved packaging for all distributions

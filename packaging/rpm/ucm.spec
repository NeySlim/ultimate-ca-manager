Name:           ucm
Version:        %{?_version}%{!?_version:1.8.0}
Release:        %{?_release}%{!?_release:1}%{?dist}
Summary:        Ultimate CA Manager - Complete PKI Management Platform

License:        Proprietary
URL:            https://github.com/kerberosmansour/ultimate-ca-manager
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3 >= 3.9
BuildRequires:  python3-pip
BuildRequires:  systemd-rpm-macros

Requires:       python3 >= 3.9
Requires:       python3-pip
Requires:       systemd
Requires:       openssl >= 1.1.1

%description
Ultimate CA Manager (UCM) is a comprehensive Public Key Infrastructure (PKI)
management platform providing:
- Root and Intermediate Certificate Authorities
- Certificate lifecycle management (create, renew, revoke, export)
- OCSP Responder
- CRL Distribution Points
- SCEP enrollment (iOS, Android, Windows, macOS MDM)
- ACME protocol support (Let's Encrypt compatible)
- WebAuthn/FIDO2 passwordless authentication
- mTLS client certificate authentication
- REST API with JWT authentication
- Email notifications for certificate expiration
- 8 beautiful themes with light/dark variants

Deployment: UCM includes a built-in HTTPS server and can run standalone
or behind a reverse proxy (nginx/apache recommended for production).

%prep
%setup -q

%build
# Nothing to build - pure Python application

%install
# Create directory structure
install -d %{buildroot}%{_sysconfdir}/%{name}
install -d %{buildroot}%{_datadir}/%{name}
install -d %{buildroot}%{_sharedstatedir}/%{name}/{cas,certs,backups,logs,temp}
install -d %{buildroot}%{_localstatedir}/log/%{name}
install -d %{buildroot}%{_unitdir}
install -d %{buildroot}%{_bindir}

# Install application files
cp -r backend %{buildroot}%{_datadir}/%{name}/
cp -r frontend %{buildroot}%{_datadir}/%{name}/
cp -r scripts %{buildroot}%{_datadir}/%{name}/

# Remove .env files (configuration is created by %post script)
find %{buildroot}%{_datadir}/%{name} -name ".env*" -delete

install -m 644 requirements.txt %{buildroot}%{_datadir}/%{name}/
install -m 644 gunicorn.conf.py %{buildroot}%{_datadir}/%{name}/
install -m 755 wsgi.py %{buildroot}%{_datadir}/%{name}/

# Install systemd service
install -m 644 packaging/rpm/ucm.service %{buildroot}%{_unitdir}/%{name}.service

# Install configuration helper
install -m 755 packaging/scripts/ucm-configure %{buildroot}%{_bindir}/ucm-configure

%pre
# Create ucm user and group
getent group %{name} >/dev/null || groupadd -r %{name}
getent passwd %{name} >/dev/null || \
    useradd -r -g %{name} -d %{_sharedstatedir}/%{name} \
    -s /sbin/nologin -c "UCM Service Account" %{name}

# Backup existing installation
if [ $1 -eq 2 ]; then
    # Upgrade - create backup
    BACKUP_DIR="/var/backups/ucm/upgrade-$(date +%%Y%%m%%d-%%H%%M%%S)"
    mkdir -p "$BACKUP_DIR"
    if [ -d "%{_sharedstatedir}/%{name}" ]; then
        cp -r %{_sharedstatedir}/%{name} "$BACKUP_DIR/"
        echo "Backup created at: $BACKUP_DIR"
    fi
fi

%post
# Generate secrets if not present
ENV_FILE="%{_sysconfdir}/%{name}/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "Generating initial configuration..."
    
    # Generate secrets
    SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
    JWT_SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
    ADMIN_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_urlsafe(16))')
    
    # Get FQDN
    FQDN=$(hostname -f 2>/dev/null || hostname)
    
    # Create .env file
    cat > "$ENV_FILE" << EOF
# UCM Configuration - Generated on $(date)
# IMPORTANT: Review and customize these settings!

# Core Settings
BASE_DIR=%{_datadir}/%{name}
DATA_DIR=%{_sharedstatedir}/%{name}
LOG_DIR=%{_localstatedir}/log/%{name}
FQDN=${FQDN}
HTTPS_PORT=8443
HTTP_PORT=8080

# Security
SECRET_KEY=${SECRET_KEY}
JWT_SECRET_KEY=${JWT_SECRET}

# Database
SQLALCHEMY_DATABASE_URI=sqlite:///%{_sharedstatedir}/%{name}/ucm.db

# Initial Admin (CHANGE PASSWORD IMMEDIATELY!)
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=${ADMIN_PASSWORD}
INITIAL_ADMIN_EMAIL=admin@${FQDN}

# HTTPS
HTTPS_AUTO_GENERATE=true
HTTPS_CERT_PATH=%{_sysconfdir}/%{name}/https_cert.pem
HTTPS_KEY_PATH=%{_sysconfdir}/%{name}/https_key.pem

# Features
SCEP_ENABLED=true
ACME_ENABLED=true
OCSP_ENABLED=true
CRL_AUTO_REGEN=true
EOF

    chmod 600 "$ENV_FILE"
    chown %{name}:%{name} "$ENV_FILE"
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo " UCM INSTALLED SUCCESSFULLY!"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo " Initial admin credentials:"
    echo "   Username: admin"
    echo "   Password: ${ADMIN_PASSWORD}"
    echo ""
    echo " ⚠️  CHANGE THIS PASSWORD IMMEDIATELY AFTER FIRST LOGIN!"
    echo ""
    echo " Configuration file: $ENV_FILE"
    echo " To reconfigure: ucm-configure"
    echo ""
fi

# Set permissions
chown -R %{name}:%{name} %{_sharedstatedir}/%{name}
chown -R %{name}:%{name} %{_localstatedir}/log/%{name}
chown -R %{name}:%{name} %{_sysconfdir}/%{name}
chmod 700 %{_sharedstatedir}/%{name}/{cas,certs,backups}
chmod 600 %{_sysconfdir}/%{name}/.env 2>/dev/null || true

# Generate self-signed HTTPS certificate compatible with modern browsers
CERT_PATH="%{_sysconfdir}/%{name}/https_cert.pem"
KEY_PATH="%{_sysconfdir}/%{name}/https_key.pem"

if [ ! -f "$CERT_PATH" ]; then
    echo "Generating HTTPS certificate..."
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
# Key Usage - critical for modern browsers (macOS/Safari/Chrome)
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
        -keyout "$KEY_PATH" \
        -out "$CERT_PATH" \
        -days 365 \
        -config /tmp/ucm-ssl.cnf \
        -extensions v3_req \
        2>/dev/null
    
    rm -f /tmp/ucm-ssl.cnf
    chmod 600 "$KEY_PATH"
    chmod 644 "$CERT_PATH"
    chown %{name}:%{name} "$KEY_PATH"
    chown %{name}:%{name} "$CERT_PATH"
    
    echo "✓ HTTPS certificate generated"
fi

# Create Python virtual environment
VENV_DIR="%{_datadir}/%{name}/venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating Python virtual environment..."
    cd %{_datadir}/%{name}
    python3 -m venv venv
    venv/bin/pip install --quiet --upgrade pip
    venv/bin/pip install --quiet -r requirements.txt
    echo "✓ Virtual environment created"
fi

# Initialize database if it doesn't exist
if [ ! -f "%{_sharedstatedir}/%{name}/ucm.db" ]; then
    echo "Initializing database..."
    cd %{_datadir}/%{name}
    # Load environment variables
    set -a
    [ -f "$ENV_FILE" ] && . "$ENV_FILE"
    set +a
    venv/bin/python backend/init_db.py
    echo "✓ Database initialized"
fi

# Force update systemd service file
if [ -f %{_datadir}/%{name}/packaging/rpm/ucm.service ]; then
    cp -f %{_datadir}/%{name}/packaging/rpm/ucm.service %{_unitdir}/ucm.service
    echo "✓ Updated systemd service file"
fi
systemctl daemon-reload >/dev/null 2>&1 || true

# Enable and start service
%systemd_post %{name}.service

echo ""
echo " Access UCM at: https://${FQDN}:8443"
echo ""
echo " Start service: systemctl start ucm"
echo " Enable on boot: systemctl enable ucm"
echo " Check status: systemctl status ucm"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

%preun
%systemd_preun %{name}.service

%postun
%systemd_postun_with_restart %{name}.service

# Remove user on uninstall (not upgrade)
if [ $1 -eq 0 ]; then
    userdel %{name} 2>/dev/null || true
    groupdel %{name} 2>/dev/null || true
fi

%files
%{_datadir}/%{name}/
%{_sysconfdir}/%{name}/
%{_sharedstatedir}/%{name}/
%{_localstatedir}/log/%{name}/
%{_unitdir}/%{name}.service
%{_bindir}/ucm-configure

%changelog
* Thu Jan 09 2026 UCM Team <dev@ucm.local> - 1.8.0-1
- Enhanced deployment infrastructure (Docker, packages, CI/CD)
- Fixed missing dependencies (Flask-Caching, pyasn1)
- Improved database initialization
- Added interactive package configuration

* Wed Jan 08 2026 UCM Team <dev@ucm.local> - 1.7.0-1
- ACME protocol Phase 1 support
- WebAuthn/FIDO2 authentication
- mTLS client authentication
- UI/UX improvements and bug fixes
- Email notifications for certificate expiry

* Tue Jan 07 2026 UCM Team <dev@ucm.local> - 1.6.2-1
- Initial RPM package
- Complete PKI management platform
- OCSP, CRL, SCEP support
- REST API and Web UI

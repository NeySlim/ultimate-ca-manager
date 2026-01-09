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
- Certificate lifecycle management
- OCSP Responder
- CRL Distribution Points
- SCEP enrollment
- ACME protocol support (Let's Encrypt compatible)
- REST API
- WebAuthn/FIDO2 authentication
- mTLS client authentication

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

# Install application files
cp -r backend %{buildroot}%{_datadir}/%{name}/
cp -r frontend %{buildroot}%{_datadir}/%{name}/
cp -r scripts %{buildroot}%{_datadir}/%{name}/
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

# Install Python dependencies
echo "Installing Python dependencies..."
cd %{_datadir}/%{name}
python3 -m pip install --quiet --no-warn-script-location -r requirements.txt

# Initialize database
echo "Initializing database..."
cd %{_datadir}/%{name}
export $(grep -v '^#' "$ENV_FILE" | xargs)
python3 -c "
import sys
sys.path.insert(0, 'backend')
from app import create_app
app = create_app()
print('Database initialized successfully!')
" 2>&1 | grep -v "WARNING\|DEPRECAT"

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

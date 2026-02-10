Name:           ucm
Version:        2.1.0~dev
Release:        1%{?dist}
Summary:        Ultimate CA Manager - Complete PKI Management Platform

License:        BSD-3-Clause
URL:            https://github.com/NeySlim/ultimate-ca-manager
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
# Disable auto-detection of requires (we manage deps via venv)
AutoReqProv:    no
Requires:       python3 >= 3.9
Requires:       python3-devel
Requires:       systemd
Requires:       openssl >= 1.1.1
Requires:       gcc-c++
Requires:       swig

# Use /opt/ucm like DEB package for consistency
%define ucm_home /opt/ucm
%define ucm_data /opt/ucm/data

%description
Ultimate CA Manager (UCM) is a comprehensive PKI management platform.

%prep
%setup -q

%build
# Nothing to build

%install
install -d %{buildroot}%{ucm_home}
install -d %{buildroot}%{ucm_home}/backend
install -d %{buildroot}%{ucm_home}/frontend
install -d %{buildroot}%{ucm_home}/scripts
install -d %{buildroot}%{ucm_data}/{ca,certs,private,crl,scep,backups,sessions}
install -d %{buildroot}%{_sysconfdir}/%{name}
install -d %{buildroot}%{_localstatedir}/log/%{name}
install -d %{buildroot}%{_unitdir}
install -d %{buildroot}/usr/lib/firewalld/services

cp -r backend/* %{buildroot}%{ucm_home}/backend/
cp -r frontend/dist %{buildroot}%{ucm_home}/frontend/
install -m 644 VERSION %{buildroot}%{ucm_home}/VERSION
find %{buildroot}%{ucm_home} -name '.env*' -delete
find %{buildroot}%{ucm_home} -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find %{buildroot}%{ucm_home} -name '*.pyc' -delete

install -m 644 backend/requirements.txt %{buildroot}%{ucm_home}/requirements.txt
install -m 755 packaging/debian/start-ucm.sh %{buildroot}%{ucm_home}/start-ucm.sh
install -m 755 packaging/scripts/configure-firewall.sh %{buildroot}%{ucm_home}/scripts/
install -m 644 packaging/firewall/ucm.xml %{buildroot}/usr/lib/firewalld/services/
install -m 644 packaging/rpm/ucm.service %{buildroot}%{_unitdir}/%{name}.service

%pre
getent group %{name} >/dev/null || groupadd -r %{name}
getent passwd %{name} >/dev/null || useradd -r -g %{name} -d %{ucm_home} -s /sbin/nologin -c "UCM Service Account" %{name}

%post
%systemd_post %{name}.service

# Install sudoers for service management (HTTPS cert apply, etc.)
cat > /etc/sudoers.d/ucm << 'SUDOERSEOF'
# UCM service management - allows ucm user to restart service without password
# This is required for HTTPS certificate application and other system operations
ucm ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart ucm
ucm ALL=(ALL) NOPASSWD: /usr/bin/systemctl reload ucm
ucm ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop ucm
ucm ALL=(ALL) NOPASSWD: /usr/bin/systemctl start ucm
SUDOERSEOF
chmod 440 /etc/sudoers.d/ucm

# Paths (same as DEB)
UCM_HOME=%{ucm_home}
UCM_DATA=%{ucm_data}
UCM_CONFIG=/etc/%{name}

mkdir -p $UCM_DATA/{ca,certs,private,crl,scep,backups,sessions}
mkdir -p /var/log/%{name}

# Check for v1.8.x data to migrate
V1_DB=""
if [ -f "$UCM_HOME/backend/data/ucm.db" ] && [ ! -f "$UCM_DATA/ucm.db" ]; then
    V1_DB="$UCM_HOME/backend/data/ucm.db"
elif [ -f "/var/lib/ucm/ucm.db" ] && [ ! -f "$UCM_DATA/ucm.db" ]; then
    V1_DB="/var/lib/ucm/ucm.db"
fi

if [ -n "$V1_DB" ]; then
    echo "Migrating v1.8.x data to v2.0..."
    cp "$V1_DB" "$UCM_DATA/ucm.db"
    V1_DIR=$(dirname "$V1_DB")
    for dir in ca certs private crl; do
        [ -d "$V1_DIR/$dir" ] && cp -r "$V1_DIR/$dir"/* "$UCM_DATA/$dir/" 2>/dev/null || true
    done
    # Update config if exists
    [ -f "$UCM_CONFIG/ucm.env" ] && sed -i "s|DATABASE_PATH=.*|DATABASE_PATH=$UCM_DATA/ucm.db|" "$UCM_CONFIG/ucm.env"
    echo "✓ Migration complete"
fi

# Generate secrets
ADMIN_PASS=$(openssl rand -hex 8)
SECRET_KEY=$(openssl rand -hex 32)
JWT_SECRET=$(openssl rand -hex 32)

# Create config if not exists
if [ ! -f "$UCM_CONFIG/ucm.env" ]; then
    cat > "$UCM_CONFIG/ucm.env" << ENVEOF
# UCM Configuration - Generated on install
DATABASE_PATH=$UCM_DATA/ucm.db
DATA_DIR=$UCM_DATA
HTTPS_PORT=8443
LOG_LEVEL=INFO

# Security (auto-generated - keep secret)
SECRET_KEY=$SECRET_KEY
JWT_SECRET_KEY=$JWT_SECRET
INITIAL_ADMIN_PASSWORD=$ADMIN_PASS
ENVEOF
    chmod 600 "$UCM_CONFIG/ucm.env"
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo " UCM INSTALLED"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo " Admin password: $ADMIN_PASS"
    echo " Config: $UCM_CONFIG/ucm.env"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
fi

# Create venv if gunicorn not found
if [ ! -f "$UCM_HOME/venv/bin/gunicorn" ]; then
    echo "Creating Python virtual environment..."
    rm -rf "$UCM_HOME/venv" 2>/dev/null || true
    python3 -m venv "$UCM_HOME/venv"
    "$UCM_HOME/venv/bin/pip" install --quiet --upgrade pip
    "$UCM_HOME/venv/bin/pip" install --quiet -r "$UCM_HOME/requirements.txt"
fi

# Set permissions
chown -R %{name}:%{name} $UCM_HOME
chown -R %{name}:%{name} $UCM_CONFIG
chown -R %{name}:%{name} /var/log/%{name}
chmod 750 $UCM_DATA

# Generate HTTPS cert if not exists
if [ ! -f "$UCM_DATA/https_cert.pem" ]; then
    echo "Generating HTTPS certificate..."
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
        -keyout "$UCM_DATA/https_key.pem" \
        -out "$UCM_DATA/https_cert.pem" \
        -subj "/CN=ucm/O=UCM/OU=PKI" 2>/dev/null
    chown %{name}:%{name} "$UCM_DATA"/https_*.pem
    chmod 600 "$UCM_DATA/https_key.pem"
    chmod 644 "$UCM_DATA/https_cert.pem"
fi

# Automatic migration from v1.8.x
V1_DATA="$UCM_HOME/backend/data"
if [ -f "$V1_DATA/ucm.db" ] && [ ! -f "$UCM_DATA/ucm.db" ]; then
    echo "Detected UCM v1.8.x - running automatic migration..."
    if [ -f "$UCM_HOME/backend/migrate_v1_to_v2.py" ]; then
        python3 "$UCM_HOME/backend/migrate_v1_to_v2.py" "$UCM_HOME" 2>&1 | tee /var/log/%{name}/migration.log
    fi
fi

# Start service
systemctl daemon-reload
systemctl enable %{name}
systemctl start %{name} || true

# Configure firewall if script exists
if [ -x "$UCM_HOME/scripts/configure-firewall.sh" ]; then
    "$UCM_HOME/scripts/configure-firewall.sh" || true
fi

%preun
%systemd_preun %{name}.service

%postun
%systemd_postun_with_restart %{name}.service

%files
%{ucm_home}/
%dir %{_sysconfdir}/%{name}/
%dir %{_localstatedir}/log/%{name}/
%{_unitdir}/%{name}.service
/usr/lib/firewalld/services/ucm.xml

%changelog
* Fri Feb 07 2026 UCM Team <dev@ucm.local> - 2.1.0-1
- Unified release: Pro features merged into main
- Interactive firewall configuration on install
- i18n support (9 languages)
- Column resize in tables

* Mon Feb 03 2026 UCM Team <dev@ucm.local> - 2.0.0-1
- Version 2.0.0 release
- Pro features: HSM, SSO, RBAC, Groups
- WebAuthn multi-key support
- Service restart permissions

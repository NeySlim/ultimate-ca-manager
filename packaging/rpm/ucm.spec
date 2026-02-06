Name:           ucm
Version:        2.0.0
Release:        1%{?dist}
Summary:        Ultimate CA Manager - Complete PKI Management Platform

License:        Proprietary
URL:            https://github.com/NeySlim/ultimate-ca-manager
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
Requires:       python3 >= 3.9
Requires:       systemd
Requires:       openssl >= 1.1.1

%description
Ultimate CA Manager (UCM) is a comprehensive PKI management platform.

%prep
%setup -q

%build
# Nothing to build

%install
install -d %{buildroot}%{_sysconfdir}/%{name}
install -d %{buildroot}%{_datadir}/%{name}
install -d %{buildroot}%{_sharedstatedir}/%{name}/{cas,certs,backups,logs,temp}
install -d %{buildroot}%{_localstatedir}/log/%{name}
install -d %{buildroot}%{_unitdir}
install -d %{buildroot}%{_bindir}

cp -r backend %{buildroot}%{_datadir}/%{name}/
cp -r frontend %{buildroot}%{_datadir}/%{name}/
cp -r packaging/scripts %{buildroot}%{_datadir}/%{name}/
find %{buildroot}%{_datadir}/%{name} -name '.env*' -delete

install -m 644 backend/requirements.txt %{buildroot}%{_datadir}/%{name}/requirements.txt
install -m 644 gunicorn.conf.py %{buildroot}%{_datadir}/%{name}/
install -m 644 backend/wsgi.py %{buildroot}%{_datadir}/%{name}/wsgi.py
install -m 755 packaging/rpm/start-ucm.sh %{buildroot}%{_datadir}/%{name}/start-ucm.sh
install -m 644 packaging/rpm/ucm.service %{buildroot}%{_unitdir}/%{name}.service

%pre
getent group %{name} >/dev/null || groupadd -r %{name}
getent passwd %{name} >/dev/null || useradd -r -g %{name} -d %{_sharedstatedir}/%{name} -s /sbin/nologin -c "UCM Service Account" %{name}

%post
%systemd_post %{name}.service
echo "ucm ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart ucm, /usr/bin/systemctl reload ucm" > /etc/sudoers.d/ucm-service
chmod 440 /etc/sudoers.d/ucm-service

# Create data directories
UCM_DATA=/var/lib/%{name}
mkdir -p $UCM_DATA/{ca,certs,private,sessions,backups}
mkdir -p /var/log/%{name}

# Generate secrets
ADMIN_PASS=$(openssl rand -hex 8)
SECRET_KEY=$(openssl rand -hex 32)
JWT_SECRET=$(openssl rand -hex 32)

# Create config if not exists
if [ ! -f /etc/%{name}/ucm.env ]; then
    cat > /etc/%{name}/ucm.env << ENVEOF
# UCM Configuration - Generated on install
DATABASE_PATH=/var/lib/ucm/ucm.db
DATA_DIR=/var/lib/ucm
HTTPS_PORT=8443
LOG_LEVEL=INFO

# Security (auto-generated - keep secret)
SECRET_KEY=$SECRET_KEY
JWT_SECRET_KEY=$JWT_SECRET
INITIAL_ADMIN_PASSWORD=$ADMIN_PASS
ENVEOF
    chmod 600 /etc/%{name}/ucm.env
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo " UCM INSTALLED"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo " Admin password: $ADMIN_PASS"
    echo " Config: /etc/%{name}/ucm.env"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
fi

# Create venv if gunicorn not found
if [ ! -f /usr/share/%{name}/venv/bin/gunicorn ]; then
    echo "Creating Python virtual environment..."
    rm -rf /usr/share/%{name}/venv 2>/dev/null || true
    python3 -m venv /usr/share/%{name}/venv
    /usr/share/%{name}/venv/bin/pip install --quiet --upgrade pip
    /usr/share/%{name}/venv/bin/pip install --quiet -r /usr/share/%{name}/requirements.txt
fi

# Set permissions
chown -R %{name}:%{name} $UCM_DATA
chown -R %{name}:%{name} /var/log/%{name}
chown -R %{name}:%{name} /etc/%{name}

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
V1_DATA="/usr/share/%{name}/backend/data"
if [ -f "$V1_DATA/ucm.db" ] && [ ! -f "$UCM_DATA/ucm.db" ]; then
    echo "Detected UCM v1.8.x - running automatic migration..."
    if [ -f "/usr/share/%{name}/backend/migrate_v1_to_v2.py" ]; then
        python3 /usr/share/%{name}/backend/migrate_v1_to_v2.py /usr/share/%{name} 2>&1 | tee /var/log/%{name}/migration.log
    fi
fi

# Start service
systemctl daemon-reload
systemctl enable %{name}
systemctl start %{name} || true

%preun
%systemd_preun %{name}.service

%postun
%systemd_postun_with_restart %{name}.service

%files
%{_datadir}/%{name}/
%dir %{_sysconfdir}/%{name}/
%dir %{_sharedstatedir}/%{name}/
%dir %{_localstatedir}/log/%{name}/
%{_unitdir}/%{name}.service

%changelog
* Mon Feb 03 2026 UCM Team <dev@ucm.local> - 2.0.0-1
- Version 2.0.0 release
- Pro features: HSM, SSO, RBAC, Groups
- WebAuthn multi-key support
- Service restart permissions

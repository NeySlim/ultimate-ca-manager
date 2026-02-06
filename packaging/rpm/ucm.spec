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
cp -r scripts %{buildroot}%{_datadir}/%{name}/
find %{buildroot}%{_datadir}/%{name} -name '.env*' -delete

install -m 644 requirements.txt %{buildroot}%{_datadir}/%{name}/
install -m 644 gunicorn.conf.py %{buildroot}%{_datadir}/%{name}/
install -m 755 wsgi.py %{buildroot}%{_datadir}/%{name}/
install -m 644 packaging/rpm/ucm.service %{buildroot}%{_unitdir}/%{name}.service
install -m 755 packaging/scripts/ucm-configure %{buildroot}%{_bindir}/ucm-configure

%pre
getent group %{name} >/dev/null || groupadd -r %{name}
getent passwd %{name} >/dev/null || useradd -r -g %{name} -d %{_sharedstatedir}/%{name} -s /sbin/nologin -c "UCM Service Account" %{name}

%post
%systemd_post %{name}.service
echo "ucm ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart ucm, /usr/bin/systemctl reload ucm" > /etc/sudoers.d/ucm-service
chmod 440 /etc/sudoers.d/ucm-service

# Create data directories
mkdir -p /var/lib/%{name}/{ca,certs,private,sessions,backups}
mkdir -p /var/log/%{name}
chown -R %{name}:%{name} /var/lib/%{name}
chown -R %{name}:%{name} /var/log/%{name}

# Automatic migration from v1.8.x
V1_DATA="/usr/share/%{name}/backend/data"
V2_DATA="/var/lib/%{name}"
if [ -f "$V1_DATA/ucm.db" ] && [ ! -f "$V2_DATA/ucm.db" ]; then
    echo "Detected UCM v1.8.x - running automatic migration..."
    if [ -x "/usr/share/%{name}/scripts/migrate-v1-to-v2.sh" ]; then
        UCM_HOME="/usr/share/%{name}" UCM_DATA="$V2_DATA" /usr/share/%{name}/scripts/migrate-v1-to-v2.sh
    elif [ -f "/usr/share/%{name}/backend/migrate_v1_to_v2.py" ]; then
        python3 /usr/share/%{name}/backend/migrate_v1_to_v2.py /usr/share/%{name} 2>&1 | tee /var/log/%{name}/migration.log
    fi
fi

%preun
%systemd_preun %{name}.service

%postun
%systemd_postun_with_restart %{name}.service

%files
%{_datadir}/%{name}/
%{_sysconfdir}/%{name}/
%{_sharedstatedir}/%{name}/
%{_localstatedir}/log/%{name}/
%{_unitdir}/%{name}.service
%{_bindir}/ucm-configure

%changelog
* Mon Feb 03 2026 UCM Team <dev@ucm.local> - 2.0.0-1
- Version 2.0.0 release
- Pro features: HSM, SSO, RBAC, Groups
- WebAuthn multi-key support
- Service restart permissions

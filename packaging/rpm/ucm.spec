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
chown -R %{name}:%{name} %{_sharedstatedir}/%{name}
chown -R %{name}:%{name} %{_localstatedir}/log/%{name}

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

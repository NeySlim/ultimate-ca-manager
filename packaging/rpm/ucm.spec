Name:           ucm
Version:        0.0.0
Release:        1%{?dist}
Summary:        Ultimate Certificate Manager - Complete PKI Management Platform

License:        AGPL-3.0-only
URL:            https://github.com/NeySlim/ultimate-ca-manager
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
# Disable auto-detection of requires (we manage deps via venv)
AutoReqProv:    no
# EL9's python3 is 3.9: the el9 build runs on the parallel-installable python3.12.
# EL10's python3 is 3.12: it takes the system python3 like Fedora
%if 0%{?rhel} && 0%{?rhel} < 10
Requires:       python3.12
%global ucm_python python3.12
%else
Requires:       python3 >= 3.12
%global ucm_python python3
%endif
Requires:       systemd
Requires:       openssl >= 1.1.1
Requires:       logrotate
Recommends:     softhsm
Suggests:       openldap-clients

# Use /opt/ucm like DEB package for consistency
%define ucm_home /opt/ucm
%define ucm_data /opt/ucm/data

%description
Ultimate Certificate Manager (UCM) is a comprehensive PKI management platform.

%prep
%setup -q

%build
# Nothing to build

%install
install -d %{buildroot}%{ucm_home}
install -d %{buildroot}%{ucm_home}/backend
install -d %{buildroot}%{ucm_home}/frontend
install -d %{buildroot}%{ucm_home}/scripts
# Listed one by one on purpose: %%install runs under /bin/sh, and a shell
# without brace expansion would create a single directory named after the
# whole list instead of the seven wanted here
for d in ca certs private crl scep backups sessions; do
    install -d %{buildroot}%{ucm_data}/$d
done
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
install -m 755 packaging/scripts/ucm-watcher.sh %{buildroot}%{ucm_home}/scripts/
install -m 755 packaging/scripts/native-setup.sh %{buildroot}%{ucm_home}/scripts/
install -m 755 packaging/scripts/archive-leftovers.sh %{buildroot}%{ucm_home}/scripts/
install -m 644 packaging/firewall/ucm.xml %{buildroot}/usr/lib/firewalld/services/
# Log rotation for the gunicorn streams (#350)
install -d %{buildroot}%{_sysconfdir}/logrotate.d
install -m 644 packaging/logrotate/ucm %{buildroot}%{_sysconfdir}/logrotate.d/%{name}
install -m 644 packaging/rpm/ucm.service %{buildroot}%{_unitdir}/%{name}.service
install -m 644 packaging/systemd/ucm-watcher.path %{buildroot}%{_unitdir}/%{name}-watcher.path
install -m 644 packaging/systemd/ucm-watcher.service %{buildroot}%{_unitdir}/%{name}-watcher.service

%pre
# Refused over a UCM older than 2.254 before the account or any file is written;
# the guard is embedded by packaging/scripts/embed-pivot-guard.sh before rpmbuild
# @UCM_PIVOT_GUARD@
command -v ucm_pivot_guard >/dev/null || exit 1
# rpm -q prints "package ucm is not installed" and fails on a first install
ucm_installed=$(rpm -q --qf '%%{VERSION}\n' %{name} 2>/dev/null) || ucm_installed=""
# $1 is 2 or more on an upgrade: a version that cannot be read is no reason to go on
if [ "$1" -ge 2 ] && [ -z "$ucm_installed" ]; then
    echo "The installed UCM version could not be read: this package was not installed." >&2
    exit 1
fi
for ucm_version in $ucm_installed; do
    ucm_pivot_guard "$ucm_version" || exit 1
done
getent group %{name} >/dev/null || groupadd -r %{name}
getent passwd %{name} >/dev/null || useradd -r -g %{name} -d %{ucm_home} -s /sbin/nologin -c "UCM Service Account" %{name}

%post
# Set first on a new install: a scriptlet that fails or is killed anywhere below leaves
# it, so the reinstall that retries ($1 = 2) still archives what a removed UCM left
UCM_HOME=%{ucm_home}
ARCHIVE_PENDING=$UCM_HOME/.leftover-archive-pending
[ "$1" -ne 1 ] || : > "$ARCHIVE_PENDING"

%systemd_post %{name}.service

# sudoers-cleanup: no sudo grant any more (the watcher restarts the service);
# drop the files earlier versions wrote. Absent file or directory is fine.
rm -f /etc/sudoers.d/ucm-service /etc/sudoers.d/ucm
# end sudoers-cleanup

# Enable ucm-watcher path unit for restart/update handling
systemctl daemon-reload
systemctl enable ucm-watcher.path
systemctl start ucm-watcher.path

# Paths (same as DEB)
UCM_DATA=%{ucm_data}
UCM_CONFIG=/etc/%{name}
UCM_SETUP=$UCM_HOME/scripts/native-setup.sh
NEW_CONFIG=""
mkdir -p /var/log/%{name}
# Resumed after a failed first attempt: the service never had a working venv
bash "$UCM_SETUP" venv-ok "$UCM_HOME" || NEW_CONFIG=1

# Built before anything is written to the data or the configuration: the archiving
# below asks this release's runner about the database left there
echo "Creating Python virtual environment..."
BUILT_FIPS=""
! bash "$UCM_SETUP" fips-requested "$UCM_CONFIG/ucm.env" || BUILT_FIPS=1
# A failed UCM_FIPS_BUILD=1 build fails the scriptlet; the standard install keeps going as before
if ! bash "$UCM_SETUP" venv "$UCM_HOME" %{ucm_python} rpm "$UCM_CONFIG/ucm.env"; then
    bash "$UCM_SETUP" fips-requested "$UCM_CONFIG/ucm.env" && exit 1
fi

# $1 is 1 when no UCM package was installed, 2 on the reinstall that retries an attempt
# that failed or was killed (its mark, or an archive journal left): archive what a
# removed one left when this release refuses it. The mark is set first; a failure
# stops here: nothing below may run.
ARCHIVE_DUE=""
if [ "$1" -eq 1 ] || [ -e "$ARCHIVE_PENDING" ]; then
    ARCHIVE_DUE=1
fi
for journal in "${UCM_HOME%%/*}"/ucm-archive/*/.journal; do
    [ ! -e "$journal" ] || ARCHIVE_DUE=1
done
# 3: a database left in place that the service will refuse, which the archiver has
# explained: no success banner follows that
LEFT_REFUSED=""
if [ -n "$ARCHIVE_DUE" ]; then
    : > "$ARCHIVE_PENDING"
    ARCHIVE_RC=0
    sh "$UCM_HOME/scripts/archive-leftovers.sh" "$UCM_HOME" "$UCM_DATA" "$UCM_CONFIG" || ARCHIVE_RC=$?
    case $ARCHIVE_RC in
        0) ;;
        3) LEFT_REFUSED=1 ;;
        *) echo "UCM was not set up. Fix the cause, then run: dnf reinstall ucm"
           exit 1 ;;
    esac
    rm -f "$ARCHIVE_PENDING"
    # A retry built the venv while ucm.env was still in the archive; the archiver then
    # carried its UCM_FIPS_BUILD=1 over: the standard venv is built again
    if [ -z "$BUILT_FIPS" ] && bash "$UCM_SETUP" fips-requested "$UCM_CONFIG/ucm.env"; then
        echo "UCM_FIPS_BUILD=1 came back after the Python environment was built: building it again against the system OpenSSL..."
        bash "$UCM_SETUP" venv "$UCM_HOME" %{ucm_python} rpm "$UCM_CONFIG/ucm.env" || exit 1
    fi
fi

# Listed one by one for the same reason as in %%install: this scriptlet
# runs under /bin/sh, which does not always expand braces
for d in ca certs private crl scep backups sessions; do
    mkdir -p $UCM_DATA/$d
done
mkdir -p $UCM_CONFIG

# SoftHSM setup: add ucm user to softhsm/ods group and prepare token directory
HSM_GROUP=""
if getent group softhsm >/dev/null 2>&1; then
    HSM_GROUP="softhsm"
elif getent group ods >/dev/null 2>&1; then
    HSM_GROUP="ods"
fi
if [ -n "$HSM_GROUP" ]; then
    usermod -aG "$HSM_GROUP" %{name} 2>/dev/null || true
    mkdir -p /var/lib/softhsm/tokens
    chown root:"$HSM_GROUP" /var/lib/softhsm/tokens
    chmod 1770 /var/lib/softhsm/tokens
fi

# Generate secrets
SECRET_KEY=$(openssl rand -hex 32)

# Create config if not exists
if [ ! -f "$UCM_CONFIG/ucm.env" ]; then
    NEW_CONFIG=1
    cat > "$UCM_CONFIG/ucm.env" << ENVEOF
# UCM Configuration - Generated on install
DATABASE_PATH=$UCM_DATA/ucm.db
DATA_DIR=$UCM_DATA
HTTPS_PORT=8443
HTTP_PROTOCOL_PORT=8080
LOG_LEVEL=INFO

# Security (auto-generated - keep secret)
SECRET_KEY=$SECRET_KEY

# Initial admin (first start only). Unset: the first start writes a generated password
# to $UCM_DATA/initial-admin-password (read it with sudo cat), to change at first login.
# To choose it, write one of these into this file BEFORE installing the package
# (it starts UCM), and remove it after the first start:
# INITIAL_ADMIN_PASSWORD_FILE=/etc/ucm/admin-password   (readable by the ucm user)
# INITIAL_ADMIN_PASSWORD=
ENVEOF
    chmod 600 "$UCM_CONFIG/ucm.env"
fi
# A file written before the install (UCM_FIPS_BUILD=1 alone) gets its secrets and defaults
ENV_STATE=$(bash "$UCM_SETUP" env "$UCM_CONFIG/ucm.env" "$UCM_DATA") || exit 1
[ "$ENV_STATE" != new ] || NEW_CONFIG=1

# Set permissions
chown -R %{name}:%{name} $UCM_HOME
chown -R %{name}:%{name} $UCM_CONFIG
chown -R %{name}:%{name} /var/log/%{name}
chmod 750 $UCM_DATA

# Host FIPS state, UCM_FIPS and readiness report (UCM_FIPS_BUILD=1 only)
bash "$UCM_SETUP" fips-finish "$UCM_HOME" "$UCM_CONFIG/ucm.env" "$UCM_DATA" %{name}
# Shown once the venv is built, so a failed build never follows the banner
if [ -n "$NEW_CONFIG" ] && [ -z "$LEFT_REFUSED" ]; then
    bash "$UCM_SETUP" banner "$UCM_CONFIG/ucm.env" rpm
fi

# Generate HTTPS cert if not exists
if [ ! -f "$UCM_DATA/https_cert.pem" ]; then
    echo "Generating HTTPS certificate..."
    # Detect hostname and IPs for SAN
    CERT_HOST=$(hostname -f 2>/dev/null || hostname)
    CERT_IPS=""
    for ip in $(hostname -I 2>/dev/null); do
        CERT_IPS="${CERT_IPS},IP:${ip}"
    done
    CERT_SAN="DNS:${CERT_HOST},DNS:localhost,IP:127.0.0.1${CERT_IPS}"
    
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
        -keyout "$UCM_DATA/https_key.pem" \
        -out "$UCM_DATA/https_cert.pem" \
        -subj "/CN=${CERT_HOST}/O=UCM/OU=PKI" \
        -addext "subjectAltName=${CERT_SAN}" 2>/dev/null
    chown %{name}:%{name} "$UCM_DATA"/https_*.pem
    chmod 600 "$UCM_DATA/https_key.pem"
    chmod 644 "$UCM_DATA/https_cert.pem"
fi

# Start/restart service
systemctl daemon-reload
systemctl enable %{name}
if systemctl is-active --quiet %{name}; then
    systemctl restart %{name} || true
else
    systemctl start %{name} || true
fi

# Configure firewall if script exists
if [ -x "$UCM_HOME/scripts/configure-firewall.sh" ]; then
    "$UCM_HOME/scripts/configure-firewall.sh" || true
fi

%preun
%systemd_preun %{name}.service
%systemd_preun %{name}-watcher.path

%postun
%systemd_postun_with_restart %{name}.service
# Erased ($1 = 0): the mark of an archiving left pending goes with the package
[ "$1" -ne 0 ] || rm -f %{ucm_home}/.leftover-archive-pending

%files
%license LICENSE NOTICE COMMERCIAL-LICENSE.md
%{ucm_home}/
%dir %attr(0750,%{name},%{name}) %{_sysconfdir}/%{name}/
%config(noreplace) %{_sysconfdir}/logrotate.d/%{name}
%dir %{_localstatedir}/log/%{name}/
%{_unitdir}/%{name}.service
%{_unitdir}/%{name}-watcher.path
%{_unitdir}/%{name}-watcher.service
/usr/lib/firewalld/services/ucm.xml

%changelog
* Sat Feb 07 2026 UCM Team <dev@ucm.local> - 2.1.0-1
- Unified release: Pro features merged into main
- Interactive firewall configuration on install
- i18n support (9 languages)
- Column resize in tables

* Tue Feb 03 2026 UCM Team <dev@ucm.local> - 2.0.0-1
- Version 2.0.0 release
- Pro features: HSM, SSO, RBAC, Groups
- WebAuthn multi-key support
- Service restart permissions

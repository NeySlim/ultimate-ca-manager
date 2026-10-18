# Installation Guide

This guide covers all installation methods for Ultimate Certificate Manager.

## System Requirements

### Minimum Requirements
- **CPU:** 2 cores
- **RAM:** 2 GB
- **Storage:** 5 GB free space
- **OS:** Linux (any distribution)

### Recommended Requirements
- **CPU:** 4 cores
- **RAM:** 4 GB
- **Storage:** 20 GB free space (for CA data and backups)

### Software Requirements
- **Docker:** 20.10+ (for Docker installation)
- **Python:** 3.11+ (for source installation)
- **Node.js:** 20.19+ or 22.12+ with npm (to build the web interface from source)
- **Database:** SQLite (included) or PostgreSQL 13+ (optional, set via `DATABASE_URL`)

### Optional: Kerberos/SPNEGO support

Windows Autoenrollment's Kerberos binding (silent GPO autoenrollment via MS-XCEP/MS-WSTEP) needs an extra dependency that none of the methods above install by default, since it requires a C compiler and the system's Kerberos headers to build:

```bash
# Debian/Ubuntu
apt-get install -y libkrb5-dev build-essential python3-dev
# RHEL/Rocky/Alma
dnf install -y krb5-devel gcc python3-devel

pip install pyspnego[kerberos]   # run inside the venv UCM uses, e.g. /opt/ucm/venv
systemctl restart ucm
```

Skip this if you don't need Kerberos/SPNEGO — every other autoenrollment binding (username/password, certificate) works without it. See the "Windows Autoenrollment" section in [ADMIN_GUIDE.md](../ADMIN_GUIDE.md) for details.

---

## Installation Methods

### Method 1: Docker (Recommended)

**Fastest and easiest installation method with automatic updates.**

See: [Docker Installation Guide](docker.md)

```bash
docker run -d \
  --name ucm \
  -p 8443:8443 \
  -p 8080:8080 \
  -v ucm-data:/opt/ucm/data \
  neyslim/ultimate-ca-manager:latest
```

**Access:** https://localhost:8443 or https://your-server-fqdn:8443  
**Default credentials:** admin / changeme123

---

### Method 2: Debian/Ubuntu Package

**Native installation for Debian, Ubuntu, and derivatives.**

```bash
# Download latest package (replace VERSION with actual version, e.g. 2.1.0)
wget https://github.com/NeySlim/ultimate-ca-manager/releases/latest/download/ucm_VERSION_all.deb

# Install
sudo dpkg -i ucm_VERSION_all.deb
sudo apt-get install -f  # Fix any dependencies

# Enable and start
sudo systemctl enable ucm
sudo systemctl start ucm
sudo systemctl status ucm
```

**Access:** https://localhost:8443 or https://your-server-fqdn:8443

---

### Method 3: Fedora and RHEL/Rocky/Alma Package

**Native installation for Fedora, Red Hat Enterprise Linux, Rocky Linux, AlmaLinux, and derivatives.**

Each release has two RPMs: `ucm-VERSION-1.fc43.noarch.rpm` for Fedora, and `ucm-el9-VERSION-1.el9.noarch.rpm` for RHEL, Rocky Linux and AlmaLinux 9, which runs on the `python3.12` package of the distribution (its `python3` is 3.9).

```bash
# Download latest package (replace VERSION with actual version, e.g. 2.241)
wget https://github.com/NeySlim/ultimate-ca-manager/releases/latest/download/ucm-el9-VERSION-1.el9.noarch.rpm

# Install
sudo dnf install ./ucm-el9-VERSION-1.el9.noarch.rpm

# Enable and start
sudo systemctl enable ucm
sudo systemctl start ucm
sudo systemctl status ucm
```

**Access:** https://localhost:8443 or https://your-server-fqdn:8443

---

### FIPS hosts: DEB and RPM built against the system OpenSSL

The packages install pre-built Python wheels, and the `cryptography` and `psycopg2-binary` wheels carry their own OpenSSL, which ignores the FIPS mode of the host. On RHEL 9 (or AlmaLinux and Rocky Linux 9) and on Ubuntu 24.04 (Ubuntu Pro for the FIPS module), `UCM_FIPS_BUILD=1` makes the package compile `cryptography`, `psycopg2`, `lxml` and `xmlsec` against the system OpenSSL instead. Other distributions refuse the option.

1. Install the build tools.

   RHEL 9 needs the CodeReady Builder repository (`sudo subscription-manager repos --enable codeready-builder-for-rhel-9-$(arch)-rpms`); on AlmaLinux and Rocky Linux it is CRB:

   ```bash
   sudo dnf config-manager --set-enabled crb
   sudo dnf install -y python3.12-devel gcc pkgconf-pkg-config libpq-devel libxml2-devel libxslt-devel \
       openssl-devel xmlsec1-devel xmlsec1-openssl libtool-ltdl-devel rust cargo
   ```

   Ubuntu 24.04 (its default Rust 1.75 is too old, the package uses `rustc-1.91` from `/usr/lib/rust-1.91/bin`):

   ```bash
   sudo apt-get install -y gcc pkg-config python3-dev python3-venv libpq-dev libxml2-dev libxslt1-dev \
       zlib1g-dev libssl-dev libxmlsec1-dev libxmlsec1t64-openssl rustc-1.91 cargo-1.91
   ```

2. Ask for the build before installing, then install the package:

   ```bash
   sudo install -d -m 750 /etc/ucm && echo 'UCM_FIPS_BUILD=1' | sudo tee /etc/ucm/ucm.env
   sudo dnf install ./ucm-el9-VERSION-1.el9.noarch.rpm  # or: sudo apt install ./ucm_VERSION_all.deb
   ```

   The package completes `/etc/ucm/ucm.env` with its secrets and defaults. `sudo UCM_FIPS_BUILD=1 dnf install ...` works too and records the option in `ucm.env` (a variable exported before `sudo` does not reach the package). The first build takes about five minutes (log: `/var/log/ucm/fips-build.log`). Later installs rebuild a package only when its version changed, and otherwise reuse pip's wheel cache. When a tool is missing or the build fails, the installation stops with the command to run, and an upgrade keeps the previous environment. The built-in updater checks the build tools before installing: when one is missing it refuses the update and leaves the installation untouched, and a failed build is reported as a failed update.

3. When the host is in FIPS mode (`/proc/sys/crypto/fips_enabled` is 1), the package adds `UCM_FIPS=1` to `ucm.env` (an explicit `UCM_FIPS=0` is kept), checks that the FIPS provider is active, and prints the readiness report of `python -m scripts.fips_preflight`. Otherwise UCM runs in standard mode on the system OpenSSL: enable FIPS mode with `sudo fips-mode-setup --enable` (RHEL) or `sudo pro enable fips-updates` (Ubuntu Pro), reboot, and reinstall the package.

TLS follows the host's configuration: with the FIPS crypto policy of RHEL 9 and the FIPS module of Ubuntu 24.04, X25519 and X448 are not offered, and UCM refuses to start in FIPS mode when its TLS contexts still accept them.

A standard package installed on a host in FIPS mode prints a reminder to set `UCM_FIPS_BUILD=1`. To return to the standard build, remove the line from `ucm.env` and reinstall.

---

### Method 4: From Source

**For development or custom deployments.**

```bash
# Clone repository
git clone https://github.com/NeySlim/ultimate-ca-manager.git
cd ultimate-ca-manager

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Build the web interface (served from frontend/dist)
(cd frontend && npm ci && npm run build)

# Run
python wsgi.py
```

Building the Docker image from a clone needs the same frontend build first: the `Dockerfile` copies `frontend/dist/` as is.

```bash
(cd frontend && npm ci && npm run build)
docker build -t ucm:local .
```

**Access:** https://localhost:8443 or https://your-server-fqdn:8443

---

## First Login

After installation, access UCM at **https://localhost:8443** (or **https://your-server-fqdn:8443** for remote access)

**Default Credentials:**
- **Username:** admin
- **Password:** `changeme123`

**IMPORTANT:** Change the default password immediately after first login!

---

## Data Locations

### Docker
- **Data:** `/opt/ucm/data` (inside container, mount as volume)
- **Volume:** `ucm-data` (Docker volume)
- **Config:** Environment variables

### DEB/RPM Packages
- **Data:** `/opt/ucm/data`
- **Config:** `/etc/ucm/ucm.env`
- **Logs:** `/var/log/ucm/`
- **Service:** `/etc/systemd/system/ucm.service`

### Source Installation
- **Data:** `./backend/data` (relative to repository root)
- **Config:** Environment variables or `/etc/ucm/ucm.env`
- **Logs:** `/var/log/ucm/ucm.log`

---

## Next Steps

After installation:

1. **Change default password** — Settings → Users & Groups
2. **Configure HTTPS certificate** — Upload a trusted certificate or use the auto-generated one
3. **Create your first CA** — Dashboard → Create Certificate Authority
4. **Configure email notifications** (optional) — Settings → SMTP
5. **Enable ACME/SCEP** (optional) — ACME / SCEP pages

---

## Additional Resources

- [Docker Deployment Guide](docker.md)
- [Upgrade Guide](../../UPGRADE.md)
- [Redis (future high-availability mode)](../REDIS.md)

---

## Support

- **Issues:** [GitHub Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)
- **Wiki:** [GitHub Wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki)
- **Discussions:** [GitHub Discussions](https://github.com/NeySlim/ultimate-ca-manager/discussions)

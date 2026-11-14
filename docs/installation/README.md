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

Windows Autoenrollment's Kerberos binding (silent GPO autoenrollment via MS-XCEP/MS-WSTEP) needs an extra dependency. The Docker images ship it; the DEB, RPM and source installs do not install it by default, since it requires a C compiler and the system's Kerberos headers to build:

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
  -v ucm-config:/etc/ucm \
  neyslim/ultimate-ca-manager:latest
```

**Access:** https://localhost:8443 or https://your-server-fqdn:8443  
**First login:** `admin`, password read with `docker exec ucm cat /opt/ucm/data/initial-admin-password` (see [First access](#first-access))

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

Each release has three RPMs: `ucm-VERSION-1.fc43.noarch.rpm` for Fedora, `ucm-el9-VERSION-1.el9.noarch.rpm` for RHEL, Rocky Linux and AlmaLinux 9, which runs on the `python3.12` package of the distribution (its `python3` is 3.9), and `ucm-el10-VERSION-1.el10.noarch.rpm` for the same distributions at 10, which runs on the system `python3` (3.12). FIPS builds of the packages are supported on EL9 and Ubuntu 24.04 only.

```bash
# Download latest package (replace VERSION with the actual version, e.g. 2.241,
# and el9 with el10 on RHEL, Rocky Linux or AlmaLinux 10)
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

The packages install pre-built Python wheels, and the `cryptography` and `psycopg-binary` wheels carry their own OpenSSL, which ignores the FIPS mode of the host. On RHEL 9 (or AlmaLinux and Rocky Linux 9) and on Ubuntu 24.04 (Ubuntu Pro for the FIPS module), `UCM_FIPS_BUILD=1` makes the package compile `cryptography`, `psycopg`, `lxml` and `xmlsec` against the system OpenSSL instead. Other distributions refuse the option.

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

#### What FIPS mode allows on each installation

In FIPS mode UCM asks the loaded module whether it approves ML-DSA, Ed25519 and Ed448, and allows them only when it does; RSA 2048+ and ECDSA on P-256, P-384 and P-521 are allowed everywhere.

| Installation | FIPS module (CMVP certificate) | ML-DSA-44/65/87 | Ed25519, Ed448 |
|---|---|---|---|
| Docker image `-fips` | OpenSSL FIPS Provider 3.5.9 (#5586) | allowed | allowed |
| DEB, Ubuntu 24.04 Pro | Ubuntu 24.04 OpenSSL Cryptographic Module (#5115) | refused | refused |
| RPM, RHEL 9 | Red Hat Enterprise Linux 9 OpenSSL FIPS Provider (#5573) | refused | refused |

- The binary certified under #5115 is the one of Ubuntu Pro's `fips` stream; `fips-updates` carries later, patched versions that are not the certified binary.
- The image is built on Debian 13, and also for arm64: neither is among the tested configurations of certificate #5586.
- Still refused with the image: Ed25519 SSH keys of deployment targets and Ed25519 host keys (paramiko signs and verifies them with libsodium, outside the module), HSM and OpenBao keys other than RSA 2048+ and ECDSA P-256, P-384 and P-521, ML-DSA and EdDSA among them (the provider signs, not the module), and SLH-DSA, which the module approves but the Python cryptography library does not provide.
- The readiness check of the image, run before the switch, judges these keys by the image's module, asked when the image was built.
- With the image, TLS 1.2 without Extended Master Secret is refused in both directions, and TLS also offers the hybrid groups X25519MLKEM768 and SecP256r1MLKEM768; X25519 and X448 alone stay refused.
- A webhook secret or TSIG key under 14 bytes is refused when saved in FIPS mode.

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

## First Access

UCM has no default password. The first administrator (`admin`, or `INITIAL_ADMIN_USERNAME`) gets its password from one of two sources, read only at the first start:

- **Provided:** `INITIAL_ADMIN_PASSWORD_FILE` names a file holding it (a Docker, Compose or Kubernetes secret), or `INITIAL_ADMIN_PASSWORD` holds it. Setting both refuses the start; an unreadable or empty file refuses it too, it never falls back to a generated one. A provided password is yours: no change is forced. The password policy is not applied to it: a weak one is accepted, and the log says it does not meet the policy.
- **Generated:** with neither set, the first start writes a random password to `initial-admin-password` in the data directory (`/opt/ucm/data` for every package and the image), mode 0600, owned by the service user. It never appears in a log, the container output or the installation message: they give the path and the command to read it. The first login must change it, and that change removes the file.

Once the administrator exists, neither variable is read again: remove the value from your environment or secret after the first start. The [Administration Guide](../ADMIN_GUIDE.md#initial-administrator-password) has the full model, the HA case and what to do if the file was lost.

### DEB (Debian, Ubuntu) and RPM (Fedora, RHEL, Rocky, Alma)

The package starts UCM at installation. Generated password:

```bash
sudo cat /opt/ucm/data/initial-admin-password
```

To provide it, write `/etc/ucm/ucm.env` before installing the package: the package keeps a file it finds, completes it, and gives `/etc/ucm` to the `ucm` user before starting UCM.

```bash
sudo install -d -m 750 /etc/ucm
sudo sh -c 'umask 077; printf "%s\n" "Your-Chosen-Password" > /etc/ucm/admin-password'
echo 'INITIAL_ADMIN_PASSWORD_FILE=/etc/ucm/admin-password' | sudo tee /etc/ucm/ucm.env
sudo apt install ./ucm_VERSION_all.deb      # or: sudo dnf install ./ucm-...rpm
```

`INITIAL_ADMIN_PASSWORD=...` in `/etc/ucm/ucm.env` works the same way. The installation message says which source it found, or gives the command above for a generated password; it never shows the value. Delete the file and the line after the first login.

### Docker

Generated password:

```bash
docker exec ucm cat /opt/ucm/data/initial-admin-password
```

To provide it, prefer a file: `-v /path/to/admin-password:/run/secrets/ucm_admin_password:ro -e INITIAL_ADMIN_PASSWORD_FILE=/run/secrets/ucm_admin_password`. The plain variable `-e INITIAL_ADMIN_PASSWORD=...` works too, but `docker inspect` shows it to anyone who can reach the Docker daemon. The file must be readable by the container user (`ucm`, UID set by the image).

### Docker Compose with a secret

```yaml
services:
  ucm:
    image: neyslim/ultimate-ca-manager:latest
    environment:
      - INITIAL_ADMIN_PASSWORD_FILE=/run/secrets/ucm_admin_password
    secrets:
      - ucm_admin_password
secrets:
  ucm_admin_password:
    file: ./ucm_admin_password.txt
```

Without the secret, read the generated password with `docker compose exec ucm cat /opt/ucm/data/initial-admin-password`. The `docker-compose*.yml` files of the repository carry this example, commented.

### Helm (Kubernetes)

The chart provides the password: `initialAdminPassword` when set, otherwise one it generates into its Secret and keeps across upgrades (that one must be changed at first login). To use your own Secret, set `INITIAL_ADMIN_PASSWORD` or `INITIAL_ADMIN_PASSWORD_FILE` in `extraEnv`: the chart then passes none. Read the generated one with:

```bash
kubectl -n ucm get secret ucm-secrets -o jsonpath='{.data.UCM_INITIAL_ADMIN_PASSWORD}' | base64 -d; echo
```

(`<fullname>-secrets` for another release name.) The value the chart generated must be changed at the first login, as a generated password (the chart sets `INITIAL_ADMIN_PASSWORD_FORCE_CHANGE=1`); a value you set in `initialAdminPassword` is yours and no change is forced. No file is written in the pod. `helm template` and GitOps tools cannot look the Secret up and render a new value each time: set `initialAdminPassword` there.

### HA (several nodes on one PostgreSQL)

The administrator is created once, in the database, by the first node to start (creation runs under the startup lock). With nothing provided, only that node writes the file. Each node's log says where it is: `generated password in <path>` on that node, `its generated password file is on node <id>` on the others. A password change made through any node removes the file on every node: at once on the node that holds it when the change is made there, through a cluster command otherwise, and at the next start for a node that was down. Providing the password through a secret shared by the nodes avoids the question.

### At the first login

With a generated password, UCM asks for a new one right after login. Until it is set, the server refuses every other request of that session, API and WebSocket included. The new password follows the password policy (Settings > Security). Once it is saved, `initial-admin-password` is deleted. The file is never removed after a delay.

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

1. **Log in and set your password**: see [First Access](#first-access); there is no default password
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

# UCM Release & Deployment Guide

## Version 2.0.3

### Supported Platforms

| Platform | Package | Architecture |
|----------|---------|--------------|
| Debian 12+ / Ubuntu 22.04+ | `.deb` | amd64, arm64 |
| Fedora 40+ / RHEL 9+ / Rocky 9+ | `.rpm` | x86_64, aarch64 |
| Docker | `ghcr.io/neyslim/ucm` | amd64, arm64 |

### Package Locations

After installation:
- **Application**: `/opt/ucm/`
- **Configuration**: `/etc/ucm/ucm.env`
- **Data**: `/opt/ucm/data/` (database, certs, CA files)
- **Logs**: `/var/log/ucm/`
- **Service**: `systemctl status ucm`

---

## Installation

### Debian/Ubuntu (DEB)

```bash
# Download
wget https://github.com/NeySlim/ultimate-ca-manager/releases/latest/download/ucm_2.0.3_all.deb

# Install
sudo dpkg -i ucm_2.0.3_all.deb

# If dependency issues (shouldn't happen with venv approach):
sudo apt-get install -f
```

### Fedora/RHEL/Rocky (RPM)

```bash
# Download
wget https://github.com/NeySlim/ultimate-ca-manager/releases/latest/download/ucm-2.0.3-1.fc43.noarch.rpm

# Install
sudo dnf install ./ucm-2.0.3-1.fc43.noarch.rpm
# or
sudo rpm -ivh ucm-2.0.3-1.fc43.noarch.rpm
```

### Docker

```bash
docker run -d \
  --name ucm \
  -p 8443:8443 \
  -v ucm-data:/opt/ucm/data \
  -e SECRET_KEY=$(openssl rand -hex 32) \
  -e JWT_SECRET_KEY=$(openssl rand -hex 32) \
  ghcr.io/neyslim/ucm:2.0.3
```

---

## Upgrade from v1.8.x

The package automatically detects and migrates v1.8.x installations:

1. **Database migration**: Copies from `/var/lib/ucm/ucm.db` to `/opt/ucm/data/ucm.db`
2. **Schema updates**: Runs migrations to add new tables (groups, templates, etc.)
3. **File migration**: Copies CA files, certificates, and private keys
4. **Config update**: Updates paths in `/etc/ucm/ucm.env`

### Pre-upgrade Backup

The postinst script automatically creates backups:
- Database: `/var/lib/ucm/backups/ucm-pre-upgrade-YYYYMMDD-HHMMSS.db`
- Config: `/var/lib/ucm/backups/ucm.env-pre-upgrade-YYYYMMDD-HHMMSS`

### Manual Migration (if needed)

```bash
# Stop service
sudo systemctl stop ucm

# Backup current data
sudo cp /var/lib/ucm/ucm.db /var/lib/ucm/ucm.db.backup
sudo cp /etc/ucm/ucm.env /etc/ucm/ucm.env.backup

# Install new version
sudo dpkg -i ucm_2.0.3_all.deb

# Check migration log
sudo cat /var/log/ucm/migration.log

# Start service
sudo systemctl start ucm
```

---

## Post-Installation

### First Access

```bash
# Get admin password (shown during install, also in config)
sudo grep INITIAL_ADMIN_PASSWORD /etc/ucm/ucm.env

# Access web interface
https://your-server:8443

# Login: admin / <password from config>
```

### Change Admin Password

After first login, go to **Account** → **Change Password**.

### Configuration

Edit `/etc/ucm/ucm.env`:

```bash
# Database location
DATABASE_PATH=/opt/ucm/data/ucm.db

# HTTPS port
HTTPS_PORT=8443

# Log level (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=INFO

# Security keys (auto-generated, keep secret!)
SECRET_KEY=...
JWT_SECRET_KEY=...
```

Restart after changes:
```bash
sudo systemctl restart ucm
```

---

## Service Management

```bash
# Status
sudo systemctl status ucm

# Logs
sudo journalctl -u ucm -f

# Restart
sudo systemctl restart ucm

# Stop
sudo systemctl stop ucm
```

---

## Troubleshooting

### Service won't start

```bash
# Check logs
sudo journalctl -u ucm --no-pager -n 50

# Check config
sudo cat /etc/ucm/ucm.env

# Test manually
cd /opt/ucm && sudo -u ucm ./venv/bin/python -m flask run --port 5000
```

### Missing Python dependencies

```bash
# Recreate venv
sudo rm -rf /opt/ucm/venv
sudo python3 -m venv /opt/ucm/venv
sudo /opt/ucm/venv/bin/pip install -r /opt/ucm/requirements.txt
sudo chown -R ucm:ucm /opt/ucm/venv
```

### Database issues

```bash
# Check database
sudo sqlite3 /opt/ucm/data/ucm.db ".tables"

# Run migrations manually
cd /opt/ucm/backend
sudo -u ucm /opt/ucm/venv/bin/python -c "from migration_runner import run_all_migrations; run_all_migrations()"
```

---

## Release Process (for maintainers)

### 1. Version Bump

```bash
# Frontend
cd frontend && npm version 2.0.0

# DEB changelog
dch -v 2.0.0 "Release notes..."

# RPM spec (auto-updated by CI)
```

### 2. Create Tag

```bash
git tag v2.0.0
git push origin v2.0.0
```

### 3. CI/CD Pipeline

The `build-release.yml` workflow automatically:
1. Builds frontend (`npm ci && npm run build`)
2. Creates DEB package
3. Creates RPM package (in Fedora container)
4. Builds Docker image
5. Creates GitHub release with all artifacts

### 4. Artifacts

| Artifact | Naming |
|----------|--------|
| DEB | `ucm_VERSION_all.deb` |
| RPM | `ucm-VERSION-1.fc43.noarch.rpm` |
| Docker | `ghcr.io/neyslim/ucm:VERSION` |

---

## Changelog

### v2.0.0 (2026-02-06)

**New Features:**
- Complete UI redesign with Radix UI components
- Groups management
- Certificate templates
- Security dashboard
- WebAuthn multi-key support
- Mobile-responsive design
- 8 theme variants

**Improvements:**
- Python venv for dependencies (no system packages needed)
- Unified `/opt/ucm` installation path
- Automatic v1.8.x migration
- Enhanced audit logging

**Pro Features:**
- RBAC (Role-Based Access Control)
- HSM integration
- SSO/SAML support

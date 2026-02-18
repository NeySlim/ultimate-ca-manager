# Installation Guide

This guide covers all installation methods for Ultimate CA Manager.

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
- **Database:** SQLite (included)

---

## Installation Methods

### Method 1: Docker (Recommended)

**Fastest and easiest installation method with automatic updates.**

See: [Docker Installation Guide](docker.md)

```bash
docker run -d \
  --name ucm \
  -p 8443:8443 \
  -v ucm-data:/opt/ucm/data \
  neyslim/ultimate-ca-manager:latest
```

**Access:** https://localhost:8443  
**Default credentials:** admin / password from install (check /etc/ucm/ucm.env or Docker logs)

---

### Method 2: Debian/Ubuntu Package

**Native installation for Debian, Ubuntu, and derivatives.**

```bash
# Download latest package
wget https://github.com/NeySlim/ultimate-ca-manager/releases/latest/download/ucm_all.deb

# Install
sudo dpkg -i ucm_*_all.deb
sudo apt-get install -f  # Fix any dependencies

# Enable and start
sudo systemctl enable ucm
sudo systemctl start ucm
sudo systemctl status ucm
```

**Access:** https://localhost:8443

---

### Method 3: RHEL/Rocky/Alma Package

**Native installation for RedHat, Rocky Linux, AlmaLinux, and derivatives.**

```bash
# Download latest package
wget https://github.com/NeySlim/ultimate-ca-manager/releases/latest/download/ucm.noarch.rpm

# Install
sudo dnf install ./ucm-*.noarch.rpm

# Enable and start
sudo systemctl enable ucm
sudo systemctl start ucm
sudo systemctl status ucm
```

**Access:** https://localhost:8443

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

# Run
python wsgi.py
```

**Access:** https://localhost:8443

---

## First Login

After installation, access UCM at **https://localhost:8443**

**Default Credentials:**
- **Username:** admin
- **Password:** shown during install (see `/etc/ucm/ucm.env`)

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
- **Config:** Environment variables or `.env` file
- **Logs:** stdout/stderr

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
- [Redis for HA](../REDIS.md)

---

## Support

- **Issues:** [GitHub Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)
- **Wiki:** [GitHub Wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki)
- **Discussions:** [GitHub Discussions](https://github.com/NeySlim/ultimate-ca-manager/discussions)

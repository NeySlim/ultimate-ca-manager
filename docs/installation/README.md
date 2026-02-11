# Installation Guide

This guide covers all installation methods for Ultimate CA Manager.

## 📋 System Requirements

### Minimum Requirements
- **CPU:** 2 cores
- **RAM:** 2 GB
- **Storage:** 5 GB free space
- **OS:** Linux (any distribution), Windows with WSL2, macOS

### Recommended Requirements
- **CPU:** 4 cores
- **RAM:** 4 GB
- **Storage:** 20 GB free space (for CA data and backups)

### Software Requirements
- **Docker:** 20.10+ (for Docker installation)
- **Python:** 3.11+ (for source installation)
- **Database:** SQLite (included)

---

## 🚀 Installation Methods

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
**Default credentials:** admin / changeme123 ⚠️ CHANGE IMMEDIATELY

---

### Method 2: Debian/Ubuntu Package

**Native installation for Debian, Ubuntu, and derivatives.**

See: [Debian/Ubuntu Installation Guide](debian-ubuntu.md)

```bash
# Download package
wget https://github.com/NeySlim/ultimate-ca-manager/releases/latest/download/ucm_all.deb

# Install
sudo dpkg -i ucm_2.0.4_all.deb
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

See: [RHEL/Rocky/Alma Installation Guide](rhel-rocky-alma.md)

```bash
# Download package
wget https://github.com/NeySlim/ultimate-ca-manager/releases/latest/download/ucm.noarch.rpm

# Install
sudo dnf install ucm-*.noarch.rpm

# Enable and start
sudo systemctl enable ucm
sudo systemctl start ucm
sudo systemctl status ucm
```

**Access:** https://localhost:8443

---

### Method 4: From Source

**For development or custom deployments.**

See: [Source Installation Guide](from-source.md)

```bash
# Clone repository
git clone https://github.com/NeySlim/ultimate-ca-manager.git
cd ultimate-ca-manager

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Initialize database
python backend/init_db.py

# Run development server
python wsgi.py
```

**Access:** https://localhost:8443

---

## 🔐 First Login

After installation, access UCM at **https://localhost:8443**

**Default Credentials:**
- **Username:** admin
- **Password:** changeme123

⚠️ **IMPORTANT:** Change the default password immediately after first login!

---

## 📁 Data Locations

### Docker
- **Data:** `/opt/ucm/data` (inside container)
- **Volume:** `ucm-data` (Docker volume)
- **Config:** Auto-generated from environment variables

### DEB/RPM Packages
- **Data:** `/opt/ucm/backend/data`
- **Config:** `/etc/ucm/config.json`
- **Logs:** `/var/log/ucm/`
- **Service:** `/lib/systemd/system/ucm.service`

### Source Installation
- **Data:** `./backend/data`
- **Config:** `.env` file in repository root
- **Logs:** stdout/stderr

---

## 🔄 Next Steps

After installation:

1. **Change default password** - Go to Settings → User Management
2. **Configure HTTPS certificate** - Upload trusted certificate or use auto-generated
3. **Create your first CA** - Dashboard → Create Certificate Authority
4. **Configure email notifications** (optional) - Settings → System Configuration
5. **Enable ACME/SCEP** (optional) - Settings → Protocol Configuration

---

## 📚 Additional Resources

- [Docker Deployment Guide](docker.md)
- [Configuration Guide](../administration/configuration.md)
- [Upgrade Guide](../../UPGRADE.md)
- [Troubleshooting](../administration/troubleshooting.md)

---

## 🆘 Support

- **Issues:** [GitHub Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)
- **Wiki:** [GitHub Wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki)
- **Discussions:** [GitHub Discussions](https://github.com/NeySlim/ultimate-ca-manager/discussions)

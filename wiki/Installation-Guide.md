# Installation Guide - UCM v1.8.2

Complete installation guide for Ultimate CA Manager on various platforms.

---

## 📋 System Requirements

### Minimum Requirements
- **OS**: Debian 11+, Ubuntu 20.04+, RHEL/Rocky/Alma 9+, Fedora 35+
- **Python**: 3.11 or higher (3.13 compatible)
- **RAM**: 1 GB minimum, 2 GB recommended
- **Disk**: 500 MB for application + space for certificates
- **Network**: Port 8443 (HTTPS), optional ports for SCEP/OCSP

### Recommended Requirements
- **OS**: Ubuntu 22.04 LTS, Debian 12, or Rocky Linux 9
- **Python**: 3.11+ (or use Docker)
- **RAM**: 4 GB
- **Disk**: 10 GB SSD
- **CPU**: 2 cores

---

## 🚀 Installation Methods

### Method 1: Docker (Recommended) 🐳

**Quick Start (5 minutes)**

```bash
# Pull the image
docker pull ghcr.io/neyslim/ultimate-ca-manager:1.8.2

# Run UCM
docker run -d \
  --name ucm \
  -p 8443:8443 \
  -v ucm-data:/opt/ucm/data \
  ghcr.io/neyslim/ultimate-ca-manager:1.8.2

# Access at https://localhost:8443
# Login: admin / changeme123
```

**Production Deployment with docker-compose**

See [Docker Quick Start Guide](https://github.com/NeySlim/ultimate-ca-manager/blob/main/DOCKER_QUICKSTART.md) for complete setup.

---

### Method 2: DEB Package (Debian/Ubuntu)

**Step 1: Download the package**
```bash
# Get latest version
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.8.2/ucm_1.8.2_all.deb
```

**Step 2: Verify checksums (optional but recommended)**
```bash
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.8.2/ucm_1.8.2_all.deb.sha256
sha256sum -c ucm_1.8.2_all.deb.sha256
```

**Step 3: Install**
```bash
sudo dpkg -i ucm_1.8.2_all.deb
sudo apt-get install -f  # Install dependencies if needed
```

**Step 4: Verify installation**
```bash
sudo systemctl status ucm
```

The service should be active and running. Access UCM at: `https://YOUR_SERVER_IP:8443`

---

### Method 3: RPM Package (RHEL/Rocky/Alma/Fedora)

**Step 1: Download the package**
```bash
# Get latest version
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.8.2/ucm-1.8.2-1.el9.noarch.rpm
```

**Step 2: Install**
```bash
sudo dnf install ./ucm-1.8.2-1.el9.noarch.rpm
# or
sudo yum install ./ucm-1.8.3-0.1.beta.el9.noarch.rpm
```

**Step 3: Verify installation**
```bash
sudo systemctl status ucm
```

Access UCM at: `https://YOUR_SERVER_IP:8443`

---

## 🔧 Post-Installation

### 1. Change Default Password ⚠️

**CRITICAL**: Change the default admin password immediately!

1. Login with `admin` / `changeme123`
2. Go to **Settings** → **User Management**
3. Change admin password

### 2. Configure Firewall

```bash
# Allow HTTPS port
sudo ufw allow 8443/tcp

# Optional: SCEP, OCSP, ACME
sudo ufw allow 8080/tcp   # SCEP
sudo ufw allow 2560/tcp   # OCSP  
sudo ufw allow 80/tcp     # ACME HTTP-01
```

### 3. SSL Certificate (Optional)

By default, UCM uses a self-signed certificate. To use your own:

```bash
# Copy your certificate files
sudo cp your-cert.pem /opt/ucm/data/certs/https_cert.pem
sudo cp your-key.pem /opt/ucm/data/certs/https_key.pem

# Restart service
sudo systemctl restart ucm
```

---

## 🔐 Default Credentials

- **Username**: `admin`
- **Password**: `changeme123`

⚠️ **CHANGE THIS PASSWORD IMMEDIATELY AFTER FIRST LOGIN!**

---

## 📊 Service Management

### Systemd Commands (DEB/RPM)

```bash
# Start service
sudo systemctl start ucm

# Stop service
sudo systemctl stop ucm

# Restart service
sudo systemctl restart ucm

# Check status
sudo systemctl status ucm

# View logs
sudo journalctl -u ucm -f

# Enable auto-start on boot
sudo systemctl enable ucm
```

### Docker Commands

```bash
# Start container
docker start ucm

# Stop container
docker stop ucm

# Restart container
docker restart ucm

# View logs
docker logs -f ucm

# Access shell
docker exec -it ucm bash
```

---

## 🗂️ File Locations

### DEB/RPM Installation
- **Application**: `/opt/ucm/`
- **Database**: `/opt/ucm/data/ucm.db`
- **Certificates**: `/opt/ucm/data/certs/`
- **CA Data**: `/opt/ucm/data/ca/`
- **Logs**: `journalctl -u ucm`
- **Service**: `/etc/systemd/system/ucm.service`

### Docker Installation
- **Data Volume**: `ucm-data` (or bind mount)
- **Database**: `/opt/ucm/data/ucm.db` (inside container)
- **Logs**: `docker logs ucm`

---

## 🆙 Upgrading

### Docker
```bash
docker pull ghcr.io/neyslim/ultimate-ca-manager:latest
docker stop ucm
docker rm ucm
docker run -d --name ucm -p 8443:8443 -v ucm-data:/opt/ucm/data ghcr.io/neyslim/ultimate-ca-manager:latest
```

### DEB
```bash
wget https://github.com/NeySlim/ultimate-ca-manager/releases/latest/download/ucm_VERSION_all.deb
sudo dpkg -i ucm_VERSION_all.deb
```

### RPM
```bash
wget https://github.com/NeySlim/ultimate-ca-manager/releases/latest/download/ucm-VERSION.rpm
sudo dnf upgrade ./ucm-VERSION.rpm
```

---

## 🐛 Troubleshooting

### Service won't start

```bash
# Check logs
sudo journalctl -u ucm -n 50

# Check permissions
sudo chown -R ucm:ucm /opt/ucm
```

### Port already in use

```bash
# Find process using port 8443
sudo lsof -i :8443

# Kill process or change UCM port in config
```

### Database errors

```bash
# Reinitialize database (CAUTION: deletes all data!)
sudo -u ucm /opt/ucm/venv/bin/python /opt/ucm/backend/init_db.py
```

---

## 📚 Next Steps

- [Quick Start Guide](Quick-Start) - First steps with UCM
- [Configuration](Configuration) - Customize your setup
- [CA Management](CA-Management) - Create your first CA
- [User Manual](User-Manual) - Complete feature guide

---

**Last Updated**: 2026-01-09  
**Version**: 1.8.3-beta

---

### Method 2: RPM Package (RHEL/CentOS/Fedora)

**Step 1: Download the package**
```bash
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.6.0/ucm-1.6.0-1.noarch.rpm
```

**Step 2: Verify checksums (optional but recommended)**
```bash
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.6.0/ucm-1.6.0-1.noarch.rpm.sha256
sha256sum -c ucm-1.6.0-1.noarch.rpm.sha256
```

**Step 3: Install**
```bash
sudo rpm -ivh ucm-1.6.0-1.noarch.rpm
```

**Step 4: Verify installation**
```bash
sudo systemctl status ucm
```

---

### Method 3: Manual Installation (All Linux)

**Step 1: Install dependencies**

*Debian/Ubuntu:*
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv nginx git
```

*RHEL/CentOS/Fedora:*
```bash
sudo dnf install -y python3 python3-pip nginx git
```

**Step 2: Clone repository**
```bash
cd /opt
sudo git clone -b v1.6.0 https://github.com/NeySlim/ultimate-ca-manager.git ucm
cd ucm
```

**Step 3: Run installer**
```bash
sudo ./scripts/install/install.sh
```

The installer will:
- Create `ucm` system user
- Set up Python virtual environment
- Install Python dependencies
- Configure systemd service
- Generate self-signed HTTPS certificate
- Start the service

**Step 4: Verify**
```bash
sudo systemctl status ucm
```

---

## 🔧 Post-Installation Configuration

### 1. First Login

Access UCM at: `https://YOUR_SERVER_IP:8443`

**Default credentials:**
- Username: `admin`
- Password: `admin`

⚠️ **Important**: Change the default password immediately after first login!

### 2. Change Admin Password

1. Log in with default credentials
2. Go to **Settings** → **Users**
3. Click on `admin` user
4. Click **Change Password**
5. Enter new strong password

### 3. Configure Environment

Edit `/opt/ucm/.env`:
```bash
sudo nano /opt/ucm/.env
```

Key settings:
```bash
# Application
SECRET_KEY=your-secret-key-here
FLASK_ENV=production

# Security
SESSION_COOKIE_SECURE=True
SESSION_COOKIE_HTTPONLY=True

# Database
DATABASE_PATH=/opt/ucm/data/ucm.db

# HTTPS
HTTPS_PORT=8443
HTTPS_CERT=/opt/ucm/data/https_cert.pem
HTTPS_KEY=/opt/ucm/data/https_key.pem
```

After changes:
```bash
sudo systemctl restart ucm
```

### 4. Firewall Configuration

**UFW (Ubuntu/Debian):**
```bash
sudo ufw allow 8443/tcp
sudo ufw reload
```

**firewalld (RHEL/CentOS/Fedora):**
```bash
sudo firewall-cmd --permanent --add-port=8443/tcp
sudo firewall-cmd --reload
```

**iptables:**
```bash
sudo iptables -A INPUT -p tcp --dport 8443 -j ACCEPT
sudo iptables-save | sudo tee /etc/iptables/rules.v4
```

---

## 🔄 Upgrading from Previous Versions

### From 1.5.x or earlier

**Step 1: Backup**
```bash
sudo systemctl stop ucm
sudo cp -r /opt/ucm/data /opt/ucm/data.backup-$(date +%Y%m%d)
```

**Step 2: Install new version**

*DEB (Debian/Ubuntu):*
```bash
sudo dpkg -i ucm_1.6.0_all.deb
```

*RPM (RHEL/CentOS):*
```bash
sudo rpm -Uvh ucm-1.6.0-1.noarch.rpm
```

**Step 3: Verify**
```bash
sudo systemctl status ucm
journalctl -u ucm -n 50
```

Your data is preserved automatically during upgrade!

---

## 🗑️ Uninstallation

**DEB (Debian/Ubuntu):**
```bash
sudo systemctl stop ucm
sudo dpkg -r ucm
```

**RPM (RHEL/CentOS):**
```bash
sudo systemctl stop ucm
sudo rpm -e ucm
```

**Manual Installation:**
```bash
cd /opt/ucm
sudo ./scripts/install/uninstall.sh
```

**To also remove data:**
```bash
sudo rm -rf /opt/ucm
```

---

## 🐛 Troubleshooting

### Service won't start

**Check logs:**
```bash
sudo journalctl -u ucm -n 100 --no-pager
```

**Common issues:**
1. Port 8443 already in use
   ```bash
   sudo netstat -tlnp | grep 8443
   ```

2. Permission issues
   ```bash
   sudo chown -R ucm:ucm /opt/ucm
   ```

3. Python dependencies
   ```bash
   cd /opt/ucm
   source venv/bin/activate
   pip install -r backend/requirements.txt
   ```

### Can't access web interface

1. Check firewall (see Firewall Configuration above)
2. Verify service is running: `sudo systemctl status ucm`
3. Check HTTPS certificate: `ls -la /opt/ucm/data/https_*`

### Database issues

**Reinitialize database (⚠️ destroys all data!):**
```bash
sudo systemctl stop ucm
sudo rm /opt/ucm/data/ucm.db
sudo -u ucm /opt/ucm/venv/bin/python /opt/ucm/backend/init_db.py
sudo systemctl start ucm
```

---

## 📚 Next Steps

After installation:
1. ✅ [Quick Start Guide](Quick-Start) - Create your first CA
2. ✅ [User Manual](User-Manual) - Complete feature documentation
3. ✅ [API Reference](API-Reference) - REST API documentation
4. ✅ [Security Best Practices](Security-Best-Practices) - Harden your installation

---

## 💬 Support

- 📖 [Documentation Wiki](Home)
- 🐛 [Report Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)
- 💬 [GitHub Discussions](https://github.com/NeySlim/ultimate-ca-manager/discussions)

---

**Last Updated:** January 5, 2026  
**Version:** 1.6.0

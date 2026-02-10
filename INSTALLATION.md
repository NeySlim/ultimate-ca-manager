# Installation Guide

**UCM v2.0.3** - Ultimate CA Manager

Choose the installation method that best suits your needs.

---

## 🚀 Quick Install (Recommended)

### Universal Installer

**One-line install** for all Linux distributions:

```bash
curl -fsSL https://raw.githubusercontent.com/NeySlim/ultimate-ca-manager/main/packaging/scripts/install-ucm.sh | sudo bash
```

Or with wget:
```bash
wget -qO- https://raw.githubusercontent.com/NeySlim/ultimate-ca-manager/main/packaging/scripts/install-ucm.sh | sudo bash
```

**Supports:**
- ✅ Debian, Ubuntu, Linux Mint, Pop!_OS
- ✅ RHEL, Rocky Linux, AlmaLinux, Fedora, CentOS
- ✅ openSUSE, SUSE Enterprise
- ✅ Arch Linux, Manjaro
- ✅ Alpine Linux

**Features:**
- Auto-detects your OS
- Uses native package (DEB/RPM) when available
- Falls back to source install if needed
- Installs all dependencies automatically
- Zero configuration required

---

## 🐳 Docker (Also Recommended)

### Quick Start

```bash
docker run -d \
  --name ucm \
  -p 8443:8443 \
  -v ucm-data:/opt/ucm/data \
  --restart unless-stopped \
  ghcr.io/neyslim/ultimate-ca-manager:2.0.3
```

**Access:** https://localhost:8443  
**Credentials:** admin / changeme123 ⚠️ **CHANGE IMMEDIATELY!**

### Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  ucm:
    image: ghcr.io/neyslim/ultimate-ca-manager:2.0.3
    container_name: ucm
    restart: unless-stopped
    ports:
      - "8443:8443"
    volumes:
      - ucm-data:/opt/ucm/data
    environment:
      - UCM_FQDN=ucm.example.com
      - UCM_ACME_ENABLED=true
      - UCM_SMTP_ENABLED=false

volumes:
  ucm-data:
```

**Start:**
```bash
docker-compose up -d
```

**See full Docker guide:** [docs/installation/docker.md](docs/installation/docker.md)

---

## 📦 Native Packages

### Debian/Ubuntu

```bash
# Download latest release
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.8.3/ucm_1.8.3_all.deb

# Install
sudo dpkg -i ucm_1.8.3_all.deb

# Start service
sudo systemctl enable --now ucm
```

### RHEL/Rocky/Alma/Fedora

```bash
# Download latest release
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.8.3/ucm-1.8.3-1.el9.noarch.rpm

# Install
sudo dnf install ucm-1.8.3-1.el9.noarch.rpm

# Start service
sudo systemctl enable --now ucm
```

---

## 🔧 From Source

### Prerequisites

- Python 3.11+
- pip
- systemd
- openssl

### Installation Steps

```bash
# 1. Clone repository
git clone https://github.com/NeySlim/ultimate-ca-manager.git
cd ultimate-ca-manager

# 2. Create virtual environment
cd backend
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4. Initialize database
python3 init_db.py

# 5. Create systemd service
sudo cp packaging/debian/ucm.service /etc/systemd/system/
sudo systemctl daemon-reload

# 6. Start service
sudo systemctl enable --now ucm
```

---

## ✅ Post-Installation

### Verify Installation

```bash
# Check service status
sudo systemctl status ucm

# Check logs
sudo journalctl -u ucm -f
```

### Access UCM

Open your browser:
- **Local:** https://localhost:8443
- **Network:** https://YOUR_SERVER_IP:8443

### Default Credentials

- **Username:** `admin`
- **Password:** `changeme123`

⚠️ **CRITICAL:** Change the default password immediately!

1. Login with default credentials
2. Click your username (top right)
3. Select "Profile & Settings"
4. Change password

---

## 🔐 HTTPS Certificate

UCM includes a self-signed certificate by default. For production:

### Option 1: Use Your Own Certificate

1. Go to **Settings → System Settings → HTTPS Certificate**
2. Choose "Upload Certificate"
3. Upload your cert/key files
4. Service restarts automatically

### Option 2: Generate from Managed CA

1. Create a CA in UCM
2. Generate a server certificate
3. Go to **Settings → System Settings → HTTPS Certificate**
4. Select your certificate from dropdown
5. Click "Apply"

### Option 3: Use Let's Encrypt (Recommended)

Use UCM's ACME server with certbot:

```bash
# Get certificate
sudo certbot certonly --standalone -d ucm.example.com

# Upload to UCM via web UI
# Settings → System Settings → HTTPS Certificate → Upload
```

---

## 🌐 Reverse Proxy (Optional)

### Nginx

```nginx
server {
    listen 80;
    server_name ucm.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name ucm.example.com;

    ssl_certificate /etc/letsencrypt/live/ucm.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ucm.example.com/privkey.pem;

    location / {
        proxy_pass https://127.0.0.1:8443;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Apache

```apache
<VirtualHost *:80>
    ServerName ucm.example.com
    Redirect permanent / https://ucm.example.com/
</VirtualHost>

<VirtualHost *:443>
    ServerName ucm.example.com

    SSLEngine on
    SSLCertificateFile /etc/letsencrypt/live/ucm.example.com/fullchain.pem
    SSLCertificateKeyFile /etc/letsencrypt/live/ucm.example.com/privkey.pem

    ProxyPreserveHost On
    ProxyPass / https://127.0.0.1:8443/
    ProxyPassReverse / https://127.0.0.1:8443/
</VirtualHost>
```

---

## 📊 System Requirements

### Minimum
- **CPU:** 1 core
- **RAM:** 1 GB
- **Disk:** 5 GB

### Recommended
- **CPU:** 2 cores
- **RAM:** 2 GB
- **Disk:** 20 GB

### Production
- **CPU:** 4+ cores
- **RAM:** 4+ GB
- **Disk:** 50+ GB SSD

---

## 🆘 Troubleshooting

### Service Won't Start

```bash
# Check logs
sudo journalctl -u ucm -n 50

# Check permissions
sudo chown -R ucm:ucm /opt/ucm
sudo chmod -R 750 /opt/ucm
sudo chmod 700 /opt/ucm/backend/data
```

### Port Already in Use

```bash
# Find what's using port 8443
sudo lsof -i :8443

# Kill the process or change UCM port
# Edit: /opt/ucm/.env
# Set: UCM_HTTPS_PORT=8444
```

### Database Permission Error

```bash
# Fix permissions
sudo chown ucm:ucm /opt/ucm/backend/data/ucm.db
sudo chmod 600 /opt/ucm/backend/data/ucm.db
```

---

## 📚 Next Steps

1. **[First Steps](https://github.com/NeySlim/ultimate-ca-manager/wiki/First-Steps)** - Initial configuration
2. **[CA Management](https://github.com/NeySlim/ultimate-ca-manager/wiki/CA-Management)** - Create your first CA
3. **[Certificate Operations](https://github.com/NeySlim/ultimate-ca-manager/wiki/Certificate-Operations)** - Issue certificates
4. **[ACME Setup](https://github.com/NeySlim/ultimate-ca-manager/wiki/ACME-Support)** - Configure ACME server
5. **[SCEP Setup](https://github.com/NeySlim/ultimate-ca-manager/wiki/SCEP-Server)** - Device enrollment

---

## 🔗 Additional Resources

- **Documentation:** https://github.com/NeySlim/ultimate-ca-manager/wiki
- **Docker Guide:** [docs/installation/docker.md](docs/installation/docker.md)
- **Issue Tracker:** https://github.com/NeySlim/ultimate-ca-manager/issues
- **Discussions:** https://github.com/NeySlim/ultimate-ca-manager/discussions

---

**Need help?** Check the [FAQ](https://github.com/NeySlim/ultimate-ca-manager/wiki/FAQ) or open an [issue](https://github.com/NeySlim/ultimate-ca-manager/issues).

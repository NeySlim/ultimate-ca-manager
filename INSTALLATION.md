# Ultimate CA Manager - Installation Guide

## System Requirements

### Minimum Requirements
- **OS:** Debian 11+, Ubuntu 20.04+, or similar Linux distribution
- **CPU:** 1 core
- **RAM:** 512 MB
- **Disk:** 1 GB free space
- **Python:** 3.9 or higher

### Recommended Requirements
- **OS:** Debian 12 or Ubuntu 22.04 LTS
- **CPU:** 2+ cores
- **RAM:** 2 GB
- **Disk:** 5 GB free space (for certificates and backups)
- **Python:** 3.11+

## Quick Installation

### 1. Download and Extract

```bash
cd /root
wget https://example.com/ucm-1.0.0.tar.gz
tar -xzf ucm-1.0.0.tar.gz
cd ucm-src
```

### 2. Run Installer

```bash
sudo ./install.sh
```

The installer will:
- ✅ Check system requirements
- ✅ Install dependencies
- ✅ Create service user
- ✅ Set up Python virtual environment
- ✅ Install UCM to `/opt/ucm`
- ✅ Initialize database
- ✅ Create systemd service
- ✅ Configure firewall (optional)

### 3. Access UCM

After installation:

```
URL: https://YOUR_SERVER_IP:8443
Username: admin
Password: changeme123
```

**⚠️ IMPORTANT: Change the default password immediately!**

## Manual Installation

If you prefer manual installation:

### 1. Install Dependencies

```bash
apt-get update
apt-get install -y python3 python3-pip python3-venv \
    python3-dev build-essential libssl-dev libffi-dev
```

### 2. Create Service User

```bash
useradd -r -s /bin/false -d /opt/ucm -m ucm
```

### 3. Install UCM

```bash
mkdir -p /opt/ucm
cp -r * /opt/ucm/
chown -R ucm:ucm /opt/ucm
```

### 4. Set Up Python Environment

```bash
cd /opt/ucm
sudo -u ucm python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
```

### 5. Configure Environment

```bash
cp .env.example .env
# Edit .env and set:
# - SECRET_KEY (generate with: openssl rand -hex 32)
# - JWT_SECRET_KEY (generate with: openssl rand -hex 32)
# - INITIAL_ADMIN_PASSWORD (your secure password)
nano .env
```

### 6. Initialize Database

```bash
cd /opt/ucm
source venv/bin/activate
python backend/init_db.py
```

### 7. Create Systemd Service

```bash
cat > /etc/systemd/system/ucm.service << EOF
[Unit]
Description=Ultimate CA Manager
After=network.target

[Service]
Type=simple
User=ucm
Group=ucm
WorkingDirectory=/opt/ucm
Environment="PATH=/opt/ucm/venv/bin"
ExecStart=/opt/ucm/venv/bin/python /opt/ucm/backend/app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ucm
systemctl start ucm
```

### 8. Verify Installation

```bash
systemctl status ucm
journalctl -u ucm -f
```

## Post-Installation

### 1. Change Default Password

1. Login to https://YOUR_SERVER_IP:8443
2. Go to Settings → Change Password
3. Use a strong password (min 12 characters)

### 2. Configure HTTPS Certificate

By default, UCM uses a self-signed certificate. For production:

**Option A: Use your own certificate**

```bash
cp your_cert.pem /opt/ucm/backend/data/https_cert.pem
cp your_key.pem /opt/ucm/backend/data/https_key.pem
chown ucm:ucm /opt/ucm/backend/data/https_*.pem
chmod 600 /opt/ucm/backend/data/https_key.pem
systemctl restart ucm
```

**Option B: Use Let's Encrypt (with reverse proxy)**

Install nginx/apache as reverse proxy with Let's Encrypt certificate.

### 3. Configure Firewall

**UFW:**
```bash
ufw allow 8443/tcp
ufw reload
```

**Firewalld:**
```bash
firewall-cmd --permanent --add-port=8443/tcp
firewall-cmd --reload
```

**IPTables:**
```bash
iptables -A INPUT -p tcp --dport 8443 -j ACCEPT
iptables-save > /etc/iptables/rules.v4
```

### 4. Set Up Backups

Create a backup cron job:

```bash
cat > /etc/cron.daily/ucm-backup << 'EOF'
#!/bin/bash
BACKUP_DIR="/var/backups/ucm"
DATE=$(date +%Y%m%d)
mkdir -p $BACKUP_DIR
tar -czf $BACKUP_DIR/ucm-backup-$DATE.tar.gz \
    /opt/ucm/backend/data/
# Keep only last 7 days
find $BACKUP_DIR -name "ucm-backup-*.tar.gz" -mtime +7 -delete
EOF

chmod +x /etc/cron.daily/ucm-backup
```

## Upgrading

To upgrade UCM to a new version:

```bash
cd /path/to/new/ucm-version
sudo ./upgrade.sh
```

Or manually:

```bash
systemctl stop ucm
# Backup
cp -r /opt/ucm/backend/data /root/ucm-data-backup
# Update files
cp -r backend frontend scripts /opt/ucm/
# Update dependencies
cd /opt/ucm
source venv/bin/activate
pip install -r backend/requirements.txt --upgrade
# Restart
systemctl start ucm
```

## Uninstalling

To completely remove UCM:

```bash
cd /path/to/ucm-src
sudo ./uninstall.sh
```

This will:
- Stop the service
- Remove all files from `/opt/ucm`
- Remove the systemd service
- Remove the service user
- Optionally backup the database

## Troubleshooting

### Service Won't Start

```bash
# Check logs
journalctl -u ucm -n 100 --no-pager

# Check file permissions
ls -la /opt/ucm/backend/data/
chown -R ucm:ucm /opt/ucm

# Check Python environment
sudo -u ucm /opt/ucm/venv/bin/python --version
```

### Can't Access Web Interface

```bash
# Check if service is running
systemctl status ucm

# Check if port is listening
ss -tlnp | grep 8443

# Check firewall
ufw status
```

### Database Errors

```bash
# Reinitialize database (⚠️ DESTROYS ALL DATA)
systemctl stop ucm
rm /opt/ucm/backend/data/ucm.db
cd /opt/ucm
source venv/bin/activate
python backend/init_db.py
systemctl start ucm
```

### Permission Denied Errors

```bash
# Fix permissions
chown -R ucm:ucm /opt/ucm
chmod 755 /opt/ucm/backend/data
chmod 700 /opt/ucm/backend/data/private
chmod 600 /opt/ucm/backend/data/private/*.key
```

## Security Best Practices

1. **Change default password** immediately after installation
2. **Use strong passwords** (min 12 characters, mixed case, numbers, symbols)
3. **Keep system updated:**
   ```bash
   apt-get update && apt-get upgrade
   ```
4. **Regular backups** of `/opt/ucm/backend/data/`
5. **Monitor logs** for suspicious activity
6. **Use firewall** to restrict access
7. **Consider reverse proxy** (nginx/apache) for additional security
8. **Enable fail2ban** to prevent brute force attacks

## Support

- **Documentation:** See README.md and docs/
- **Logs:** `journalctl -u ucm -f`
- **Configuration:** `/opt/ucm/.env`
- **Data directory:** `/opt/ucm/backend/data/`

---

**Installation successful!** 🎉

Access UCM at: https://YOUR_SERVER_IP:8443

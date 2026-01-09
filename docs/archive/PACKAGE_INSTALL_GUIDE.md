# UCM Package Installers - User Guide

## Installation Methods

UCM provides three installation methods:
1. **DEB Package** (Ubuntu/Debian)
2. **RPM Package** (RHEL/CentOS/Fedora)
3. **Docker** (All platforms)

This guide covers DEB and RPM package installation.

---

## Debian/Ubuntu Installation

### Quick Install

```bash
# Download latest DEB package
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.8.0-beta/ucm_1.8.0-beta_all.deb

# Install package
sudo dpkg -i ucm_1.8.0-beta_all.deb

# Install dependencies if needed
sudo apt-get install -f
```

### Interactive Installation

During installation, you'll be prompted for:

1. **FQDN** (Fully Qualified Domain Name)
   - Example: `ucm.example.com`
   - Used for HTTPS certificate and ACME URLs
   - **IMPORTANT**: Must be accessible from clients

2. **HTTPS Port**
   - Default: `8443`
   - Use `443` for standard HTTPS (requires root/capability)

3. **Administrator Account**
   - Username (default: `admin`)
   - Password (minimum 8 characters)
   - Password confirmation

4. **Email Notifications** (Optional)
   - Enable/disable SMTP
   - SMTP server and credentials
   - From address

5. **Auto-start Service**
   - Start UCM immediately
   - Enable service at boot

### Example Installation Session

```
┌─────────────────────────────────────┐
│  Ultimate CA Manager Setup          │
├─────────────────────────────────────┤
│                                     │
│  FQDN: ucm.example.com             │
│  HTTPS Port: 8443                   │
│                                     │
│  Administrator                      │
│  Username: admin                    │
│  Password: ********                 │
│  Confirm:  ********                 │
│                                     │
│  Enable SMTP? Yes                   │
│  Server: smtp.gmail.com             │
│  Port: 587                          │
│  Username: alerts@example.com       │
│  Password: ********                 │
│  From: noreply@example.com          │
│                                     │
│  Auto-start service? Yes            │
│  Generate HTTPS cert? Yes           │
│                                     │
└─────────────────────────────────────┘

Creating backup of existing database...
✓ Backup created: /var/lib/ucm/backups/ucm-pre-upgrade-20260109.db

Generating self-signed HTTPS certificate...
✓ HTTPS certificate generated

✓ UCM service started successfully

╔════════════════════════════════════════╗
║   UCM Installation Complete! 🎉       ║
╚════════════════════════════════════════╝

Access: https://ucm.example.com:8443
Login:  admin / (your password)

Configuration: /etc/ucm/ucm.env
Logs:          journalctl -u ucm -f
Service:       systemctl status ucm

To reconfigure: dpkg-reconfigure ucm
```

---

## Post-Installation

### 1. Access Web Interface

```bash
# Open in browser
https://your-fqdn:8443

# Or with curl
curl -k https://your-fqdn:8443
```

### 2. First Login

- Navigate to web interface
- Login with configured credentials
- **IMMEDIATELY change admin password**
- Configure first Certificate Authority

### 3. Service Management

```bash
# Check status
sudo systemctl status ucm

# View logs
sudo journalctl -u ucm -f

# Restart service
sudo systemctl restart ucm

# Stop service
sudo systemctl stop ucm

# Disable auto-start
sudo systemctl disable ucm
```

### 4. Configuration Files

| Path | Purpose |
|------|---------|
| `/etc/ucm/ucm.env` | Main configuration |
| `/var/lib/ucm/` | Database and certificates |
| `/var/log/ucm/` | Application logs |
| `/opt/ucm/` | Application files |

---

## Reconfiguration

### Method 1: Debconf (Debian/Ubuntu)

```bash
# Interactive reconfiguration wizard
sudo dpkg-reconfigure ucm
```

### Method 2: UCM Configure Script

```bash
# Alternative configuration tool
sudo ucm-configure
```

### Method 3: Manual Edit

```bash
# Edit configuration directly
sudo nano /etc/ucm/ucm.env

# Restart service
sudo systemctl restart ucm
```

---

## Upgrade

### Automatic Upgrade

```bash
# Download new DEB package
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.9.0/ucm_1.9.0_all.deb

# Install (automatically backs up database)
sudo dpkg -i ucm_1.9.0_all.deb
```

**Upgrade Process:**
1. ✅ Pre-upgrade backup created automatically
2. ✅ Service stopped
3. ✅ Files updated
4. ✅ Database migrated (if needed)
5. ✅ Service restarted
6. ✅ Configuration preserved

### Manual Backup Before Upgrade

```bash
# Backup database
sudo cp /var/lib/ucm/ucm.db ~/ucm-backup-$(date +%Y%m%d).db

# Backup configuration
sudo cp /etc/ucm/ucm.env ~/ucm-config-backup.env
```

---

## Uninstallation

### Remove Package (Keep Data)

```bash
# Remove package but preserve data
sudo apt-get remove ucm

# Data remains in:
# - /var/lib/ucm/
# - /etc/ucm/
# - /var/log/ucm/
```

### Complete Removal (Purge)

```bash
# Remove package AND all data
sudo apt-get purge ucm

# Everything removed:
# - Application files
# - Configuration
# - Database
# - Logs
# - User/group
```

---

## Troubleshooting

### Service Won't Start

```bash
# Check logs
sudo journalctl -u ucm -n 50

# Common issues:
# 1. Port already in use
#    → Change HTTPS_PORT in /etc/ucm/ucm.env
#
# 2. Permission denied
#    → Check: ls -la /var/lib/ucm
#    → Fix: sudo chown -R ucm:ucm /var/lib/ucm
#
# 3. Missing dependencies
#    → sudo apt-get install -f
```

### Cannot Access Web Interface

```bash
# 1. Check service is running
sudo systemctl status ucm

# 2. Check port is open
sudo netstat -tlnp | grep 8443

# 3. Check firewall
sudo ufw status
sudo ufw allow 8443/tcp

# 4. Test locally
curl -k https://localhost:8443
```

### Password Reset

```bash
# Method 1: Reconfigure
sudo dpkg-reconfigure ucm

# Method 2: Direct database
sudo sqlite3 /var/lib/ucm/ucm.db
# Then update users table
```

### Database Corruption

```bash
# Restore from automatic backup
sudo systemctl stop ucm

# List backups
ls -lh /var/lib/ucm/backups/

# Restore
sudo cp /var/lib/ucm/backups/ucm-*.db /var/lib/ucm/ucm.db
sudo chown ucm:ucm /var/lib/ucm/ucm.db

# Restart
sudo systemctl start ucm
```

---

## Configuration Options

### Environment Variables

See `/etc/ucm/ucm.env` for all configuration options:

```bash
# Core
FQDN=ucm.example.com
HTTPS_PORT=8443
DEBUG=false
LOG_LEVEL=INFO

# Security
SECRET_KEY=auto-generated
JWT_SECRET_KEY=auto-generated
SESSION_TIMEOUT=3600

# SMTP
SMTP_ENABLED=true
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=alerts@example.com
SMTP_PASSWORD=***
SMTP_FROM=noreply@example.com

# Features
ACME_ENABLED=true
SCEP_ENABLED=true
CACHE_ENABLED=true
MTLS_ENABLED=false
```

---

## Security Best Practices

1. **HTTPS Certificate**
   - Replace self-signed cert with trusted CA cert
   - Use Let's Encrypt or internal CA
   - Store in `/var/lib/ucm/`

2. **Firewall**
   ```bash
   sudo ufw allow 8443/tcp
   sudo ufw enable
   ```

3. **Reverse Proxy**
   - Use Nginx/Apache for mTLS
   - Terminate SSL at proxy
   - See: `/usr/share/doc/ucm/DOCKER_QUICKSTART.md`

4. **Regular Backups**
   ```bash
   # Automatic backups enabled by default
   # Manual backup:
   sudo cp /var/lib/ucm/ucm.db ~/backup-$(date +%Y%m%d).db
   ```

5. **Updates**
   ```bash
   # Check for updates
   apt-cache policy ucm
   
   # Install updates
   sudo apt-get update
   sudo apt-get install ucm
   ```

---

## Support

- **Documentation**: `/usr/share/doc/ucm/`
- **GitHub**: https://github.com/NeySlim/ultimate-ca-manager
- **Issues**: https://github.com/NeySlim/ultimate-ca-manager/issues
- **Logs**: `journalctl -u ucm -f`

---

**Version**: UCM v1.8.0-beta  
**Last Updated**: 2026-01-09  
**License**: See `/usr/share/doc/ucm/LICENSE`

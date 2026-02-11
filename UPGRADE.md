# UCM Upgrade Guide

This guide covers upgrading UCM to newer versions across different installation methods.

## Table of Contents

- [Docker Upgrade](#docker-upgrade)
- [DEB Package Upgrade](#deb-package-upgrade)
- [RPM Package Upgrade](#rpm-package-upgrade)
- [Source Installation Upgrade](#source-installation-upgrade)
- [Version-Specific Notes](#version-specific-notes)

---

## Docker Upgrade

### Using Docker Compose

```bash
# 1. Backup current data
docker-compose exec ucm cp /opt/ucm/data/ucm.db /opt/ucm/data/backups/manual-backup-$(date +%Y%m%d).db

# 2. Pull new image
docker-compose pull

# 3. Restart containers
docker-compose down
docker-compose up -d

# 4. Check logs
docker-compose logs -f ucm
```

### Using docker-helper.sh

```bash
# Interactive update
./docker-helper.sh
# Select option 10: Update UCM
```

### Manual Docker Commands

```bash
# 1. Stop container
docker stop ucm

# 2. Backup data
docker cp ucm:/opt/ucm/data/ucm.db ./backup-$(date +%Y%m%d).db

# 3. Remove old container
docker rm ucm

# 4. Pull new image
docker pull neyslim/ultimate-ca-manager:latest

# 5. Start new container
docker run -d \
  --name ucm \
  -p 8443:8443 \
  -v ucm-data:/opt/ucm/data \
  -e UCM_FQDN=ucm.example.com \
  neyslim/ultimate-ca-manager:latest
```

---

## DEB Package Upgrade

### Automatic Upgrade

```bash
# Download new version
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.9.0/ucm_1.9.0_all.deb

# Install (automatically backs up database)
sudo dpkg -i ucm_1.9.0_all.deb

# Fix dependencies if needed
sudo apt-get install -f
```

**What happens during upgrade:**
1. ✅ Pre-upgrade backup created automatically
2. ✅ Service stopped gracefully
3. ✅ Files updated
4. ✅ Database migrated (if schema changed)
5. ✅ Configuration preserved
6. ✅ Service restarted

### Manual Backup Before Upgrade

```bash
# Recommended for major version upgrades
sudo systemctl stop ucm
sudo cp /var/lib/ucm/ucm.db ~/ucm-backup-$(date +%Y%m%d).db
sudo cp /etc/ucm/ucm.env ~/ucm-config-backup.env
sudo systemctl start ucm
```

### Rollback

```bash
# If upgrade fails, rollback to backup
sudo systemctl stop ucm

# Restore database
sudo cp /var/lib/ucm/backups/ucm-pre-upgrade-*.db /var/lib/ucm/ucm.db

# Reinstall previous version
sudo dpkg -i ucm_1.8.3_all.deb

sudo systemctl start ucm
```

---

## RPM Package Upgrade

### Using DNF/YUM

```bash
# Download new version
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.9.0/ucm-1.9.0-1.rpm

# Upgrade
sudo dnf upgrade ucm-1.9.0-1.rpm
# or
sudo yum upgrade ucm-1.9.0-1.rpm
```

### Manual Backup

```bash
sudo systemctl stop ucm
sudo cp /var/lib/ucm/ucm.db ~/ucm-backup-$(date +%Y%m%d).db
sudo systemctl start ucm
```

---

## Source Installation Upgrade

### Git-based Installation

```bash
# 1. Stop service
sudo systemctl stop ucm

# 2. Backup database
sudo cp /opt/ucm/backend/data/ucm.db ~/ucm-backup-$(date +%Y%m%d).db

# 3. Backup configuration
cp /opt/ucm/.env ~/ucm-env-backup

# 4. Pull updates
cd /opt/ucm
git fetch --tags
git checkout v1.9.0

# 5. Update dependencies
cd backend
pip install -r requirements.txt --upgrade

# 6. Run migrations (if any)
python migrate.py # if migration script exists

# 7. Restart service
sudo systemctl start ucm
```

---

## Version-Specific Notes

### Upgrading to v1.9.0 from v1.8.x

**No breaking changes** - Safe to upgrade directly.

**New features:**
- Multi-architecture Docker images (amd64, arm64)
- Automated release workflow
- Enhanced package installers

**Steps:**
1. Standard upgrade procedure
2. No configuration changes required

### Upgrading to v1.8.3 from v1.7.x

**Important changes:**
- New environment variables for Docker
- mTLS configuration moved to dedicated page

**Migration steps:**

1. **Docker users:**
   ```bash
   # Add new ENV variable
   export UCM_FQDN=your-domain.com
   docker-compose up -d
   ```

2. **Package users:**
   ```bash
   # Reconfigure after upgrade
   sudo dpkg-reconfigure ucm
   # or
   sudo ucm-configure
   ```

3. **mTLS users:**
   - Check configuration at `/config/mtls`
   - Update reverse proxy if needed
   - See [Docker Guide](docs/installation/docker.md) for new setup

### Upgrading to v1.7.0 from v1.6.x

**Breaking changes:**
- Database schema updated (auto-migrated)
- ACME support added

**Steps:**
1. **MANDATORY BACKUP** before upgrade
2. Standard upgrade procedure
3. Check logs after upgrade: `journalctl -u ucm -n 50`

---

## Troubleshooting

### Upgrade Failed - Service Won't Start

```bash
# Check logs
sudo journalctl -u ucm -n 100 --no-pager

# Common fixes:

# 1. Permission issues
sudo chown -R ucm:ucm /var/lib/ucm
sudo chown -R ucm:ucm /var/log/ucm

# 2. Missing dependencies
sudo apt-get install -f # Debian/Ubuntu
sudo dnf install -y ucm # RHEL/CentOS

# 3. Database corruption
sudo systemctl stop ucm
sudo cp /var/lib/ucm/backups/ucm-pre-upgrade-*.db /var/lib/ucm/ucm.db
sudo systemctl start ucm
```

### Configuration Lost

```bash
# Restore configuration backup
sudo cp ~/ucm-config-backup.env /etc/ucm/ucm.env
sudo systemctl restart ucm
```

### Port Conflict After Upgrade

```bash
# Check what's using the port
sudo netstat -tlnp | grep 8443

# Change port
sudo nano /etc/ucm/ucm.env
# Change: HTTPS_PORT=8444
sudo systemctl restart ucm
```

### Docker Image Pull Fails

```bash
# Try different registry
docker pull neyslim/ultimate-ca-manager:latest
# or
docker pull neyslim/ultimate-ca-manager:latest

# Check authentication
docker login ghcr.io
```

---

## Best Practices

### Before Upgrading

1. ✅ **Read release notes** - Check for breaking changes
2. ✅ **Backup database** - Always create manual backup
3. ✅ **Test in staging** - Try upgrade in test environment first
4. ✅ **Check disk space** - Ensure enough space for backup
5. ✅ **Schedule maintenance** - Notify users of downtime

### After Upgrading

1. ✅ **Check service status** - `systemctl status ucm`
2. ✅ **Review logs** - Look for errors or warnings
3. ✅ **Test functionality** - Login, create test CA
4. ✅ **Verify certificates** - Check existing CAs still work
5. ✅ **Update documentation** - Note any config changes

### Automated Upgrades (Advanced)

```bash
# Cron job for auto-update (DEB)
# /etc/cron.weekly/ucm-update

#!/bin/bash
BACKUP_DIR="/var/backups/ucm"
mkdir -p "$BACKUP_DIR"

# Backup
cp /var/lib/ucm/ucm.db "$BACKUP_DIR/ucm-$(date +%Y%m%d).db"

# Update
apt-get update
apt-get install -y --only-upgrade ucm

# Cleanup old backups
find "$BACKUP_DIR" -name "ucm-*.db" -mtime +30 -delete

# Check status
systemctl is-active --quiet ucm || \
  (systemctl restart ucm && \
   echo "UCM restarted after upgrade" | mail -s "UCM Upgrade" admin@example.com)
```

---

## Downgrade

### Docker

```bash
# Specify exact version
docker pull neyslim/ultimate-ca-manager:latest
docker-compose down
# Edit docker-compose.yml to use version 1.8.3
docker-compose up -d
```

### DEB Package

```bash
# Download previous version
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v1.8.3/ucm_1.8.3_all.deb

# Force install previous version
sudo dpkg -i --force-downgrade ucm_1.8.3_all.deb
```

**⚠️ Warning:** Downgrading may cause data loss if database schema changed. Always backup first!

---

## Support

- **Documentation:** `/usr/share/doc/ucm/` (package) or `/root/ucm-src/` (source)
- **Logs:** `journalctl -u ucm -f` or `docker logs -f ucm`
- **Issues:** https://github.com/NeySlim/ultimate-ca-manager/issues
- **Discussions:** https://github.com/NeySlim/ultimate-ca-manager/discussions

---

**Last Updated:** 2026-01-09
**Applies to:** UCM v1.8.3 and later

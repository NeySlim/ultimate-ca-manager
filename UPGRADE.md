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
# Download new version from https://github.com/NeySlim/ultimate-ca-manager/releases/latest
wget https://github.com/NeySlim/ultimate-ca-manager/releases/latest/download/ucm_all.deb

# Install (automatically backs up database)
sudo dpkg -i ucm_*.deb

# Fix dependencies if needed
sudo apt-get install -f
```

**What happens during upgrade:**
1. Pre-upgrade backup created automatically
2. Service stopped gracefully
3. Files updated
4. Database migrated (if schema changed)
5. Configuration preserved
6. Service restarted

### Manual Backup Before Upgrade

```bash
sudo systemctl stop ucm
sudo cp /opt/ucm/data/ucm.db ~/ucm-backup-$(date +%Y%m%d).db
sudo cp /etc/ucm/ucm.env ~/ucm-config-backup.env
sudo systemctl start ucm
```

### Rollback

```bash
sudo systemctl stop ucm

# Restore database
sudo cp /opt/ucm/data/backups/ucm-pre-upgrade-*.db /opt/ucm/data/ucm.db

# Reinstall previous version
sudo dpkg -i ucm_<previous-version>_all.deb

sudo systemctl start ucm
```

---

## RPM Package Upgrade

### Using DNF/YUM

```bash
# Download new version from https://github.com/NeySlim/ultimate-ca-manager/releases/latest
wget https://github.com/NeySlim/ultimate-ca-manager/releases/latest/download/ucm.noarch.rpm

# Upgrade
sudo dnf upgrade ./ucm-*.rpm
```

### Manual Backup

```bash
sudo systemctl stop ucm
sudo cp /opt/ucm/data/ucm.db ~/ucm-backup-$(date +%Y%m%d).db
sudo systemctl start ucm
```

---

## Source Installation Upgrade

### Git-based Installation

```bash
# 1. Stop service
sudo systemctl stop ucm

# 2. Backup database
sudo cp /opt/ucm/data/ucm.db ~/ucm-backup-$(date +%Y%m%d).db

# 3. Pull updates
cd /opt/ucm
git fetch --tags
git checkout <version-tag>

# 4. Update dependencies
cd backend
pip install -r requirements.txt --upgrade

# 5. Restart service
sudo systemctl start ucm
```

Database migrations run automatically at startup.

---

## Version-Specific Notes

### Upgrading to v2.1.0 from v2.0.x

**No breaking changes** -- safe to upgrade directly.

**New features:**
- AKI/SKI-based certificate chain matching (automatic migration at startup)
- Chain repair scheduler (hourly background task)
- Chain repair widget on CAs page
- Smart import deduplication (prevents duplicate CAs)
- Webhook management UI
- 9-language i18n

**Automatic migration:**
- On first startup, UCM populates SKI/AKI fields for all existing CAs and certificates
- Orphan CAs and certificates are automatically re-chained if their parent CA exists
- Duplicate CAs (same Subject Key Identifier) are merged

No action required -- all migration happens automatically.

### Upgrading from v1.8.x to v2.0.x

**Major version upgrade** -- data is automatically migrated.

- Database path moved from `/var/lib/ucm/` to `/opt/ucm/data/`
- Frontend replaced: HTMX -> React 18
- Authentication: JWT -> session cookies
- A backup is created automatically during upgrade

Steps:
1. Standard upgrade procedure (install new package)
2. No configuration changes required
3. Check logs: `journalctl -u ucm -n 50`

---

## Troubleshooting

### Upgrade Failed - Service Won't Start

```bash
# Check logs
sudo journalctl -u ucm -n 100 --no-pager

# Common fixes:

# 1. Permission issues
sudo chown -R ucm:ucm /opt/ucm/data
sudo chown -R ucm:ucm /var/log/ucm

# 2. Missing dependencies
sudo apt-get install -f     # Debian/Ubuntu
sudo dnf install -y ucm     # RHEL

# 3. Database corruption
sudo systemctl stop ucm
sudo cp /opt/ucm/data/backups/ucm-pre-upgrade-*.db /opt/ucm/data/ucm.db
sudo systemctl start ucm
```

### Configuration Lost

```bash
sudo cp ~/ucm-config-backup.env /etc/ucm/ucm.env
sudo systemctl restart ucm
```

### Port Conflict After Upgrade

```bash
sudo netstat -tlnp | grep 8443
# Change port in /etc/ucm/ucm.env: HTTPS_PORT=8444
sudo systemctl restart ucm
```

---

## Best Practices

### Before Upgrading

1. Read release notes for breaking changes
2. Backup database manually
3. Test in staging environment first
4. Ensure enough disk space for backup

### After Upgrading

1. Check service status: `systemctl status ucm`
2. Review logs for errors
3. Test login and basic operations
4. Verify existing CAs and certificates

---

## Support

- **Logs:** `journalctl -u ucm -f` or `docker logs -f ucm`
- **Issues:** https://github.com/NeySlim/ultimate-ca-manager/issues
- **Wiki:** https://github.com/NeySlim/ultimate-ca-manager/wiki

# Backup & Restore

**Version:** 1.8.3  
**Status:** Backup only (Restore UI coming in v1.8.4)

## Current Status

✅ **Backup:** Available via web UI  
⏳ **Restore:** Manual only (UI planned for v1.8.4)

---

## Backup

### Via Web UI

1. Go to **Settings → System Settings**
2. Click **Database** tab
3. Click **"Create Backup"** button
4. Backup is created in: `/opt/ucm/backend/data/backups/`
5. Filename: `ucm_backup_YYYYMMDD_HHMMSS.db`

**What's backed up:**
- SQLite database (all CAs, certificates, users, settings)

**NOT included:**
- Certificate files (`data/certs/`)
- Private keys (`data/private/`)
- CRL files (`data/crl/`)

### Via CLI

```bash
# Manual database backup
sudo -u ucm cp /opt/ucm/backend/data/ucm.db \
  /opt/ucm/backend/data/backups/ucm_backup_$(date +%Y%m%d_%H%M%S).db

# Full system backup (includes all files)
sudo tar czf /root/ucm-backup-$(date +%Y%m%d).tar.gz \
  /opt/ucm/backend/data/
```

### Docker Backup

```bash
# Backup volume
docker run --rm \
  -v ucm-data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/ucm-backup-$(date +%Y%m%d).tar.gz -C /data .
```

---

## Restore

### Manual Restore (Current Method)

**⚠️ Warning:** This requires stopping the UCM service

```bash
# 1. Stop UCM
sudo systemctl stop ucm

# 2. Backup current database (safety)
sudo cp /opt/ucm/backend/data/ucm.db /opt/ucm/backend/data/ucm.db.old

# 3. Restore from backup
sudo cp /opt/ucm/backend/data/backups/ucm_backup_YYYYMMDD_HHMMSS.db \
  /opt/ucm/backend/data/ucm.db

# 4. Fix permissions
sudo chown ucm:ucm /opt/ucm/backend/data/ucm.db
sudo chmod 600 /opt/ucm/backend/data/ucm.db

# 5. Start UCM
sudo systemctl start ucm
```

### Docker Restore

```bash
# Stop container
docker stop ucm

# Restore volume
docker run --rm \
  -v ucm-data:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/ucm-backup-20260110.tar.gz -C /data

# Start container
docker start ucm
```

---

## Automated Backups

### Systemd Timer (Linux)

Create cron job or systemd timer:

```bash
# Edit crontab
sudo crontab -e -u ucm

# Add daily backup at 2 AM
0 2 * * * cp /opt/ucm/backend/data/ucm.db /opt/ucm/backend/data/backups/ucm_backup_$(date +\%Y\%m\%d_\%H\%M\%S).db
```

### Docker Cron

Add to docker-compose.yml:

```yaml
services:
  ucm-backup:
    image: alpine:latest
    volumes:
      - ucm-data:/data
      - ./backups:/backups
    command: sh -c "tar czf /backups/ucm-backup-$$(date +%Y%m%d).tar.gz /data"
    # Run with: docker-compose run --rm ucm-backup
```

---

## Backup Retention

**Manual cleanup:**

```bash
# Keep only last 30 days
find /opt/ucm/backend/data/backups/ -name "ucm_backup_*.db" -mtime +30 -delete
```

---

## Coming in v1.8.4

### Restore UI Features

- 📤 Upload backup file via web interface
- 📋 List available backups with metadata
- ✅ One-click restore with confirmation
- 🔄 Automatic service restart after restore
- 📊 Backup file validation before restore

**ETA:** 1-2 days

---

## Best Practices

✅ **Do:**
- Create backups before major changes
- Test restore process quarterly
- Keep multiple backup versions
- Store backups offsite
- Backup before upgrades

❌ **Don't:**
- Modify backup files manually
- Store only one backup
- Forget to test restores
- Delete old backups immediately

---

## Troubleshooting

### Backup Button Not Working

Check logs:
```bash
sudo journalctl -u ucm -f
```

Check permissions:
```bash
ls -la /opt/ucm/backend/data/backups/
sudo chown -R ucm:ucm /opt/ucm/backend/data/
```

### Database Locked Error

Stop UCM before manual restore:
```bash
sudo systemctl stop ucm
# ... perform restore ...
sudo systemctl start ucm
```

### Backup File Missing

Check if directory exists:
```bash
sudo mkdir -p /opt/ucm/backend/data/backups
sudo chown ucm:ucm /opt/ucm/backend/data/backups
sudo chmod 700 /opt/ucm/backend/data/backups
```

---

**See also:**
- [System Configuration](System-Config)
- [Troubleshooting](Troubleshooting)
- [ROADMAP](https://github.com/NeySlim/ultimate-ca-manager/blob/main/ROADMAP.md) (v1.8.4 features)

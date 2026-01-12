# UCM Log Rotation

## 📋 Configuration

**Location:** `/etc/logrotate.d/ucm`

## 📊 Rotation Schedule

### Application Logs (access.log, error.log)
- **Frequency:** Daily
- **Retention:** 14 days
- **Compression:** Yes (gzip)
- **Total disk usage:** ~10-50 MB (depending on traffic)

### DB Optimizer Log (db-optimizer.log)
- **Frequency:** Weekly
- **Retention:** 8 weeks
- **Compression:** Yes (gzip)
- **Total disk usage:** < 1 MB

## 🔄 How It Works

1. **Daily at ~3 AM**: Logrotate runs (via system cron)
2. **Rotation**: Moves current log to dated file (e.g., `access.log-20260112`)
3. **Compression**: Yesterday's log gets compressed (e.g., `access.log-20260111.gz`)
4. **Service Reload**: UCM service reloaded to open new log files
5. **Cleanup**: Logs older than retention period are deleted

## 📁 Log Files

```
/var/log/ucm/
├── access.log              # Current access log
├── access.log-20260112     # Yesterday (uncompressed)
├── access.log-20260111.gz  # Day before (compressed)
├── access.log-20260110.gz  # ...
├── error.log               # Current error log  
├── error.log-20260112      # Yesterday
├── db-optimizer.log        # DB optimization log
```

## 🛠️ Manual Operations

### Force rotation (testing)
```bash
sudo logrotate -f /etc/logrotate.d/ucm
```

### Test configuration
```bash
sudo logrotate -d /etc/logrotate.d/ucm
```

### View compressed logs
```bash
zcat /var/log/ucm/access.log-20260111.gz | less
zgrep "ERROR" /var/log/ucm/error.log-*.gz
```

## 📈 Disk Space Estimation

**Without rotation:**
- 30 days × 3 MB/day = ~90 MB

**With rotation (14 days + compression):**
- 1 day uncompressed: 3 MB
- 13 days compressed: 13 × 0.6 MB = ~8 MB
- **Total: ~11 MB** (87% savings)

## ⚙️ Configuration Options

Current settings in `/etc/logrotate.d/ucm`:

```
daily          # Rotate every day
rotate 14      # Keep 14 rotations
compress       # Compress old logs
delaycompress  # Don't compress most recent rotation
notifempty     # Don't rotate empty logs
missingok      # Don't error if log missing
dateext        # Use date extension (not .1, .2)
sharedscripts  # Run postrotate once for all logs
```

## 🔧 Troubleshooting

### Logs not rotating
```bash
# Check logrotate status
sudo cat /var/lib/logrotate/status | grep ucm

# Check for errors
sudo journalctl -u logrotate -n 50

# Force rotation
sudo logrotate -f /etc/logrotate.d/ucm
```

### Service not reloading
```bash
# Check UCM service
systemctl status ucm

# Manual reload
systemctl reload ucm
```

### Disk space issues
```bash
# Check log directory size
du -sh /var/log/ucm/

# Find large logs
find /var/log/ucm/ -type f -size +10M

# Emergency cleanup (remove logs > 7 days)
find /var/log/ucm/ -name "*.gz" -mtime +7 -delete
```

## 📝 Integration with Installer

The logrotate configuration is automatically deployed by the UCM installer to `/etc/logrotate.d/ucm` during installation.

---

**Last Updated:** 2026-01-12  
**UCM Version:** 1.9.0

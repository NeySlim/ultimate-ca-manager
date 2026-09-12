# UCM Log Rotation

## Configuration

**Location:** `/etc/logrotate.d/ucm`, installed by the Debian package and by the RPM.

A container writes both streams to standard output and needs none of this. A
source install has no file here either: bound its `access.log` and `error.log`
yourself, or copy `packaging/logrotate/ucm` into place.

## Rotation Schedule

### The gunicorn streams (access.log, error.log)
- **Frequency:** Daily
- **Retention:** 14 days
- **Compression:** Yes (gzip)
- **Total disk usage:** ~10-50 MB (depending on traffic)

`access.log` is the loudest file on a server answering ACME and SCEP polling,
and it is the one this configuration exists for.

### The application log (ucm.log)

Not handled here. The application rotates it itself, ten megabytes over five
generations, roughly sixty megabytes in all, on every kind of install. It is
neither compressed nor aged out by date.

## How It Works

1. **Daily at ~3 AM**: Logrotate runs (via system cron)
2. **Rotation**: Moves current log to dated file (e.g., `access.log-20260112`)
3. **Compression**: Yesterday's log gets compressed (e.g., `access.log-20260111.gz`)
4. **Reopening**: gunicorn is sent `USR1`, which makes it reopen its files. It
   is not reloaded: a reload maps to `HUP`, which gracefully restarts the
   worker and would drop every open WebSocket at each rotation.
5. **Cleanup**: Logs older than retention period are deleted

## Log Files

```
/var/log/ucm/
├── access.log # Current access log
├── access.log-20260112 # Yesterday (uncompressed)
├── access.log-20260111.gz # Day before (compressed)
├── access.log-20260110.gz # ...
├── error.log # Current error log
├── error.log-20260112 # Yesterday
├── ucm.log # Application log, rotated by the application
├── ucm.log.1 # ... over five generations
```

## Manual Operations

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

## Disk Space Estimation

**Without rotation:**
- 30 days × 3 MB/day = ~90 MB

**With rotation (14 days + compression):**
- 1 day uncompressed: 3 MB
- 13 days compressed: 13 × 0.6 MB = ~8 MB
- **Total: ~11 MB** (87% savings)

## Configuration Options

Current settings in `/etc/logrotate.d/ucm`:

```
daily # Rotate every day
rotate 14 # Keep 14 rotations
compress # Compress old logs
delaycompress # Don't compress most recent rotation
notifempty # Don't rotate empty logs
missingok # Don't error if log missing
dateext # Use date extension (not .1, .2)
sharedscripts # Run postrotate once for all logs
create 0640 ucm ucm # Owner and mode of the fresh file
postrotate # Send USR1 so gunicorn reopens, never a reload
```

## Troubleshooting

### Logs not rotating
```bash
# Check logrotate status
sudo cat /var/lib/logrotate/status | grep ucm

# Check for errors
sudo journalctl -u logrotate -n 50

# Force rotation
sudo logrotate -f /etc/logrotate.d/ucm
```

### Logs still going to the rotated file
The reopening did not happen. Check the service, then send the signal by hand.
```bash
# Check UCM service
systemctl status ucm

# Ask gunicorn to reopen its files
systemctl kill -s USR1 ucm.service
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

## Integration with Installer

The Debian package and the RPM install the configuration at
`/etc/logrotate.d/ucm`, as a configuration file: an edit of your own survives
an upgrade.

---

**Last Updated:** 2026-09-12
**UCM Version:** 2.230 and later

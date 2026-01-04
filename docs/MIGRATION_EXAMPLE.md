# UCM Docker Migration Guide

## Quick Migration Between Hosts

### Scenario: Moving from Server A to Server B

**Server A (current):**
- Path: `/mnt/disk2/data/Apps/ucm-docker/`
- Port: 8444 (custom)
- Data: 2.5 GB of certificates and database

**Server B (new):**
- Path: `/opt/ucm/`
- Port: 8443 (default)
- Fresh install

---

## Step-by-Step Migration

### 1️⃣ On Server A - Prepare Backup

```bash
# Stop container (optional, can backup while running)
cd /mnt/disk2/data/Apps/ucm-docker
docker-compose down

# Create complete backup
tar -czf ucm-backup-$(date +%Y%m%d).tar.gz \
    data/ \
    postgres-data/ \
    .env \
    docker-compose.yml \
    docker-compose.postgres.yml

# Check backup size
ls -lh ucm-backup-*.tar.gz
```

**Expected backup contents:**
```
ucm-backup-20260104.tar.gz
├── data/                     # All UCM data
│   ├── ucm.db               # SQLite database
│   ├── ca/                  # CA certificates
│   ├── certs/               # Issued certificates
│   ├── private/             # Private keys
│   ├── https_cert.pem       # HTTPS certificate
│   └── https_key.pem        # HTTPS private key
├── postgres-data/           # PostgreSQL data (if used)
├── .env                     # Configuration
└── docker-compose.yml       # Compose file
```

---

### 2️⃣ Transfer to Server B

```bash
# From Server A - Transfer via SCP
scp ucm-backup-20260104.tar.gz root@server-b:/opt/ucm/

# OR via rsync (shows progress)
rsync -avzP ucm-backup-20260104.tar.gz root@server-b:/opt/ucm/

# OR via USB/network share
cp ucm-backup-20260104.tar.gz /mnt/usb/
# (then copy from USB on Server B)
```

---

### 3️⃣ On Server B - Restore and Start

```bash
# Extract backup
cd /opt/ucm
tar -xzf ucm-backup-20260104.tar.gz

# Adjust .env if needed (optional)
nano .env

# Start UCM
docker-compose up -d

# Check status
docker-compose ps
docker-compose logs -f ucm
```

**That's it!** UCM is now running on Server B with all data intact.

---

## Configuration Changes

### Adjust Paths in .env

If Server B has different storage paths:

```bash
# Original .env from Server A
UCM_HTTPS_PORT=8444
UCM_DATA_DIR=/mnt/disk2/data/Apps/ucm-docker/data
POSTGRES_DATA_DIR=/mnt/disk2/data/Apps/ucm-docker/postgres-data

# Modified .env for Server B
UCM_HTTPS_PORT=8443                    # Changed port
UCM_DATA_DIR=/opt/ucm/data             # New path
POSTGRES_DATA_DIR=/opt/ucm/postgres-data  # New path
```

### Move Data to Custom Location

If you want data on separate storage:

```bash
# Server B - Move data to external storage
mkdir -p /mnt/storage/ucm
mv /opt/ucm/data /mnt/storage/ucm/
mv /opt/ucm/postgres-data /mnt/storage/ucm/

# Update .env
cat > /opt/ucm/.env << 'ENVEOF'
UCM_HTTPS_PORT=8443
UCM_DATA_DIR=/mnt/storage/ucm/data
POSTGRES_DATA_DIR=/mnt/storage/ucm/postgres-data
POSTGRES_PASSWORD=your-secure-password
ENVEOF

# Restart with new paths
docker-compose down
docker-compose up -d
```

---

## Verification Checklist

After migration, verify everything works:

```bash
# ✅ Container running
docker ps | grep ucm

# ✅ Health check passing
docker inspect ucm | grep -A 10 Health

# ✅ Test API endpoint
curl -k https://localhost:8443/api/health
# Expected: {"status":"healthy"}

# ✅ Check logs for errors
docker-compose logs ucm | grep -i error

# ✅ Access web interface
# Open: https://server-b-ip:8443
# Login with existing credentials

# ✅ Verify certificates present
docker exec ucm ls -la /app/backend/data/ca/
docker exec ucm ls -la /app/backend/data/certs/
```

---

## Rollback Plan

If migration fails, rollback to Server A:

```bash
# Server A - Restart original container
cd /mnt/disk2/data/Apps/ucm-docker
docker-compose up -d
```

Your data on Server A remains unchanged during migration.

---

## Production Migration Tips

### Zero-Downtime Migration

1. **Keep Server A running** during migration
2. Set up Server B with backup
3. Test Server B thoroughly
4. Update DNS/load balancer to point to Server B
5. Shutdown Server A

### Database-Specific Notes

**SQLite (docker-compose.yml):**
- Database is in `data/ucm.db`
- Single file, easy to backup
- No extra services needed

**PostgreSQL (docker-compose.postgres.yml):**
- Database is in `postgres-data/`
- ~100-500MB depending on usage
- Backup includes entire PostgreSQL cluster

### Permission Issues

If you get permission errors:

```bash
# Fix ownership (UCM runs as UID 1000)
sudo chown -R 1000:1000 /opt/ucm/data
sudo chown -R 1000:1000 /opt/ucm/postgres-data

# Restart container
docker-compose restart
```

---

## Migration Time Estimates

| Data Size | Transfer Method | Estimated Time |
|-----------|----------------|----------------|
| < 1 GB    | SCP/rsync      | 1-5 minutes    |
| 1-10 GB   | SCP/rsync      | 5-30 minutes   |
| > 10 GB   | rsync/USB      | 30-120 minutes |

**Downtime:** 0-5 minutes (just restart time)

---

## Automated Migration Script

Create a migration helper:

```bash
#!/bin/bash
# ucm-migrate.sh

SOURCE_HOST="$1"
SOURCE_PATH="$2"
DEST_PATH="${3:-/opt/ucm}"

if [ -z "$SOURCE_HOST" ] || [ -z "$SOURCE_PATH" ]; then
    echo "Usage: $0 <source-host> <source-path> [dest-path]"
    echo "Example: $0 root@server-a /mnt/disk2/data/Apps/ucm-docker /opt/ucm"
    exit 1
fi

echo "🚀 Migrating UCM from $SOURCE_HOST:$SOURCE_PATH to $DEST_PATH"

# Create destination
mkdir -p "$DEST_PATH"
cd "$DEST_PATH"

# Sync data
rsync -avzP --exclude 'ucm-*.tar.gz' \
    "$SOURCE_HOST:$SOURCE_PATH/" \
    .

# Start UCM
docker-compose up -d

# Check status
docker-compose ps
docker-compose logs --tail 50 ucm

echo "✅ Migration complete! Access at https://$(hostname -I | awk '{print $1}'):$(grep UCM_HTTPS_PORT .env | cut -d= -f2)"
```

Usage:
```bash
chmod +x ucm-migrate.sh
./ucm-migrate.sh root@old-server /mnt/disk2/data/Apps/ucm-docker /opt/ucm
```

---

## Support

If migration fails:
1. Check Docker logs: `docker-compose logs ucm`
2. Verify permissions: `ls -la data/`
3. Check .env configuration
4. Review DOCKER.md for troubleshooting
5. GitHub Issues: https://github.com/NeySlim/ultimate-ca-manager/issues

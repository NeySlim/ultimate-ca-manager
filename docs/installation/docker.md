# Docker Installation Guide

Complete guide for installing Ultimate Certificate Manager using Docker.

## Prerequisites

- Docker Engine 20.10+ or Docker Desktop
- 2GB RAM minimum, 4GB recommended
- 5GB free disk space

**Install Docker:**
- Ubuntu/Debian: `sudo apt install docker.io`
- RHEL/Rocky/Alma: `sudo dnf install docker`
- Other: https://docs.docker.com/engine/install/

---

## Quick Start

### Pull and Run

```bash
# Pull latest image
docker pull neyslim/ultimate-ca-manager:latest

# Run container
docker run -d \
  --name ucm \
  -p 8443:8443 \
  -p 8080:8080 \
  -v ucm-data:/opt/ucm/data \
  -v ucm-config:/etc/ucm \
  --restart unless-stopped \
  neyslim/ultimate-ca-manager:latest
```

**Access:** https://localhost:8443 or https://your-server-fqdn:8443
**Credentials:** `admin`, with the password generated at first start: `docker exec <container> cat /opt/ucm/data/initial-admin-password`. The first login must set a new password before anything else, which removes the file. To provide the password yourself, see [First access](README.md#first-access).

---

## Docker Compose (Recommended)

### Basic Configuration

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  ucm:
    image: neyslim/ultimate-ca-manager:latest
    container_name: ucm
    restart: unless-stopped
    ports:
      - "8443:8443"
      - "8080:8080"   # HTTP — CRL/CDP and OCSP public endpoints
    volumes:
      - ucm-data:/opt/ucm/data
      - ucm-config:/etc/ucm   # holds master.key
    environment:
      - UCM_FQDN=ucm.example.com

volumes:
  ucm-data:
  ucm-config:
```

**Start:**
```bash
docker-compose up -d
```

### Advanced Configuration

```yaml
version: '3.8'

services:
  ucm:
    image: neyslim/ultimate-ca-manager:latest
    container_name: ucm
    restart: unless-stopped

    ports:
      # Container side must equal UCM_HTTPS_PORT, which is where UCM listens
      - "8443:8443"
      - "8080:8080"   # HTTP — CRL/CDP and OCSP public endpoints

    volumes:
      # Persistent data
      - ucm-data:/opt/ucm/data

      # Persistent configuration: master.key, which encrypts the private keys
      - ucm-config:/etc/ucm

      # Optional: Custom HTTPS certificates
      # - ./certs/https_cert.pem:/opt/ucm/data/https_cert.pem:ro
      # - ./certs/https_key.pem:/opt/ucm/data/https_key.pem:ro

    environment:
      # Network
      - UCM_FQDN=ucm.example.com
      - UCM_HTTPS_PORT=8443

      # SMTP, ACME, session timeout and the other application settings are
      # configured in the web interface, not through the environment.

    healthcheck:
      # Same port as UCM_HTTPS_PORT
      test: ["CMD", "curl", "-f", "-k", "https://localhost:8443/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

    # Security
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - SETGID
      - SETUID

volumes:
  ucm-data:
  ucm-config:
```

---

## Environment Variables

### Required

| Variable | Default | Description |
|----------|---------|-------------|
| `UCM_FQDN` | `ucm.example.com` | Server FQDN (important for SSL) |
| `UCM_HTTPS_PORT` | `8443` | HTTPS port |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `UCM_DEBUG` | `false` | Enable debug mode |
| `UCM_LOG_LEVEL` | `INFO` | Log level (DEBUG/INFO/WARNING/ERROR) |
| `UCM_LOG_MAX_BYTES` | `10485760` | Size at which `/opt/ucm/data/ucm.log` is rotated (10 MB) |
| `UCM_LOG_BACKUPS` | `5` | Generations of `ucm.log` kept in the data volume |
| `UCM_WORKER_TIMEOUT` | `120` | Seconds a web request may run before the worker is restarted, 30 to 3600; out of bounds the container refuses to start |
| `UCM_SECRET_KEY` | auto-generated | Session secret key |
| `UCM_CONFIG_DIR` | `/etc/ucm` | Directory holding `ucm.env` and `master.key`. Changing it does not change the Docker mounts: mount a persistent directory at the configured path as well as the data directory |
| `DATABASE_URL` | (unset → SQLite) | SQLAlchemy URL. Set to `postgresql://user:pass@host:5432/dbname` to use an external PostgreSQL 13+ instance instead of the bundled SQLite. |
| `UCM_HA` | (unset) | `1` enables HA mode: settings and restarts propagate to every node (a restart exits each container in turn with code 0: use the restart policy `always` or `unless-stopped`, as `on-failure` and `no` leave the container stopped), operations that only change the local host are refused (see [HA.md](../HA.md)). Requires `DATABASE_URL` (PostgreSQL), `UCM_SECRET_KEY` and `KEY_ENCRYPTION_KEY`, identical on every node |
| `UCM_NODE_ID` | container hostname | Node name reported as `node_id` by `/health` |
| `BACKUP_MAX_UPLOAD_MB` | `512` | Largest archive written before 3.0 (format v1 to v3) a restore accepts and reads, in MB; its decompressed content may be four times that. Every other request keeps the 50 MB limit. |
| `BACKUP_MAX_ARCHIVE_MB` | `0` | Largest v4 archive (written since 3.0) a restore accepts, in MB; `0` accepts any size. |
| `UCM_ACCEPT_MAJOR_UPGRADE` | (unset) | `3` lets the 3.x image upgrade a database last started by 2.254; unset or any other value, the container stops on such a database without changing anything (see [Image tags and major upgrades](#image-tags-and-major-upgrades)). A fresh or 3.x database ignores it. |

See full list in [docker-compose.yml](../../docker-compose.yml). SMTP, ACME, the session timeout and the other application settings are configured in the web interface.

---

## Data Persistence

### Using Named Volumes (Recommended)

Mount both the data and configuration directories on persistent volumes.

```bash
docker volume create ucm-data
docker volume create ucm-config
docker run -v ucm-data:/opt/ucm/data -v ucm-config:/etc/ucm ...
```

### Using Bind Mounts

```bash
mkdir -p /opt/ucm/data /opt/ucm/config
chown -R 1000:1000 /opt/ucm/data /opt/ucm/config
docker run -v /opt/ucm/data:/opt/ucm/data -v /opt/ucm/config:/etc/ucm ...
```

The container runs as UID 1000 and cannot change the owner of a bind-mounted directory, so a directory left to root (or created by Docker on the first run) is refused at startup. Give it to UID 1000 as above rather than opening it to everyone with `chmod 777`; the same applies to a host directory mounted on `/etc/ucm`.

### Data Structure

```
ucm-data/
├── ucm.db # SQLite database (omitted when DATABASE_URL points to PostgreSQL)
├── ucm.db-wal # Its write-ahead log: writes not yet in ucm.db, never to delete
├── ucm.db-shm # Its WAL index
├── https_cert.pem # HTTPS certificate
├── https_key.pem # HTTPS private key
├── cas/ # Certificate Authority files
├── certs/ # Certificate files
├── backups/ # Automatic backups
├── logs/ # Application logs
└── temp/ # Temporary files
```

---

## Custom HTTPS Certificates

### Option 1: Environment Variables

```bash
docker run -e UCM_HTTPS_CERT="$(cat cert.pem)" \
           -e UCM_HTTPS_KEY="$(cat key.pem)" \
           ...
```

### Option 2: Volume Mount

```bash
docker run -v /path/to/cert.pem:/opt/ucm/data/https_cert.pem:ro \
           -v /path/to/key.pem:/opt/ucm/data/https_key.pem:ro \
           ...
```

### Certificate changes without a restart

Applying or regenerating the HTTPS certificate in **Settings > HTTPS**, a renewal of the applied certificate, and a change of the mTLS settings or of the WSTEP switch reload the TLS listener in place: UCM sends SIGHUP to its gunicorn master, which re-reads its configuration and replaces its worker. The container keeps running, whatever its restart policy, and needs no access to the Docker socket. Settings > HTTPS shows *Renewed, not served yet* while the listener still presents another certificate than the one on disk; the container log says why a reload failed. Files replaced by hand on a mounted volume are loaded the same way with `docker kill --signal=HUP ucm`. In HA mode a rolling restart of the nodes is requested instead.

---

## Update & Maintenance

### Update to Latest Version

```bash
# Pull new image
docker pull neyslim/ultimate-ca-manager:latest

# Stop and remove old container
docker stop ucm
docker rm ucm

# Start with same configuration
docker run -d \
  --name ucm \
  -p 8443:8443 \
  -p 8080:8080 \
  -v ucm-data:/opt/ucm/data \
  -v ucm-config:/etc/ucm \
  --restart unless-stopped \
  neyslim/ultimate-ca-manager:latest
```

`/etc/ucm` holds `master.key`. If the old container ran without a volume there, copy the key out before `docker rm` (`docker cp ucm:/etc/ucm/master.key ./master.key`) and into the new container afterwards.

**With Docker Compose:**
```bash
docker-compose pull
docker-compose up -d
```

### Image tags and major upgrades

| Tag | Moves to |
|-----|----------|
| `3.0`, `2.254.4`, ... | Never: one release |
| `3` (and `3-fips`) | Each stable 3.x release, never a later major version |
| `2` (and `2-fips`) | Each stable 2.254.N maintenance release |
| `latest` (and `latest-fips`) | The highest stable release, whatever its major version |

Release candidates get only their own tag (`3.1-rc1`, `3.1-rc1-fips`). Pin `3` to receive every 3.x update automatically without a later major version arriving unannounced.

Moving to a new major version is an explicit step. A 3.x image started on a database last started by 2.254 (SQLite in the volume, or PostgreSQL through `DATABASE_URL`, every HA node included) stops before writing anything and prints:

```
This database was last started by UCM 2.254 and this image is UCM 3: starting it would upgrade the database to the new major version, which 2.254 cannot start afterwards. Nothing was changed.
To upgrade: back up the data volume (and the PostgreSQL database if you use one), then set UCM_ACCEPT_MAJOR_UPGRADE=3 and start again. See UPGRADE.md, Upgrading to v3.0.
To stay on 2.x: pin the image tag '2' (or an exact version, 2.254.N) instead of 'latest'.
```

The container exits with code 78: `docker logs <container>` shows the message, `docker ps -a` shows `Exited (78)`, or `Restarting (78)` with a restart policy, each new start refusing the same way. To upgrade, back up, then add `-e UCM_ACCEPT_MAJOR_UPGRADE=3` (or `UCM_ACCEPT_MAJOR_UPGRADE: "3"` under `environment:` in Compose) and start again; the variable can stay set, a 3.x database ignores it. An accepted upgrade of a SQLite database that stopped partway resumes at the next start, variable set or not. Any other value (`true`, `1`, `4`) is refused, so consent given for 3 never covers a later major version. The Helm chart sets it for you (`majorUpgrade.accept`).

### Backup Data

```bash
# Backup both volumes to a tarball
docker run --rm -v ucm-data:/data -v ucm-config:/config -v $(pwd):/backup \
  alpine tar czf /backup/ucm-backup-$(date +%Y%m%d).tar.gz -C / data config
```

### Restore Data

```bash
# Restore from tarball
docker run --rm -v ucm-data:/data -v ucm-config:/config -v $(pwd):/backup \
  alpine tar xzf /backup/ucm-backup-20260109.tar.gz -C /
```

---

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker logs ucm

# Check if port is already in use
sudo netstat -tlnp | grep 8443
```

### SSL Certificate Issues

```bash
# Regenerate certificate (or Settings > HTTPS > Regenerate, without a restart)
docker exec ucm rm -f /opt/ucm/data/https_cert.pem /opt/ucm/data/https_key.pem
docker restart ucm
```

### Database Locked

A write that meets another write waits up to 5 seconds, then answers `503` with `Retry-After`: retry it. Never delete `ucm.db-wal`, `ucm.db-shm` or `ucm.db-journal` to clear a lock: they hold writes not yet in `ucm.db`, and the database loses them or is corrupted. A lock that outlives a restart of the container comes from another process holding the file (a `sqlite3` shell, a second container on the same volume): stop it. The volume must be on a local filesystem: SQLite's WAL does not work over a network filesystem (https://www.sqlite.org/wal.html).

### Health Check Failing

```bash
# Test health endpoint
docker exec ucm curl -k https://localhost:8443/api/health

# Check if Gunicorn is running
docker exec ucm ps aux | grep gunicorn
```

---

## Advanced Deployment

### Reverse Proxy (Nginx)

UCM uses WebSocket (Socket.IO) for real-time updates. Your reverse proxy must support WebSocket upgrade.

```nginx
# Add at http {} level (outside server blocks)
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 443 ssl http2;
    server_name ucm.example.com;

    ssl_certificate /etc/nginx/ssl/ucm.crt;
    ssl_certificate_key /etc/nginx/ssl/ucm.key;

    # Socket.IO WebSocket — must be before catch-all
    location /socket.io/ {
        proxy_pass https://localhost:8443/socket.io/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
    }

    location / {
        proxy_pass https://localhost:8443;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Important:** Add the proxy origin to UCM's CORS allowlist:
```bash
# In .env or docker-compose environment
CORS_EXTRA_ORIGINS=https://ucm.example.com
```

Without this, WebSocket connections from the proxy domain will be rejected.

### Multi-Architecture

Images are available for:
- `linux/amd64` (x86_64)
- `linux/arm64` (ARM64/aarch64)

Docker automatically pulls the correct architecture.

---

## Next Steps

- [User Guide](../USER_GUIDE.md)
- [Admin Guide](../ADMIN_GUIDE.md)
- [API Reference](../API_REFERENCE.md)

---

**Questions?** Open an issue on [GitHub](https://github.com/NeySlim/ultimate-ca-manager/issues)

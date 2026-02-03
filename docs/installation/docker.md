# Docker Installation Guide

Complete guide for installing Ultimate CA Manager using Docker.

## 🐳 Prerequisites

- Docker Engine 20.10+ or Docker Desktop
- 2GB RAM minimum, 4GB recommended
- 5GB free disk space

**Install Docker:**
- Ubuntu/Debian: `sudo apt install docker.io`
- RHEL/Rocky/Alma: `sudo dnf install docker`
- Other: https://docs.docker.com/engine/install/

---

## 🚀 Quick Start

### Pull and Run

```bash
# Pull latest image
docker pull ghcr.io/neyslim/ultimate-ca-manager:2.0.3

# Run container
docker run -d \
  --name ucm \
  -p 8443:8443 \
  -v ucm-data:/app/backend/data \
  --restart unless-stopped \
  ghcr.io/neyslim/ultimate-ca-manager:2.0.3
```

**Access:** https://localhost:8443  
**Credentials:** admin / changeme123

---

## 📝 Docker Compose (Recommended)

### Basic Configuration

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
      - ucm-data:/app/backend/data
    environment:
      - UCM_FQDN=ucm.example.com
      - UCM_ACME_ENABLED=true

volumes:
  ucm-data:
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
    image: ghcr.io/neyslim/ultimate-ca-manager:2.0.3
    container_name: ucm
    restart: unless-stopped
    
    ports:
      - "8443:8443"
    
    volumes:
      # Persistent data
      - ucm-data:/app/backend/data
      
      # Optional: Custom HTTPS certificates
      # - ./certs/https_cert.pem:/app/backend/data/https_cert.pem:ro
      # - ./certs/https_key.pem:/app/backend/data/https_key.pem:ro
    
    environment:
      # Network
      - UCM_FQDN=ucm.example.com
      - UCM_HTTPS_PORT=8443
      
      # Security
      - UCM_SESSION_TIMEOUT=3600
      - UCM_JWT_EXPIRATION=86400
      
      # Features
      - UCM_ACME_ENABLED=true
      - UCM_CACHE_ENABLED=true
      
      # Email notifications (optional)
      - UCM_SMTP_ENABLED=true
      - UCM_SMTP_SERVER=smtp.gmail.com
      - UCM_SMTP_PORT=587
      - UCM_SMTP_USERNAME=your@email.com
      - UCM_SMTP_PASSWORD=yourpassword
      - UCM_SMTP_FROM=noreply@ucm.example.com
    
    healthcheck:
      test: ["CMD", "curl", "-f", "-k", "https://localhost:8443/"]
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
```

---

## 🔧 Environment Variables

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
| `UCM_SECRET_KEY` | auto-generated | Session secret key |
| `UCM_JWT_SECRET` | auto-generated | JWT secret key |
| `UCM_SESSION_TIMEOUT` | `3600` | Session timeout (seconds) |
| `UCM_JWT_EXPIRATION` | `86400` | JWT token expiration (seconds) |
| `UCM_ACME_ENABLED` | `true` | Enable ACME protocol |
| `UCM_CACHE_ENABLED` | `true` | Enable response caching |
| `UCM_SMTP_ENABLED` | `false` | Enable email notifications |

See full list in [docker-compose.yml](../../docker-compose.yml)

---

## 💾 Data Persistence

### Using Named Volumes (Recommended)

```bash
docker volume create ucm-data
docker run -v ucm-data:/app/backend/data ...
```

### Using Bind Mounts

```bash
mkdir -p /opt/ucm/data
docker run -v /opt/ucm/data:/app/backend/data ...
```

### Data Structure

```
ucm-data/
├── ucm.db              # SQLite database
├── https_cert.pem      # HTTPS certificate
├── https_key.pem       # HTTPS private key
├── cas/                # Certificate Authority files
├── certs/              # Certificate files
├── backups/            # Automatic backups
├── logs/               # Application logs
└── temp/               # Temporary files
```

---

## 🔐 Custom HTTPS Certificates

### Option 1: Environment Variables

```bash
docker run -e UCM_HTTPS_CERT="$(cat cert.pem)" \
           -e UCM_HTTPS_KEY="$(cat key.pem)" \
           ...
```

### Option 2: Volume Mount

```bash
docker run -v /path/to/cert.pem:/app/backend/data/https_cert.pem:ro \
           -v /path/to/key.pem:/app/backend/data/https_key.pem:ro \
           ...
```

---

## 🔄 Update & Maintenance

### Update to Latest Version

```bash
# Pull new image
docker pull ghcr.io/neyslim/ultimate-ca-manager:2.0.3

# Stop and remove old container
docker stop ucm
docker rm ucm

# Start with same configuration
docker run -d \
  --name ucm \
  -p 8443:8443 \
  -v ucm-data:/app/backend/data \
  --restart unless-stopped \
  ghcr.io/neyslim/ultimate-ca-manager:2.0.3
```

**With Docker Compose:**
```bash
docker-compose pull
docker-compose up -d
```

### Backup Data

```bash
# Backup volume to tarball
docker run --rm -v ucm-data:/data -v $(pwd):/backup \
  alpine tar czf /backup/ucm-backup-$(date +%Y%m%d).tar.gz -C /data .
```

### Restore Data

```bash
# Restore from tarball
docker run --rm -v ucm-data:/data -v $(pwd):/backup \
  alpine tar xzf /backup/ucm-backup-20260109.tar.gz -C /data
```

---

## 🐛 Troubleshooting

### Container Won't Start

```bash
# Check logs
docker logs ucm

# Check if port is already in use
sudo netstat -tlnp | grep 8443
```

### SSL Certificate Issues

```bash
# Regenerate certificate
docker exec ucm rm -f /app/backend/data/https_cert.pem /app/backend/data/https_key.pem
docker restart ucm
```

### Database Locked

```bash
# Stop container
docker stop ucm

# Remove lock file
docker run --rm -v ucm-data:/data alpine rm -f /data/ucm.db-journal

# Restart
docker start ucm
```

### Health Check Failing

```bash
# Test health endpoint
docker exec ucm curl -k https://localhost:8443/api/health

# Check if Gunicorn is running
docker exec ucm ps aux | grep gunicorn
```

---

## 🎯 Advanced Deployment

### Portainer Stack

See: [docker-compose.portainer.yml](../../docker-compose.portainer.yml)

### Reverse Proxy (Nginx)

```nginx
server {
    listen 443 ssl http2;
    server_name ucm.example.com;
    
    ssl_certificate /etc/nginx/ssl/ucm.crt;
    ssl_certificate_key /etc/nginx/ssl/ucm.key;
    
    location / {
        proxy_pass https://localhost:8443;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Multi-Architecture

Images are available for:
- `linux/amd64` (x86_64)
- `linux/arm64` (ARM64/aarch64)

Docker automatically pulls the correct architecture.

---

## 📚 Next Steps

- [Configuration Guide](../administration/configuration.md)
- [First Steps](../user-guide/first-steps.md)
- [CA Management](../user-guide/ca-management.md)

---

**Questions?** Open an issue on [GitHub](https://github.com/NeySlim/ultimate-ca-manager/issues)

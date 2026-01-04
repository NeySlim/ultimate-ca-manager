# UCM Docker Deployment Guide

## Table of Contents
1. [Quick Start](#quick-start)
2. [Building the Image](#building-the-image)
3. [Running with Docker](#running-with-docker)
4. [Running with Docker Compose](#running-with-docker-compose)
5. [Configuration](#configuration)
6. [Volumes and Persistence](#volumes-and-persistence)
7. [Security](#security)
8. [Multi-Architecture](#multi-architecture)
9. [Troubleshooting](#troubleshooting)

## Quick Start

### Using Docker Compose (Recommended)

```bash
# Clone repository
git clone https://github.com/NeySlim/ultimate-ca-manager.git
cd ultimate-ca-manager

# Start UCM
docker-compose up -d

# Check logs
docker-compose logs -f ucm

# Access web interface
open https://localhost:8443
```

**Default credentials:**
- Username: `admin`
- Password: `changeme123`

⚠️ **CHANGE THIS PASSWORD IMMEDIATELY!**

### Using Docker Run

```bash
# Pull image (when available on Docker Hub)
docker pull neyslim/ucm:latest

# Or build locally
docker build -t ucm:latest .

# Run container
docker run -d \
  --name ucm \
  -p 8443:8443 \
  -v ucm-data:/app/backend/data \
  --restart unless-stopped \
  ucm:latest

# Access web interface
open https://localhost:8443
```

## Building the Image

### Standard Build

```bash
# Build with default settings
docker build -t ucm:latest .

# Build with specific version
docker build -t ucm:1.0.0 --build-arg VERSION=1.0.0 .

# Build without cache
docker build --no-cache -t ucm:latest .
```

### Using Build Script

```bash
# Standard build
./docker/build.sh

# Build and push to registry
./docker/build.sh --push

# Build for multiple architectures
./docker/build.sh --multiarch

# Build specific tag
./docker/build.sh --tag 1.0.0

# Build without cache
./docker/build.sh --no-cache
```

### Multi-Architecture Build

Build for AMD64 and ARM64 (Raspberry Pi, Apple Silicon):

```bash
# Using build script
./docker/build.sh --multiarch

# Or manually
docker buildx create --name ucm-builder --use
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag ucm:latest \
  --push \
  .
```

## Running with Docker

### Basic Run

```bash
docker run -d \
  --name ucm \
  -p 8443:8443 \
  -v ucm-data:/app/backend/data \
  ucm:latest
```

### Run with Custom Configuration

```bash
docker run -d \
  --name ucm \
  -p 8443:8443 \
  -v ucm-data:/app/backend/data \
  -v $(pwd)/custom.env:/app/.env:ro \
  -e UCM_SECRET_KEY="your-secret-key" \
  -e UCM_JWT_SECRET="your-jwt-secret" \
  ucm:latest
```

### Run with Resource Limits

```bash
docker run -d \
  --name ucm \
  -p 8443:8443 \
  -v ucm-data:/app/backend/data \
  --memory="1g" \
  --cpus="2" \
  --restart unless-stopped \
  ucm:latest
```

## Running with Docker Compose

### Standard Deployment (SQLite)

```yaml
# docker-compose.yml
version: '3.8'

services:
  ucm:
    image: ucm:latest
    container_name: ucm
    restart: unless-stopped
    ports:
      - "8443:8443"
    volumes:
      - ucm-data:/app/backend/data
    environment:
      - UCM_DOCKER=1

volumes:
  ucm-data:
```

Start:
```bash
docker-compose up -d
```

### Production Deployment (PostgreSQL)

```bash
# Use PostgreSQL backend for better performance
docker-compose -f docker-compose.postgres.yml up -d
```

### Behind Reverse Proxy

```yaml
version: '3.8'

services:
  ucm:
    image: ucm:latest
    container_name: ucm
    restart: unless-stopped
    expose:
      - "8443"
    volumes:
      - ucm-data:/app/backend/data
    networks:
      - web
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.ucm.rule=Host(`ca.example.com`)"
      - "traefik.http.routers.ucm.tls=true"
      - "traefik.http.routers.ucm.tls.certresolver=letsencrypt"

networks:
  web:
    external: true

volumes:
  ucm-data:
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `UCM_DOCKER` | Indicates running in Docker | `1` |
| `UCM_SECRET_KEY` | Flask secret key | Auto-generated |
| `UCM_JWT_SECRET` | JWT secret key | Auto-generated |
| `UCM_HTTPS_PORT` | HTTPS port | `8443` |
| `UCM_DATABASE_PATH` | Database file path | `/app/backend/data/ucm.db` |
| `DATABASE_TYPE` | Database type (sqlite/postgresql) | `sqlite` |
| `DATABASE_HOST` | PostgreSQL host | - |
| `DATABASE_PORT` | PostgreSQL port | `5432` |
| `DATABASE_NAME` | PostgreSQL database name | - |
| `DATABASE_USER` | PostgreSQL user | - |
| `DATABASE_PASSWORD` | PostgreSQL password | - |

### Custom Configuration File

```bash
# Create custom.env
cat > custom.env << EOF
SECRET_KEY=your-custom-secret-key-here
JWT_SECRET_KEY=your-custom-jwt-secret-here
HTTPS_PORT=8443
DATABASE_PATH=/app/backend/data/ucm.db
EOF

# Mount as volume
docker run -d \
  --name ucm \
  -p 8443:8443 \
  -v ucm-data:/app/backend/data \
  -v $(pwd)/custom.env:/app/.env:ro \
  ucm:latest
```

## Volumes and Persistence

### Important Data Locations

| Path | Description | Persistent |
|------|-------------|------------|
| `/app/backend/data` | All application data | ✅ Yes |
| `/app/backend/data/ucm.db` | SQLite database | ✅ Yes |
| `/app/backend/data/ca` | CA certificates and keys | ✅ Yes |
| `/app/backend/data/certs` | Issued certificates | ✅ Yes |
| `/app/backend/data/private` | Private keys | ✅ Yes |
| `/app/.env` | Configuration file | ⚠️ Optional |

### Backup Data

```bash
# Create backup
docker run --rm \
  -v ucm-data:/data \
  -v $(pwd)/backup:/backup \
  alpine \
  tar czf /backup/ucm-backup-$(date +%Y%m%d).tar.gz /data

# Restore backup
docker run --rm \
  -v ucm-data:/data \
  -v $(pwd)/backup:/backup \
  alpine \
  tar xzf /backup/ucm-backup-YYYYMMDD.tar.gz -C /
```

### Migrate Data

```bash
# Export from old container
docker cp ucm:/app/backend/data ./ucm-data-export

# Import to new container
docker cp ./ucm-data-export/. new-ucm:/app/backend/data/
docker restart new-ucm
```

## Security

### Security Features

- ✅ **Non-root user**: Container runs as UID 1000
- ✅ **Read-only root**: Application files are read-only
- ✅ **Dropped capabilities**: Minimal Linux capabilities
- ✅ **No new privileges**: `no-new-privileges` security option
- ✅ **Health checks**: Automated health monitoring
- ✅ **HTTPS only**: No HTTP support
- ✅ **Secret generation**: Auto-generated secrets on first run

### Hardening

```yaml
services:
  ucm:
    image: ucm:latest
    security_opt:
      - no-new-privileges:true
      - seccomp:unconfined
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - SETGID
      - SETUID
    read_only: false  # Database needs write access
    tmpfs:
      - /tmp:size=100M,mode=1777
```

### Secrets Management

Use Docker secrets for production:

```bash
# Create secrets
echo "your-secret-key" | docker secret create ucm_secret_key -
echo "your-jwt-secret" | docker secret create ucm_jwt_secret -

# Use in compose
services:
  ucm:
    image: ucm:latest
    secrets:
      - ucm_secret_key
      - ucm_jwt_secret
    environment:
      - UCM_SECRET_KEY_FILE=/run/secrets/ucm_secret_key
      - UCM_JWT_SECRET_FILE=/run/secrets/ucm_jwt_secret

secrets:
  ucm_secret_key:
    external: true
  ucm_jwt_secret:
    external: true
```

## Multi-Architecture

UCM Docker images support:
- **linux/amd64** - Intel/AMD 64-bit
- **linux/arm64** - ARM 64-bit (Raspberry Pi 4/5, Apple Silicon)

### Pull Multi-Arch Image

```bash
# Docker automatically selects the right architecture
docker pull neyslim/ucm:latest

# Verify architecture
docker inspect neyslim/ucm:latest | grep Architecture
```

### Run on Raspberry Pi

```bash
# Same command works on ARM64
docker run -d \
  --name ucm \
  -p 8443:8443 \
  -v ucm-data:/app/backend/data \
  --restart unless-stopped \
  ucm:latest
```

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker logs ucm

# Check health status
docker inspect ucm | grep -A 10 Health

# Interactive shell
docker exec -it ucm /bin/bash
```

### Permission Issues

```bash
# Check volume permissions
docker exec ucm ls -la /app/backend/data

# Fix permissions
docker exec -u root ucm chown -R ucm:ucm /app/backend/data
```

### Database Issues

```bash
# Check database file
docker exec ucm ls -la /app/backend/data/ucm.db

# Database integrity check
docker exec ucm sqlite3 /app/backend/data/ucm.db "PRAGMA integrity_check;"

# Recreate database (⚠️ destroys data)
docker exec ucm rm /app/backend/data/ucm.db
docker restart ucm
```

### Network Issues

```bash
# Test from inside container
docker exec ucm curl -k https://localhost:8443/api/health

# Check port binding
docker port ucm

# Check firewall
sudo ufw status
sudo ufw allow 8443/tcp
```

### Memory Issues

```bash
# Check resource usage
docker stats ucm

# Increase memory limit
docker update --memory="2g" ucm
```

### Rebuild Image

```bash
# Clean rebuild
docker-compose down
docker rmi ucm:latest
docker-compose build --no-cache
docker-compose up -d
```

## Production Deployment

### Using Nginx Reverse Proxy

```nginx
server {
    listen 443 ssl http2;
    server_name ca.example.com;

    ssl_certificate /etc/letsencrypt/live/ca.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ca.example.com/privkey.pem;

    location / {
        proxy_pass https://localhost:8443;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### Using Traefik

```yaml
services:
  ucm:
    image: ucm:latest
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.ucm.rule=Host(`ca.example.com`)"
      - "traefik.http.routers.ucm.tls=true"
      - "traefik.http.routers.ucm.tls.certresolver=letsencrypt"
      - "traefik.http.services.ucm.loadbalancer.server.port=8443"
      - "traefik.http.services.ucm.loadbalancer.server.scheme=https"
```

### Monitoring

```yaml
services:
  ucm:
    image: ucm:latest
    labels:
      - "prometheus.io/scrape=true"
      - "prometheus.io/port=8443"
      - "prometheus.io/path=/metrics"
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

## Support

- **Issues**: [GitHub Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)
- **Documentation**: [README.md](../README.md)
- **Deployment**: [DEPLOYMENT.md](../DEPLOYMENT.md)

---

**Docker Version**: 1.0.0  
**Last Updated**: January 4, 2026

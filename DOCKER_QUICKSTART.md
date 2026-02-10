# UCM v2.0.3 - Docker Quick Start Guide

## 🚀 Quick Start (5 minutes)

### Option 1: Simple Deployment

```bash
# 1. Clone or download UCM
git clone https://github.com/NeySlim/ultimate-ca-manager.git
cd ucm

# 2. Create environment file
cp .env.docker .env

# 3. Edit FQDN (REQUIRED!)
nano .env
# Set: UCM_FQDN=ucm.example.com

# 4. Start container
docker-compose up -d

# 5. Access web interface
# https://ucm.example.com:8443
# Login: admin / changeme123
# ⚠️ CHANGE PASSWORD IMMEDIATELY!
```

### Option 2: Production Deployment

```bash
# 1. Set environment variables
export UCM_FQDN=ca.company.com
export UCM_SMTP_ENABLED=true
export UCM_SMTP_SERVER=smtp.gmail.com
export UCM_SMTP_USERNAME=alerts@company.com
export UCM_SMTP_PASSWORD=your-app-password

# 2. Start with production config
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 3. View logs
docker-compose logs -f ucm
```

## 📋 Configuration

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `UCM_FQDN` | **REQUIRED** Your domain name | `ucm.example.com` |
| `UCM_HTTPS_PORT` | HTTPS port | `8443` (default) |

### Optional Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `UCM_SECRET_KEY` | Session encryption key | Auto-generated |
| `UCM_JWT_SECRET` | JWT signing key | Auto-generated |
| `UCM_DEBUG` | Debug mode | `false` |
| `UCM_LOG_LEVEL` | Logging level | `INFO` |

See `.env.example` for complete list of configuration options.

## 🔐 Security Setup

### 1. Change Admin Password

```bash
# First login
https://your-domain:8443
Username: admin
Password: changeme123

# Navigate to: Settings → User Management → Change Password
```

### 2. Generate Secure Secrets (Recommended)

```bash
# Generate random secrets
export UCM_SECRET_KEY=$(openssl rand -hex 32)
export UCM_JWT_SECRET=$(openssl rand -hex 32)

# Save to .env file
cat >> .env <<EOF
UCM_SECRET_KEY=$UCM_SECRET_KEY
UCM_JWT_SECRET=$UCM_JWT_SECRET
EOF

# Restart container
docker-compose restart
```

### 3. Use Trusted HTTPS Certificate

**Option A: Mount certificate files**

```yaml
# docker-compose.yml
volumes:
  - ./certs/https_cert.pem:/app/backend/data/https_cert.pem:ro
  - ./certs/https_key.pem:/app/backend/data/https_key.pem:ro
```

**Option B: Environment variables**

```bash
export UCM_HTTPS_CERT="$(cat /path/to/cert.pem)"
export UCM_HTTPS_KEY="$(cat /path/to/key.pem)"
```

## 📧 Email Notifications

Enable SMTP for certificate expiration alerts:

```bash
# .env file
UCM_SMTP_ENABLED=true
UCM_SMTP_SERVER=smtp.gmail.com
UCM_SMTP_PORT=587
UCM_SMTP_USERNAME=alerts@example.com
UCM_SMTP_PASSWORD=app-specific-password
UCM_SMTP_FROM=noreply@example.com
UCM_SMTP_TLS=true
```

**Gmail App Password**: https://support.google.com/accounts/answer/185833

## 🔄 Backup & Restore

### Automatic Backups

Enabled by default. Backups created on container start.

```bash
# View backups
docker exec ucm ls -lh /app/backend/data/backups/

# Copy backup to host
docker cp ucm:/app/backend/data/backups/ucm-backup-20260109.db ./
```

### Manual Backup

```bash
# Stop container
docker-compose stop

# Backup data volume
docker run --rm \
  -v ucm-data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/ucm-backup-$(date +%Y%m%d).tar.gz /data

# Restart container
docker-compose start
```

### Restore Backup

```bash
# Stop container
docker-compose down

# Restore data
docker run --rm \
  -v ucm-data:/data \
  -v $(pwd):/backup \
  alpine sh -c "cd / && tar xzf /backup/ucm-backup-20260109.tar.gz"

# Restart
docker-compose up -d
```

## 🌐 Reverse Proxy Setup

### Nginx

```nginx
server {
    listen 443 ssl http2;
    server_name ucm.example.com;
    
    ssl_certificate /etc/ssl/certs/ucm.crt;
    ssl_certificate_key /etc/ssl/private/ucm.key;
    
    # mTLS (optional)
    # ssl_client_certificate /etc/ssl/ca/client-ca.crt;
    # ssl_verify_client optional;
    
    location / {
        proxy_pass https://ucm:8443;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # mTLS headers
        proxy_set_header X-SSL-Client-Cert $ssl_client_escaped_cert;
        proxy_set_header X-SSL-Client-Verify $ssl_client_verify;
        proxy_set_header X-SSL-Client-S-DN $ssl_client_s_dn;
    }
}
```

### Traefik

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.ucm.rule=Host(`ucm.example.com`)"
  - "traefik.http.routers.ucm.tls=true"
  - "traefik.http.services.ucm.loadbalancer.server.port=8443"
  - "traefik.http.services.ucm.loadbalancer.server.scheme=https"
```

## 🛠️ Troubleshooting

### Container won't start

```bash
# Check logs
docker-compose logs ucm

# Common issues:
# 1. Port already in use
#    → Change UCM_HTTPS_PORT in .env
# 2. Permission denied on volume
#    → chmod 755 ./data
# 3. Invalid FQDN
#    → Must be valid domain name
```

### Cannot access web interface

```bash
# 1. Check container is running
docker-compose ps

# 2. Check port binding
docker-compose port ucm 8443

# 3. Check firewall
sudo ufw allow 8443/tcp

# 4. Test from inside container
docker exec ucm curl -k https://localhost:8443/api/health
```

### Database errors

```bash
# Reset database (⚠️ ALL DATA WILL BE LOST)
docker-compose down
docker volume rm ucm_ucm-data
docker-compose up -d
```

### View real-time logs

```bash
# All logs
docker-compose logs -f

# UCM only
docker-compose logs -f ucm

# Last 100 lines
docker-compose logs --tail=100 ucm
```

## 📊 Monitoring

### Health Check

```bash
# Check health status
docker inspect ucm | jq '.[0].State.Health'

# Manual health check
curl -k https://ucm.example.com:8443/api/health
```

### Resource Usage

```bash
# Container stats
docker stats ucm

# Disk usage
docker system df -v
```

## 🔄 Updates

### Update to new version

```bash
# 1. Backup data
docker cp ucm:/app/backend/data/ucm.db ./backup-$(date +%Y%m%d).db

# 2. Pull new image
docker-compose pull

# 3. Restart with new version
docker-compose up -d

# 4. Check logs
docker-compose logs -f ucm
```

### Downgrade

```bash
# Specify version
docker-compose down
docker-compose -f docker-compose.yml \
  -e UCM_VERSION=1.7.0 \
  up -d
```

## 🚧 Development

Run in development mode with hot-reload:

```bash
# Start with dev config
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

# Access Mailhog (email testing)
http://localhost:8025
```

## 📚 Additional Resources

- **Full Documentation**: `/docs` directory
- **API Reference**: `https://your-domain:8443/api/docs`
- **Environment Variables**: `.env.example`
- **GitHub**: https://github.com/NeySlim/ultimate-ca-manager
- **Issues**: https://github.com/NeySlim/ultimate-ca-manager/issues

## 🆘 Support

- GitHub Issues: https://github.com/NeySlim/ultimate-ca-manager/issues
- Documentation: https://ucm.example.com/docs
- Community Forum: https://community.ucm.example.com

---

**Version**: 1.8.3  
**Last Updated**: 2026-01-09

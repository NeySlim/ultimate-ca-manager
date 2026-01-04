# UCM Production Deployment Guide

## Table of Contents
1. [Production Checklist](#production-checklist)
2. [Security Hardening](#security-hardening)
3. [High Availability Setup](#high-availability-setup)
4. [Backup Strategy](#backup-strategy)
5. [Monitoring](#monitoring)
6. [Performance Tuning](#performance-tuning)

## Production Checklist

### Pre-Deployment

- [ ] Server meets minimum requirements (2GB RAM, 2 CPU cores)
- [ ] OS is updated (`sudo apt-get update && sudo apt-get upgrade`)
- [ ] Firewall is configured
- [ ] Valid SSL/TLS certificate obtained
- [ ] Backup strategy defined
- [ ] Monitoring solution prepared
- [ ] Documentation reviewed

### Security

- [ ] Default admin password changed
- [ ] Strong password policy enforced
- [ ] HTTPS-only access configured
- [ ] Unnecessary services disabled
- [ ] SELinux/AppArmor configured
- [ ] Fail2ban installed and configured
- [ ] Rate limiting enabled
- [ ] Security headers configured

### Post-Deployment

- [ ] All tests passing (`python3 test_complete_system.py`)
- [ ] Backup tested and working
- [ ] Monitoring alerts configured
- [ ] Log rotation configured
- [ ] Documentation updated
- [ ] Team trained
- [ ] Runbook created

## Security Hardening

### 1. Change Default Credentials

```bash
# Login to UCM web interface
# Go to Configuration → Users
# Change admin password to strong password (20+ chars, mixed case, numbers, symbols)
```

### 2. Configure Production SSL Certificate

#### Using Let's Encrypt

```bash
# Install Certbot
sudo apt-get install certbot

# Get certificate
sudo certbot certonly --standalone \
  --preferred-challenges http \
  -d ca.yourdomain.com

# Configure UCM
sudo nano /opt/ucm/.env
# Update:
HTTPS_CERT_PATH=/etc/letsencrypt/live/ca.yourdomain.com/fullchain.pem
HTTPS_KEY_PATH=/etc/letsencrypt/live/ca.yourdomain.com/privkey.pem

# Set up auto-renewal
sudo crontab -e
# Add:
0 3 * * * certbot renew --quiet --post-hook "systemctl restart ucm"
```

#### Using Your Own CA

```bash
# Option 1: Use external certificate
sudo cp your-cert.pem /opt/ucm/data/https/
sudo cp your-key.pem /opt/ucm/data/https/
sudo chown ucm:ucm /opt/ucm/data/https/*
sudo chmod 600 /opt/ucm/data/https/your-key.pem

# Update .env
HTTPS_CERT_PATH=/opt/ucm/data/https/your-cert.pem
HTTPS_KEY_PATH=/opt/ucm/data/https/your-key.pem

# Option 2: Use UCM-managed certificate
# - Create Root CA via web interface
# - Issue server certificate
# - Apply via Configuration → HTTPS Certificate
```

### 3. Firewall Configuration

#### UFW (Ubuntu/Debian)

```bash
# Default deny
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH (adjust port if needed)
sudo ufw allow 22/tcp

# Allow UCM HTTPS
sudo ufw allow 8443/tcp

# Enable firewall
sudo ufw enable
```

#### Restrict to specific IPs

```bash
# Only allow management from specific subnet
sudo ufw delete allow 8443/tcp
sudo ufw allow from 192.168.1.0/24 to any port 8443 proto tcp
```

### 4. Install Fail2ban

```bash
# Install
sudo apt-get install fail2ban

# Create UCM jail
sudo nano /etc/fail2ban/jail.d/ucm.conf
```

Add:
```ini
[ucm]
enabled = true
port = 8443
protocol = tcp
filter = ucm
logpath = /var/log/ucm/ucm.log
maxretry = 5
bantime = 3600
findtime = 600
```

Create filter:
```bash
sudo nano /etc/fail2ban/filter.d/ucm.conf
```

Add:
```ini
[Definition]
failregex = ^.*Failed login attempt.*from <HOST>.*$
            ^.*Unauthorized access.*from <HOST>.*$
ignoreregex =
```

```bash
# Restart fail2ban
sudo systemctl restart fail2ban

# Check status
sudo fail2ban-client status ucm
```

### 5. Rate Limiting (Nginx Reverse Proxy)

```nginx
# /etc/nginx/sites-available/ucm
limit_req_zone $binary_remote_addr zone=ucm:10m rate=10r/s;

server {
    listen 443 ssl http2;
    server_name ca.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/ca.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ca.yourdomain.com/privkey.pem;
    
    # Strong SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Rate limiting
    limit_req zone=ucm burst=20 nodelay;
    
    location / {
        proxy_pass https://127.0.0.1:8443;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 6. Database Encryption

```bash
# Backup database
sudo systemctl stop ucm
sudo cp /opt/ucm/data/ucm.db /opt/ucm/data/ucm.db.backup

# Encrypt with SQLCipher (if needed)
# For now, rely on filesystem encryption
sudo apt-get install cryptsetup

# Set up LUKS for /opt/ucm/data
# (Advanced - see your organization's encryption policy)
```

### 7. Restrict File Permissions

```bash
# Set strict permissions
sudo chown -R ucm:ucm /opt/ucm
sudo chmod 750 /opt/ucm
sudo chmod 640 /opt/ucm/.env
sudo chmod 600 /opt/ucm/data/https/*.pem
sudo chmod 750 /opt/ucm/data
sudo chmod 640 /opt/ucm/data/ucm.db
```

## High Availability Setup

### Active-Passive with Shared Storage

```bash
# On both servers:
# 1. Install UCM
sudo bash install.sh

# 2. Configure shared storage (NFS/GlusterFS)
sudo mkdir -p /mnt/ucm-data
sudo mount server1:/exports/ucm-data /mnt/ucm-data

# 3. Update UCM data directory
sudo systemctl stop ucm
sudo mv /opt/ucm/data /opt/ucm/data.local
sudo ln -s /mnt/ucm-data /opt/ucm/data
sudo systemctl start ucm

# 4. Configure Keepalived for VIP
sudo apt-get install keepalived

# /etc/keepalived/keepalived.conf (Master)
vrrp_script check_ucm {
    script "/usr/bin/systemctl is-active ucm"
    interval 2
    weight 2
}

vrrp_instance VI_UCM {
    state MASTER
    interface eth0
    virtual_router_id 51
    priority 101
    advert_int 1
    
    virtual_ipaddress {
        192.168.1.250/24
    }
    
    track_script {
        check_ucm
    }
}

# Start keepalived
sudo systemctl enable keepalived
sudo systemctl start keepalived
```

### Database Replication

```bash
# Use PostgreSQL instead of SQLite for production HA

# Update requirements.txt
echo "psycopg2-binary>=2.9.0" >> requirements.txt

# Configure in .env
DATABASE_TYPE=postgresql
DATABASE_HOST=postgres-master.local
DATABASE_PORT=5432
DATABASE_NAME=ucm
DATABASE_USER=ucm_user
DATABASE_PASSWORD=strong_password

# Set up PostgreSQL streaming replication
# (Follow PostgreSQL HA documentation)
```

## Backup Strategy

### Automated Backups

Create backup script:

```bash
sudo nano /opt/ucm/scripts/backup.sh
```

Add:
```bash
#!/bin/bash
# UCM Backup Script

BACKUP_DIR="/backup/ucm"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=30

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Stop UCM for consistent backup
systemctl stop ucm

# Backup database
cp /opt/ucm/data/ucm.db "$BACKUP_DIR/ucm_db_$DATE.db"

# Backup certificates and CA data
tar -czf "$BACKUP_DIR/ucm_data_$DATE.tar.gz" \
    /opt/ucm/data/ca \
    /opt/ucm/data/certificates \
    /opt/ucm/data/https

# Backup configuration
cp /opt/ucm/.env "$BACKUP_DIR/env_$DATE"

# Start UCM
systemctl start ucm

# Compress database backup
gzip "$BACKUP_DIR/ucm_db_$DATE.db"

# Delete old backups
find "$BACKUP_DIR" -name "ucm_*" -mtime +$RETENTION_DAYS -delete

# Verify backup
if [ -f "$BACKUP_DIR/ucm_db_$DATE.db.gz" ]; then
    echo "✓ Backup completed successfully: $DATE"
    exit 0
else
    echo "✗ Backup failed: $DATE"
    exit 1
fi
```

```bash
# Make executable
sudo chmod +x /opt/ucm/scripts/backup.sh

# Schedule daily backups
sudo crontab -e
# Add:
0 2 * * * /opt/ucm/scripts/backup.sh >> /var/log/ucm/backup.log 2>&1
```

### Off-site Backup

```bash
# Using rsync to remote server
rsync -avz --delete \
    /backup/ucm/ \
    backup-server:/remote/backup/ucm/

# Or using rclone to cloud storage
rclone sync /backup/ucm/ remote:ucm-backups/
```

### Backup Verification

```bash
# Test restore monthly
sudo /opt/ucm/scripts/test-restore.sh
```

## Monitoring

### 1. Service Monitoring

```bash
# Install monitoring agent
sudo apt-get install prometheus-node-exporter

# UCM health check endpoint
curl -k https://localhost:8443/health

# Create monitoring script
sudo nano /opt/ucm/scripts/health-check.sh
```

Add:
```bash
#!/bin/bash
HEALTH_URL="https://localhost:8443/health"
STATUS=$(curl -k -s -o /dev/null -w "%{http_code}" $HEALTH_URL)

if [ "$STATUS" = "200" ]; then
    exit 0
else
    echo "UCM health check failed: HTTP $STATUS"
    exit 1
fi
```

### 2. Log Monitoring

```bash
# Configure log rotation
sudo nano /etc/logrotate.d/ucm
```

Add:
```
/var/log/ucm/*.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    create 0640 ucm ucm
    sharedscripts
    postrotate
        systemctl reload ucm > /dev/null 2>&1 || true
    endscript
}
```

### 3. Alerting

```bash
# Email alerts on service failure
sudo nano /etc/systemd/system/ucm.service.d/alert.conf
```

Add:
```ini
[Service]
OnFailure=failure-email@%n.service
```

## Performance Tuning

### 1. System Tuning

```bash
# Increase file descriptors
sudo nano /etc/security/limits.conf
# Add:
ucm soft nofile 65536
ucm hard nofile 65536

# Optimize kernel parameters
sudo nano /etc/sysctl.d/99-ucm.conf
```

Add:
```
# Network tuning
net.core.somaxconn = 1024
net.ipv4.tcp_max_syn_backlog = 2048
net.ipv4.ip_local_port_range = 10000 65535

# Memory tuning
vm.swappiness = 10
```

Apply:
```bash
sudo sysctl -p /etc/sysctl.d/99-ucm.conf
```

### 2. Application Tuning

```bash
# Use production WSGI server (Gunicorn)
pip install gunicorn

# Update systemd service
sudo nano /etc/systemd/system/ucm.service
```

Update ExecStart:
```ini
ExecStart=/opt/ucm/venv/bin/gunicorn \
    --workers 4 \
    --bind 0.0.0.0:8443 \
    --certfile /opt/ucm/data/https/cert.pem \
    --keyfile /opt/ucm/data/https/key.pem \
    --access-logfile /var/log/ucm/access.log \
    --error-logfile /var/log/ucm/error.log \
    --log-level info \
    app:app
```

### 3. Database Optimization

```bash
# Enable WAL mode for SQLite
sqlite3 /opt/ucm/data/ucm.db "PRAGMA journal_mode=WAL;"

# Regular optimization
echo "0 3 * * 0 sqlite3 /opt/ucm/data/ucm.db 'VACUUM;'" | sudo crontab -
```

## Disaster Recovery

### Recovery Time Objective (RTO): < 1 hour

1. **Restore from backup**
   ```bash
   sudo systemctl stop ucm
   gunzip -c /backup/ucm/ucm_db_YYYYMMDD.db.gz > /opt/ucm/data/ucm.db
   tar -xzf /backup/ucm/ucm_data_YYYYMMDD.tar.gz -C /
   sudo systemctl start ucm
   ```

2. **Verify restoration**
   ```bash
   python3 /opt/ucm/test_complete_system.py
   ```

3. **Switch to standby** (if using HA)
   ```bash
   # On standby server
   sudo systemctl start ucm
   # Update DNS or VIP
   ```

## Maintenance

### Monthly Tasks

- [ ] Review logs for anomalies
- [ ] Test backup restoration
- [ ] Update OS packages
- [ ] Review user accounts
- [ ] Check disk space
- [ ] Verify certificate expiration dates

### Quarterly Tasks

- [ ] Security audit
- [ ] Performance review
- [ ] Capacity planning
- [ ] Update documentation
- [ ] Disaster recovery drill

### Annual Tasks

- [ ] Penetration testing
- [ ] Architecture review
- [ ] Technology stack update
- [ ] Business continuity plan update

## Support

For production support:
- Emergency: [Create critical issue](https://github.com/NeySlim/ultimate-ca-manager/issues/new?labels=critical)
- Documentation: [Wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki)
- Community: [Discussions](https://github.com/NeySlim/ultimate-ca-manager/discussions)

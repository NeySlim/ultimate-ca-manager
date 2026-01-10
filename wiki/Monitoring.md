# Monitoring

Ultimate CA Manager v1.8.2 provides comprehensive monitoring capabilities through its dashboard and API endpoints.

## Dashboard Monitoring

### Real-Time Status

The main dashboard displays:
- **Total Certificates**: Active, expired, and revoked counts
- **Certificate Expiration**: Visual timeline of upcoming expirations
- **CA Health**: Root and intermediate CA status
- **Recent Activity**: Latest certificate operations
- **System Status**: Service health indicators

### Certificate Status Widget

Real-time overview:
```
📊 Certificate Statistics
├── Active: 45
├── Expiring (30 days): 3
├── Expired: 2
└── Revoked: 1
```

### Expiration Alerts

Visual indicators:
- 🔴 **Critical** (< 7 days): Red highlighting
- 🟡 **Warning** (< 30 days): Yellow highlighting
- 🟢 **Healthy** (> 30 days): Green status

## System Monitoring

### Service Health Checks

**Built-in Health Endpoint:**
```bash
curl https://ca.example.com/health
```

Response:
```json
{
  "status": "healthy",
  "database": "connected",
  "ca_available": true,
  "version": "1.8.2"
}
```

### Log Monitoring

**Application Logs:**
```bash
# Systemd service
sudo journalctl -u ucm -f

# Direct logs
tail -f /opt/ucm/logs/ucm.log
```

**Log Levels:**
- `INFO`: Normal operations
- `WARNING`: Non-critical issues
- `ERROR`: Operation failures
- `CRITICAL`: System failures

### Database Monitoring

**Check Database Status:**
```bash
cd /opt/ucm
source venv/bin/activate
flask db current
```

**Database Size:**
```bash
du -h /opt/ucm/instance/ucm.db
```

## ACME/SCEP Monitoring

### ACME Server Status

Monitor certificate issuance:
```bash
# Check ACME logs
grep "ACME" /opt/ucm/logs/ucm.log

# Recent ACME orders
curl -H "Authorization: Bearer $TOKEN" \
  https://ca.example.com/api/acme/stats
```

### SCEP Server Status

Track device enrollments:
```bash
# SCEP operations
grep "SCEP" /opt/ucm/logs/ucm.log

# Active SCEP profiles
curl -H "Authorization: Bearer $TOKEN" \
  https://ca.example.com/api/scep/profiles
```

## Performance Monitoring

### Resource Usage

**System Resources:**
```bash
# CPU and memory
systemctl status ucm

# Process details
ps aux | grep gunicorn
```

**Disk Usage:**
```bash
# Certificate storage
du -sh /opt/ucm/instance/certs/

# Database and backups
du -sh /opt/ucm/instance/
```

### Response Times

**API Performance:**
```bash
# Time certificate operation
time curl -X POST https://ca.example.com/api/certificates \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"cn":"test.example.com"}'
```

## OCSP Responder Monitoring

### OCSP Health Check

```bash
# Check OCSP responder
openssl ocsp -issuer ca.crt -cert test.crt \
  -url http://ocsp.example.com:2560 \
  -resp_text
```

**Expected Response:**
```
Response verify OK
test.crt: good
```

### OCSP Logs

```bash
# Monitor OCSP queries
grep "OCSP" /opt/ucm/logs/ucm.log | tail -20
```

## Email Notification Monitoring

### Test Email Delivery

```bash
# Send test notification
curl -X POST https://ca.example.com/api/test-email \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"email":"admin@example.com"}'
```

### Email Queue Status

Check pending notifications:
```bash
# Recent email activity
grep "Email sent" /opt/ucm/logs/ucm.log | tail -10
```

## Security Monitoring

### Failed Authentication Attempts

```bash
# Monitor failed logins
grep "Failed login" /opt/ucm/logs/ucm.log

# WebAuthn attempts
grep "WebAuthn" /opt/ucm/logs/ucm.log
```

### Certificate Revocation Activity

```bash
# Recent revocations
grep "revoked" /opt/ucm/logs/ucm.log | tail -20

# CRL generation
grep "CRL" /opt/ucm/logs/ucm.log
```

## External Monitoring Integration

### Prometheus/Grafana

UCM can be monitored with Prometheus:

**Metrics Endpoint:**
```bash
curl https://ca.example.com/metrics
```

**Example Prometheus Config:**
```yaml
scrape_configs:
  - job_name: 'ucm'
    static_configs:
      - targets: ['ca.example.com:443']
    scheme: https
```

### Nagios/Icinga

**Health Check Plugin:**
```bash
#!/bin/bash
response=$(curl -s https://ca.example.com/health)
if echo "$response" | grep -q '"status": "healthy"'; then
  echo "OK - UCM is healthy"
  exit 0
else
  echo "CRITICAL - UCM is unhealthy"
  exit 2
fi
```

### Uptime Monitoring

Services to monitor:
- Web interface (HTTPS)
- ACME server (port 443/tcp)
- SCEP server (port 443/tcp)
- OCSP responder (port 2560/tcp)

## Automated Alerts

### Email Alerts

Configure in System Config:
- Certificate expiration warnings (30, 14, 7 days)
- CA certificate expiration
- System errors
- Failed authentication attempts

### Webhook Integration

Send alerts to external systems:
```python
# Example webhook config
WEBHOOK_URL = "https://hooks.slack.com/services/YOUR/WEBHOOK"
WEBHOOK_EVENTS = ["cert_expiring", "cert_revoked", "error"]
```

## Backup Monitoring

### Verify Backup Status

```bash
# List backups
ls -lh /opt/ucm/backups/

# Check latest backup
ls -lt /opt/ucm/backups/ | head -2
```

### Test Backup Integrity

```bash
# Extract and verify
tar -tzf /opt/ucm/backups/ucm-backup-*.tar.gz
```

## Troubleshooting Common Issues

### High CPU Usage

```bash
# Check worker processes
ps aux | grep gunicorn | wc -l

# Restart service
sudo systemctl restart ucm
```

### Database Lock Errors

```bash
# Check active connections
lsof /opt/ucm/instance/ucm.db

# Restart if needed
sudo systemctl restart ucm
```

### Certificate Issuance Failures

```bash
# Check CA availability
openssl x509 -in /opt/ucm/instance/certs/ca.crt -noout -text

# Verify permissions
ls -l /opt/ucm/instance/certs/
```

## Best Practices

1. **Regular Monitoring**: Check dashboard daily for expiring certificates
2. **Log Rotation**: Configure logrotate for `/opt/ucm/logs/`
3. **Disk Space**: Monitor `/opt/ucm/instance/` growth
4. **Backup Verification**: Test backup restoration monthly
5. **Security Audits**: Review authentication logs weekly
6. **Performance Baselines**: Establish normal response times
7. **Alert Thresholds**: Set appropriate warning levels

## See Also

- [Dashboard](Dashboard.md) - Dashboard features and widgets
- [Security](Security.md) - Security monitoring and hardening
- [Backup & Restore](Backup-Restore.md) - Backup strategies
- [System Config](System-Config.md) - System configuration options

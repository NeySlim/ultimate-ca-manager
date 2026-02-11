# Redis Integration Guide

UCM supports Redis for distributed caching and rate limiting. Redis is **optional** - UCM works perfectly without it using in-memory storage.

## When to Use Redis

| Scenario | Redis Needed? |
|----------|---------------|
| Single UCM instance | ❌ No |
| Multiple UCM instances (load balanced) | ✅ Yes |
| High availability setup | ✅ Yes |
| Persistent rate limiting across restarts | ✅ Yes |
| UCM with many concurrent users | ✅ Recommended |

## Features Enabled by Redis

- **Distributed Rate Limiting**: Limits are shared across all workers/instances
- **Shared Cache**: Reduces memory usage and ensures cache consistency
- **Persistent Sessions**: Sessions survive UCM restarts

---

## Installation

### Docker (Recommended)

```bash
# Use the Redis overlay file
docker compose -f docker-compose.yml -f docker-compose.redis.yml up -d
```

Or uncomment the Redis service in `docker-compose.yml`.

### Debian / Ubuntu

```bash
# Install Redis server
sudo apt update
sudo apt install -y redis-server

# Enable and start
sudo systemctl enable redis-server
sudo systemctl start redis-server

# Verify
redis-cli ping # Should return PONG
```

### CentOS / RHEL / Rocky Linux

```bash
# Install Redis
sudo dnf install -y redis

# Enable and start
sudo systemctl enable redis
sudo systemctl start redis

# Verify
redis-cli ping # Should return PONG
```

### Alpine Linux

```bash
apk add redis
rc-update add redis default
rc-service redis start
```

---

## Configuration

Add to `/etc/ucm/ucm.env`:

```bash
# Local Redis
UCM_REDIS_URL=redis://localhost:6379/0

# Redis with password
UCM_REDIS_URL=redis://:mypassword@localhost:6379/0

# Remote Redis
UCM_REDIS_URL=redis://redis.example.com:6379/0

# Redis Sentinel (high availability)
UCM_REDIS_URL=redis+sentinel://sentinel1:26379,sentinel2:26379/mymaster/0
```

Then restart UCM:
```bash
sudo systemctl restart ucm
```

---

## Verify Redis Integration

Check UCM logs after restart:

```bash
# Should show "Redis" instead of "Memory"
journalctl -u ucm --no-pager | grep -i "cache\|rate"
```

Expected output:
```
✓ Cache enabled (Redis)
✓ Rate limiting enabled (Redis - distributed)
```

---

## Redis Security

### Bind to localhost only (default)

Edit `/etc/redis/redis.conf`:
```
bind 127.0.0.1
```

### Enable authentication

```
requirepass your_strong_password_here
```

### Disable dangerous commands

```
rename-command FLUSHALL ""
rename-command FLUSHDB ""
rename-command CONFIG ""
```

Restart Redis after changes:
```bash
sudo systemctl restart redis
```

---

## Troubleshooting

### UCM not using Redis

1. Check Redis is running: `redis-cli ping`
2. Check UCM_REDIS_URL is set: `grep REDIS /etc/ucm/ucm.env`
3. Check UCM logs: `journalctl -u ucm -n 50`

### Connection refused

```bash
# Check Redis is listening
ss -tlnp | grep 6379

# Check firewall (if remote Redis)
sudo firewall-cmd --list-ports
```

### Memory issues

Redis is configured with memory limits in docker-compose:
```
--maxmemory 128mb --maxmemory-policy allkeys-lru
```

Adjust based on your needs. For most UCM deployments, 64-256MB is sufficient.

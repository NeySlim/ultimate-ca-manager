# Redis Integration Guide

UCM can keep its sessions and relay its real-time events through Redis. Redis is **optional**: without it, sessions are stored on disk and events stay on the instance.

## When to Use Redis

| Scenario | Redis Needed? |
|----------|---------------|
| Single UCM instance | No |
| Multiple UCM instances (load balanced) | Yes |
| High availability setup | Yes |

## Features Enabled by Redis

- **Shared sessions**: a session opened on one instance is valid on the others, and survives restarts
- **Real-time events across instances**: WebSocket events go through Redis, so a browser connected to one instance sees changes made on another

Both need the `redis` Python package, which UCM packages do not install: `/opt/ucm/venv/bin/pip install redis` on a DEB or RPM installation. Without it, UCM logs a warning and keeps working without Redis.

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
REDIS_URL=redis://localhost:6379/0

# Redis with password
REDIS_URL=redis://:mypassword@localhost:6379/0

# Remote Redis
REDIS_URL=redis://redis.example.com:6379/0
```

`UCM_REDIS_URL`, the name earlier versions of this guide used, is read too. Instances sharing a Redis server stay apart by database number (`/0`, `/1`, ...): give each UCM installation its own.

Then restart UCM:
```bash
sudo systemctl restart ucm
```

---

## Verify Redis Integration

Check UCM logs after restart:

```bash
journalctl -u ucm --no-pager | grep -i redis
```

Expected output:
```
✓ Redis session store enabled
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
2. Check REDIS_URL is set: `grep REDIS /etc/ucm/ucm.env`
3. Check the `redis` Python package is installed: `/opt/ucm/venv/bin/python -c 'import redis'`
4. Check UCM logs: `journalctl -u ucm -n 50`

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

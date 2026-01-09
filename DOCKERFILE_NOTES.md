# Dockerfile Technical Notes

## Bash Syntax in Dockerfiles

### Brace Expansion

When using brace expansion `{a,b,c}` in Dockerfiles, you **MUST** use `bash -c`:

```dockerfile
# ❌ INCORRECT - This will fail (uses /bin/sh by default)
RUN mkdir -p /app/data/{cas,certs,backups}

# ✅ CORRECT - Explicitly use bash
RUN bash -c 'mkdir -p /app/data/{cas,certs,backups}'
```

**Why?** Docker's default shell is `/bin/sh` which doesn't support brace expansion. Bash must be explicitly invoked.

### Alternative Without Bash

```dockerfile
# Without brace expansion (works with /bin/sh)
RUN mkdir -p /app/data/cas && \
    mkdir -p /app/data/certs && \
    mkdir -p /app/data/backups
```

## UCM Dockerfile Structure

### Multi-Stage Build

```
Stage 1 (builder):
  - Install build dependencies
  - Create virtual environment
  - Install Python packages

Stage 2 (runtime):
  - Copy only virtual environment
  - Minimal runtime dependencies
  - Non-root user
  - Application files
```

### Directory Structure

Created at build time:
```
/app/
├── backend/
│   └── data/
│       ├── cas/       (CA certificates)
│       ├── certs/     (issued certificates)
│       ├── backups/   (database backups)
│       ├── logs/      (application logs)
│       └── temp/      (temporary files)
├── frontend/
├── wsgi.py
└── gunicorn.conf.py
```

### Security Considerations

1. **Non-root user**: Container runs as `ucm` (UID 1000)
2. **Minimal image**: Only runtime dependencies installed
3. **Multi-stage**: Build dependencies not in final image
4. **Read-only**: Application files owned by root, data dirs by ucm

### Build Command

```bash
# Standard build
docker build -t ucm:1.8.0-beta .

# With build args
docker build \
  --build-arg PYTHON_VERSION=3.11 \
  -t ucm:1.8.0-beta \
  .

# Multi-platform (requires buildx)
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t ucm:1.8.0-beta \
  --push \
  .
```

### Common Issues

#### Issue: Permission denied on /app/backend/data

**Cause**: Volume mounted with wrong permissions

**Solution**:
```bash
# Before running container
mkdir -p ./data
chown -R 1000:1000 ./data

# Or in docker-compose.yml
volumes:
  - ./data:/app/backend/data:rw
```

#### Issue: Entrypoint not executable

**Cause**: Missing executable permission on entrypoint.sh

**Solution**: Added in Dockerfile:
```dockerfile
COPY --chown=ucm:ucm docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
```

#### Issue: Health check fails

**Cause**: Service not ready within start period

**Solution**: Increase `start-period`:
```dockerfile
HEALTHCHECK --start-period=60s ...
```

## Development vs Production

### Development

```dockerfile
# Use Flask dev server (in docker-compose.dev.yml)
command: python3 -m flask run --host=0.0.0.0 --reload
```

### Production

```dockerfile
# Use Gunicorn (default in Dockerfile)
CMD ["gunicorn", "--config", "/app/gunicorn.conf.py", "wsgi:app"]
```

## Testing the Build

```bash
# Build image
docker build -t ucm:test .

# Run container
docker run -d \
  -p 8443:8443 \
  -e UCM_FQDN=ucm.local \
  --name ucm-test \
  ucm:test

# Check logs
docker logs -f ucm-test

# Test health
curl -k https://localhost:8443/api/health

# Shell into container
docker exec -it ucm-test bash

# Cleanup
docker stop ucm-test
docker rm ucm-test
```

## Size Optimization

Current image size: ~450MB

Breakdown:
- Base image (python:3.11-slim): ~150MB
- Python dependencies: ~200MB
- Application files: ~100MB

Further optimization possible:
- Use Alpine Linux: -50MB (but compatibility issues)
- Remove unnecessary files: -20MB
- Compress layers: -30MB

Trade-off: Size vs compatibility/security updates

---

**Last Updated**: 2026-01-09  
**UCM Version**: 1.8.0-beta  
**Docker Version**: 24.0+

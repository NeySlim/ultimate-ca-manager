# UCM Docker Quick Start

## Run

```bash
docker run -d --restart=unless-stopped \
  --name ucm \
  -p 8443:8443 \
  -v ucm-data:/opt/ucm/data \
  neyslim/ultimate-ca-manager:latest
```

Also available from GitHub Container Registry:

```bash
docker pull ghcr.io/neyslim/ultimate-ca-manager:latest
```

## Access

- **URL:** https://localhost:8443
- **Username:** admin
- **Password:** changeme123

Change the password immediately after first login.

## Docker Compose

```yaml
services:
  ucm:
    image: neyslim/ultimate-ca-manager:latest
    container_name: ucm
    ports:
      - "8443:8443"
    volumes:
      - ucm-data:/opt/ucm/data
    environment:
      - UCM_FQDN=ucm.example.com
    restart: unless-stopped

volumes:
  ucm-data:
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `UCM_FQDN` | `ucm.example.com` | Server FQDN for ACME/SCEP |
| `UCM_HTTPS_PORT` | `8443` | HTTPS listen port |
| `UCM_SECRET_KEY` | auto-generated | Session encryption key |

## Data Persistence

All data is stored in `/opt/ucm/data/`:
- SQLite database
- CA certificates and keys
- HTTPS certificates
- Backups

Mount this directory as a Docker volume to persist data across container restarts.

## Backup

```bash
docker stop ucm
docker run --rm -v ucm-data:/data -v $(pwd):/backup \
  alpine tar czf /backup/ucm-backup.tar.gz -C /data .
docker start ucm
```

## Upgrade

```bash
docker stop ucm && docker rm ucm
docker pull neyslim/ultimate-ca-manager:latest
docker run -d --restart=unless-stopped \
  --name ucm \
  -p 8443:8443 \
  -v ucm-data:/opt/ucm/data \
  neyslim/ultimate-ca-manager:latest
```

## Documentation

- [Full README](https://github.com/NeySlim/ultimate-ca-manager)
- [Admin Guide](https://github.com/NeySlim/ultimate-ca-manager/blob/main/docs/ADMIN_GUIDE.md)
- [API Reference](https://github.com/NeySlim/ultimate-ca-manager/blob/main/docs/API_REFERENCE.md)

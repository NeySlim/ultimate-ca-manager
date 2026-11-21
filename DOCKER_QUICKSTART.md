# UCM Docker Quick Start

## Run

```bash
docker run -d --restart=unless-stopped \
  --name ucm \
  -p 8443:8443 \
  -p 8080:8080 \
  -v ucm-data:/opt/ucm/data \
  -v ucm-config:/etc/ucm \
  neyslim/ultimate-ca-manager:latest
```

Also available from GitHub Container Registry:

```bash
docker pull ghcr.io/neyslim/ultimate-ca-manager:latest
```

## Access

- **URL:** https://localhost:8443
- **Username:** admin
- **Password:** generated at first start, read it with `docker exec <container> cat /opt/ucm/data/initial-admin-password`

The first login must change it, which removes the file. To choose it instead, pass a secret file with `INITIAL_ADMIN_PASSWORD_FILE` (see [First access](docs/installation/README.md#first-access)).

## Docker Compose

```yaml
services:
  ucm:
    image: neyslim/ultimate-ca-manager:latest
    container_name: ucm
    ports:
      - "8443:8443"
      - "8080:8080"   # HTTP — CRL/CDP and OCSP public endpoints
    volumes:
      - ucm-data:/opt/ucm/data
      - ucm-config:/etc/ucm   # master.key: without it, encrypted private keys are lost
    environment:
      - UCM_FQDN=ucm.example.com
    restart: unless-stopped

volumes:
  ucm-data:
  ucm-config:
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

`/etc/ucm/` holds `master.key`, which decrypts every private key stored in the database. Mount it as a volume too: without one, recreating the container loses the key.

## Backup

```bash
docker stop ucm
docker run --rm -v ucm-data:/data -v ucm-config:/config -v $(pwd):/backup \
  alpine tar czf /backup/ucm-backup.tar.gz -C / data config
docker start ucm
```

## Upgrade

```bash
docker stop ucm && docker rm ucm
docker pull neyslim/ultimate-ca-manager:latest
docker run -d --restart=unless-stopped \
  --name ucm \
  -p 8443:8443 \
  -p 8080:8080 \
  -v ucm-data:/opt/ucm/data \
  -v ucm-config:/etc/ucm \
  neyslim/ultimate-ca-manager:latest
```

`/etc/ucm` holds `master.key`. If the old container ran without a volume there, copy the key out before `docker rm` (`docker cp ucm:/etc/ucm/master.key ./master.key`) and into the new container afterwards.

## Documentation

- [Full README](https://github.com/NeySlim/ultimate-ca-manager)
- [Admin Guide](https://github.com/NeySlim/ultimate-ca-manager/blob/main/docs/ADMIN_GUIDE.md)
- [API Reference](https://github.com/NeySlim/ultimate-ca-manager/blob/main/docs/API_REFERENCE.md)

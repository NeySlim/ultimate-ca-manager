# HSM Docker Deployment Guide

UCM includes SoftHSM2 in its Docker image. HSM features work out of the box — no extra configuration required.

## Quick Start

```bash
docker compose -f docker-compose.hsm.yml up -d
```

On first start, a default SoftHSM token (`UCM-Default`) is automatically initialized. The PIN is printed in the container logs.

## Persistent Tokens

Mount a volume for `/var/lib/softhsm/tokens` to keep HSM keys across container restarts:

```bash
docker run -d --name ucm -p 8443:8443 \
  -v ucm-data:/opt/ucm/data \
  -v ucm-hsm:/var/lib/softhsm/tokens \
  neyslim/ultimate-ca-manager:latest
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HSM_AUTO_INIT` | `true` | Auto-create a default SoftHSM token on first start |
| `HSM_PIN` | *(random)* | PIN for the auto-initialized token |
| `HSM_SO_PIN` | *(random)* | SO PIN for the auto-initialized token |

## Manual Token Management

```bash
# List tokens
docker exec ucm softhsm2-util --show-slots

# Create additional token
docker exec ucm softhsm2-util --init-token --free \
  --label "MyToken" --pin 1234 --so-pin 5678

# Delete a token
docker exec ucm softhsm2-util --delete-token --serial <serial>
```

## Hardware HSM

For hardware HSMs (Thales, SafeNet, etc.), mount the vendor PKCS#11 library and device:

```yaml
services:
  ucm:
    image: neyslim/ultimate-ca-manager:latest
    devices:
      - /dev/pkcs11
    volumes:
      - /opt/vendor/lib:/opt/vendor/lib:ro
```

Then configure the provider in the UCM web UI with the vendor library path.

## Cloud HSM

Configure cloud HSM providers via the UCM web UI (Settings → HSM):

- **AWS CloudHSM** — uses PKCS#11 with the CloudHSM client library
- **Azure Key Vault** — requires `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`
- **Google Cloud KMS** — requires GCP service account credentials

## Backup & Restore

```bash
# Backup tokens
docker cp ucm:/var/lib/softhsm/tokens ./hsm-backup/

# Restore tokens
docker cp ./hsm-backup/. ucm:/var/lib/softhsm/tokens/
```

Or use Docker volumes:

```bash
# Create backup archive
docker run --rm -v ucm-hsm:/data -v $(pwd):/backup \
  alpine tar czf /backup/hsm-tokens.tar.gz -C /data .
```

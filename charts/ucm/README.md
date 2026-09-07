# UCM Helm Chart

Deploy [Ultimate Certificate Manager](https://github.com/NeySlim/ultimate-ca-manager) (UCM) — a web-based Certificate Authority and PKI platform (ACME, SCEP, EST, OCSP, CRL/CDP) — into a Kubernetes cluster.

> Clusters can already *consume* UCM today via the cert-manager integration in `examples/kubernetes/cert-manager/`. This chart deploys UCM *itself* in-cluster.

## TL;DR

```bash
helm install ucm ./charts/ucm \
  --namespace ucm --create-namespace \
  --set fqdn=ucm.example.com \
  --set initialAdminPassword='change-me-now'
```

Then `kubectl -n ucm port-forward svc/ucm 8443:8443` and open <https://localhost:8443> (admin / your password).

## Prerequisites

- Kubernetes 1.23+
- Helm 3.8+ (uses `lookup` to persist generated secrets across upgrades)
- A default StorageClass providing **ReadWriteOnce** volumes

## Single instance only

UCM runs as **one replica** (`replicaCount: 1`, `strategy: Recreate`):

- the default database is **SQLite** (single writer) on a RWO volume, and
- UCM runs an in-process **background scheduler** (CRL refresh, webhook delivery, scheduled backups, auto-renewal) that is **not yet HA-safe** — two pods would double-run scheduled tasks.

Pointing UCM at an external PostgreSQL gives you durable, HA-grade storage, but the application itself still runs as a single pod. Do not scale up.

## ⚠️ master.key — do not lose it

The `*-etc` PVC mounts `/etc/ucm`, which holds `master.key` — the symmetric key that decrypts **every private key in the database** (CAs, certs, ACME, SSH-CA). If this volume is lost, all encrypted keys become **unrecoverable**. The PVC carries `helm.sh/resource-policy: keep` so it survives `helm uninstall`. Back it up.

## Configuration

| Key | Default | Description |
|-----|---------|-------------|
| `image.repository` | `neyslim/ultimate-ca-manager` | Image repo |
| `image.tag` | `""` (→ chart `appVersion`) | Image tag |
| `replicaCount` | `1` | Keep at 1 (see above) |
| `fqdn` | `ucm.local` | FQDN for the self-signed UI cert / default AIA-CRL-OCSP base URL |
| `initialAdminPassword` | `""` (→ image default `changeme123`) | First-boot admin password |
| `secrets.secretKey` / `secrets.jwtSecret` | `""` (auto-generated + persisted) | Flask / JWT secrets |
| `database.type` | `sqlite` | `sqlite` or `postgresql` |
| `database.databaseUrl` | `""` | `postgresql://…` when `type=postgresql` |
| `database.existingSecret` / `database.existingSecretKey` | `""` / `DATABASE_URL` | Use an existing Secret for the DB URL |
| `persistence.data.size` | `5Gi` | DB / CA files / backups volume |
| `persistence.etc.size` | `64Mi` | `/etc/ucm` (master.key) volume |
| `service.type` | `ClusterIP` | Service type |
| `service.httpsPort` / `service.httpPort` | `8443` / `8080` | UI/API (HTTPS) and protocol (HTTP) ports |
| `ingress.enabled` | `false` | Expose the HTTPS UI via Ingress |
| `ingress.protocolHttp.enabled` | `false` | Second Ingress for cleartext CDP/OCSP/ACME-HTTP-01 (port 8080) |
| `proxy.behindProxy` | `false` | Set `UCM_BEHIND_PROXY=1` (honor `X-Forwarded-*` for one hop) |
| `proxy.trustedProxies` | `[]` | `UCM_TRUSTED_PROXIES` — proxy IPs / CIDRs allowed to set forwarded / client-cert headers |
| `extraEnv` | `[]` | Extra `UCM_*` env vars |
| `resources` | requests 100m/256Mi, limit 1Gi | Pod resources |

See [`values.yaml`](values.yaml) for the full list.

### External PostgreSQL

```bash
helm install ucm ./charts/ucm \
  --set database.type=postgresql \
  --set database.databaseUrl='postgresql://ucm:secret@postgres:5432/ucm'
# or reference an existing Secret:
  --set database.existingSecret=ucm-db --set database.existingSecretKey=url
```

### Ingress

UCM terminates TLS itself, so the UI Ingress should speak HTTPS to the backend. With ingress-nginx:

```yaml
ingress:
  enabled: true
  className: nginx
  host: ucm.example.com
  annotations:
    nginx.ingress.kubernetes.io/backend-protocol: "HTTPS"
  tls:
    - secretName: ucm-tls
      hosts: [ucm.example.com]
```

Protocol endpoints that need cleartext HTTP (ACME HTTP-01, CRL, OCSP) can be exposed via `ingress.protocolHttp.enabled=true` on a separate host.

### Behind a reverse proxy

UCM only honors `X-Forwarded-*` (and proxy-injected client-cert headers) when the request's immediate peer is a **trusted proxy**. Behind an Ingress the peer is the controller's pod IP, which is not loopback, so you must opt in:

```yaml
proxy:
  behindProxy: true
  trustedProxies:
    - 10.42.0.0/16   # the ingress controller's pod network (CIDR ok)
```

Leaving `trustedProxies` empty while `behindProxy` is true trusts loopback only, so the forwarded headers are dropped and proxied requests can return `403`. A `trustedProxies` entry that is not a valid IP or CIDR is ignored with a warning in the pod log.

## Uninstall

```bash
helm uninstall ucm -n ucm
```

The `*-etc` PVC (master.key) is intentionally **retained**. Delete it manually only when you are certain no encrypted data needs recovery.

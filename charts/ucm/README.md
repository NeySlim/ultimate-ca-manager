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
- With `ha.enabled`, `get` on `serviceaccounts` and `secrets` in the release namespace for the account that runs `helm`: the chart's `lookup` reads them, and without that right the render stops with Kubernetes' `forbidden` error
- A default StorageClass providing **ReadWriteOnce** volumes

## One instance, or several with `ha.enabled`

By default UCM runs as **one replica** (`replicaCount: 1`, `strategy: Recreate`) on a **SQLite** database (single writer) on a RWO volume. Do not raise `replicaCount` on its own: on SQLite two pods would share neither the database nor the volume.

For several pods set `ha.enabled=true`, `database.type=postgresql` and `replicaCount` >= 2: the pods share the PostgreSQL database, one of them runs the scheduled tasks, and a rolling update replaces them one at a time. See `docs/HA.md`.

## ⚠️ master.key — do not lose it

The `*-etc` PVC mounts `/etc/ucm`, which holds `master.key` — the symmetric key that decrypts **every private key in the database** (CAs, certs, ACME, SSH-CA). If this volume is lost, all encrypted keys become **unrecoverable**. The PVC carries `helm.sh/resource-policy: keep` so it survives `helm uninstall`. Back it up.

## Configuration

| Key | Default | Description |
|-----|---------|-------------|
| `image.repository` | `neyslim/ultimate-ca-manager` | Image repo |
| `image.tag` | `""` (→ chart `appVersion`) | Image tag |
| `image.pullPolicy` | `IfNotPresent` | Image pull policy |
| `imagePullSecrets` | `[]` | Pull secrets for a private registry |
| `nameOverride` / `fullnameOverride` | `""` / `""` | Replace the chart name / the full resource name prefix |
| `replicaCount` | `1` | Keep at 1 unless `ha.enabled` (then 2 or more); above 1 without `ha.enabled` the render fails |
| `ha.enabled` | `false` | Several nodes on one PostgreSQL (`UCM_HA=1`). Needs `database.type=postgresql` and `replicaCount` >= 2, or the render fails. Adds a PodDisruptionBudget, a preferred pod anti-affinity, a rolling update, `UCM_NODE_ID` (pod name) and a shared `KEY_ENCRYPTION_KEY` and `UCM_DB_ENCRYPTION_KEY`; no etc PVC. On an existing release (`helm upgrade`) the render fails until both keys are given or already in the Secret. See `docs/HA.md` |
| `ha.podDisruptionBudget.minAvailable` | `1` | Pods kept available during voluntary disruptions |
| `redis.url` | `""` | Redis shared by the nodes (`REDIS_URL`, HA only) |
| `secrets.keyEncryptionKey` | `""` | `KEY_ENCRYPTION_KEY`, passed to the pods whenever set or already in the Secret; generated once when empty only with `ha.enabled`, where a render without cluster access (`helm template`, GitOps) refuses to draw it |
| `secrets.dbEncryptionKey` | `""` | `UCM_DB_ENCRYPTION_KEY` (Fernet key) for the integration secrets, passed to the pods whenever set or already in the Secret; generated once when empty only with `ha.enabled`, where a render without cluster access (`helm template`, GitOps) refuses to draw it |
| `fqdn` | `ucm.local` | FQDN for the self-signed UI cert / default AIA-CRL-OCSP base URL |
| `initialAdminPassword` | `""` (generated into the Secret, kept across upgrades) | First-boot admin password; the generated one must be changed at first login, a value set here is not forced to change. Read the generated one with `kubectl get secret <fullname>-secrets -o jsonpath='{.data.UCM_INITIAL_ADMIN_PASSWORD}' \| base64 -d`. Unused when `extraEnv` sets `INITIAL_ADMIN_PASSWORD` (your own Secret) or `INITIAL_ADMIN_PASSWORD_FILE`: the chart then passes no password of its own and forces no change |
| `secrets.secretKey` | `""` (auto-generated + persisted) | Flask session secret |
| `database.type` | `sqlite` | `sqlite` or `postgresql` |
| `database.databaseUrl` | `""` | `postgresql://…` when `type=postgresql` |
| `database.existingSecret` / `database.existingSecretKey` | `""` / `DATABASE_URL` | Use an existing Secret for the DB URL |
| `persistence.data.size` | `5Gi` | DB / CA files / backups volume |
| `persistence.etc.size` | `64Mi` | `/etc/ucm` (master.key) volume |
| `persistence.enabled` | `true` | PVCs for the data and `/etc/ucm` volumes; `false` uses `emptyDir` (lost with the pod) |
| `persistence.storageClass` | `""` | Storage class of both PVCs (empty = cluster default) |
| `persistence.data.accessMode` / `persistence.etc.accessMode` | `ReadWriteOnce` | Access modes of the claims |
| `persistence.data.existingClaim` / `persistence.etc.existingClaim` | `""` | Use an existing claim; in HA a data claim must be ReadWriteMany |
| `fips.enabled` | `false` | Run the `<tag>-fips` image with `UCM_FIPS=1`; the pod refuses to start without the FIPS provider |
| `service.type` | `ClusterIP` | Service type |
| `service.httpsPort` / `service.httpPort` | `8443` / `8080` | UI/API (HTTPS) and protocol (HTTP) ports |
| `service.annotations` | `{}` | Annotations of the Service |
| `dnsUpdate.enabled` | `false` | Enable the DNS UPDATE (RFC 2136) listener and its own Service (internal networks only) |
| `dnsUpdate.port` / `dnsUpdate.host` | `8053` / `""` | Container port (UDP and TCP, 1024-65535; sets `UCM_DNS_UPDATE_PORT`) and bind address (`UCM_DNS_UPDATE_HOST`, empty = default) |
| `dnsUpdate.service.type` / `dnsUpdate.service.port` | `ClusterIP` / `53` | Type and client port of the separate DNS UPDATE Service (port 53 maps to `dnsUpdate.port`) |
| `dnsUpdate.service.annotations` / `dnsUpdate.service.loadBalancerIP` | `{}` / `""` | Annotations and fixed address (type `LoadBalancer` only) |
| `dnsUpdate.networkPolicy.enabled` / `dnsUpdate.networkPolicy.from` / `dnsUpdate.networkPolicy.extraPorts` | `false` / `[]` / `[]` | Additional NetworkPolicy: the listener ports accept only the `from` peers; `https`, `http` and `extraPorts` accept all sources; every other pod port is closed |
| `ingress.enabled` | `false` | Expose the HTTPS UI via Ingress |
| `ingress.className` / `ingress.annotations` | `""` / `{}` | Ingress class and annotations (e.g. the backend protocol HTTPS for nginx) |
| `ingress.host` / `ingress.tls` | `ucm.local` / `[]` | Host and TLS section of the HTTPS Ingress |
| `ingress.protocolHttp.enabled` | `false` | Second Ingress for cleartext CDP/OCSP/ACME-HTTP-01 (port 8080) |
| `ingress.protocolHttp.host` | `pki.local` | Host of the cleartext protocol Ingress |
| `proxy.behindProxy` | `false` | Set `UCM_BEHIND_PROXY=1` (honor `X-Forwarded-*` for one hop) |
| `proxy.trustedProxies` | `[]` | `UCM_TRUSTED_PROXIES`: proxy IPs / CIDRs allowed to set forwarded / client-cert headers (CIDR entries need UCM 2.224 or later) |
| `extraEnv` | `[]` | Extra `UCM_*` env vars |
| `resources` | requests 100m/512Mi, limit 1Gi | Pod resources |
| `livenessProbe` | enabled, 40 s delay, every 30 s, timeout 10 s, 3 failures | Liveness probe on `/health/live` |
| `readinessProbe` | enabled, 20 s delay, every 15 s, timeout 10 s, 3 failures | Readiness probe on `/health/ready` |
| `startupProbe` | enabled, every 10 s, timeout 10 s, 36 failures | HA only: startup probe on `/health/live` |
| `serviceAccount.create` / `serviceAccount.name` / `serviceAccount.annotations` | `true` / `""` / `{}` | Create a ServiceAccount (name defaults to the full name) |
| `podSecurityContext` / `securityContext` | non-root UID/GID 1000, `fsGroup` 1000, seccomp `RuntimeDefault`; no privilege escalation, every capability dropped | Pod and container security contexts |
| `nodeSelector` / `tolerations` / `affinity` | `{}` / `[]` / `{}` | Scheduling; `affinity` replaces the HA anti-affinity |
| `podAnnotations` / `podLabels` | `{}` / `{}` | Extra pod annotations and labels |

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

### DNS UPDATE listener

The ACME proxy of UCM can accept TSIG-signed DNS UPDATE messages (RFC 2136) for DNS-01 challenges, for example from cert-manager `rfc2136` solvers. The listener is **off by default** and is for **internal networks only**.

```yaml
dnsUpdate:
  enabled: true
```

- The chart creates a **separate Service** `<fullname>-dns-update` (`ucm-dns-update` for the release `ucm`; UDP and TCP, port 53, target port 8053). The Service of the HTTPS UI never carries the listener, so exposing the UI (Ingress, LoadBalancer) does not expose it.
- The pod runs as a non-root user and cannot bind port 53. The Service maps port 53 to `dnsUpdate.port`.
- Keep `dnsUpdate.service.type: ClusterIP` unless clients outside the cluster must reach it. A `LoadBalancer` with UDP and TCP on the same port needs mixed-protocol support from your cloud or load balancer. Check the documentation of your provider.
- kube-proxy can replace the client IP with a node IP (SNAT). UCM then sees many clients as one source, and its limits per source address apply to all of them together.
- `dnsUpdate.networkPolicy.enabled: true` adds a NetworkPolicy that accepts the listener ports only from the peers in `dnsUpdate.networkPolicy.from`. The policy allows from all sources only the HTTPS port, the HTTP port and the ports in `dnsUpdate.networkPolicy.extraPorts` (list of `{port, protocol}`). Every other port of the pod is closed while the policy is enabled. For example, add the port of the ACME client TLS-ALPN-01 proof listener, or a port that you add through `extraEnv`, to `extraPorts`. The policy works only with a CNI that enforces NetworkPolicy.
- The TSIG keys are created per proxy account in the UCM web interface. See [`docs/integrations/acme-proxy-dns-update.md`](../../docs/integrations/acme-proxy-dns-update.md) and the [Admin Guide](../../docs/ADMIN_GUIDE.md).

## Uninstall

```bash
helm uninstall ucm -n ucm
```

The `*-etc` PVC (master.key) is intentionally **retained**. Delete it manually only when you are certain no encrypted data needs recovery.

The Secret is retained too whenever it holds `KEY_ENCRYPTION_KEY` (HA, or `secrets.keyEncryptionKey` set), and so is the `*-data` PVC of a former single-node release that an HA release still renders. Outside HA the `*-data` PVC is deleted with the release.

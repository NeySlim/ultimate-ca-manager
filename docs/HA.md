# High availability

UCM can run on two or more nodes that share one PostgreSQL database. This page covers what a node needs, three ways to deploy it, what stays local to a node and what is refused in HA mode. The scheduler, leader election and rolling restart are described in [HA mode (preview)](ADMIN_GUIDE.md#ha-mode-preview-scheduler-and-startup).

## Prerequisites

- **PostgreSQL 13 or later**, reachable by every node (`DATABASE_URL`). SQLite is refused at startup.
- **The same `SECRET_KEY` on every node** (`UCM_SECRET_KEY` in the Docker image). Sessions and signed tokens depend on it.
- **The same `KEY_ENCRYPTION_KEY` on every node**, a Fernet key. It decrypts every private key in the database: losing it makes them unrecoverable. Do not keep a different `master.key` file on a node: a local file overrides the variable.
- **A distinct `UCM_NODE_ID` per node** (default: the host name).
- **`UCM_HA=1`** on every node.
- **A load balancer** in front of the nodes. Probe `/health/ready`. Without Redis (see [REDIS.md](REDIS.md)) UI sessions are kept per node: use cookie affinity so a user stays on one node.
- **One gunicorn worker per node**, which is the default (`workers = 1`). Do not raise it.
- **Synchronised clocks** (NTP): node heartbeats are compared across hosts.

Generate the keys once:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"                                       # SECRET_KEY
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"          # KEY_ENCRYPTION_KEY
```

## Deployment 1: Helm

Set `ha.enabled=true`, `replicaCount` to 2 or more and a PostgreSQL URL:

```yaml
ha:
  enabled: true
replicaCount: 2
database:
  type: postgresql
  existingSecret: ucm-database      # or databaseUrl: postgresql://ucm:...@db.example.com:5432/ucm
fqdn: ucm.example.com
ingress:
  enabled: true
  host: ucm.example.com
  annotations:
    nginx.ingress.kubernetes.io/backend-protocol: "HTTPS"
    nginx.ingress.kubernetes.io/affinity: "cookie"
    nginx.ingress.kubernetes.io/session-cookie-name: "ucm-node"
```

The render fails with an explicit message when the database is not PostgreSQL or `replicaCount` is below 2. In HA mode the chart:

- sets `UCM_HA=1` and `UCM_NODE_ID` to the pod name;
- puts `UCM_SECRET_KEY` and `KEY_ENCRYPTION_KEY` in one Secret, generated once and kept across upgrades, including when `ha.enabled` is later set to false (override with `secrets.secretKey` and `secrets.keyEncryptionKey`). The Secret carries `helm.sh/resource-policy: keep`, so `helm uninstall` leaves it; back it up. With `helm template` or GitOps (ArgoCD) there is no lookup: set `secrets.keyEncryptionKey` explicitly, or each render generates a new key;
- creates no `etc` volume or claim: the key comes from the Secret;
- updates with `RollingUpdate` (`maxUnavailable: 0`), adds a PodDisruptionBudget (`ha.podDisruptionBudget.minAvailable`, default 1) and a preferred pod anti-affinity that spreads the pods over hosts (your own `affinity` value replaces it);
- passes `redis.url` as `REDIS_URL` when set;
- uses an `emptyDir` data volume per pod, with a warning in the release notes, unless `persistence.data.existingClaim` names a ReadWriteMany claim.

### From a single node

Moving an existing single-node release to `ha.enabled=true` needs these steps, because HA requires PostgreSQL, the data volume is no longer mounted and the key comes from the Secret:

0. If the release uses SQLite (the chart default), move it to PostgreSQL while still single-node: in Settings > Database, test the PostgreSQL URL and run **Migrate data and switch**, then `helm upgrade` with `database.type=postgresql` and that URL, and check the data in the UI. Setting `database.type=postgresql` alone starts on an empty database, and data migration is refused once in HA.
1. Copy the content of `/etc/ucm/master.key` (the `etc` volume) into `secrets.keyEncryptionKey`. A new key cannot decrypt the existing database.
2. Back up the data volume. The chart keeps the old claim (`helm.sh/resource-policy: keep`) but HA pods no longer mount it, so SoftHSM tokens, an uploaded HTTPS certificate and local backups stay behind in it.
3. Run `helm upgrade` with `ha.enabled=true`, then check `/health/ready`.

## Deployment 2: Docker Compose

`docker-compose.ha.yml` at the root of the repository starts PostgreSQL, two nodes and an HAProxy balancer with cookie affinity and a `/health/ready` probe. Create a `.env` file next to it with `POSTGRES_PASSWORD`, `UCM_SECRET_KEY`, `KEY_ENCRYPTION_KEY`, `HA_LB_CERT` (a PEM file with the certificate and key for the balancer) and `UCM_FQDN`, then:

```bash
docker compose -f docker-compose.ha.yml up -d
```

Compose refuses to start while one of these variables is missing. The balancer listens on port 8443. The image entrypoint writes no SQLite path and takes no SQLite backup copy when `UCM_HA=1`. Keep the restart policy `unless-stopped` or `always`: a rolling restart exits each container in turn.

## Deployment 3: DEB or RPM on two hosts

1. Install the package on both hosts.
2. In `/etc/ucm/ucm.env` on each host set the same `DATABASE_URL`, `SECRET_KEY` and `KEY_ENCRYPTION_KEY`, `UCM_HA=1`, and a different `UCM_NODE_ID`. The packages generate a random key per node at install: replace it on both hosts.
3. Every node must hold the same encryption key: either no `/etc/ucm/master.key` and `KEY_ENCRYPTION_KEY` in `ucm.env`, or the same `master.key` copied to every node (a local file wins over the variable).
4. Restart `ucm` on each host, one at a time, and check `/health/ready` through the balancer (HAProxy, nginx or any layer 7 balancer with cookie affinity).

## What stays local to a node

- **Backups.** Scheduled and manual backups are written under the node's data directory by the leader. They are not replicated: copy them off the host, and also back PostgreSQL up with its own tools.
- **SoftHSM tokens.** A token lives on the node's own disk, so the chart and the compose example set `HSM_AUTO_INIT=false`. CA keys must sit in a network HSM (PKCS#11 remote, Vault, Azure) when running HA; on packages, set `HSM_AUTO_INIT=false` too.
- **Certificate files** mirrored by renewals and session file cleanup, which run on the leader only.
- **The self-signed HTTPS certificate** of each node, as long as none was applied or regenerated from the web interface. Once one is, every node writes it from the database before it starts (see [ADMIN_GUIDE.md](ADMIN_GUIDE.md), HA mode).

## Shared encryption key

Every node holds the same key-encryption key (KEK): `KEY_ENCRYPTION_KEY`, or the same `master.key` on every node. The data-encryption keys it wraps live in the database (`encryption_keys`), so enabling, disabling, encrypting all keys and rotating the data key work from any node; the others reload the keys within seconds (`reload_encryption`). Each node publishes the fingerprint of its KEK (a truncated hash, never the key) in `cluster_nodes`, and a node whose fingerprint differs from a live peer's refuses to start and names that peer. Back up the KEK: the database without it is unreadable. See [Private-Key Encryption](ADMIN_GUIDE.md#private-key-encryption-kek-and-dek).

## Refused in HA mode today

These operations answer `409` with code `ha_mode`, because they only change the host that receives the request:

- backend switch and data migration between databases (`database.py`): change `DATABASE_URL` by hand, then restart;
- secret rotation (it writes `ucm.env`);
- installing an update from the web interface;
- backup restore, both from System and from Settings (restored files land on one node).

## Upgrading

Upgrade the nodes one at a time. Migrations run under a PostgreSQL advisory lock: the first node to start applies them, the others wait and find nothing to do. Keep the nodes on adjacent versions during the roll, and do not run an older version after a newer one migrated the schema.

- **Helm:** `helm upgrade` rolls the pods with no unavailable pod; the PodDisruptionBudget protects them from node drains.
- **Compose:** `docker compose -f docker-compose.ha.yml pull`, then `up -d ucm-1`, wait until it is healthy, then `up -d ucm-2`.
- **DEB/RPM:** upgrade and restart one host, wait for `/health/ready`, then the next.

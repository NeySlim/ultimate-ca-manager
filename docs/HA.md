# High availability

UCM can run on two or more nodes that share one PostgreSQL database. This page covers what a node needs, three ways to deploy it, what stays local to a node and what is refused in HA mode. The scheduler, leader election and rolling restart are described in [HA mode (preview)](ADMIN_GUIDE.md#ha-mode-preview-scheduler-and-startup).

## Prerequisites

- **PostgreSQL 13 or later**, reachable by every node (`DATABASE_URL`). SQLite is refused at startup.
- **The same `SECRET_KEY` on every node** (`UCM_SECRET_KEY` in the Docker image). It signs the CSRF tokens until the session key is rotated from the web interface, which stores the new key in the database for every node; it then stays the fallback (see [ADMIN_GUIDE.md](ADMIN_GUIDE.md#session-key-rotation)).
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
2. Back up the data volume. HA pods no longer mount it, so SoftHSM tokens, an uploaded HTTPS certificate and local backups stay behind in it. `helm upgrade` still renders the existing claim, unmounted and with `helm.sh/resource-policy: keep`, when its cluster lookup finds it; `helm template` and GitOps tools have no lookup and drop the claim from the manifest, so protect it on their side before the switch.
3. Run `helm upgrade` with `ha.enabled=true`, then check `/health/ready`.

## Deployment 2: Docker Compose

`docker-compose.ha.yml` at the root of the repository starts PostgreSQL, two nodes and an HAProxy balancer with cookie affinity and a `/health/ready` probe. Create a `.env` file next to it with `POSTGRES_PASSWORD`, `UCM_SECRET_KEY`, `KEY_ENCRYPTION_KEY`, `HA_LB_CERT` (a PEM file with the certificate and key for the balancer) and `UCM_FQDN`, then:

```bash
docker compose -f docker-compose.ha.yml up -d
```

Compose refuses to start while one of these variables is missing. The balancer listens on port 8443. The image entrypoint writes no SQLite path and takes no SQLite backup copy when `UCM_HA=1`. Keep the restart policy `unless-stopped` or `always`: a rolling restart exits each container in turn.

The network uses the fixed subnet `172.28.0.0/24`, trusted as the proxy. When `up` fails with "Pool overlaps", another Docker network already holds that range: set `UCM_HA_SUBNET` in `.env` to a free one.

## Deployment 3: DEB or RPM on two hosts

1. Install the package on both hosts.
2. In `/etc/ucm/ucm.env` on each host set the same `DATABASE_URL`, `SECRET_KEY` and `KEY_ENCRYPTION_KEY`, `UCM_HA=1`, and a different `UCM_NODE_ID`. The packages generate a random key per node at install: replace it on both hosts.
3. Every node must hold the same encryption key: either no `/etc/ucm/master.key` and `KEY_ENCRYPTION_KEY` in `ucm.env`, or the same `master.key` copied to every node (a local file wins over the variable).
4. Restart `ucm` on each host, one at a time, and check `/health/ready` through the balancer (HAProxy, nginx or any layer 7 balancer with cookie affinity).

## First administrator

The administrator is created once, by the first node to start, under the startup lock. Provide its password through a secret shared by the nodes (`INITIAL_ADMIN_PASSWORD_FILE`; the Helm chart passes `INITIAL_ADMIN_PASSWORD` from its Secret to every pod), or let that node generate it: only that node then writes `initial-admin-password`, and every node's log says which node holds it. The password change at first login removes the file wherever it is. See [ADMIN_GUIDE.md](ADMIN_GUIDE.md#initial-administrator-password).

## Backups

Scheduled and manual archives are stored in PostgreSQL (`backup_archives`, and the archive itself in chunks of 1 MiB in `backup_archive_chunks`), encrypted as on disk, with the node that wrote it, its date, size and SHA-256. Every node lists the same archives (Settings > Backup shows the node) and downloads any of them, also when the node that wrote it is gone; the download carries the SHA-256 in a `Repr-Digest` header. An archive appears once it is whole: an export that fails or a node that dies mid-write leaves nothing behind. Retention runs once, on the leader (and on demand from any node, one at a time across the cluster), over the whole set, with the rules of a single node (age, the newest archives always kept); each archive is read back before it is stored, so none counts as unproven. Archives a node kept on its disk before HA are no longer listed; copy them off the host. Writing an archive holds one transaction for as long as it lasts, so its connection lifts `idle_in_transaction_session_timeout` for that transaction: a server that sets it, as managed PostgreSQL services often do, does not cut a slow backup short. A download reads each chunk in a short transaction of its own and holds no connection between two, so slow clients do not exhaust a node's connection pool; an archive deleted during a download ends it short of its `Content-Length`, never with other bytes.

An archive kept in the database does not survive the loss of that database: download the archives you keep to a place outside the cluster, and back PostgreSQL up with its own tools (to restore such a dump, see [Restoring with PostgreSQL's tools](#restoring-with-postgresqls-tools)). Each archive adds about its own size to the database and to its dumps, so the database holds what retention keeps: with the default 30 days and daily backups, about 30 archives, and never fewer than the 2 newest. `pg_dump --exclude-table-data=backup_archives --exclude-table-data=backup_archive_chunks` leaves them out of a dump.

## Restoring a backup

An archive is restored from any node, from Settings > Backup or `POST /api/v2/system/restore`. The node that receives it holds a cluster maintenance (one row in `cluster_maintenance`) for the whole restore. Before setting it, that node checks the password and the archive's header and first chunk, which FIPS mode refuses for an Argon2id archive: a wrong password or a file that is not a backup answers `400` without touching the other nodes. An archive damaged further on is refused under the maintenance.

1. Every process of every node reads the maintenance within about 2 seconds and from then on refuses writes, then records it in `cluster_nodes` (`maintenance_ack` for the web worker, `maintenance_ack_scheduler` for the process that runs the scheduled tasks).
2. The restore starts once both processes of every node with a fresh heartbeat have recorded it. After 30 seconds without, it is refused with `409` and code `maintenance_not_acknowledged`, the silent nodes listed in `nodes` with the process missing; nothing is changed and the maintenance is lifted. A node that died counts until its heartbeat is stale (3 minutes).
3. The restore is one transaction, as on a single node. Just before its commit it checks, in that transaction, that the maintenance is still its own and within its lease; otherwise everything is rolled back (`409`, code `maintenance_lost`).
4. Once it commits, the sessions are revoked and the CRLs signed again, as on a single node, then a rolling restart is requested. A process started after that request serves again; every node not restarted yet keeps refusing writes and answering 503 on `/health/ready`. The maintenance is lifted once every node with a fresh heartbeat has restarted.

A restore that fails leaves the database as it was, lifts the maintenance and answers the error. An archive that carries no data lifts it with no restart. Sessions, archives encrypted by another installation and archives of older versions follow the single-node rules (see [ADMIN_GUIDE.md](ADMIN_GUIDE.md#restoring-backups)).

### What a node in maintenance serves

- Writes are refused with `503`, `Retry-After: 30` and code `maintenance`: every `POST`, `PUT`, `PATCH` and `DELETE` of the API (sign-in included) and every request to ACME, EST, SCEP, MS-XCEP, MS-WSTEP and TSA, whatever its method. A write the node's own code still sends (a read that writes, a task already running) fails the same way, and so does the commit of a transaction that wrote before the node saw the maintenance.
- No scheduled task starts, on the leader as on the others; a "run now" waits for the end. The heartbeat goes on, and no session is saved.
- `/health/ready` answers `503` with `status: "maintenance"`, so the balancer takes the node out of rotation; `/health` and `/health/live` answer 200, and `/health` reports `maintenance` (reason, phase, node, lease).
- Reads of the API and the web interface are served, as are `GET` and `DELETE /api/v2/system/maintenance`.
- OCSP, CRL distribution points and AIA keep answering from the state before the restore: relying parties keep validating certificates, a client that fails hard on a missing revocation answer is not cut off, and the answer is at most one restore old. Meanwhile no OCSP response is stored and no CRL is signed: a CRL past its next update is served as it is, and a CA with no stored CRL answers `503` with `Retry-After`.
- Socket.IO connections are answered before the request hooks and are not covered.

A node that starts while a restore has not committed yet waits for its end before migrating or writing, and says so in its log.

### When the restoring node dies

The maintenance has a lease of 5 minutes, renewed every 30 seconds while the restore runs. A restore that had not committed is rolled back by PostgreSQL with the node's connection, and the first node that sees the lease ended lifts the maintenance. A restore that had committed is completed by the first node that sees its lease ended: it revokes the sessions and requests the rolling restart, as the restoring node would have. The rolling restart phase has a lease of 30 minutes. An administrator lifts the maintenance at once from any node with `DELETE /api/v2/system/maintenance`, which first completes a committed restore the same way.

### Restoring with PostgreSQL's tools

`POST /api/v2/system/maintenance` with `{"lease_minutes": 60}` (1 to 1440) sets the same maintenance by hand. It answers once every node with a fresh heartbeat has recorded it, or `409` naming the others and lifts it; posting again extends it, `GET` shows it with each node's acknowledgement, `DELETE` lifts it. A manual maintenance survives a restart of the nodes.

Before restoring a `pg_dump`, make sure every node runs with the key-encryption key of the installation that was dumped (`KEY_ENCRYPTION_KEY` or `master.key`): the data-encryption keys in `encryption_keys` are wrapped by it. The tables that describe the running cluster are not data to restore: `cluster_nodes`, `cluster_commands`, `cluster_maintenance`, `scheduler_requests`, `websocket_relay` and the sessions (`user_sessions`, `pro_sso_sessions`, and `flask_sessions` on PostgreSQL without Redis).

- **Nodes stopped** (simplest): stop every node, run `pg_restore --clean --if-exists`, empty the tables above (`TRUNCATE`), and with Redis sessions delete the keys under `SESSION_KEY_PREFIX` (default `ucm:session:`). Start the nodes one at a time: a dump of an earlier release is migrated by the first one.
- **Nodes running**: set the maintenance, list the dump (`pg_restore -l dump > list`), remove the lines of the tables above from `list`, run `pg_restore --clean --if-exists -L list`, empty the session tables, restart every node with its service manager (`systemctl restart ucm`, `kubectl rollout restart`, `docker compose restart`), then lift the maintenance. The nodes refuse writes until it is lifted, and `--clean` drops the tables they read while it runs, so expect errors on reads meanwhile.

## What stays local to a node

- **Update result.** The outcome of an update is read on the node that installed it, leader or not.
- **Per-node task status.** The scheduler view shows the update result runs of the node that answers, and Run now runs them on that node.
- **SoftHSM tokens.** A token lives on the node's own disk, so UCM refuses to create one in HA mode (see [Refused in HA mode today](#refused-in-ha-mode-today)). A SoftHSM provider already in the database stays visible, a warning at start names it, and its keys sign only on the node that holds the token. Software CA keys stored in PostgreSQL under the shared `KEY_ENCRYPTION_KEY` work on every node; keys kept in an HSM must use a network HSM (PKCS#11 over the network, OpenBao, Azure Key Vault, AWS CloudHSM, Google KMS).
- **Kerberos negotiation state.** A SPNEGO handshake that takes more than one request is kept in the memory of the node that received its first leg (see [Windows enrollment](#windows-enrollment-kerberos)).
- **Certificate files** mirrored by renewals and session file cleanup, which run on the leader only.
- **The self-signed HTTPS certificate** of each node, as long as none was applied or regenerated from the web interface. Once one is, every node writes it from the database before it starts (see [ADMIN_GUIDE.md](ADMIN_GUIDE.md), HA mode).

## Scheduled passes across nodes

The `certificate.expired` webhooks resume from the last pass on any node, at most 30 days back, as on a single node. A pass of the expiry alerts or of a CA's scheduled CRL skipped because another node holds its lease runs once more 30 seconds after that lease ends, instead of waiting a day or an hour. See [ADMIN_GUIDE.md](ADMIN_GUIDE.md#ha-mode-preview-scheduler-and-startup).

## Shared encryption key

Every node holds the same key-encryption key (KEK): `KEY_ENCRYPTION_KEY`, or the same `master.key` on every node. The data-encryption keys it wraps live in the database (`encryption_keys`), so enabling, disabling, encrypting all keys and rotating the data key work from any node; the others reload the keys within seconds (`reload_encryption`). Each node publishes the fingerprint of its KEK (a truncated hash, never the key) in `cluster_nodes`, and a node whose fingerprint differs from a live peer's refuses to start and names that peer, unless the database names its KEK and not the peer's. Enabling encryption is refused (409, naming the node) while a live node holds another KEK. Back up the KEK: the database without it is unreadable. See [Private-Key Encryption](ADMIN_GUIDE.md#private-key-encryption-kek-and-dek).

## Windows enrollment (Kerberos)

The Windows enrollment profiles, their connectors and the switches are in the database, so every node serves them. Two things are per node:

- **SPNEGO state.** Some Windows clients need more than one request to complete the Negotiate handshake (a request-MIC leg). The context in progress is kept in the memory of the node that answered the first leg, under the client's source address (the address behind the trusted proxy when there is one), and expires after 30 seconds. The balancer must therefore send the requests of one client address to one node: use source-address affinity for the two Kerberos endpoints (`/ADPolicyProvider_CEP_Kerberos/` and `/ADCertificateService_CES_Kerberos/`), while the web interface keeps its cookie affinity. Two clients behind one address that negotiate at the same moment can make each other retry, never authenticate wrongly.
- **The keytab file.** A profile's keytab is stored in the database, under the master key. UCM composes the keytabs of all profiles into one file, stores it in the database and asks every node to write it (`reload_keytab`, within seconds, and at each start); the composition is made under a lock, so two uploads at once give one result on every node. A node that cannot read the stored keytab (a different `KEY_ENCRYPTION_KEY`) cannot write the file and logs the reason. A keytab found on one node only, as 2.x kept it, is not shared in HA: upload it again.

## Refused in HA mode today

These operations answer `409` with code `ha_mode`, because they only change the host that receives the request:

- backend switch and data migration between databases (`database.py`): change `DATABASE_URL` by hand, then restart;
- session key rotation without encryption (it would write `ucm.env`); with the KEK every HA node holds, it is stored in the database and works from any node, see [Session key rotation](ADMIN_GUIDE.md#session-key-rotation);
- creating a SoftHSM provider, pointing a provider at SoftHSM, generating a key on a SoftHSM provider, syncing the keys of a SoftHSM provider, and creating a CA (root, intermediate or external CSR) on a new or an existing SoftHSM key (the token is on one node's disk). A CA already bound to a SoftHSM key keeps signing on the node that holds the token. The image does not initialize its default token when `UCM_HA` is set, whatever `HSM_AUTO_INIT` says. Network PKCS#11, OpenBao and cloud KMS providers are not affected.

## Upgrading

Upgrade the nodes one at a time. Migrations run under a PostgreSQL advisory lock: the first node to start applies them, the others wait and find nothing to do. Keep the nodes on adjacent versions during the roll, and do not run an older version after a newer one migrated the schema. A cluster moves to 3.0 from 2.254 only: roll every node to 2.254 first; a 3.0 node refuses to start, without writing, on a database 2.254 has not started (see UPGRADE.md).

- **Helm:** `helm upgrade` rolls the pods with no unavailable pod; the PodDisruptionBudget protects them from node drains.
- **Compose:** `docker compose -f docker-compose.ha.yml pull`, then `up -d ucm-1`, wait until it is healthy, then `up -d ucm-2`.
- **DEB/RPM:** upgrade and restart one host, wait for `/health/ready`, then the next. Or install the update from the web interface (System > Updates), or let the scheduled automatic install do it: in HA mode either starts a rolling update.

### Rolling update from the web interface (DEB/RPM)

One campaign runs at a time. The scheduler leader gives the turn to one node at a time, in `UCM_NODE_ID` order, among the nodes with a fresh heartbeat when it starts. Each node installs the package of its own family, reported in `cluster_nodes.package_family` at every heartbeat: `deb`, `rpm-el9`, `rpm-el10` (any `rpm-elN`) or `rpm-fedora` (an RPM host of no EL release). At the start the campaign records one package per family present among the nodes beating, with its SHA-256 from the release; it refuses to start, naming the node and the reason, when a node runs Docker or Kubernetes (`container`) or an unknown packaging, or when the release has no package for a present family or no SHA-256 for it. An EL host whose release has no `.elN.` build is offered the Fedora RPM, which installs only where the system `python3` is 3.12 or later (it does not on EL8), and the campaign refuses only when the release has no RPM at all. On its turn, a node takes the entry of the family it detects itself, checks that the command carries the SHA-256 frozen at the start for that family, downloads and verifies the package, then asks its own update watcher to install it. The next node starts only once the previous one has a fresh heartbeat on the target version in `cluster_nodes`. A node already on the target is counted done without an install.

The campaign stops, and leaves the remaining nodes alone, when a node fails to download or verify the package, has a family the campaign holds no package for (a node that joined after the start; one that joins with a family present takes a turn), comes back on another version, or is not back on the target within 15 minutes (download, install, migrations under the startup lock and the first heartbeat). Every step is audited and pushed to the browsers. System > Updates shows the target, the nodes done, the node in progress and the node where it stopped with the reason; fix that node, then **Resume** continues from it. Nodes without a fresh heartbeat at the start are listed as skipped and not updated; the end message names them.

While the campaign runs, the updated nodes and the others share the database. The first updated node applies the target's migrations: a migration that the older version cannot run against leaves the nodes not yet updated failing until their turn. Read the release notes before updating a cluster.

In Docker and Kubernetes the route and the scheduled install refuse with a message: the orchestrator updates the image (`docker compose pull`, `helm upgrade`).

During a roll from a version without the scheduled backup's conclusion marker, a scheduled backup run by an older leader is not marked as concluded: a newer leader then writes one extra archive two hours later, once.

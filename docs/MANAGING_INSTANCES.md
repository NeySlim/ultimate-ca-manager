# Managing several instances

Many deployments run more than one UCM: one per environment, per trust domain or per site. Each
instance stays independent, with its own database, private keys and administrators. What UCM
offers is a stable contract that a monitoring tool, a script or a central console can rely on to
watch and operate several instances from one place, over each instance's own API.

This page describes that contract: the state route, the API key scopes a console needs, the
identity that lets it recognize an instance, and how to expose all of it safely.

## The state of an instance

`GET /api/v2/system/instance` answers in one request what a console shows for an instance:

- the version and the update channel (`stable` or `rc`), and how it was installed (`deb`,
  `rpm-elN`, `rpm-fedora`, `container`);
- the mode: single node, or HA with the list of its nodes, the leader and those that stopped
  answering;
- the database engine and server version (never its URL, its host or its credentials);
- the health: `ok`, `degraded` or `maintenance`, with the readiness checks behind it (in safe mode
  the route answers `503`, as the rest of the API does);
- the CAs: how many, how many are active, expired, and expiring within 90 and 365 days, and the
  nearest expiry;
- whether an update is available, as the last scheduled check found it (the route itself never
  contacts GitHub);
- the scheduled backup: whether it is on, when the newest archive was written and how the last
  run ended;
- whether FIPS mode was requested and is active.

The answer carries `schema_version` (`1`). Later releases only add fields to schema 1; a field
removed or changing meaning would come with schema 2. The exact fields are in the
[API reference](API_REFERENCE.md#instance-state).

## The key a console uses

Create a dedicated API key for the console on each instance, as an administrator, in **My
Account > API Keys**, with the **Instance management** scope. It holds exactly:

| Scope | Allows |
|---|---|
| `read:instance` | `GET /api/v2/system/instance` |
| `read:settings` | reading the settings (`GET /api/v2/settings/...`), except the backup history and download and `audit-logs`, which take `admin:system`, and the e-mail OAuth callback (`email/oauth/callback`), which takes `admin:settings` |
| `write:backups` | starting a backup (`POST /api/v2/system/backup/create`) and following its job |
| `write:updates` | installing an update (`POST /api/v2/system/updates/install`) and following an HA rolling update |

None of them reads, downloads or restores a backup archive, changes a setting, or reaches the rest
of `admin:system`. The three new scopes are reserved for administrators: a custom role cannot
grant them, and only an administrator can put them on a key. A console that only watches needs
`read:instance` alone.

The key is sent as `Authorization: Bearer ucm_ak_...` (or `X-API-Key`). Give it an expiry and
rotate it like any other credential: a key cannot be read back after its creation.

## Limiting the key to the console's address

A console connects from afar, so its key should work from the console's address only. When
creating the key, fill **Allowed source addresses** (or `allowed_networks` in the API) with the
console's IP addresses or CIDR networks. From any other address the key is refused with `403` and
its last use is not updated. A key created or regenerated through a limited key stays inside the same networks.

The address checked is the one UCM resolves for the request. Behind a reverse proxy, declare it
in `UCM_TRUSTED_PROXIES` and `UCM_TRUSTED_PROXY_HOPS`, otherwise every request seems to come from
the proxy. The instance-wide admin allowlist (`UCM_ADMIN_ALLOWED_NETWORKS`, see the
[administration guide](ADMIN_GUIDE.md#admin-access-allowlist)) still applies on top of it: the
console's address must pass both.

## Recognizing an instance

`instance_id` (32 hexadecimal characters) identifies the instance. It is created once, kept in
the instance's database, and does not change when the instance restarts, changes address or
hostname, or is updated. In HA every node answers the same id, since they share the database:
a console sees one instance, with its nodes in `mode.nodes`.

A backup restore keeps the id of the database it restores into:

- restoring on the same instance keeps its id;
- restoring an archive on another machine, a new installation included, gives the data the id of
  that machine's database. The console sees a new instance holding the restored content; recover
  the console's record by hand if the new machine replaces the old one.

A copy of the database itself (copying the SQLite file, `pg_dump` and restore) carries the id
with it. Two instances started from such copies answer the same id: when cloning an instance this
way to make another one, remove the `backup_installation_id` row of `system_config` in the copy
before its first start, and a new id is created.

## Network practices

- Reach each instance over HTTPS, and have the console check its certificate.
- Prefer a management network: the console talks to the instances' API, never the other way.
- One key per instance and per console, limited to the console's address, with an expiry.
- A console that only displays state holds `read:instance` only; give `write:backups` and
  `write:updates` to the one that acts.
- UCM records the actions of the key in the audit log, under the account that owns the key: use a
  dedicated administrator account for the console to tell its actions apart.

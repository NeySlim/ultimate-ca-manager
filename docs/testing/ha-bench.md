# HA bench

Two or three real UCM nodes (gunicorn, as the packages run them) in HA mode on
one PostgreSQL schema, and the scenarios that prove what HA mode promises. The
bench is not part of the suite: its tests carry the `ha` marker, which
`backend/pyproject.toml` deselects by default.

## One command

```bash
cd backend
UCM_TEST_HA=1 UCM_TEST_PG_URL=postgresql://user:password@host:5432/dbname pytest -m ha tests/ha
```

`UCM_TEST_PG_URL` is the same non-superuser role as the PostgreSQL CI job. The
role owns the database (`CREATE` on it, and closing it to new connections from
the `postgres` database in `test_database_cut.py`). Without both variables the `ha` tests are
skipped. On GitHub Actions, run the *Tests & Quality Checks* workflow by hand
with the `ha` input ticked (job *HA bench (three nodes)*).

## What a node gets

Each test module starts a fresh cluster: a schema `ucm_ha_<pid>_<random>`,
created empty and dropped afterwards, and two nodes started at the same time
(three, or once with each size, for the modules marked `node_counts(...)`).
Each node runs with an environment built by the bench and nothing else:

- its own `DATA_DIR`, `UCM_CONFIG_DIR`, logs and `TMPDIR` under the pytest
  temporary directory, and a free HTTPS port (the plain HTTP protocol port is off);
- the shared `DATABASE_URL` (the schema through `search_path`), `SECRET_KEY`,
  `KEY_ENCRYPTION_KEY` and `UCM_HA=1`, with its own `UCM_NODE_ID`.

A `sitecustomize` on the node's `PYTHONPATH` (`backend/tests/ha/guard`) installs
an audit hook in every process of the node: opening, listing or changing a path
under `/etc/ucm`, `/opt/ucm`, `/var/lib/softhsm` or `/var/log/ucm` kills the
node and is recorded, and the test fails. The bench waits for `/health/ready`
within a bound, stops a node with SIGTERM and kills its process group as a last
resort; a failed test's report carries every node's log.

## Scenarios

| File | Nodes | Proves |
|---|---|---|
| `test_startup.py` | 2 | both nodes started on an empty schema: the schema is built once, every migration recorded, both ready |
| `test_health.py` | 2 | each `/health` reports its own `node_id` and the same `cluster` state |
| `test_bench.py` | 2 | a closed cluster leaves no process, schema or database session |
| `test_sessions.py` | 2, 3 | a login on node A is valid on every other node, CSRF token included |
| `test_session_key.py` | 2, 3 | the session key rotated on A is accepted by every other node without a restart, tokens of the old key still pass |
| `test_leader.py` | 2, 3 | one leader; a task asked on a follower runs on the leader only; the leader killed, one follower takes over within the bound of the Administration guide |
| `test_restore.py` | 2, 3 | a restore on A while B issues starts once every node acknowledged the maintenance; B refuses writes from then on, every node restarts in turn, B serves the restored state |
| `test_issuance.py` | 2 | 20 parallel issuances over both nodes: distinct serials, CA count 20, a duplicate serial refused by the database |
| `test_revocation_crl.py` | 2 | revocations on both nodes, CRLs regenerated from both: distinct and increasing `crlNumber`, every revocation listed |
| `test_backups.py` | 2 | a backup taken on A is listed on B and downloads from B after A is killed; retention runs on the leader only |
| `test_https.py` | 2 | a certificate applied to HTTPS on A is served by B after its restart |
| `test_realtime.py` | 2 | an event born on one node reaches a browser of each node once, without Redis |
| `test_crash_issuance.py` | 3 | a follower killed while its requests wait inside their transaction: every 2xx has its certificate, readable from another node, under a unique serial; cut requests fail with a broken connection and leave no row; the CA count equals the certificates kept (no gap) |
| `test_crash_crl.py` | 3 | the leader killed while its scheduled pass signs a CRL: a follower leads within the documented bound, the dead leader's lease holds until its 15 minutes are over and no longer, the CRL is signed once more under the next number |
| `test_database_cut.py` | 3 | every database session terminated, new ones refused for 10 s: `/health/ready` answers 503 meanwhile; then every node serves without a restart under one leader, issues and revokes, and no advisory lock, lease or maintenance is left |
| `test_rolling_restart.py` | 3 | each node stopped (SIGTERM) and started again in turn while a client issues through the others: no issuance lost or made twice, the session survives, the leader changes once per stop of the leader |

The crash scenarios make the instant of the failure deterministic with a row lock
the test holds (the CA row, the CRL number counter): the node is killed once its
session waits on it in `pg_stat_activity`, then the lock is released.
`test_crash_crl.py` waits out the real lease, about 16 minutes.

The leader lock is database-wide, and `test_database_cut.py` closes the
database to new connections for 10 seconds (`ALLOW_CONNECTIONS false`): run the bench on a database no other
UCM instance or PostgreSQL test uses at the same time.

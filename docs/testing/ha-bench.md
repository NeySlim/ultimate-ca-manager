# HA bench

Two real UCM nodes (gunicorn, as the packages run them) in HA mode on one
PostgreSQL schema, and the scenarios that prove what HA mode promises. The
bench is not part of the suite: its tests carry the `ha` marker, which
`backend/pyproject.toml` deselects by default.

## One command

```bash
cd backend
UCM_TEST_HA=1 UCM_TEST_PG_URL=postgresql://user:password@host:5432/dbname pytest -m ha tests/ha
```

`UCM_TEST_PG_URL` is the same non-superuser role as the PostgreSQL CI job. The
role needs `CREATE` on the database. Without both variables the `ha` tests are
skipped. On GitHub Actions, run the *Tests & Quality Checks* workflow by hand
with the `ha` input ticked (job *HA bench (two nodes)*).

## What a node gets

Each test module starts a fresh cluster: a schema `ucm_ha_<pid>_<random>`,
created empty and dropped afterwards, and two nodes started at the same time.
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
resort; a failed test's report carries both nodes' logs.

## Scenarios

| File | Proves |
|---|---|
| `test_sessions.py` | a login on node A is valid on node B, CSRF token included |
| `test_issuance.py` | 20 parallel issuances over both nodes: distinct serials, CA count 20, a duplicate serial refused by the database |
| `test_revocation_crl.py` | revocations on both nodes, CRLs regenerated from both: distinct and increasing `crlNumber`, every revocation listed |
| `test_leader.py` | one leader; a task asked on the follower runs on the leader only; after the leader is killed the other node takes over within the bound documented in the Administration guide |
| `test_startup.py` | both nodes started on an empty schema: the schema is built once, every migration recorded, both ready |
| `test_health.py` | each `/health` reports its own `node_id` and the same `cluster` state |
| `test_bench.py` | a closed cluster leaves no process, schema or database session |

The leader lock is database-wide: run the bench on a database no other UCM
instance or PostgreSQL test uses at the same time.

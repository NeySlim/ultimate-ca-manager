# Running the backend suite on PostgreSQL

By default the session `app` fixture of `backend/tests/conftest.py` runs on
SQLite. Setting `UCM_TEST_APP_PG_URL` runs it on PostgreSQL instead, so the
application logic (ACME, issuance, revocation, backup and restore through the
routes, mTLS, the scheduler) is exercised on the backend that HA installations
use.

## Variables

| Variable | Used by | Meaning |
|---|---|---|
| `UCM_TEST_APP_PG_URL` | the `app` fixture | PostgreSQL database the session application runs on |
| `UCM_TEST_POSTGRES_URL` | tests marked `postgres` | their own engine, unchanged |
| `UCM_TEST_PG_URL` | migration, backend-switch and restore tests | their own engine on a non-superuser role, unchanged |

The three are independent: setting the first does not change what the other
two tests do.

## One schema per process

Each pytest process creates its own schema, `ucm_app_<pid>_<random>`, and reaches it
through the URL's `search_path` (`options=-csearch_path=...`), so the
application, the migration runner and any engine built from `DATABASE_URL`
all land in it. The schema is created empty: `create_app()` builds it with
`create_all()` and marks every migration as applied, as on a fresh
installation. It is dropped (`DROP SCHEMA ... CASCADE`) at the end of the
session; a schema left behind by a killed run is dropped by the next run.

A test module that builds its own application with `create_app('testing')`
gets a further schema, `ucm_app_<pid>_<random>_<n>`, as it gets a fresh in-memory
database on SQLite: it never shares rows (or a locked admin) with the session.

The URL also sets `lock_timeout=30s`: a lock the process waits for while
holding it itself fails the test instead of hanging the run.

The role only needs `CREATE` on the database: no superuser rights, and the
`public` schema is never touched. Under xdist each worker is its own process
and gets its own schema, so `-n 4 --dist loadfile` works.

## The upgrade from 2.254

`tests/test_upgrade_from_2_254.py` loads the schema of 2.254 with its migration
registry (`tests/fixtures/schema_v2254_{sqlite,postgresql}.sql`) into a database of
its own, runs the migration runner on it and compares the result with a fresh
`create_all()`: tables, columns, indexes and their predicates, constraints, foreign
keys, sequences and `AUTOINCREMENT`. Every accepted difference is listed with its
reason in `TOLERATED`. The same file checks the data steps, an upgrade interrupted
after each step, and the refusal of a database older than 2.254. On PostgreSQL it
uses `UCM_TEST_PG_URL`, one schema `up2254_<name>_<worker>` per database.

The fixtures are generated from a tag, never edited by hand:

```bash
python3 scripts/schema_fixture.py v2.254-rc1 2.254
```

## `sqlite_only`

A test that only makes sense on SQLite (it opens the database file, or builds
a state PostgreSQL's foreign keys refuse) is marked:

```python
@pytest.mark.sqlite_only(reason='opens the SQLite file directly')
```

It runs as before on SQLite and is skipped, with its reason, in PostgreSQL
mode. A test that fails on PostgreSQL because the product is wrong there is
not marked: the product is fixed.

PostgreSQL never reuses ids and its sequences only move forward, so a test
must find its own rows by name or filter (`search=`, `cn=`), never by counting
rows or reading the first page.

## Locally

```bash
cd backend
export UCM_TEST_APP_PG_URL=postgresql://user:password@localhost:5432/ucm_test
python -m pytest tests/test_certificates.py -p no:xdist
python -m pytest tests/ -n 4 --dist loadfile
```

## CI

The `test-backend-postgres` job runs, in this mode and as a non-superuser
role, the ACME, backup, restore, mTLS, certificate, revocation and scheduler
files, plus
`test_postgres_schema_of_its_own.py` and `test_db_error_parameters_hidden.py`,
whose PostgreSQL cases only run in this mode.

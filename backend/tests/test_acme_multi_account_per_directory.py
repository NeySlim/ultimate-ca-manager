"""Issue #276 — multiple external ACME client accounts may share one directory
URL, and an empty directory_url defaults to Let's Encrypt Production.

Covers both the API contract (POST /acme/client/accounts) and the service-side
resolution preference (default account wins when several share a URL).
"""
import importlib
import sqlite3
from tests.acme_rows import delete_client_accounts

import pytest

from models import db, AcmeClientAccount

LE_PROD = AcmeClientAccount.LE_PRODUCTION_URL
DUP_DIR = 'https://acme-multi.example/directory'


@pytest.fixture
def fresh_account_table(app):
    with app.app_context():
        delete_client_accounts(AcmeClientAccount.query)
        db.session.commit()
        yield


class TestDuplicateDirectoryCreate:
    def test_second_account_same_directory_allowed(self, auth_client, fresh_account_table):
        payload1 = {'directory_url': DUP_DIR, 'label': 'LE One', 'email': 'a@e.com'}
        payload2 = {'directory_url': DUP_DIR, 'label': 'LE Two', 'email': 'b@e.com'}
        r1 = auth_client.post('/api/v2/acme/client/accounts', json=payload1)
        assert r1.status_code == 201
        r2 = auth_client.post('/api/v2/acme/client/accounts', json=payload2)
        assert r2.status_code == 201
        body2 = r2.get_json()
        assert body2['data']['label'] == 'LE Two'
        assert body2['data']['directory_url'] == DUP_DIR
        assert body2['data']['id'] != r1.get_json()['data']['id']

    def test_same_directory_same_email_also_allowed(self, auth_client, fresh_account_table):
        # No uniqueness constraint on (url, email) either — administrative
        # separation is the point of #276.
        for label in ('A', 'B'):
            r = auth_client.post(
                '/api/v2/acme/client/accounts',
                json={'directory_url': DUP_DIR, 'label': label, 'email': 'same@e.com'},
            )
            assert r.status_code == 201

    def test_empty_directory_url_defaults_to_letsencrypt_production(
        self, auth_client, fresh_account_table
    ):
        r = auth_client.post(
            '/api/v2/acme/client/accounts',
            json={'directory_url': '', 'label': 'Default LE', 'email': 'ops@e.com'},
        )
        assert r.status_code == 201
        assert r.get_json()['data']['directory_url'] == LE_PROD

    def test_accounts_list_sorted_default_first(self, auth_client, fresh_account_table, app):
        auth_client.post('/api/v2/acme/client/accounts',
                         json={'directory_url': DUP_DIR, 'label': 'X', 'email': 'x@e.com'})
        r2 = auth_client.post('/api/v2/acme/client/accounts',
                              json={'directory_url': DUP_DIR, 'label': 'Y', 'email': 'y@e.com'})
        acct_id = r2.get_json()['data']['id']
        # First auto-defaults to the first row created; flip via the endpoint
        auth_client.post(f'/api/v2/acme/client/accounts/{acct_id}/default')
        r = auth_client.get('/api/v2/acme/client/accounts')
        labels = [a['label'] for a in r.get_json()['data']]
        assert labels[0] == 'Y'


class TestAmbiguousResolutionPrefersDefault:
    """services.acme.acme_client_service._resolve_account must pick the default
    account (or the oldest) when several share a directory URL."""

    def _build(self, app, url):
        with app.app_context():
            for label, default in [('first', False), ('preferred', True), ('third', False)]:
                db.session.add(AcmeClientAccount(
                    directory_url=url, label=label, email='x@e.com', is_default=default,
                ))
            db.session.commit()

    def test_default_row_wins(self, app, fresh_account_table):
        self._build(app, DUP_DIR)
        from services.acme.acme_client_service import AcmeClientService
        with app.app_context():
            svc = AcmeClientService(directory_url=DUP_DIR)
            assert svc.account.label == 'preferred'  # is_default=True
            db.session.rollback()  # dispose of any service-commit side effects

    def test_no_default_falls_back_to_oldest(self, app, fresh_account_table):
        with app.app_context():
            for label in ('oldest', 'newer'):
                db.session.add(AcmeClientAccount(
                    directory_url=DUP_DIR, label=label, email='x@e.com',
                ))
            db.session.commit()
        from services.acme.acme_client_service import AcmeClientService
        with app.app_context():
            svc = AcmeClientService(directory_url=DUP_DIR)
            assert svc.account.label == 'oldest'
            db.session.rollback()


def _migration():
    return importlib.import_module('migrations.077_acme_client_account_dup_directory')


def _make_legacy_schema_sqlite(conn):
    """Recreate the pre-077 table shape: inline UNIQUE on directory_url."""
    conn.execute(
        """CREATE TABLE acme_client_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            directory_url VARCHAR(500) NOT NULL UNIQUE,
            label VARCHAR(100) NOT NULL,
            email VARCHAR(255) NOT NULL,
            account_url VARCHAR(500),
            account_key TEXT,
            account_key_algorithm VARCHAR(20) NOT NULL DEFAULT 'ES256',
            eab_kid VARCHAR(255),
            eab_hmac_key TEXT,
            is_default BOOLEAN NOT NULL DEFAULT 0,
            proxy_slug VARCHAR(63),
            proxy_enabled BOOLEAN NOT NULL DEFAULT 0,
            order_poll_timeout_sec INTEGER NOT NULL DEFAULT 180,
            order_poll_interval_sec INTEGER NOT NULL DEFAULT 3,
            http_timeout_sec INTEGER NOT NULL DEFAULT 60,
            preferred_chain VARCHAR(255),
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute(
        "INSERT INTO acme_client_accounts (directory_url, label, email) VALUES (?, ?, ?)",
        (DUP_DIR, 'legacy', 'op@e.com'),
    )
    conn.commit()


class TestMigration077SQLite:
    def test_drops_unique_and_preserves_rows(self):
        conn = sqlite3.connect(':memory:')
        _make_legacy_schema_sqlite(conn)
        migration = _migration()
        migration.upgrade(conn)

        schema = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='acme_client_accounts'"
        ).fetchone()[0]
        compiled = ' '.join(line.strip().rstrip(',') for line in schema.splitlines())
        assert 'directory_url VARCHAR(500) NOT NULL UNIQUE' not in compiled

        # Pre-existing row survived the rebuild
        rows = conn.execute(
            'SELECT directory_url, label FROM acme_client_accounts'
        ).fetchall()
        assert rows == [(DUP_DIR, 'legacy')]

        # Plain index exists and duplicate insert now succeeds
        idx = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name='idx_acme_client_accounts_directory_url'"
        ).fetchone()
        assert idx is not None
        conn.execute(
            "INSERT INTO acme_client_accounts (directory_url, label, email) "
            "VALUES (?, ?, ?)",
            (DUP_DIR, 'second', 'b@e.com'),
        )
        conn.commit()
        assert conn.execute(
            'SELECT COUNT(*) FROM acme_client_accounts WHERE directory_url = ?',
            (DUP_DIR,),
        ).fetchone()[0] == 2

    def test_idempotent(self):
        conn = sqlite3.connect(':memory:')
        _make_legacy_schema_sqlite(conn)
        migration = _migration()
        migration.upgrade(conn)
        migration.upgrade(conn)  # second run must not error or re-rebuild
        count = conn.execute('SELECT COUNT(*) FROM acme_client_accounts').fetchone()[0]
        assert count == 1

    def test_noop_when_table_missing(self):
        conn = sqlite3.connect(':memory:')
        _migration().upgrade(conn)  # no table, no error


class _FakeInspector:
    def __init__(self, tables=('acme_client_accounts',),
                 uniques=('acme_client_accounts_directory_url_key',)):
        self._tables = list(tables)
        self._uniques = list(uniques)

    def get_table_names(self):
        return self._tables

    def get_unique_constraints(self, table):
        return [{'name': n} for n in self._uniques]


class _RecordingConn:
    """Fake SQLAlchemy Connection capturing executed statements."""
    def __init__(self):
        self.execute_sql = []

    def execute(self, clause, *args, **kwargs):
        self.execute_sql.append(str(clause))


class TestMigration077Pg:
    def _run(self, monkeypatch, tables, uniques):
        import sqlalchemy
        import importlib
        migration = _migration()
        insp = _FakeInspector(tables=tables, uniques=uniques)
        monkeypatch.setattr(sqlalchemy, 'inspect', lambda *a, **k: insp)
        # _upgrade_pg does `from sqlalchemy import inspect` BEFORE exec, so patch
        # sqlalchemy.inspect is sufficient.
        conn = _RecordingConn()
        migration._upgrade_pg(conn)
        return conn

    def test_drops_unique_constraint_and_creates_index(self, monkeypatch):
        conn = self._run(
            monkeypatch,
            tables=['acme_client_accounts'],
            uniques=['acme_client_accounts_directory_url_key'],
        )
        sql = '\n'.join(conn.execute_sql)
        assert 'DROP CONSTRAINT IF EXISTS acme_client_accounts_directory_url_key' in sql
        assert 'CREATE INDEX IF NOT EXISTS idx_acme_client_accounts_directory_url' in sql

    def test_idempotent(self, monkeypatch):
        conn = self._run(
            monkeypatch, tables=['acme_client_accounts'], uniques=[]
        )
        sql = '\n'.join(conn.execute_sql)
        assert 'DROP CONSTRAINT' not in sql
        assert 'CREATE INDEX IF NOT EXISTS idx_acme_client_accounts_directory_url' in sql

    def test_pg_noop_when_table_missing(self, monkeypatch):
        conn = self._run(monkeypatch, tables=[], uniques=[])
        assert conn.execute_sql == []

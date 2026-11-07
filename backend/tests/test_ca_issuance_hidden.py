"""A CA can be kept out of the manual issuance pickers (#430): a flag the UI
reads, listed by default, set through the CA update and carried by backups."""
import importlib
import json
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text

from models import AuditLog, CA, db

from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

PG_URL = os.getenv('UCM_TEST_PG_URL')


def _patch(auth_client, ca_id, **body):
    return auth_client.patch(f'/api/v2/cas/{ca_id}', data=json.dumps(body), content_type='application/json')


def test_a_new_ca_is_listed(create_ca):
    assert create_ca(cn='Issuance listed CA')['issuance_hidden'] is False


@pytest.mark.parametrize('field', ['issuanceHidden', 'issuance_hidden'])
def test_the_flag_is_set_and_cleared(app, auth_client, create_ca, field):
    ca = create_ca(cn=f'Issuance hidden CA {field}')
    r = _patch(auth_client, ca['id'], **{field: True})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['data']['issuance_hidden'] is True
    assert auth_client.get(f"/api/v2/cas/{ca['id']}").get_json()['data']['issuance_hidden'] is True
    r = _patch(auth_client, ca['id'], **{field: False})
    assert r.get_json()['data']['issuance_hidden'] is False


@pytest.mark.parametrize('value', ['true', 1, None, 'yes'])
def test_only_a_boolean_is_accepted(app, auth_client, create_ca, value):
    ca = create_ca(cn=f'Issuance strict CA {value!r}')
    r = _patch(auth_client, ca['id'], issuanceHidden=value)
    assert r.status_code == 400
    assert r.get_json()['message'] == 'issuanceHidden must be true or false'
    with app.app_context():
        assert db.session.get(CA, ca['id']).issuance_hidden is False


def test_the_change_is_audited(app, auth_client, create_ca):
    ca = create_ca(cn='Issuance audited CA')
    assert _patch(auth_client, ca['id'], issuanceHidden=True).status_code == 200
    with app.app_context():
        details = [a.details for a in AuditLog.query.filter_by(action='ca_updated', resource_id=str(ca['id']))]
    assert 'CA Issuance audited CA updated: hidden from issuance pickers' in details, details


def test_backups_export_the_flag(app, auth_client, create_ca):
    """The generic column restore brings it back (test_backup_manifest covers the columns)."""
    from services.backup.backup_service import BackupService
    ca = create_ca(cn='Issuance backup CA')
    _patch(auth_client, ca['id'], issuanceHidden=True)
    with app.app_context():
        exported = next(r for r in BackupService()._export_cas(True) if r['refid'] == ca['refid'])
    assert exported['issuance_hidden'] is True


def test_sqlite_migration_lists_existing_cas():
    m = importlib.import_module('migrations.118_ca_issuance_hidden')
    conn = sqlite3.connect(':memory:')
    conn.execute(f"CREATE TABLE {CA.__tablename__} (id INTEGER PRIMARY KEY, descr TEXT)")
    conn.execute(f"INSERT INTO {CA.__tablename__} VALUES (1, 'old')")
    m.upgrade(conn)
    m.upgrade(conn)
    assert conn.execute(f"SELECT issuance_hidden FROM {CA.__tablename__}").fetchone()[0] == 0
    m.upgrade(sqlite3.connect(':memory:'))  # no table: a no-op


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_migration_lists_existing_cas():
    m = importlib.import_module('migrations.118_ca_issuance_hidden')
    schema = f"migtest_118_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        table = CA.__tablename__
        conn.execute(text(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, descr TEXT)"))
        conn.execute(text(f"INSERT INTO {table} VALUES (1, 'old')"))
        m.upgrade(conn)
        m.upgrade(conn)
        assert conn.execute(text(f"SELECT issuance_hidden FROM {table}")).scalar() is False
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()

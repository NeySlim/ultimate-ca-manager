"""Migration 114 creates ca_cross_certificates and deploy_bindings.chain_variant, idempotently."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

PG_URL = os.getenv('UCM_TEST_PG_URL')


def _migration():
    return importlib.import_module('migrations.114_ca_cross_certificates')


def test_sqlite_creates_the_table_and_the_binding_column():
    conn = sqlite3.connect(':memory:')
    conn.execute("CREATE TABLE certificate_authorities (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE deploy_bindings (id INTEGER PRIMARY KEY, cert_path TEXT)")
    conn.execute("INSERT INTO deploy_bindings (cert_path) VALUES ('/a')")
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(ca_cross_certificates)")}
    assert {'ca_id', 'crt', 'fingerprint_sha256', 'issuer_caref', 'served', 'revoked'} <= columns
    assert conn.execute("SELECT cert_path, chain_variant FROM deploy_bindings").fetchall() == [('/a', 'auto')]
    conn.execute("INSERT INTO certificate_authorities (id) VALUES (1)")
    conn.execute("INSERT INTO ca_cross_certificates (ca_id, crt, fingerprint_sha256) VALUES (1, 'x', 'f')")
    assert conn.execute("SELECT served, revoked FROM ca_cross_certificates").fetchall() == [(0, 0)]
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO ca_cross_certificates (ca_id, crt, fingerprint_sha256) VALUES (1, 'y', 'f')")


def test_sqlite_without_bindings_still_creates_the_table():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert 'ca_cross_certificates' in names and 'deploy_bindings' not in names


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_creates_the_table_and_the_binding_column():
    schema = f"migtest_114_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text("CREATE TABLE certificate_authorities (id SERIAL PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE deploy_bindings (id SERIAL PRIMARY KEY, cert_path TEXT)"))
        conn.execute(text("INSERT INTO deploy_bindings (cert_path) VALUES ('/a')"))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        inspector = inspect(conn)
        columns = {c['name'] for c in inspector.get_columns('ca_cross_certificates', schema=schema)}
        assert {'ca_id', 'crt', 'fingerprint_sha256', 'issuer_caref', 'served', 'revoked'} <= columns
        assert conn.execute(text("SELECT cert_path, chain_variant FROM deploy_bindings")
                            ).fetchall() == [('/a', 'auto')]
        conn.execute(text("INSERT INTO certificate_authorities DEFAULT VALUES"))
        conn.execute(text("INSERT INTO ca_cross_certificates (ca_id, crt, fingerprint_sha256) "
                          "VALUES (1, 'x', 'f')"))
        assert conn.execute(text("SELECT served, revoked FROM ca_cross_certificates")
                            ).fetchall() == [(False, False)]
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


def test_a_binding_defaults_to_the_served_chain(app):
    from models import Certificate, db
    from models.deploy import DeployBinding, DeployTarget
    with app.app_context():
        target = DeployTarget(name=f'm114-{os.urandom(3).hex()}', host='h', username='u', private_key='k')
        cert = Certificate(refid=os.urandom(8).hex(), descr='m114')
        db.session.add_all([target, cert])
        db.session.flush()
        binding = DeployBinding(target_id=target.id, certificate_id=cert.id)
        db.session.add(binding)
        db.session.flush()
        assert binding.chain_variant == 'auto' and binding.to_dict()['chain_variant'] == 'auto'
        db.session.rollback()

"""Migration 300: a 2.254 database upgraded by the runner has the schema of a fresh 3.0
install, on SQLite and PostgreSQL; its data steps transform a populated 2.254 database; it
replays after an interruption; the runner refuses, untouched, any other existing database."""
import base64
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from tests.upgrade_2254_support import (BACKENDS, differences, fresh_metadata, make_base, schema_2254,
                                        snapshot)

# (dialect or None for both, kind, table, name or '*'): why an upgraded 2.254 database may differ
# from a fresh 3.0 install there. Any other difference fails; an entry nothing matches fails too.
TOLERATED = {
    ('sqlite', 'column type', '*', '*'):
        "TIMESTAMP written by a step where the model says DATETIME: one SQLite affinity, and "
        "SQLAlchemy reads and writes both through the model's DateTime",
    (None, 'column default', 'cluster_nodes', 'is_leader'):
        "server default FALSE written by step 141; the model always sets the value",
    (None, 'column default', 'windows_enrollment_profiles', 'is_default'):
        "server default FALSE written by step 155; the model always sets the value",
    (None, 'column default', 'windows_enrollment_profiles', 'enabled'):
        "server default TRUE written by step 155; the model always sets the value",
    (None, 'column default', 'windows_enrollment_profiles', 'validity_days'):
        "server default 365 written by step 155; the model always sets the value",
    ('sqlite', 'column nullable', 'ad_connector_config', 'name'):
        "SQLite cannot add NOT NULL to an existing table; step 155 names every row and the "
        "model always writes a name",
    (None, 'unique', 'ad_connector_config', 'name'):
        "uniqueness of the name enforced by the unique index uq_ad_connector_config_name "
        "(step 155) where create_all writes a UNIQUE constraint: the same rule",
    (None, 'index', 'ad_connector_config', 'uq_ad_connector_config_name'):
        "the unique index that carries the rule above",
    ('postgresql', 'index', 'ad_connector_config', 'ad_connector_config_name_key'):
        "the index behind the UNIQUE constraint of a fresh install, the rule above",
    ('postgresql', 'column default', '_migrations', 'applied_at'):
        "the registry table was created by 2.254; every 3.0 write passes applied_at in UTC",
    ('postgresql', '*', 'flask_sessions', '*'):
        "created by step 138 on an upgraded database, by Flask-Session at the first start of "
        "a fresh one (create_all knows nothing of it)",
}


_ASPECTS = ('column type', 'column nullable', 'column default')


def _classified(diffs):
    """(kind, table, name, upgraded, fresh), a column split into the aspects that differ."""
    for kind, table, name, upgraded, fresh in diffs:
        if kind == 'column' and upgraded is not None and fresh is not None:
            for label, u, f in zip(_ASPECTS, upgraded, fresh):
                if u != f:
                    yield label, table, name, u, f
        else:
            yield kind, table, name, upgraded, fresh


def _tolerated(dialect, diff):
    kind, table, name = diff[:3]
    for d in (dialect, None):
        for key in ((d, kind, table, name), (d, kind, table, '*'), (d, kind, '*', '*'), (d, '*', table, '*')):
            if key in TOLERATED:
                return key
    return None


@pytest.fixture(params=BACKENDS)
def dialect(request):
    return request.param


@pytest.fixture
def base(dialect, tmp_path, monkeypatch):
    yield from make_base(dialect, tmp_path, monkeypatch, 'b')


@pytest.fixture
def fresh(dialect, tmp_path, monkeypatch):
    for db in make_base(dialect, tmp_path, monkeypatch, 'f', sql=''):
        fresh_metadata().create_all(db.engine)
        db.mark_all_applied()
        yield db


# --- Schema equivalence -----------------------------------------------------------------------

def test_an_upgraded_2254_database_has_the_schema_of_a_fresh_install(base, fresh):
    assert base.upgrade()
    diffs = list(_classified(differences(snapshot(base.engine), snapshot(fresh.engine))))
    unexplained = [d for d in diffs if _tolerated(base.dialect, d) is None]
    assert unexplained == [], 'differences no entry of TOLERATED explains:\n' + '\n'.join(map(repr, unexplained))
    used = {_tolerated(base.dialect, d) for d in diffs}
    unused = [k for k in TOLERATED if k[0] in (None, base.dialect) and k not in used]
    assert unused == [], f'TOLERATED entries no difference uses any more: {unused}'


def _filler(column, n):
    """Row n's value for a required column: distinct per row, so unique columns accept it."""
    from sqlalchemy import Boolean, DateTime, Integer
    if isinstance(column.type, Boolean):
        return False
    if isinstance(column.type, Integer):
        return n
    if isinstance(column.type, DateTime):
        return datetime(2026, 1, 1)
    return f'{column.name}{n}'


@pytest.mark.parametrize('table', ['windows_enrollment_profiles', 'windows_profile_templates',
                                   'acme_proxy_challenge_links', 'users', 'websocket_relay'])
def test_a_fresh_sqlite_install_never_hands_a_deleted_id_out_again(table, tmp_path, monkeypatch):
    """The same AUTOINCREMENT as the upgrade creates: a deleted last row keeps its id."""
    for db in make_base('sqlite', tmp_path, monkeypatch, 'ai', sql=''):
        model = fresh_metadata().tables[table]
        model.metadata.create_all(db.engine, tables=[model])
        required = [c for c in model.columns if not c.primary_key and not c.nullable]
        with db.engine.begin() as conn:
            def add(n):
                values = {c.name: _filler(c, n) for c in required}
                return conn.execute(model.insert().values(**values)).inserted_primary_key[0]
            add(1)
            last = add(2)
            conn.execute(model.delete().where(model.c.id == last))
            assert add(3) > last


def test_the_registry_of_both_ends_names_the_upgrade(base, fresh):
    assert base.upgrade()
    assert '300_upgrade_from_2_254' in base.registry()
    assert fresh.registry() == ['300_upgrade_from_2_254']


# --- Data steps on a populated 2.254 database ---------------------------------------------------

def _key():
    return ec.generate_private_key(ec.SECP256R1())


def _cert(serial, cn, issuer_key=None, ca=False):
    key = _key()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.now(timezone.utc)
    builder = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
               .public_key(key.public_key()).serial_number(serial)
               .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30)))
    if ca:
        builder = builder.add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
    cert = builder.sign(issuer_key or key, hashes.SHA256())
    return cert, base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode()


SETTINGS_2X = {'wstep_enabled': 'true', 'wstep_ca_refid': 'ca-a', 'wstep_username': 'ces-user',
               'wstep_password': 'pbkdf2:sha256:600000$salt$ces', 'wstep_validity_days': '30',
               'kerberos_spn': 'HTTP/ucm.corp.example'}


_MATERIAL = {}


def _material():
    """The certificates, made once: every database populated holds the same bytes."""
    if not _MATERIAL:
        _MATERIAL.update(ca=_cert(1, 'CA A', ca=True), hex=_cert(0xA1B2, 'hex.example'),
                         ambiguous=_cert(16, 'ambiguous.example'), twin=_cert(255, 'twin.example'))
    return _MATERIAL


def populate(db):
    """Rows each data step of migration 300 rewrites; returns what the checks need."""
    material = _material()
    ca_crt = material['ca'][1]
    for refid in ('ca-a', 'ca-b'):
        db.run("INSERT INTO certificate_authorities (refid, descr, crt, signature_scheme, issuance_hidden) "
               "VALUES (:r, :r, :c, 'pkcs1v15', FALSE)", {'r': refid, 'c': ca_crt})
    (hex_cert, hex_crt), (ambiguous_cert, ambiguous_crt), (twin, twin_crt) = (
        material['hex'], material['ambiguous'], material['twin'])
    rows = [(1, 'ca-a', 'A1B2', hex_crt, 'wstep'), (2, 'ca-a', '10', ambiguous_crt, None),
            (3, 'ca-b', '255', twin_crt, None), (4, 'ca-b', 'FF', twin_crt, None)]
    for row_id, caref, serial, crt, source in rows:
        db.run("INSERT INTO certificates (id, refid, descr, caref, serial_number, crt, source, renewed_times) "
               "VALUES (:i, :r, :r, :ca, :s, :c, :src, 0)",
               {'i': row_id, 'r': f'cert-{row_id}', 'ca': caref, 's': serial, 'c': crt, 'src': source})
    db.run("INSERT INTO revoked_serials (caref, serial_number, revoked_at, valid_to, created_at, certificate_id) "
           "VALUES ('ca-a', 'A1B2', '2026-01-02 03:04:05', '2026-01-02 03:04:05', '2026-01-02 03:04:05', 1)")
    db.run("INSERT INTO acme_client_orders (id, domains, challenge_type, environment, key_source, status, "
           "created_at) VALUES (1, '[]', 'dns-01', 'production', 'generated', 'valid', '2026-01-02 03:04:05')")
    for user_id in (1, 3):
        db.run("INSERT INTO users (id, username, email, password_hash, role, auth_source) "
               "VALUES (:i, :u, :e, 'x', 'viewer', 'local')",
               {'i': user_id, 'u': f'u{user_id}', 'e': f'u{user_id}@example.test'})
    # A deleted account (7) still named by the audit log: its id must never come back
    db.run("INSERT INTO audit_logs (id, action, resource_type, resource_id, timestamp) "
           "VALUES (1, 'user_deleted', 'user', '7', '2026-01-02 03:04:05')")
    for key, value in SETTINGS_2X.items():
        db.run("INSERT INTO system_config (key, value) VALUES (:k, :v)", {'k': key, 'v': value})
    return {'hex': hex_cert, 'ambiguous': ambiguous_cert, 'twin': twin}


@pytest.fixture
def upgraded(base):
    certs = populate(base)
    assert base.upgrade()
    return base, certs


def _cert_row(db, row_id, columns):
    return db.run(f"SELECT {columns} FROM certificates WHERE id = :i", {'i': row_id})[0]


def test_step_139_fills_key_size_and_signature_hash(upgraded):
    db, _ = upgraded
    for row_id in (1, 2, 3, 4):
        assert _cert_row(db, row_id, 'key_bits, sig_hash') == (256, 'sha256')


def test_steps_142_and_144_store_serials_in_decimal_and_keep_twins_pending(upgraded):
    db, certs = upgraded
    assert _cert_row(db, 1, 'serial_number') == (str(0xA1B2),)
    assert _cert_row(db, 2, 'serial_number') == ('16',)
    # Two rows of ca-b hold serial 255: both are left as stored and listed
    assert {_cert_row(db, i, 'serial_number')[0] for i in (3, 4)} == {'255', 'FF'}
    assert db.run("SELECT serial_number FROM revoked_serials WHERE certificate_id = 1") == [(str(0xA1B2),)]
    (value,), = db.run("SELECT value FROM system_config WHERE key = 'serial_unique_index_pending'")
    pending = json.loads(value)['duplicates']
    assert [(d['caref'], sorted(r['id'] for r in d['rows'])) for d in pending] == [('ca-b', [3, 4])]
    assert 'uix_certificates_ca_serial' in snapshot_index_names(db)


def snapshot_index_names(db):
    return {k[2] for k in snapshot(db.engine) if k[0] == 'index'}


def test_a_start_after_the_twins_are_resolved_runs_step_144_alone(base):
    """The documented cleanup is a restart: 144 runs again, no other step, the 300 row stays."""
    populate(base)
    twin_crt = _material()['twin'][1]
    # A third row spelled '255' too: 142 finds a raw duplicate and creates no index
    base.run("INSERT INTO certificates (id, refid, descr, caref, serial_number, crt, renewed_times) "
             "VALUES (5, 'cert-5', 'cert-5', 'ca-b', '255', :c, 0)", {'c': twin_crt})
    assert base.upgrade()
    assert 'uix_certificates_ca_serial' not in snapshot_index_names(base)
    # The admin swaps the default profile for a non-default one and keeps the live key
    # kerberos_spn: a replay of step 155 would make a default profile again
    base.run("UPDATE certificates SET windows_profile_id = NULL")
    base.run("DELETE FROM windows_enrollment_profiles")
    base.run("INSERT INTO windows_enrollment_profiles (name, realm, is_default, enabled, validity_days, "
             "policy_id, policy_oid_root, created_at) VALUES ('corp', 'CORP.EXAMPLE', FALSE, TRUE, 365, "
             "'00000000-0000-4000-8000-000000000001', '1.3.6.1.4.1.311.21.8.1.2.3.4', '2026-01-02 03:04:05')")
    base.run("INSERT INTO system_config (key, value) VALUES ('kerberos_spn', 'HTTP/ucm.corp.example') "
             "ON CONFLICT (key) DO NOTHING")
    profiles = base.run("SELECT id, name, is_default FROM windows_enrollment_profiles ORDER BY id")
    stamp = base.run("SELECT applied_at FROM _migrations WHERE name = '300_upgrade_from_2_254'")
    base.run("DELETE FROM certificates WHERE id IN (3, 5)")
    assert base.upgrade()
    assert _cert_row(base, 4, 'serial_number') == ('255',)
    assert base.run("SELECT key FROM system_config WHERE key = 'serial_unique_index_pending'") == []
    assert 'uix_certificates_ca_serial' in snapshot_index_names(base)
    assert base.run("SELECT id, name, is_default FROM windows_enrollment_profiles ORDER BY id") == profiles
    assert base.run("SELECT applied_at FROM _migrations WHERE name = '300_upgrade_from_2_254'") == stamp
    # Nothing pending any more: the next start runs nothing
    assert base.upgrade()


def test_a_replay_that_fails_leaves_the_key_for_the_next_start(base, monkeypatch):
    """The key is the only replay trigger: a failed replay must not have cleared it first."""
    import migrations._from_2_254 as package
    real = package.step
    populate(base)
    assert base.upgrade()
    base.run("DELETE FROM certificates WHERE id = 3")

    class _Broken:
        @staticmethod
        def upgrade(conn):
            raise RuntimeError('killed during the PEM scan')

    monkeypatch.setattr(package, 'step',
                        lambda name: _Broken if name == '144_canonical_certificate_serials' else real(name))
    assert base.upgrade() is False
    assert base.run("SELECT key FROM system_config WHERE key = 'serial_unique_index_pending'") != []
    monkeypatch.setattr(package, 'step', real)
    assert base.upgrade()
    assert _cert_row(base, 4, 'serial_number') == ('255',)
    assert base.run("SELECT key FROM system_config WHERE key = 'serial_unique_index_pending'") == []


def test_a_replay_killed_after_the_sqlite_index_commits_ends_at_the_next_start(tmp_path, monkeypatch, capsys):
    """SQLite runs CREATE INDEX outside a transaction when no row changed: a process killed before
    the step's commit leaves the index and the key; the next start replays and clears the key."""
    import sqlite3
    from migrations._from_2_254 import step
    key = "SELECT key FROM system_config WHERE key = 'serial_unique_index_pending'"
    for db in make_base('sqlite', tmp_path, monkeypatch, 'kw'):
        populate(db)
        db.run("INSERT INTO certificates (id, refid, descr, caref, serial_number, crt, renewed_times) "
               "VALUES (5, 'cert-5', 'cert-5', 'ca-b', '255', :c, 0)", {'c': _material()['twin'][1]})
        assert db.upgrade()
        assert 'uix_certificates_ca_serial' not in snapshot_index_names(db)
        # Row 3 already holds '255': the replay converts nothing, so no transaction precedes the index
        db.run("DELETE FROM certificates WHERE id IN (4, 5)")

        class _KilledBeforeCommit(sqlite3.Connection):
            def commit(self):
                raise _Cut()

        conn = sqlite3.connect(db.sqlite_path, factory=_KilledBeforeCommit)
        with pytest.raises(_Cut):
            step('144_canonical_certificate_serials').upgrade(conn)
        conn.close()
        assert 'uix_certificates_ca_serial' in snapshot_index_names(db)
        assert db.run(key) != []
        assert db.upgrade()
        assert db.run(key) == []
        capsys.readouterr()
        assert db.upgrade()
        assert 'up to date' in capsys.readouterr().out


@pytest.mark.postgres
def test_a_replay_leaves_certificates_writable_when_the_index_exists(tmp_path, monkeypatch):
    """Another node writes a certificate while a replay holds its transaction open: a replay
    that finds the index takes no lock that blocks writers (lock_timeout 500 ms)."""
    from sqlalchemy import create_engine, text
    import migrations._from_2_254 as package
    real = package.step
    for db in make_base('postgresql', tmp_path, monkeypatch, 'lk'):
        populate(db)
        assert db.upgrade()
        assert 'uix_certificates_ca_serial' in snapshot_index_names(db)
        writes = []

        class _ThenWrite:
            @staticmethod
            def upgrade(conn):
                real('144_canonical_certificate_serials').upgrade(conn)
                other = create_engine(db.url, connect_args={'options': db.options + ' -clock_timeout=500'})
                try:
                    with other.connect() as c:
                        c.execute(text("INSERT INTO certificates (id, refid, descr, renewed_times) "
                                       "VALUES (1000, 'lk', 'lk', 0)"))
                        c.rollback()
                    writes.append('written')
                except Exception as exc:  # noqa: BLE001
                    writes.append(str(exc).splitlines()[0])
                finally:
                    other.dispose()

        monkeypatch.setattr(package, 'step', lambda name: _ThenWrite if name == '144_canonical_certificate_serials'
                            else real(name))
        assert db.upgrade()
        assert writes == ['written']


def test_dry_run_and_status_tell_that_a_start_replays_step_144(base, capsys):
    """While the key stands a real start rewrites rows: neither may report "up to date"."""
    populate(base)
    assert base.upgrade()
    capsys.readouterr()
    runner = base._route()
    before = _untouched(base)
    assert runner.run_all_migrations(dry_run=True) is True
    runner.show_status()
    out = capsys.readouterr().out
    assert _untouched(base) == before
    assert 'up to date' not in out
    assert out.count('step 144 runs again at each start') == 2, out


def test_the_cleanup_never_asks_to_edit_the_registry():
    from utils.serial_duplicates import CLEANUP
    assert '_migrations' not in CLEANUP and 'restart' in CLEANUP.lower()


def test_steps_146_and_148_leave_a_2254_order_without_replaced_certificates(upgraded):
    """2.254 has no replaced_certificates column: 146 adds it empty, 148 finds nothing to name."""
    db, _ = upgraded
    assert db.run("SELECT replaced_certificates FROM acme_client_orders WHERE id = 1") == [(None,)]


def test_step_150_never_hands_out_an_id_a_row_still_names(upgraded):
    db, _ = upgraded
    db.run("INSERT INTO users (username, email, password_hash, role) "
           "VALUES ('new', 'new@example.test', 'x', 'viewer')")
    assert db.run("SELECT id FROM users WHERE username = 'new'") == [(8,)]


def test_step_155_turns_the_2x_settings_into_the_default_profile(upgraded):
    db, _ = upgraded
    assert db.run("SELECT name, realm, issuing_ca_refid, validity_days, wstep_username FROM "
                  "windows_enrollment_profiles WHERE is_default") == [
        ('default', None, 'ca-a', 30, 'ces-user')]
    assert db.run("SELECT key FROM system_config WHERE key LIKE 'wstep_%' AND key <> 'wstep_enabled'") == []
    (profile_id,), = db.run("SELECT id FROM windows_enrollment_profiles WHERE is_default")
    assert _cert_row(db, 1, 'windows_profile_id') == (profile_id,)
    assert db.run("SELECT name FROM ad_connector_config") == []


def test_step_157_fills_the_subject_key(upgraded):
    from utils.dn_match import name_key
    db, certs = upgraded
    assert _cert_row(db, 1, 'subject_key') == (name_key(certs['hex'].subject),)


# --- Replay -----------------------------------------------------------------------------------

# Columns a second run writes again with the time of that run
_VOLATILE = {'_migrations': ('id', 'applied_at'), 'system_config': ('id', 'updated_at'),
             'windows_enrollment_profiles': ('created_at',)}


def _state(db):
    """Schema and every row, without the columns a run stamps with its own time."""
    from sqlalchemy import inspect
    rows = {}
    for table in sorted(inspect(db.engine).get_table_names()):
        if table == 'sqlite_sequence':
            continue
        columns = [c['name'] for c in inspect(db.engine).get_columns(table)
                   if c['name'] not in _VOLATILE.get(table, ())]
        quoted = ', '.join(f'"{c}"' for c in columns)
        rows[table] = sorted(map(repr, db.run(f'SELECT {quoted} FROM "{table}"')))
    if db.dialect == 'sqlite':
        rows['sqlite_sequence'] = sorted(map(repr, db.run(
            "SELECT name, seq FROM sqlite_sequence WHERE name <> 'system_config'")))
    else:
        rows['users_sequence'] = db.run("SELECT last_value FROM users_id_seq")
    return snapshot(db.engine), rows


def _interrupt_after(db, count):
    """The first *count* steps committed, then the start stops before the registry row."""
    from migrations._from_2_254 import STEPS, step
    if db.dialect == 'sqlite':
        conn = db.connection()
        try:
            for name in STEPS[:count]:
                step(name).upgrade(conn)
            conn.commit()
        finally:
            conn.close()
        return
    with db.connection() as conn:
        for name in STEPS[:count]:
            step(name).upgrade(conn)


def test_an_upgrade_interrupted_after_any_step_ends_in_the_same_state(dialect, tmp_path, monkeypatch):
    from migrations._from_2_254 import STEPS
    for reference in make_base(dialect, tmp_path, monkeypatch, 'ref'):
        populate(reference)
        assert reference.upgrade()
        expected = _state(reference)
    for count in range(1, len(STEPS) + 1):
        (tmp_path / str(count)).mkdir()
        for db in make_base(dialect, tmp_path / str(count), monkeypatch, f'r{count}'):
            populate(db)
            _interrupt_after(db, count)
            assert '300_upgrade_from_2_254' not in db.registry()
            assert db.upgrade(), STEPS[count - 1]
            schema, rows = _state(db)
            assert differences(schema, expected[0]) == [], f'interrupted after {STEPS[count - 1]}'
            changed = {t: (rows.get(t), expected[1].get(t)) for t in set(rows) | set(expected[1])
                       if rows.get(t) != expected[1].get(t)}
            assert changed == {}, f'interrupted after {STEPS[count - 1]}'


def test_a_start_cut_after_the_profiles_table_ends_with_the_2254_identity(dialect, tmp_path, monkeypatch):
    """SQLite commits the DDL of step 155 apart: a start cut there leaves the table empty; the next
    start makes the default profile with the identity 2.254 served, and a further start keeps it."""
    from migrations._from_2_254 import STEPS, step
    from utils.policy_identity import derived_oid_root, derived_policy_id
    for db in make_base(dialect, tmp_path, monkeypatch, 'cut155'):
        populate(db)
        _interrupt_after(db, STEPS.index('155_windows_enrollment_profiles'))
        ddl = step('155_windows_enrollment_profiles')
        with db.engine.begin() as conn:
            from sqlalchemy import text
            for sql in (ddl._SQLITE_DDL if dialect == 'sqlite' else ddl._PG_DDL) + ddl._INDEXES:
                conn.execute(text(sql))
        assert db.run("SELECT COUNT(*) FROM windows_enrollment_profiles") == [(0,)]
        assert db.upgrade()
        served = [(True, derived_policy_id('ca-a'), derived_oid_root('ca-a'))]
        query = "SELECT is_default, policy_id, policy_oid_root FROM windows_enrollment_profiles"
        assert db.run(query) == served
        db.run("DELETE FROM _migrations WHERE name = '300_upgrade_from_2_254'")
        assert db.upgrade()
        assert db.run(query) == served


# 2.x migration 035 created this index on the databases it upgraded, never on a fresh install
_INDEX_OF_2X = ("CREATE UNIQUE INDEX uq_ca_hsm_key_id ON certificate_authorities(hsm_key_id) "
                "WHERE hsm_key_id IS NOT NULL;\n")


def test_the_2254_fixture_has_no_x509_hsm_key_index(dialect):
    assert 'uq_ca_hsm_key_id' not in schema_2254(dialect)


def test_a_2254_database_with_the_index_of_2x_has_the_schema_of_a_fresh_install(dialect, tmp_path,
                                                                                  monkeypatch):
    for db in make_base(dialect, tmp_path, monkeypatch, 'i35', sql=schema_2254(dialect) + _INDEX_OF_2X):
        assert db.upgrade()
        upgraded = snapshot(db.engine)
    (tmp_path / 'fresh').mkdir()
    for db in make_base(dialect, tmp_path / 'fresh', monkeypatch, 'i35f', sql=''):
        fresh_metadata().create_all(db.engine)
        db.mark_all_applied()
        expected = snapshot(db.engine)
    index = [d for d in differences(upgraded, expected) if d[0] == 'index' and d[1] == 'certificate_authorities']
    assert index == []
    assert ('index', 'certificate_authorities', 'uq_ca_hsm_key_id') in upgraded


def _two_cas_on_one_key(db):
    db.run("INSERT INTO hsm_providers (id, name, type, config) VALUES (7, 'token', 'pkcs11', '{}')")
    db.run("INSERT INTO hsm_keys (id, provider_id, key_identifier, label, algorithm, key_type, purpose) "
           "VALUES (9, 7, 'k9', 'shared-key', 'EC-P256', 'asymmetric', 'signing')")
    for ca_id, descr in ((3, 'Root A'), (4, 'Root B')):
        db.run("INSERT INTO certificate_authorities (id, refid, descr, crt, signature_scheme, issuance_hidden, "
               "hsm_key_id) VALUES (:i, :r, :d, :c, 'pkcs1v15', FALSE, 9)",
               {'i': ca_id, 'r': f'ca-{ca_id}', 'd': descr, 'c': _material()['ca'][1]})


def test_two_x509_cas_on_one_hsm_key_stop_the_upgrade_untouched(dialect, tmp_path, monkeypatch, capsys):
    for db in make_base(dialect, tmp_path, monkeypatch, 'dup'):
        _two_cas_on_one_key(db)
        before = _untouched(db)
        assert db.upgrade() is False
        assert _untouched(db) == before
        out = capsys.readouterr().out
        assert ("HSM key 'shared-key' (#9) backs 2 X.509 CAs: 'Root A' (#3), 'Root B' (#4)" in out), out
        assert 'Nothing was changed: 2.254 still starts on this database' in out, out
        assert 'IntegrityError' not in out and 'UNIQUE constraint' not in out, out
        # Once one CA leaves the key, the same database upgrades
        db.run("UPDATE certificate_authorities SET hsm_key_id = NULL WHERE id = 4")
        assert db.upgrade() is True, capsys.readouterr().out


def _sso_provider(db, provider_id, name, provider_type):
    db.run("INSERT INTO pro_sso_providers (id, name, provider_type, saml_allow_idp_initiated, id_token_verify, "
           "ldap_start_tls, sync_role_on_login, enforce_2fa) VALUES (:i, :n, :t, FALSE, TRUE, FALSE, FALSE, FALSE)",
           {'i': provider_id, 'n': name, 't': provider_type})


def test_two_sso_providers_of_one_type_stop_the_upgrade_untouched(dialect, tmp_path, monkeypatch, capsys):
    for db in make_base(dialect, tmp_path, monkeypatch, 'sso2'):
        _sso_provider(db, 5, 'Corp', 'oauth2')
        _sso_provider(db, 6, 'Directory', 'ldap')
        _sso_provider(db, 8, 'Okta', 'oauth2')
        before = _untouched(db)
        assert db.upgrade() is False
        assert _untouched(db) == before
        out = capsys.readouterr().out
        assert "2 SSO providers of type oauth2: 'Corp' (#5), 'Okta' (#8)" in out, out
        assert 'Directory' not in out, out
        assert 'keep one provider of each type and delete the others' in out, out
        assert 'Nothing was changed: 2.254 still starts on this database' in out, out
        assert 'IntegrityError' not in out and 'UNIQUE constraint' not in out, out
        # Once one of them is deleted, the same database upgrades and holds the rule
        db.run("DELETE FROM pro_sso_providers WHERE id = 8")
        assert db.upgrade() is True, capsys.readouterr().out
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            _sso_provider(db, 9, 'Okta', 'oauth2')


def test_a_fresh_install_refuses_a_second_sso_provider_of_one_type(fresh):
    from sqlalchemy.exc import IntegrityError
    _sso_provider(fresh, 5, 'Corp', 'oauth2')
    with pytest.raises(IntegrityError):
        _sso_provider(fresh, 6, 'Okta', 'oauth2')
    _sso_provider(fresh, 7, 'Idp', 'saml')


def test_one_sso_provider_of_each_type_upgrades_unchanged(dialect, tmp_path, monkeypatch):
    for db in make_base(dialect, tmp_path, monkeypatch, 'sso1'):
        for provider_id, name, kind in ((5, 'Corp', 'oauth2'), (6, 'Directory', 'ldap'), (7, 'Idp', 'saml')):
            _sso_provider(db, provider_id, name, kind)
        assert db.upgrade() is True
        assert db.run("SELECT id, name, provider_type FROM pro_sso_providers ORDER BY id") == [
            (5, 'Corp', 'oauth2'), (6, 'Directory', 'ldap'), (7, 'Idp', 'saml')]


# --- Pivot guard ------------------------------------------------------------------------------

def _untouched(db):
    """What a refused start must leave as it found it."""
    state = (sorted(db.tables()), db.registry(), snapshot(db.engine))
    if db.dialect == 'sqlite':
        state += (hashlib.sha256(open(db.sqlite_path, 'rb').read()).hexdigest(),)
    return state


def test_a_2253_database_is_refused_and_left_untouched(dialect, tmp_path, monkeypatch, capsys):
    sql = schema_2254(dialect).replace("INSERT INTO _migrations (name) VALUES ('136_lifted_hold_leftovers');\n", '')
    for db in make_base(dialect, tmp_path, monkeypatch, 'g53', sql=sql):
        before = _untouched(db)
        assert db.upgrade() is False
        assert _untouched(db) == before
    out = capsys.readouterr().out
    assert 'last started by a release older than 2.254' in out
    assert 'Install 2.254, start it once, then upgrade' in out
    assert '1 migration(s) of 2.254 are missing' in out and '136_lifted_hold_leftovers' in out


def test_the_refusal_names_the_count_and_the_first_three(dialect, tmp_path, monkeypatch, capsys):
    sql = schema_2254(dialect)
    for name in ('120_certificates_lookup_indexes', '130_auth_certificate_serial_per_issuer',
                 '135_user_totp_step_session_version', '137_ldap_start_tls'):
        sql = sql.replace(f"INSERT INTO _migrations (name) VALUES ('{name}');\n", '')
    for db in make_base(dialect, tmp_path, monkeypatch, 'g4', sql=sql):
        assert db.upgrade() is False
    out = capsys.readouterr().out
    assert ('4 migration(s) of 2.254 are missing from its registry, first 120_certificates_lookup_indexes, '
            '130_auth_certificate_serial_per_issuer, 135_user_totp_step_session_version)') in out
    assert '137_ldap_start_tls' not in out


UNKNOWN = "INSERT INTO _migrations (name) VALUES ('301_from_a_later_release');\n"


def _refused_as_unknown(db, capsys):
    before = _untouched(db)
    assert db.upgrade() is False
    assert _untouched(db) == before
    out = capsys.readouterr().out
    assert 'names 1 migration(s) this release does not know, first 301_from_a_later_release' in out, out
    assert 'older than 2.254' not in out


def test_a_2254_database_naming_an_unknown_migration_is_refused_untouched(dialect, tmp_path, monkeypatch,
                                                                          capsys):
    for db in make_base(dialect, tmp_path, monkeypatch, 'gu', sql=schema_2254(dialect) + UNKNOWN):
        _refused_as_unknown(db, capsys)


def test_a_3_0_database_naming_an_unknown_migration_is_refused_untouched(fresh, capsys):
    """Going back from a later 3.x: its migrations are unknown here."""
    fresh.run(UNKNOWN.rstrip(';\n'))
    _refused_as_unknown(fresh, capsys)


def test_a_2254_database_still_naming_2_0_migrations_upgrades(dialect, tmp_path, monkeypatch):
    """2.52 folded 001 to 042 of the 2.0 series into its baseline, which kept their names, and
    the 2.x upgrade from 1.8 recorded its own: a 2.254 database started that long ago still holds them."""
    old = ''.join(f"INSERT INTO _migrations (name) VALUES ('{n}');\n"
                  for n in ('001_add_api_keys', '042_add_discovery_san_sni', 'v1_to_v2_migration'))
    for db in make_base(dialect, tmp_path, monkeypatch, 'go', sql=schema_2254(dialect) + old):
        assert db.upgrade() is True
        assert '300_upgrade_from_2_254' in db.registry()


def test_a_database_without_registry_is_refused_and_left_untouched(dialect, tmp_path, monkeypatch, capsys):
    sql = '\n'.join(line for line in schema_2254(dialect).splitlines() if '_migrations' not in line)
    for db in make_base(dialect, tmp_path, monkeypatch, 'gl', sql=sql):
        before = _untouched(db)
        assert db.upgrade() is False
        assert _untouched(db) == before
        assert db.registry() is None
    assert 'it has no migration registry' in capsys.readouterr().out


def test_an_empty_database_is_a_fresh_install(dialect, tmp_path, monkeypatch):
    for db in make_base(dialect, tmp_path, monkeypatch, 'ge', sql=''):
        assert db.upgrade() is True
        assert db.tables() == set()


class _Cut(Exception):
    """A fresh install's start stopping where the test says."""


def test_a_fresh_install_cut_after_its_tables_is_never_taken_for_an_old_database(dialect, tmp_path,
                                                                                 monkeypatch, capsys):
    """Tables without a registry would be refused as older than 2.254: the registry comes first."""
    import migration_runner
    for db in make_base(dialect, tmp_path, monkeypatch, 'fc', sql=''):
        db._route()

        def create_all():
            fresh_metadata().create_all(db.engine)
            raise _Cut()
        with pytest.raises(_Cut):
            migration_runner.build_fresh_schema(create_all)
        assert db.upgrade() is True, capsys.readouterr().out
        migration_runner.build_fresh_schema(lambda: fresh_metadata().create_all(db.engine))
        assert db.registry() == ['300_upgrade_from_2_254']
        assert db.upgrade() is True


def test_a_3_0_registry_without_tables_is_accepted_and_completed(dialect, tmp_path, monkeypatch, capsys):
    """A fresh install cut between its registry and its tables: the next start accepts it and
    create_all builds the tables."""
    import migration_runner
    for db in make_base(dialect, tmp_path, monkeypatch, 'fb', sql=''):
        db.mark_all_applied()
        assert db.tables() == {'_migrations'}
        assert db.upgrade() is True, capsys.readouterr().out
        migration_runner.build_fresh_schema(lambda: fresh_metadata().create_all(db.engine))
        assert db.registry() == ['300_upgrade_from_2_254']
        assert {'users', 'certificate_authorities'} <= db.tables()
        assert db.upgrade() is True


def test_a_fresh_install_that_cannot_record_its_registry_stops_then_starts_fresh(dialect, tmp_path,
                                                                                  monkeypatch, capsys):
    """Cut once `_migrations` exists but before its row: an empty registry without a business
    table is a fresh database, which the next start builds."""
    import migration_runner
    real = migration_runner._mark_applied
    for db in make_base(dialect, tmp_path, monkeypatch, 'fr', sql=''):
        db._route()
        monkeypatch.setattr(migration_runner, '_mark_applied', lambda *a, **k: (_ for _ in ()).throw(_Cut()))
        with pytest.raises(_Cut):
            migration_runner.build_fresh_schema(lambda: fresh_metadata().create_all(db.engine))
        assert 'users' not in db.tables()
        assert db.registry() == []
        monkeypatch.setattr(migration_runner, '_mark_applied', real)
        assert db.upgrade() is True, capsys.readouterr().out
        migration_runner.build_fresh_schema(lambda: fresh_metadata().create_all(db.engine))
        assert db.registry() == ['300_upgrade_from_2_254']
        assert {'users', 'certificate_authorities'} <= db.tables()
        assert db.upgrade() is True


def test_a_3_0_database_starts_without_running_anything(fresh, capsys):
    before = _untouched(fresh)
    assert fresh.upgrade() is True
    assert _untouched(fresh) == before
    assert 'up to date' in capsys.readouterr().out


def test_a_database_reset_keeps_its_3_0_registry_and_starts(fresh, capsys):
    """The reset route drops and recreates the model tables: `_migrations` is not one of them."""
    before = fresh.registry()
    fresh_metadata().drop_all(fresh.engine)
    fresh_metadata().create_all(fresh.engine)
    assert fresh.registry() == before == ['300_upgrade_from_2_254']
    assert fresh.upgrade() is True, capsys.readouterr().out


def test_a_2254_database_starts_once_then_is_up_to_date(base, capsys):
    assert base.upgrade() is True
    capsys.readouterr()
    assert base.upgrade() is True
    assert 'up to date' in capsys.readouterr().out


def test_a_failed_step_leaves_the_upgrade_unrecorded(base, monkeypatch, capsys):
    """An error that reads like "already exists" is a failure too: the start stops, 300 stays pending."""
    import migrations._from_2_254 as package
    real = package.step

    class _Broken:
        @staticmethod
        def upgrade(conn):
            raise RuntimeError('table cluster_commands already exists')

    monkeypatch.setattr(package, 'step', lambda name: _Broken if name == '143_cluster_commands' else real(name))
    assert base.upgrade() is False
    assert '300_upgrade_from_2_254' not in base.registry()
    assert 'upgrade step 143_cluster_commands failed' in capsys.readouterr().out
    monkeypatch.setattr(package, 'step', real)
    assert base.upgrade() is True
    assert '300_upgrade_from_2_254' in base.registry()


def _canonical_since(db, recorded_at, monkeypatch):
    """utils.serial_format.recorded_before_canonical, its query run on *db*."""
    import types
    from sqlalchemy.orm import Session
    import models
    from utils.serial_format import recorded_before_canonical
    with Session(db.engine) as session:
        monkeypatch.setattr(models, 'db', types.SimpleNamespace(session=session))
        return recorded_before_canonical(recorded_at)


def test_the_hex_reading_ends_when_the_upgrade_or_the_fresh_install_ran(dialect, tmp_path, monkeypatch):
    """A serial recorded before the 300 row may still read as hex, one recorded after may not,
    on an upgraded database and on a fresh install alike."""
    from datetime import datetime, timedelta, timezone

    def now():
        return datetime.now(timezone.utc).replace(tzinfo=None)
    for label, sql in (('du', None), ('df', '')):
        for db in make_base(dialect, tmp_path, monkeypatch, label, sql=sql):
            before = now().replace(microsecond=0)
            assert db.upgrade() if sql is None else db.mark_all_applied() is None
            after = now() + timedelta(seconds=1)
            (applied,), = db.run("SELECT applied_at FROM _migrations WHERE name = '300_upgrade_from_2_254'")
            applied = applied if isinstance(applied, datetime) else datetime.fromisoformat(str(applied))
            assert before <= applied <= after, (label, before, applied, after)
            assert _canonical_since(db, before - timedelta(seconds=2), monkeypatch) is True
            assert _canonical_since(db, after + timedelta(seconds=2), monkeypatch) is False


# --- What the journal shows during a long upgrade ---------------------------------------------

def test_each_step_logs_its_start_and_its_end_with_the_duration(base, capsys):
    from migrations._from_2_254 import STEPS
    assert base.upgrade() is True
    lines = capsys.readouterr().out.splitlines()
    for name in [*STEPS, '300_upgrade_from_2_254']:
        started = [i for i, line in enumerate(lines) if line.strip().endswith(f'{name}: started')]
        done = [i for i, line in enumerate(lines) if re.search(rf'{name}: done in \d+\.\d s$', line)]
        assert len(started) == 1 and len(done) == 1 and started[0] < done[0], (name, lines)


class _Clock:
    def __init__(self, step):
        self.now, self.step = 0.0, step

    def __call__(self):
        self.now += self.step
        return self.now


def test_progress_is_logged_at_most_every_30_seconds(monkeypatch, capsys):
    import migrations._from_2_254 as package
    clock = _Clock(10)
    monkeypatch.setattr(package, '_clock', clock)
    tick = package.Progress('step 999_example', 7)
    for done in range(1, 8):
        tick(done)
    out = capsys.readouterr().out.splitlines()
    # Started at 10 s, called at 20 s to 80 s: lines at 40 s (3 of 7) and 70 s (6 of 7) only
    assert out == ['    step 999_example: 3 of 7 rows', '    step 999_example: 6 of 7 rows']

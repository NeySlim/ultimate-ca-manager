"""Upgrade step 168: a non-zero SSH certificate serial is held once under its CA; the pairs a 2.254
database already holds keep their number, are marked, listed once at the next start, and the
counter of every CA moves past the serials it holds."""
import importlib
import json

import pytest
from sqlalchemy.exc import IntegrityError

from models.ssh import SSHCertificate, SSHCertificateAuthority
from tests.upgrade_2254_support import BACKENDS, make_base
from utils.ssh_serials import FLAG, INDEX, MARKED_ACTION, MARKED_KEY

STEP = '168_ssh_certificate_serial_unique'
CAS = SSHCertificateAuthority.__tablename__
CERTS = SSHCertificate.__tablename__


def test_the_step_follows_the_sso_identities_step():
    from migrations._from_2_254 import STEPS
    assert STEPS.index(STEP) == STEPS.index('167_user_sso_identities') + 1 == len(STEPS) - 1


def test_the_model_declares_what_the_step_writes():
    table = SSHCertificate.__table__
    assert not table.columns[FLAG].nullable
    index = {i.name: i for i in table.indexes}[INDEX]
    assert index.unique and [c.name for c in index.columns] == ['ssh_ca_id', 'serial']
    for dialect in ('sqlite', 'postgresql'):
        assert str(index.dialect_options[dialect]['where']) == f'serial <> 0 AND NOT {FLAG}'


def _ca(db, ca_id, counter):
    db.run(f"INSERT INTO {CAS} (id, refid, descr, ca_type, public_key, private_key, key_type, fingerprint, "
           "serial_counter, allow_any_principal, allow_custom_key_id) VALUES (:i, :r, :d, 'user', 'pub', 'prv', "
           "'ed25519', :f, :c, TRUE, FALSE)",
           {'i': ca_id, 'r': f'ca-{ca_id}', 'd': f'CA {ca_id}', 'f': f'SHA256:{ca_id}', 'c': counter})


def _cert(db, cert_id, ca_id, serial):
    db.run(f"INSERT INTO {CERTS} (id, refid, ssh_ca_id, cert_type, key_id, public_key, certificate, principals, "
           "serial, valid_from, valid_to, key_type, fingerprint, revoked) VALUES (:i, :r, :c, 'user', :k, 'pub', "
           "'cert', '[]', :s, '2026-01-01 00:00:00', '2027-01-01 00:00:00', 'ed25519', :f, FALSE)",
           {'i': cert_id, 'r': f'cert-{cert_id}', 'c': ca_id, 'k': f'key-{cert_id}', 's': serial,
            'f': f'SHA256:c{cert_id}'})


def _populate(db):
    _ca(db, 1, 2)    # behind: holds serial 3 twice, counter 2
    _ca(db, 2, 9)    # ahead, and serial 0 twice, which is no number
    _cert(db, 11, 1, 1)
    _cert(db, 12, 1, 3)
    _cert(db, 13, 1, 3)
    _cert(db, 14, 1, 2)
    _cert(db, 21, 2, 0)
    _cert(db, 22, 2, 0)
    _cert(db, 23, 2, 3)  # serial 3 under another CA: not a duplicate


def _flags(db):
    return {i: bool(f) for i, f in db.run(f"SELECT id, {FLAG} FROM {CERTS} ORDER BY id")}


def _listed(db):
    rows = db.run("SELECT value FROM system_config WHERE key = :k", {'k': MARKED_KEY})
    return json.loads(rows[0][0]) if rows else None


def _run_step_again(db, dialect):
    step = importlib.import_module(f'migrations._from_2_254.{STEP}')
    if dialect == 'sqlite':
        conn = db.connection()
        step.upgrade(conn)
        conn.close()
    else:
        with db.connection() as conn:
            step.upgrade(conn)


@pytest.mark.parametrize('dialect', BACKENDS)
def test_a_2254_database_keeps_its_serials_and_marks_the_pairs(dialect, tmp_path, monkeypatch, caplog):
    for db in make_base(dialect, tmp_path, monkeypatch, 'ssh168'):
        _populate(db)
        with caplog.at_level('WARNING'):
            assert db.upgrade()
        flags = _flags(db)
        assert flags == {11: False, 12: True, 13: True, 14: False, 21: False, 22: False, 23: False}
        # Nothing is renumbered: the signature carries the serial
        assert dict(db.run(f"SELECT id, serial FROM {CERTS} ORDER BY id")) == {
            11: 1, 12: 3, 13: 3, 14: 2, 21: 0, 22: 0, 23: 3}
        assert dict(db.run(f"SELECT id, serial_counter FROM {CAS} ORDER BY id")) == {1: 3, 2: 9}
        listed = _listed(db)
        assert [(e['ssh_ca_id'], e['serial'], e['ids']) for e in listed] == [(1, 3, [12, 13])]
        assert any('serial 3 to 2 certificates' in m and 'revoke' in m for m in caplog.messages)

        # The index holds from now on, serial 0 aside
        with pytest.raises(IntegrityError):
            _cert(db, 15, 1, 2)
        _cert(db, 24, 2, 0)

        _run_step_again(db, dialect)
        assert _flags(db) == {**flags, 24: False}
        assert _listed(db) == listed


@pytest.mark.parametrize('dialect', BACKENDS)
def test_a_2254_database_without_pairs_lists_nothing(dialect, tmp_path, monkeypatch):
    for db in make_base(dialect, tmp_path, monkeypatch, 'ssh168c'):
        _ca(db, 1, 0)
        _cert(db, 11, 1, 1)
        _cert(db, 12, 1, 2)
        assert db.upgrade()
        assert _flags(db) == {11: False, 12: False}
        assert _listed(db) is None
        assert db.run(f"SELECT serial_counter FROM {CAS}") == [(2,)]


def test_the_next_start_reports_each_pair_once(app, caplog):
    from models import db, AuditLog, SystemConfig
    from utils.ssh_serials import report_marked_duplicates
    listed = [{'ssh_ca_id': 901, 'ca': 'Users', 'serial': 7, 'ids': [3, 4], 'key_ids': ['a', 'b']},
              {'ssh_ca_id': 902, 'ca': 'Hosts', 'serial': 9, 'ids': [5, 6], 'key_ids': ['c', 'd']}]
    with app.app_context():
        before = db.session.query(db.func.max(AuditLog.id)).scalar() or 0
        db.session.add(SystemConfig(key=MARKED_KEY, value=json.dumps(listed)))
        db.session.commit()
    try:
        with caplog.at_level('WARNING'):
            assert report_marked_duplicates(app) == 2
        assert report_marked_duplicates(app) == 0
        with app.app_context():
            assert SystemConfig.query.filter_by(key=MARKED_KEY).first() is None
            entries = AuditLog.query.filter(AuditLog.id > before, AuditLog.action == MARKED_ACTION).all()
            assert sorted(e.resource_id for e in entries) == ['901', '902']
            assert all('revoke them and issue new certificates' in e.details for e in entries)
        assert sum('to 2 certificates' in m for m in caplog.messages) == 2
    finally:
        with app.app_context():
            SystemConfig.query.filter_by(key=MARKED_KEY).delete()
            db.session.commit()


def test_the_list_never_leaves_the_installation():
    from services.backup import installation
    assert installation.is_local_setting(MARKED_KEY)


def test_the_start_calls_the_report(app, monkeypatch):
    """create_app reports the list the upgrade left, as it does for the trust store."""
    import utils.ssh_serials as serials
    called = []
    monkeypatch.setattr(serials, 'report_marked_duplicates', lambda a: called.append(a) or 0)
    from tests.fresh_app import fresh_app
    with fresh_app() as application:
        assert called == [application]

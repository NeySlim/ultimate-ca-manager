"""An SSH CA's serial counter never trails the serials it holds, whatever path wrote them.

The KRL revokes by serial (PROTOCOL.krl §2.2): a counter behind its certificates hands a number out
twice. Every path that writes certificates or counters ends with ``serial_counter >= max(serial)``
and never lowers it, so the next signature takes a number no certificate of the CA ever had.

Matrix: path {upgrade, import of a CA, import of a certificate, restore merge, restore replace,
change of database} x state of the counter {ahead, equal, behind, CA absent from the target, CA
present with other certificates}. Pruned: the CA absent for an upgrade, an import of a
certificate and a change of database (nothing precedes the first, the second refuses an unknown
CA, the target of the third is empty, so every CA is absent there); for the import of a CA every
state but absent (a CA already here is refused by its fingerprint). 23 cells per engine.
"""
import copy
import os
import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import select, text

from models import db
from models.ssh import SSHCertificate, SSHCertificateAuthority
from services.ssh_ca_service import SSHCAService
from services.ssh_cert import SSHCertificateService
from tests.fresh_app import fresh_app_fixtures
from tests.test_backup_cross_installation import PASSWORD, Keys, _bound_to, _installation, _only
from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own
from tests.upgrade_2254_support import make_base

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
ENGINES = [
    'sqlite',
    pytest.param('postgresql', marks=[
        pytest.mark.postgres,
        pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')]),
]
STATES = ('ahead', 'equal', 'behind', 'absent', 'others')
CAS = SSHCertificateAuthority.__table__
CERTS = SSHCertificate.__table__


def _schema_url(name):
    separator = '&' if '?' in _PG_URL else '?'
    return f'{_PG_URL}{separator}options=-csearch_path%3D{name}'


@pytest.fixture(scope='module', params=ENGINES)
def installation(request, app, tmp_path_factory):
    """One installation per engine, shared by the cases: each works on CAs of its own."""
    directory = tmp_path_factory.mktemp('ssh-serial-matrix')
    keys = Keys(directory, f'ssh-matrix-{request.param}')
    if request.param == 'sqlite':
        with _installation(app, f"sqlite:///{directory / 'target.db'}", keys), app.app_context():
            yield request.param
        return
    with _a_schema_of_our_own(f'ssh_matrix_{uuid.uuid4().hex[:10]}') as url:
        with _installation(app, url, keys, is_postgresql=True), app.app_context():
            yield request.param
            db.session.rollback()


def _pubkey():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    return ed25519.Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode()


def _ca(label):
    return SSHCAService.create_ca(descr=f'{label} {uuid.uuid4().hex[:8]}', ca_type='user', key_type='ed25519',
                                  username='t', allow_any_principal=True).id


def _sign(ca_id):
    return SSHCertificateService.sign_certificate(ca_id, _pubkey(), 'user', ['matrix']).serial


def _counter(ca_id):
    return db.session.execute(select(CAS.c.serial_counter).where(CAS.c.id == ca_id)).scalar_one()


def _set_counter(ca_id, value):
    db.session.execute(CAS.update().where(CAS.c.id == ca_id).values(serial_counter=value))
    db.session.commit()


def _forget(ca_id, serials):
    db.session.execute(CERTS.delete().where(CERTS.c.ssh_ca_id == ca_id, CERTS.c.serial.in_(serials)))
    db.session.commit()


def _ca_by_refid(refid):
    return db.session.execute(select(CAS.c.id).where(CAS.c.refid == refid)).scalar_one()


def _next_is_new(ca_id, issued):
    """The invariant itself, then the signature it promises: a number the CA never gave out."""
    db.session.expire_all()
    assert _counter(ca_id) >= max(issued, default=0), (_counter(ca_id), sorted(issued))
    serial = _sign(ca_id)
    assert serial not in issued, (serial, sorted(issued))
    return serial


# --- restore, merge and replace -----------------------------------------------------------

def _archive():
    from services.backup_service import BackupService
    service = BackupService()
    blob = service.create_backup(PASSWORD, include=_only('ssh_cas', 'ssh_certificates'))
    return service._decrypt_framed(blob, PASSWORD)


def _restore(master, payload, mode):
    from services.backup_service import BackupService
    return BackupService()._restore_payload(copy.deepcopy(payload), master, mode)


def _restore_case(mode, state):
    ca_id = _ca(f'restore {mode} {state}')
    refid = db.session.get(SSHCertificateAuthority, ca_id).refid
    issued = {_sign(ca_id) for _ in range(3)}
    master, payload = _archive()
    if state == 'ahead':
        issued |= {_sign(ca_id), _sign(ca_id)}
    elif state == 'behind':
        _forget(ca_id, [2, 3])
        _set_counter(ca_id, 1)
    elif state == 'absent':
        _forget(ca_id, sorted(issued))
        db.session.execute(CAS.delete().where(CAS.c.id == ca_id))
        db.session.commit()
    elif state == 'others':
        # Certificates the archive never saw, and a counter left behind them
        issued |= {_sign(ca_id), _sign(ca_id)}
        _set_counter(ca_id, 3)
    _restore(master, payload, mode)
    db.session.remove()
    _next_is_new(_ca_by_refid(refid), issued)


@pytest.mark.parametrize('mode', ('merge', 'replace'))
@pytest.mark.parametrize('state', STATES)
def test_a_restore_leaves_the_counter_past_every_serial(installation, mode, state):
    _restore_case(mode, state)


def test_a_restore_of_an_older_archive_keeps_the_higher_counter(installation):
    """The archive's counter is lower than the target's and the target issued nothing since."""
    ca_id = _ca('restore older')
    refid = db.session.get(SSHCertificateAuthority, ca_id).refid
    _sign(ca_id)
    master, payload = _archive()
    _set_counter(ca_id, 40)
    _restore(master, payload, 'merge')
    db.session.remove()
    assert _counter(_ca_by_refid(refid)) == 40


# --- imports -------------------------------------------------------------------------------

def _imported_ca(label):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    key = ed25519.Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
                            serialization.NoEncryption())
    ca = SSHCAService.import_ca(descr=f'{label} {uuid.uuid4().hex[:8]}', ca_type='user', private_key_pem=pem,
                                username='t', allow_any_principal=True)
    return ca.id, key


def _signed_elsewhere(key, serial):
    """A certificate the same CA key signed outside UCM, with the serial it chose."""
    import time
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    subject = ed25519.Ed25519PrivateKey.generate().public_key()
    now = int(time.time())
    cert = (serialization.SSHCertificateBuilder().public_key(subject).serial(serial)
            .type(serialization.SSHCertificateType.USER).key_id(b'outside')
            .valid_principals([b'outside']).valid_after(now - 60).valid_before(now + 3600).sign(key))
    return cert.public_bytes().decode()


def test_an_imported_ca_signs_from_a_fresh_serial(installation):
    ca_id, _ = _imported_ca('import ca')
    _next_is_new(ca_id, set())


@pytest.mark.parametrize('state', ('ahead', 'equal', 'behind', 'others'))
def test_an_imported_certificate_leaves_the_counter_past_its_serial(installation, state):
    ca_id, key = _imported_ca(f'import cert {state}')
    issued = set()
    if state == 'ahead':
        _set_counter(ca_id, 10)
        serial = 5
    elif state == 'equal':
        _set_counter(ca_id, 5)
        serial = 5
    elif state == 'behind':
        serial = 7
    else:
        issued = {_sign(ca_id), _sign(ca_id)}
        serial = 9
    before = _counter(ca_id)
    SSHCertificateService.import_certificate(_signed_elsewhere(key, serial), ssh_ca_id=ca_id, username='t')
    issued.add(serial)
    db.session.remove()
    assert _counter(ca_id) == max(before, serial)
    _next_is_new(ca_id, issued)


# --- the upgrade ---------------------------------------------------------------------------

UPGRADE_CASES = {'ahead': (9, [1, 2]), 'equal': (2, [1, 2]), 'behind': (1, [1, 2, 3]), 'others': (2, [1, 3, 3])}


def _private_key_value():
    from cryptography.hazmat.primitives.asymmetric import ed25519
    key = ed25519.Ed25519PrivateKey.generate()
    return SSHCAService._serialize_private_key(key), key.public_key()


@pytest.mark.parametrize('dialect', ENGINES)
def test_an_upgraded_2254_database_signs_from_a_fresh_serial(app, dialect, tmp_path, monkeypatch):
    from cryptography.hazmat.primitives import serialization
    with app.app_context():
        keys = {state: _private_key_value() for state in UPGRADE_CASES}
    label = 'sshmx'
    with contextmanager(make_base)(dialect, tmp_path, monkeypatch, label) as base:
        for n, (state, (counter, serials)) in enumerate(UPGRADE_CASES.items(), start=1):
            stored, public = keys[state]
            base.run("INSERT INTO ssh_cas (id, refid, descr, ca_type, public_key, private_key, key_type, "
                     "fingerprint, serial_counter, allow_any_principal, allow_custom_key_id) VALUES "
                     "(:i, :r, :d, 'user', :pub, :prv, 'ed25519', :f, :c, TRUE, FALSE)",
                     {'i': n, 'r': f'up-{state}', 'd': f'Upgrade {state}', 'c': counter, 'prv': stored,
                      'f': SSHCAService._compute_fingerprint(public),
                      'pub': public.public_bytes(serialization.Encoding.OpenSSH,
                                                 serialization.PublicFormat.OpenSSH).decode()})
            for m, serial in enumerate(serials):
                base.run("INSERT INTO ssh_certificates (refid, ssh_ca_id, cert_type, key_id, public_key, "
                         "certificate, principals, serial, valid_from, valid_to, key_type, fingerprint, revoked) "
                         "VALUES (:r, :c, 'user', 'k', 'pub', 'cert', '[]', :s, '2026-01-01 00:00:00', "
                         "'2027-01-01 00:00:00', 'ed25519', :f, FALSE)",
                         {'r': f'up-{state}-{m}', 'c': n, 's': serial, 'f': f'SHA256:{state}{m}'})
        assert base.upgrade()
        url = base.url if dialect == 'sqlite' else _schema_url(
            f"up2254_{label}_{os.getenv('PYTEST_XDIST_WORKER', 'main')}")
        with _bound_to(app, url, is_postgresql=dialect != 'sqlite', create_schema=False), app.app_context():
            for n, (state, (_, serials)) in enumerate(UPGRADE_CASES.items(), start=1):
                _next_is_new(n, set(serials))
            db.session.remove()


# --- a change of database ------------------------------------------------------------------

DB_CHANGE_CASES = {'ahead': (10, [1, 2, 3]), 'equal': (3, [1, 2, 3]), 'behind': (1, [1, 2, 3]),
                   'others': (2, [1, 2, 3, 4])}


@pytest.mark.parametrize('engine', ENGINES)
def test_a_change_of_database_leaves_the_counter_past_every_serial(app, engine, tmp_path):
    from services.database_admin import migration
    keys = Keys(tmp_path, 'ssh-db-change')
    with _installation(app, f"sqlite:///{tmp_path / 'source.db'}", keys), app.app_context():
        cas = {}
        for state, (counter, serials) in DB_CHANGE_CASES.items():
            ca_id = cas[state] = _ca(f'db change {state}')
            for _ in serials:
                _sign(ca_id)
            _set_counter(ca_id, counter)
        db.session.remove()
        if engine == 'sqlite':
            target, target_url = None, f"sqlite:///{tmp_path / 'target.db'}"
        else:
            target = _a_schema_of_our_own(f'ssh_dbchange_{uuid.uuid4().hex[:10]}')
            target_url = target.__enter__()
        try:
            ok, message, _ = migration.migrate_data(target_url)
            assert ok is True, message
            with _bound_to(app, target_url, is_postgresql=engine != 'sqlite', create_schema=False), \
                    app.app_context():
                for state, (_, serials) in DB_CHANGE_CASES.items():
                    _next_is_new(cas[state], set(serials))
                db.session.remove()
        finally:
            if target is not None:
                target.__exit__(None, None, None)


def test_the_raise_never_lowers_a_counter(installation):
    from utils.ssh_serials import raise_counters, session_run
    ca_id = _ca('never lower')
    _sign(ca_id)
    _set_counter(ca_id, 30)
    raise_counters(session_run, ca_id)
    db.session.commit()
    assert _counter(ca_id) == 30
    _set_counter(ca_id, 0)
    raise_counters(session_run)
    db.session.commit()
    assert _counter(ca_id) == 1
    assert db.session.execute(text('SELECT 1')).scalar() == 1


@pytest.mark.parametrize('mode', ('merge', 'replace'))
def test_an_archive_holding_a_serial_twice_restores_both_marked(installation, mode):
    """A 2.254 archive may carry a pair: both rows come back, marked, under their number."""
    ca_id = _ca(f'archived pair {mode}')
    refid = db.session.get(SSHCertificateAuthority, ca_id).refid
    _sign(ca_id), _sign(ca_id)
    master, store = _archive()
    # As a 2.254 archive reads: a plain payload, no digest to keep
    payload = {name: copy.deepcopy(list(store[name])) for name in ('ssh_cas', 'ssh_certificates')}
    held = [row for row in payload['ssh_certificates'] if row.get('ssh_ca_id_ref', {}).get('refid') == refid
            or row.get('ssh_ca_id') == ca_id]
    assert sorted(row['serial'] for row in held) == [1, 2]
    for row in payload['ssh_certificates']:
        row.pop('serial_duplicate', None)
    next(row for row in held if row['serial'] == 2)['serial'] = 1
    # The target holds neither row: the archive alone brings the pair
    _forget(ca_id, [1, 2])
    _restore(master, payload, mode)
    db.session.remove()
    restored = _ca_by_refid(refid)
    rows = db.session.execute(select(CERTS.c.serial, CERTS.c.serial_duplicate)
                              .where(CERTS.c.ssh_ca_id == restored).order_by(CERTS.c.id)).all()
    pair = [bool(flag) for serial, flag in rows if serial == 1]
    # The oldest holder back under the index, the other one marked
    assert pair == [False, True], rows
    _next_is_new(restored, {1, 2})


@pytest.mark.parametrize('mode', ('merge', 'replace'))
def test_an_archive_whose_counter_trails_its_certificates_restores_past_them(installation, mode):
    """A 2.254 archive taken where the counter had fallen behind: the restore counts past its rows."""
    ca_id = _ca(f'archived lag {mode}')
    refid = db.session.get(SSHCertificateAuthority, ca_id).refid
    issued = {_sign(ca_id) for _ in range(3)}
    master, store = _archive()
    payload = {name: copy.deepcopy(list(store[name])) for name in ('ssh_cas', 'ssh_certificates')}
    next(row for row in payload['ssh_cas'] if row['refid'] == refid)['serial_counter'] = 0
    _forget(ca_id, sorted(issued))
    db.session.execute(CAS.delete().where(CAS.c.id == ca_id))
    db.session.commit()
    _restore(master, payload, mode)
    db.session.remove()
    _next_is_new(_ca_by_refid(refid), issued)

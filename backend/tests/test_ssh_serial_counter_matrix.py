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
from datetime import datetime

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
def test_an_archive_with_rows_after_its_pair_restores_them_all(installation, mode):
    """Certificates signed after a 2.254 pair sit after it in the archive: the restore writes them too."""
    ca_id = _ca(f'pair then more {mode}')
    refid = db.session.get(SSHCertificateAuthority, ca_id).refid
    for _ in range(4):
        _sign(ca_id)
    master, store = _archive()
    payload = {name: copy.deepcopy(list(store[name])) for name in ('ssh_cas', 'ssh_certificates')}
    held = [row for row in payload['ssh_certificates'] if row.get('ssh_ca_id_ref', {}).get('refid') == refid
            or row.get('ssh_ca_id') == ca_id]
    assert sorted(row['serial'] for row in held) == [1, 2, 3, 4]
    for row in payload['ssh_certificates']:
        row.pop('serial_duplicate', None)
    next(row for row in held if row['serial'] == 2)['serial'] = 1
    _forget(ca_id, [1, 2, 3, 4])
    _restore(master, payload, mode)
    db.session.remove()
    restored = _ca_by_refid(refid)
    rows = db.session.execute(select(CERTS.c.serial, CERTS.c.serial_duplicate)
                              .where(CERTS.c.ssh_ca_id == restored).order_by(CERTS.c.id)).all()
    assert [(serial, bool(flag)) for serial, flag in rows] == [(1, False), (1, True), (3, False), (4, False)], rows
    _next_is_new(restored, {1, 3, 4})


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


# --- a pair whose holders are revoked or not -----------------------------------------------
# The KRL revokes a serial (PROTOCOL.krl §2.2): once a holder of a pair is revoked, its partner is
# revoked too, with the date and reason of the oldest revoked holder. Pair {none revoked, the older,
# the newer, both} x path {upgrade, restore merge, restore replace}; an import cannot make a pair (it
# refuses a held serial), so its cells are the holder {valid, revoked}. 14 cells per engine.
PAIRS = ('none', 'older', 'newer', 'both')
REASONS = {'older': 'keyCompromise', 'newer': 'superseded'}


def _expected_pair(pair):
    """(revoked, reason) of the older and the newer holder once the path ran."""
    if pair == 'none':
        return [(False, None), (False, None)]
    if pair == 'both':
        return [(True, REASONS['older']), (True, REASONS['newer'])]
    return [(True, REASONS[pair])] * 2


def _holders(ca_id, serial):
    return db.session.execute(select(CERTS.c.revoked, CERTS.c.revoke_reason, CERTS.c.revoked_at)
                              .where(CERTS.c.ssh_ca_id == ca_id, CERTS.c.serial == serial)
                              .order_by(CERTS.c.id)).all()


def _assert_pair(rows, pair):
    assert [(bool(r[0]), r[1]) for r in rows] == _expected_pair(pair), rows
    if pair in ('older', 'newer'):
        assert rows[0][2] is not None and rows[0][2] == rows[1][2], rows


@pytest.mark.parametrize('mode', ('merge', 'replace'))
@pytest.mark.parametrize('pair', PAIRS)
def test_a_restored_pair_is_revoked_as_the_krl_revokes_it(installation, mode, pair):
    ca_id = _ca(f'revoked pair {mode} {pair}')
    refid = db.session.get(SSHCertificateAuthority, ca_id).refid
    first, second = (SSHCertificateService.sign_certificate(ca_id, _pubkey(), 'user', ['pair'])
                     for _ in range(2))
    ids = [first.id, second.id]
    if pair in ('older', 'both'):
        SSHCertificateService.revoke_certificate(first.id, REASONS['older'], 't')
    if pair in ('newer', 'both'):
        SSHCertificateService.revoke_certificate(second.id, REASONS['newer'], 't')
    master, store = _archive()
    payload = {name: copy.deepcopy(list(store[name])) for name in ('ssh_cas', 'ssh_certificates')}
    for row in payload['ssh_certificates']:
        row.pop('serial_duplicate', None)
    held = [row for row in payload['ssh_certificates'] if row['refid'] in
            {c.refid for c in db.session.query(SSHCertificate).filter(SSHCertificate.id.in_(ids))}]
    serial = min(row['serial'] for row in held)
    for row in held:
        row['serial'] = serial
    _forget(ca_id, [first.serial, second.serial])
    results = _restore(master, payload, mode)
    db.session.remove()
    _assert_pair(_holders(_ca_by_refid(refid), serial), pair)
    # The restore says how many certificates it revoked with their serial, and audits each
    assert results['ssh_revoked_with_serial'] == (1 if pair in ('older', 'newer') else 0)
    held = db.session.execute(select(CERTS.c.id).where(CERTS.c.ssh_ca_id == _ca_by_refid(refid),
                                                       CERTS.c.serial == serial).order_by(CERTS.c.id)).scalars().all()
    audited = _revocations_audited(held)
    if pair in ('older', 'newer'):
        revoked, source = (held[1], held[0]) if pair == 'older' else (held[0], held[1])
        assert audited == [(str(revoked), f'SSH certificate revoked with #{source}, which holds serial {serial} '
                                          'under their CA: the KRL revokes by serial')]
    else:
        assert audited == []


def _revocations_audited(ids):
    from models import AuditLog
    return [(r.resource_id, r.details) for r in AuditLog.query.filter(
        AuditLog.action == 'ssh_cert_revoked', AuditLog.resource_type == 'ssh_certificate',
        AuditLog.username == 'system', AuditLog.resource_id.in_([str(i) for i in ids])).order_by(AuditLog.id)]


def test_three_holders_take_the_oldest_revocation_which_the_check_sees_missing(installation):
    """The date reported is the oldest revocation, not the revoked holder of lowest id."""
    from services.database_admin.verify import VerificationError, check_ssh_serials
    from utils import ssh_serials
    ca_id = _ca('three holders')
    ids = [SSHCertificateService.sign_certificate(ca_id, _pubkey(), 'user', ['three']).id for _ in range(3)]
    serial = db.session.get(SSHCertificate, ids[0]).serial
    late, early = datetime(2026, 3, 1, 12, 0), datetime(2026, 1, 1, 12, 0)
    for row_id, values in ((ids[1], {'serial': serial, 'serial_duplicate': True, 'revoked': True,
                                     'revoked_at': early, 'revoke_reason': 'keyCompromise'}),
                           (ids[2], {'serial': serial, 'serial_duplicate': True}),
                           (ids[0], {'revoked': True, 'revoked_at': late, 'revoke_reason': 'superseded'})):
        db.session.execute(CERTS.update().where(CERTS.c.id == row_id).values(**values))
    db.session.commit()
    with pytest.raises(VerificationError) as excinfo:
        check_ssh_serials(db.engine)
    assert f'#{ids[2]}' in str(excinfo.value) and 'revoked' in str(excinfo.value)

    assert ssh_serials.align_revocations(ssh_serials.session_run) == {ids[2]: ids[1]}
    db.session.commit()
    rows = _holders(ca_id, serial)
    assert [(bool(r[0]), r[1], r[2]) for r in rows] == [
        (True, 'superseded', late), (True, 'keyCompromise', early), (True, 'keyCompromise', early)]
    assert check_ssh_serials(db.engine)['diverging_revocations'] == 0


def _signed_with_key_id(key, serial, key_id):
    import time
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    now = int(time.time())
    cert = (serialization.SSHCertificateBuilder().public_key(ed25519.Ed25519PrivateKey.generate().public_key())
            .serial(serial).type(serialization.SSHCertificateType.USER).key_id(key_id)
            .valid_principals([b'outside']).valid_after(now - 60).valid_before(now + 3600).sign(key))
    return cert.public_bytes().decode()


def test_a_revoked_serial_zero_revokes_its_key_id_which_the_check_sees_missing(installation):
    """The KRL revokes the key ID of a revoked serial 0 certificate under its CA: a valid
    certificate bearing it is flagged, then revoked with it and audited; another key ID is not."""
    from services.database_admin.verify import VerificationError, check_ssh_serials
    from utils import ssh_serials
    ca_id, key = _imported_ca('serial zero key ID')
    ids = [SSHCertificateService.import_certificate(_signed_with_key_id(key, s, k), ssh_ca_id=ca_id,
                                                    username='t').id
           for s, k in ((0, b'alice'), (7, b'alice'), (8, b'bob'))]
    revoked_at = datetime(2026, 2, 1, 12, 0)
    db.session.execute(CERTS.update().where(CERTS.c.id == ids[0]).values(
        revoked=True, revoked_at=revoked_at, revoke_reason='keyCompromise'))
    db.session.commit()
    with pytest.raises(VerificationError) as excinfo:
        check_ssh_serials(db.engine)
    assert f'#{ids[1]} beside #{ids[0]}' in str(excinfo.value)
    assert f'#{ids[2]}' not in str(excinfo.value)

    aligned = ssh_serials.align_revocations(ssh_serials.session_run)
    assert aligned == {ids[1]: ids[0]}
    assert ssh_serials.revocation_entries(ssh_serials.session_run, aligned)[0]['details'] == (
        f'SSH certificate revoked with #{ids[0]}, of serial 0 and the same key ID under their CA: '
        'the KRL revokes that key ID')
    db.session.commit()
    rows = db.session.execute(select(CERTS.c.revoked, CERTS.c.revoke_reason, CERTS.c.revoked_at)
                              .where(CERTS.c.id.in_(ids)).order_by(CERTS.c.id)).all()
    assert [(bool(r[0]), r[1], r[2]) for r in rows] == [
        (True, 'keyCompromise', revoked_at), (True, 'keyCompromise', revoked_at), (False, None, None)]
    assert check_ssh_serials(db.engine)['diverging_revocations'] == 0


def test_the_holder_of_a_serial_a_revoked_key_id_takes_is_revoked_too(installation):
    """Revoked through its key ID, a certificate revokes its serial: its pair follows, with and
    after it, in the restore alignment as in a revocation."""
    from utils import ssh_serials
    for path in ('align', 'revoke'):
        ca_id, key = _imported_ca(f'key ID then serial {path}')
        zero, numbered = [SSHCertificateService.import_certificate(_signed_with_key_id(key, s, k), ssh_ca_id=ca_id,
                                                                   username='t').id
                          for s, k in ((0, b'erin'), (7, b'erin'))]
        mate = SSHCertificateService.import_certificate(_signed_with_key_id(key, 8, b'frank'), ssh_ca_id=ca_id,
                                                        username='t').id
        db.session.execute(CERTS.update().where(CERTS.c.id == mate).values(serial=7, serial_duplicate=True))
        db.session.commit()
        if path == 'align':
            db.session.execute(CERTS.update().where(CERTS.c.id == zero).values(revoked=True))
            assert ssh_serials.align_revocations(ssh_serials.session_run) == {numbered: zero, mate: numbered}
            db.session.commit()
        else:
            cert = SSHCertificateService.revoke_certificate(zero, 'superseded', 't')
            assert [c.id for c in cert.revoked_with] == [numbered, mate]
        db.session.expire_all()
        assert all(db.session.get(SSHCertificate, i).revoked for i in (zero, numbered, mate))


def test_a_key_id_the_krl_revokes_is_neither_issued_nor_imported(installation):
    """A certificate bearing the key ID of a revoked serial 0 certificate of its CA would be
    revoked by the KRL from the start: issuance and import refuse it, and spend no serial."""
    ca_id, key = _imported_ca('revoked key ID')
    db.session.execute(CAS.update().where(CAS.c.id == ca_id).values(allow_custom_key_id=True))
    db.session.commit()
    zero = SSHCertificateService.import_certificate(_signed_with_key_id(key, 0, b'carol'), ssh_ca_id=ca_id,
                                                    username='t')
    SSHCertificateService.revoke_certificate(zero.id, 'superseded', 't')
    counter = _counter(ca_id)
    with pytest.raises(ValueError, match=f"key ID 'carol'.*#{zero.id}.*Use another key ID"):
        SSHCertificateService.sign_certificate(ca_id, _pubkey(), 'user', ['carol'], key_id='carol')
    db.session.rollback()
    # The key ID of an imported certificate is under its signature: no other one to suggest
    with pytest.raises(ValueError, match=f"key ID 'carol'.*#{zero.id}.*then import again$"):
        SSHCertificateService.import_certificate(_signed_with_key_id(key, 9, b'carol'), ssh_ca_id=ca_id,
                                                 username='t')
    db.session.rollback()
    assert _counter(ca_id) == counter
    assert db.session.query(SSHCertificate).filter_by(ssh_ca_id=ca_id).count() == 1
    assert SSHCertificateService.sign_certificate(ca_id, _pubkey(), 'user', ['carol'], key_id='dave').id


def test_a_restore_without_ssh_certificates_still_counts_them(installation):
    _ca('no certificate in the archive')
    master, store = _archive()
    results = _restore(master, {'ssh_cas': copy.deepcopy(list(store['ssh_cas']))}, 'merge')
    assert results['ssh_revoked_with_serial'] == 0


@pytest.mark.parametrize('holder', ('valid', 'revoked'))
def test_an_import_never_makes_a_pair(installation, holder):
    ca_id, key = _imported_ca(f'import pair {holder}')
    SSHCertificateService.import_certificate(_signed_elsewhere(key, 4), ssh_ca_id=ca_id, username='t')
    held = db.session.query(SSHCertificate).filter_by(ssh_ca_id=ca_id, serial=4).one()
    if holder == 'revoked':
        SSHCertificateService.revoke_certificate(held.id, 'superseded', 't')
    with pytest.raises(ValueError, match='already exists'):
        SSHCertificateService.import_certificate(_signed_elsewhere(key, 4), ssh_ca_id=ca_id, username='t')
    db.session.rollback()
    assert len(_holders(ca_id, 4)) == 1


@pytest.mark.parametrize('dialect', ENGINES)
def test_an_upgraded_pair_is_revoked_as_the_krl_revokes_it(app, dialect, tmp_path, monkeypatch):
    import json
    from utils.ssh_serials import MARKED_KEY, describe
    when = {'older': '2026-03-01 10:00:00', 'newer': '2026-04-01 10:00:00'}
    for base in make_base(dialect, tmp_path, monkeypatch, 'sshpr'):
        for n, pair in enumerate(PAIRS, start=1):
            base.run("INSERT INTO ssh_cas (id, refid, descr, ca_type, public_key, private_key, key_type, "
                     "fingerprint, serial_counter, allow_any_principal, allow_custom_key_id) VALUES "
                     "(:i, :r, :d, 'user', 'pub', 'prv', 'ed25519', :f, 1, TRUE, FALSE)",
                     {'i': n, 'r': f'pair-{pair}', 'd': f'Pair {pair}', 'f': f'SHA256:pair{n}'})
            for m, side in enumerate(('older', 'newer')):
                revoked = pair in (side, 'both')
                base.run("INSERT INTO ssh_certificates (id, refid, ssh_ca_id, cert_type, key_id, public_key, "
                         "certificate, principals, serial, valid_from, valid_to, key_type, fingerprint, revoked, "
                         "revoked_at, revoke_reason) VALUES (:i, :r, :c, 'user', 'k', 'pub', 'cert', '[]', 5, "
                         "'2026-01-01 00:00:00', '2027-01-01 00:00:00', 'ed25519', :f, :rv, :at, :why)",
                         {'i': 10 * n + m, 'r': f'pair-{pair}-{m}', 'c': n, 'f': f'SHA256:{pair}{m}',
                          'rv': revoked, 'at': when[side] if revoked else None,
                          'why': REASONS[side] if revoked else None})
        assert base.upgrade()
        listed = {e['ssh_ca_id']: e for e in json.loads(
            base.run('SELECT value FROM system_config WHERE key = :k', {'k': MARKED_KEY})[0][0])}
        for n, pair in enumerate(PAIRS, start=1):
            rows = base.run('SELECT revoked, revoke_reason, revoked_at FROM ssh_certificates '
                            'WHERE ssh_ca_id = :c ORDER BY id', {'c': n})
            assert [(bool(r[0]), r[1]) for r in rows] == _expected_pair(pair), (pair, rows)
            text_of = describe(listed[n])
            if pair in ('older', 'newer'):
                assert str(rows[0][2])[:19] == str(rows[1][2])[:19] == when[pair], rows
                partner, source = (10 * n + 1, 10 * n) if pair == 'older' else (10 * n, 10 * n + 1)
                assert f'#{partner} revoked with #{source}' in text_of, text_of
            else:
                assert 'revoked with' not in text_of, text_of

"""A revocation of an SSH certificate and an issuance or import under the same CA take the CA row
first: the KRL never revokes a certificate the database holds valid (PROTOCOL.krl, ssh-keygen -k
revokes the key ID of a serial 0 certificate), whichever of the two commits first."""
import threading
import time
import uuid

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from models import db
from models.ssh import SSHCertificate, SSHCertificateAuthority
from services.ssh_ca_service import SSHCAService
from services.ssh_cert import SSHCertificateService
from tests.test_revocation_record_rule import _on_postgresql, _wait_for_a_lock_waiter
from utils import ssh_serials

CERTS = SSHCertificate.__table__
CAS = SSHCertificateAuthority.__table__
PG_ONLY = 'row locks are PostgreSQL behaviour; SQLite serializes writers'


def _pubkey():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    return ed25519.Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode()


def _signed(key, serial, key_id):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    now = int(time.time())
    cert = (serialization.SSHCertificateBuilder().public_key(ed25519.Ed25519PrivateKey.generate().public_key())
            .serial(serial).type(serialization.SSHCertificateType.USER).key_id(key_id.encode())
            .valid_principals([b'race']).valid_after(now - 60).valid_before(now + 3600).sign(key))
    return cert.public_bytes().decode()


@pytest.fixture
def ssh_ca(app):
    """An imported user CA that lets requesters set the key ID: (id, key); its rows dropped after."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    key = ed25519.Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
                            serialization.NoEncryption())
    with app.app_context():
        ca = SSHCAService.import_ca(descr=f'race {uuid.uuid4().hex[:8]}', ca_type='user', private_key_pem=pem,
                                    username='t', allow_any_principal=True)
        ca_id = ca.id
        db.session.execute(CAS.update().where(CAS.c.id == ca_id).values(allow_custom_key_id=True))
        db.session.commit()
        db.session.remove()
    yield ca_id, key
    with app.app_context():
        db.session.execute(CERTS.delete().where(CERTS.c.ssh_ca_id == ca_id))
        db.session.execute(CAS.delete().where(CAS.c.id == ca_id))
        db.session.commit()
        db.session.remove()


def _import(app, ca_id, key, serial, key_id):
    with app.app_context():
        cert_id = SSHCertificateService.import_certificate(_signed(key, serial, key_id), ssh_ca_id=ca_id,
                                                           username='t').id
        db.session.remove()
    return cert_id


def _rows(app, ca_id):
    """{id: (serial, key_id, revoked)} as another connection reads them."""
    with app.app_context():
        with db.engine.connect() as conn:
            return {r[0]: (r[1], r[2], bool(r[3])) for r in conn.execute(
                select(CERTS.c.id, CERTS.c.serial, CERTS.c.key_id, CERTS.c.revoked)
                .where(CERTS.c.ssh_ca_id == ca_id))}


def _diverging(app, ca_id):
    """The valid certificates of the CA that its KRL revokes."""
    ids = set(_rows(app, ca_id))
    with app.app_context():
        with db.engine.connect() as conn:
            found = ssh_serials.diverging_revocations(lambda sql, p: conn.execute(text(sql), p))
    return {i: s for i, s in found.items() if i in ids}


def _issue(app, kind, ca_id, key, key_id):
    if kind == 'sign':
        return SSHCertificateService.sign_certificate(ca_id, _pubkey(), 'user', ['race'], key_id=key_id).id
    # An import refuses a second serial 0 certificate of its CA: a numbered one bears the key ID
    return SSHCertificateService.import_certificate(_signed(key, 9, key_id), ssh_ca_id=ca_id, username='t').id


def _in_thread(app, name, outcome, call):
    def run():
        with app.app_context():
            try:
                outcome[name] = call()
            except Exception as e:  # noqa: BLE001  (a refusal, or the deadlock victim)
                db.session.rollback()
                outcome[name] = e
            finally:
                db.session.remove()
    worker = threading.Thread(target=run, name=name)
    worker.start()
    return worker


def _pause_before_commit(name, paused, go):
    """The thread *name* stops at its next commit, every write of the transaction made."""
    def hold(session):
        if threading.current_thread().name == name and not paused.is_set():
            paused.set()
            go.wait(30)
    event.listen(Session, 'before_commit', hold)
    return lambda: event.remove(Session, 'before_commit', hold)


def _pause_once(monkeypatch, owner, attr, name, paused, go):
    """The thread *name* stops once, after its first call of ``owner.attr``."""
    real = getattr(owner, attr)

    def held(*args, **kwargs):
        done = real(*args, **kwargs)
        if threading.current_thread().name == name and not paused.is_set():
            paused.set()
            go.wait(30)
        return done
    monkeypatch.setattr(owner, attr, held)


@pytest.mark.parametrize('kind', ('sign', 'import'))
def test_an_issuance_during_a_revocation_of_its_key_id_is_refused(app, ssh_ca, monkeypatch, kind):
    """The issuance passed its first check before the revocation began; the revocation then searched
    the certificates of the key ID and holds its commit. The issuance waits, then is refused."""
    if not _on_postgresql(app):
        pytest.skip(PG_ONLY)
    ca_id, key = ssh_ca
    zero = _import(app, ca_id, key, 0, 'alice')
    issue_paused, issue_go, revoke_paused, revoke_go = (threading.Event() for _ in range(4))
    # Past the first check and, for a signature, past the serial (its own committed transaction)
    if kind == 'sign':
        _pause_once(monkeypatch, SSHCAService, 'check_signing_public_key', 'issue', issue_paused, issue_go)
    else:
        _pause_once(monkeypatch, ssh_serials, 'refuse_revoked_key_id', 'issue', issue_paused, issue_go)
    outcome = {}
    issuer = _in_thread(app, 'issue', outcome, lambda: _issue(app, kind, ca_id, key, 'alice'))
    assert issue_paused.wait(30)
    unhook = _pause_before_commit('revoke', revoke_paused, revoke_go)
    try:
        revoker = _in_thread(app, 'revoke', outcome, lambda: [
            c.id for c in SSHCertificateService.revoke_certificate(zero, 'keyCompromise', 't').revoked_with])
        assert revoke_paused.wait(30)
        issue_go.set()
        with app.app_context():
            with db.engine.connect() as conn:
                waited = _wait_for_a_lock_waiter(conn, 5)
        revoke_go.set()
        issuer.join(30)
        revoker.join(30)
    finally:
        issue_go.set()
        revoke_go.set()
        unhook()
    assert waited, outcome
    assert outcome['revoke'] == [], outcome
    assert isinstance(outcome['issue'], ValueError), outcome
    assert "KRL of this SSH CA revokes key ID 'alice'" in str(outcome['issue'])
    assert _rows(app, ca_id) == {zero: (0, 'alice', True)}
    assert _diverging(app, ca_id) == {}


@pytest.mark.parametrize('kind', ('sign', 'import'))
def test_an_issuance_committed_first_is_revoked_with_its_key_id(app, ssh_ca, monkeypatch, kind):
    """The issuance has written its certificate and holds its commit when the revocation starts:
    the revocation waits, then finds it and revokes it with the serial 0 certificate."""
    if not _on_postgresql(app):
        pytest.skip(PG_ONLY)
    ca_id, key = ssh_ca
    zero = _import(app, ca_id, key, 0, 'bob')
    issue_paused, issue_go = threading.Event(), threading.Event()

    def written(session, _context):
        if (threading.current_thread().name == 'issue' and not issue_paused.is_set()
                and any(isinstance(o, SSHCertificate) for o in session.new)):
            issue_paused.set()
            issue_go.wait(30)
    event.listen(Session, 'after_flush', written)
    outcome = {}
    try:
        issuer = _in_thread(app, 'issue', outcome, lambda: _issue(app, kind, ca_id, key, 'bob'))
        assert issue_paused.wait(30)
        revoker = _in_thread(app, 'revoke', outcome, lambda: [
            c.id for c in SSHCertificateService.revoke_certificate(zero, 'keyCompromise', 't').revoked_with])
        with app.app_context():
            with db.engine.connect() as conn:
                waited = _wait_for_a_lock_waiter(conn, 5)
        issue_go.set()
        issuer.join(30)
        revoker.join(30)
    finally:
        issue_go.set()
        event.remove(Session, 'after_flush', written)
    assert waited, outcome
    issued = outcome['issue']
    assert isinstance(issued, int), outcome
    assert outcome['revoke'] == [issued], outcome
    assert _rows(app, ca_id)[issued][2] is True
    assert _diverging(app, ca_id) == {}


def test_two_revocations_crossing_one_key_id_do_not_deadlock(app, ssh_ca):
    """Two serial 0 certificates of one key ID each revoke the other: the second revocation waits
    for the first, then finds its certificate revoked by it."""
    if not _on_postgresql(app):
        pytest.skip(PG_ONLY)
    ca_id, key = ssh_ca
    first, second, numbered = (_import(app, ca_id, key, s, 'carol') for s in (0, 6, 5))
    with app.app_context():
        # A second serial 0 certificate of one key ID, as an older installation could hold
        db.session.execute(CERTS.update().where(CERTS.c.id == second).values(serial=0))
        db.session.commit()
        db.session.remove()
    paused, go, outcome = threading.Event(), threading.Event(), {}
    unhook = _pause_before_commit('first', paused, go)
    try:
        a = _in_thread(app, 'first', outcome, lambda: [
            c.id for c in SSHCertificateService.revoke_certificate(first, 'superseded', 't').revoked_with])
        assert paused.wait(30)
        b = _in_thread(app, 'second', outcome, lambda: [
            c.id for c in SSHCertificateService.revoke_certificate(second, 'superseded', 't').revoked_with])
        with app.app_context():
            with db.engine.connect() as conn:
                waited = _wait_for_a_lock_waiter(conn, 5)
        go.set()
        a.join(30)
        b.join(30)
    finally:
        go.set()
        unhook()
    assert waited, outcome
    assert outcome['first'] == [second, numbered], outcome
    assert isinstance(outcome['second'], ValueError) and 'already revoked' in str(outcome['second']), outcome
    assert all(revoked for _, _, revoked in _rows(app, ca_id).values())
    assert _diverging(app, ca_id) == {}


@pytest.mark.parametrize('kind', ('sign', 'import'))
def test_a_revocation_after_an_issuance_revokes_it_on_every_engine(app, ssh_ca, kind):
    """In sequence, on SQLite as on PostgreSQL: the certificate issued first is in revoked_with."""
    ca_id, key = ssh_ca
    zero = _import(app, ca_id, key, 0, 'dave')
    with app.app_context():
        issued = _issue(app, kind, ca_id, key, 'dave')
        assert [c.id for c in SSHCertificateService.revoke_certificate(zero, 'superseded', 't').revoked_with] \
            == [issued]
        db.session.remove()
    assert _diverging(app, ca_id) == {}


def test_sqlite_is_sent_no_row_lock(app, ssh_ca):
    """SQLite has no FOR UPDATE: the lock of the CA row adds nothing to what it is sent."""
    if _on_postgresql(app):
        pytest.skip('SQLite only')
    ca_id, key = ssh_ca
    sent = []

    def seen(conn, cursor, statement, *args):
        sent.append(statement)
    with app.app_context():
        engine = db.engine
        event.listen(engine, 'before_cursor_execute', seen)
        try:
            zero = SSHCertificateService.import_certificate(_signed(key, 0, 'erin'), ssh_ca_id=ca_id,
                                                            username='t').id
            SSHCertificateService.sign_certificate(ca_id, _pubkey(), 'user', ['race'], key_id='erin')
            SSHCertificateService.revoke_certificate(zero, 'superseded', 't')
        finally:
            event.remove(engine, 'before_cursor_execute', seen)
        db.session.remove()
    assert sent and not [s for s in sent if 'FOR UPDATE' in s.upper()]
    assert _diverging(app, ca_id) == {}

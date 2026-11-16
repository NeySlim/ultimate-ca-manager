"""An SSH certificate serial is issued once under its CA, from any number of workers or nodes:
the KRL revokes by serial, so a reissued number would revoke two certificates at once."""
import os
import threading
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import event, select

from models import SSHCertificate, SSHCertificateAuthority, db
from services.ssh_ca_service import SSHCAService
from services.ssh_cert import SSHCertificateService

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
WORKERS = 6
TABLE = SSHCertificateAuthority.__table__


def _ca(descr):
    return SSHCAService.create_ca(descr=f'{descr} {uuid.uuid4().hex[:6]}', ca_type='user',
                                  key_type='ed25519', username='t', allow_any_principal=True)


def _pubkey():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    return ed25519.Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode()


def _stored(ca_id):
    """The counter as another connection reads it, outside this session."""
    with db.engine.connect() as conn:
        return conn.execute(select(TABLE.c.serial_counter).where(TABLE.c.id == ca_id)).scalar_one()


def _another_node_sets(ca_id, value):
    with db.engine.begin() as conn:
        conn.execute(TABLE.update().where(TABLE.c.id == ca_id).values(serial_counter=value))


def test_a_loaded_row_counts_from_the_stored_value_not_its_copy(app):
    with app.app_context():
        ca_id = _ca('Stale copy').id
        db.session.remove()
        loaded = db.session.get(SSHCertificateAuthority, ca_id)
        assert loaded.serial_counter == 0
        _another_node_sets(ca_id, 50)
        assert SSHCAService.get_next_serial(ca_id) == 51
        assert _stored(ca_id) == 51 and loaded.serial_counter == 51
        db.session.remove()


def test_signing_counts_from_the_stored_value_when_another_node_signed_meanwhile(app):
    """sign_certificate loads the CA, then another node issues before the serial is taken."""
    with app.app_context():
        ca_id = _ca('Stale sign').id
        db.session.remove()
        real = SSHCAService.get_private_key_object

        def another_node_signs_first(cid):
            _another_node_sets(cid, 50)
            return real(cid)

        with patch.object(SSHCAService, 'get_private_key_object', side_effect=another_node_signs_first):
            cert = SSHCertificateService.sign_certificate(ca_id, _pubkey(), 'user', ['alice'])
        assert cert.serial == 51
        assert _stored(ca_id) == 51
        db.session.remove()


def test_the_serial_returned_is_the_one_stored_not_a_later_one(app):
    """Another node counting right after this commit does not change what this call returns."""
    with app.app_context():
        ca_id = _ca('After commit').id
        before = SSHCAService.get_next_serial(ca_id)

        def another_node_counts(_session):
            _another_node_sets(ca_id, 9999)

        event.listen(db.session(), 'after_commit', another_node_counts, once=True)
        assert SSHCAService.get_next_serial(ca_id) == before + 1
        db.session.remove()


def test_serials_count_on_a_dialect_without_update_returning(app, monkeypatch):
    """SQLite before 3.35 has no UPDATE ... RETURNING: the count is read back under the write lock."""
    def refuse_returning(conn, cursor, statement, *args):
        if 'RETURNING' in statement.upper():
            raise RuntimeError('RETURNING is not available on this database')

    with app.app_context():
        ca_id = _ca('No returning').id
        engine = db.session.get_bind()
        monkeypatch.setattr(engine.dialect, 'update_returning', False)
        event.listen(engine, 'before_cursor_execute', refuse_returning)
        try:
            assert [SSHCAService.get_next_serial(ca_id), SSHCAService.get_next_serial(ca_id)] == [1, 2]
            with pytest.raises(ValueError, match='not found'):
                SSHCAService.get_next_serial(-1)
        finally:
            event.remove(engine, 'before_cursor_execute', refuse_returning)
        assert _stored(ca_id) == 2


def test_an_unknown_ca_has_no_serial(app):
    with app.app_context():
        with pytest.raises(ValueError, match='not found'):
            SSHCAService.get_next_serial(-1)


def _sign_together(app, ca_id):
    """Every worker has loaded the CA before any of them takes a serial."""
    errors, serials, loaded = [], [], threading.Barrier(WORKERS)
    real = SSHCAService.get_private_key_object

    def wait_for_the_others(cid):
        try:
            loaded.wait(10)
        except threading.BrokenBarrierError:
            pass
        return real(cid)

    def worker(n):
        try:
            with app.app_context():
                cert = SSHCertificateService.sign_certificate(ca_id, _pubkey(), 'user', [f'w{n}'])
                serials.append(cert.serial)
                db.session.remove()
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))

    with patch.object(SSHCAService, 'get_private_key_object', side_effect=wait_for_the_others):
        threads = [threading.Thread(target=worker, args=(n,)) for n in range(WORKERS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)
    return errors, serials


def _signatures_together_get_distinct_serials(app):
    with app.app_context():
        ca_id = _ca('Concurrent sign').id
        db.session.remove()
    errors, serials = _sign_together(app, ca_id)
    with app.app_context():
        stored = sorted(s for (s,) in db.session.query(SSHCertificate.serial).filter_by(ssh_ca_id=ca_id))
        counter = _stored(ca_id)
        db.session.remove()
    assert errors == []
    assert sorted(serials) == stored == list(range(1, WORKERS + 1))
    assert counter == WORKERS


def test_concurrent_signatures_under_one_ca_get_distinct_serials_on_sqlite(app, tmp_path):
    """A database file: the suite's in-memory one is a single connection threads cannot share."""
    from tests.test_backup_cross_installation import _bound_to
    with _bound_to(app, f"sqlite:///{tmp_path / 'ssh-serial.db'}"):
        _signatures_together_get_distinct_serials(app)


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_concurrent_signatures_under_one_ca_get_distinct_serials_on_postgresql(app):
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own
    with _a_schema_of_our_own(f'ssh_sign_race_{uuid.uuid4().hex[:6]}') as url, \
            _bound_to(app, url, is_postgresql=True):
        _signatures_together_get_distinct_serials(app)


def _race(app, url, ca_id):
    """Each worker on a connection of its own, the CA row loaded before any serial is taken."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    errors, results, loaded = [], [], threading.Barrier(WORKERS)

    def worker():
        engine = create_engine(url, pool_size=1, max_overflow=0)
        try:
            with app.app_context():
                db.session.registry.set(Session(bind=engine))
                db.session.get(SSHCertificateAuthority, ca_id)
                try:
                    loaded.wait(10)
                except threading.BrokenBarrierError:
                    pass
                results.append(SSHCAService.get_next_serial(ca_id))
                db.session.remove()
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))
        finally:
            engine.dispose()

    threads = [threading.Thread(target=worker) for _ in range(WORKERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    return errors, results


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_nodes_taking_serials_together_get_distinct_consecutive_ones(app):
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

    schema = f'ssh_serial_race_{uuid.uuid4().hex[:6]}'
    with _a_schema_of_our_own(schema) as url, _bound_to(app, url, is_postgresql=True):
        with app.app_context():
            ca_id = _ca('Race').id
            db.session.remove()
        errors, results = _race(app, url, ca_id)
        with app.app_context():
            stored = _stored(ca_id)
            db.session.remove()
    assert errors == []
    assert sorted(results) == list(range(1, WORKERS + 1))
    assert stored == WORKERS

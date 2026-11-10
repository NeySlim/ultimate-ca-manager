"""Issuance under one CA from many workers: distinct serials, no lost count.

The certificate serial is random (RFC 5280 §4.1.2.2); ``ca.serial`` counts the
certificates a CA issued and is incremented in the database, so two workers on
two nodes never overwrite each other's count.
"""
import os
import threading
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from models import CA, Certificate, db
from tests.test_crl_number_monotonic import _authority, _ca_row

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
# Eight workers, each on an engine (a connection) of its own, as eight processes would be
WORKERS, EACH = 8, 13


@pytest.fixture(autouse=True, scope='module')
def _rows_issued_here_are_removed(app):
    """The shared tables leave this file as they came in."""
    from sqlalchemy import text
    tables = ('certificates', 'certificate_authorities')
    with app.app_context():
        before = {t: {i for (i,) in db.session.execute(text(f'SELECT id FROM {t}'))} for t in tables}
        db.session.remove()
    yield
    with app.app_context():
        db.session.rollback()
        for table in tables:
            for (row_id,) in db.session.execute(text(f'SELECT id FROM {table}')).fetchall():
                if row_id not in before[table]:
                    db.session.execute(text(f'DELETE FROM {table} WHERE id = :i'), {'i': row_id})
        db.session.commit()


def _csr(name):
    key = ec.generate_private_key(ec.SECP256R1())
    return (x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
            .sign(key, hashes.SHA256()))


def _issue(ca_id, name):
    from services.ca import CAService
    ca = db.session.get(CA, ca_id)
    return CAService.sign_csr_from_crypto(ca, _csr(name), validity_days=30, source='test')


def test_next_ca_serial_counts_in_the_database(app):
    from utils.ca_serial_counter import next_ca_serial
    with app.app_context():
        ca = _ca_row(*_authority())
        assert [next_ca_serial(ca), next_ca_serial(ca)] == [1, 2]
        assert ca.serial == 2 and 'serial' not in db.inspect(ca).committed_state
        db.session.commit()
        db.session.expire_all()
        assert db.session.get(CA, ca.id).serial == 2


def test_issuance_counts_one_per_certificate_on_sqlite(app):
    with app.app_context():
        ca_id = _ca_row(*_authority()).id
        for i in range(3):
            _issue(ca_id, f'sqlite-{i}.example.test')
        db.session.expire_all()
        assert db.session.get(CA, ca_id).serial == 3



def test_a_taken_random_serial_is_signed_again_once(app):
    """RFC 5280 §4.1.2.2: the second certificate cannot reuse a serial; one retry, then a clean failure."""
    from unittest.mock import patch
    from sqlalchemy.exc import IntegrityError
    taken = x509.random_serial_number()
    with app.app_context():
        ca_id = _ca_row(*_authority()).id
        with patch('cryptography.x509.random_serial_number', return_value=taken):
            _issue(ca_id, 'first.example.test')
        fresh = x509.random_serial_number()
        with patch('cryptography.x509.random_serial_number', side_effect=[taken, fresh]):
            _, second = _issue(ca_id, 'second.example.test')
        assert int(second, 16) == fresh
        with patch('cryptography.x509.random_serial_number', return_value=taken), \
                pytest.raises(IntegrityError):
            _issue(ca_id, 'third.example.test')
        db.session.expire_all()
        assert db.session.get(CA, ca_id).serial == 2


def _signed_serial(row):
    import base64
    return x509.load_pem_x509_certificate(base64.b64decode(row.crt)).serial_number


def test_a_collision_keeps_the_rows_the_caller_flushed(app):
    """ACME flushes its request row before signing: a retry rolls back its own attempt, not that row."""
    import base64
    from unittest.mock import patch
    from cryptography.hazmat.primitives import serialization
    from services.cert_service import CertificateService
    taken = x509.random_serial_number()
    with app.app_context():
        ca = _ca_row(*_authority())
        ca_id, caref = ca.id, ca.refid
        with patch('cryptography.x509.random_serial_number', return_value=taken):
            _issue(ca_id, 'first-flushed.example.test')
        csr_pem = _csr('acme-flushed.example.test').public_bytes(serialization.Encoding.PEM)
        request = Certificate(refid=uuid.uuid4().hex[:16], descr='acme-shaped', caref=caref,
                              csr=base64.b64encode(csr_pem).decode(), cert_type='server_cert',
                              source='acme', created_by='acme')
        db.session.add(request)
        db.session.flush()
        request_id = request.id
        fresh = x509.random_serial_number()
        with patch('cryptography.x509.random_serial_number', side_effect=[taken, fresh]):
            signed = CertificateService.sign_csr(cert_id=request_id, caref=caref, validity_days=30)
        db.session.expire_all()
        stored = db.session.get(Certificate, request_id)
        assert signed.id == request_id and stored is not None and stored.source == 'acme'
        assert _signed_serial(stored) == fresh
        assert db.session.get(CA, ca_id).serial == 2


def test_a_second_collision_rolls_back_only_the_signing_attempt(app):
    from unittest.mock import patch
    from sqlalchemy.exc import IntegrityError
    taken = x509.random_serial_number()
    with app.app_context():
        ca = _ca_row(*_authority())
        ca_id, caref = ca.id, ca.refid
        with patch('cryptography.x509.random_serial_number', return_value=taken):
            _issue(ca_id, 'first-kept.example.test')
        decision = Certificate(refid=uuid.uuid4().hex[:16], descr='caller row', caref=caref,
                               cert_type='server_cert', source='test')
        db.session.add(decision)
        db.session.flush()
        decision_id = decision.id
        with patch('cryptography.x509.random_serial_number', return_value=taken), \
                pytest.raises(IntegrityError):
            _issue(ca_id, 'second-kept.example.test')
        assert db.session.get(Certificate, decision_id) is not None
        db.session.commit()
        db.session.expire_all()
        assert db.session.get(Certificate, decision_id).descr == 'caller row'
        assert db.session.get(CA, ca_id).serial == 1


def _stale(ca):
    from sqlalchemy.orm.attributes import set_committed_value
    set_committed_value(ca, 'serial', 0)  # what this worker read before another one issued


def _by_create_certificate(ca):
    from services.cert_service import CertificateService
    CertificateService.create_certificate(
        descr='stale count', caref=ca.refid, dn={'CN': 'stale-create.example.test'},
        key_type='secp256r1', validity_days=30)


def _by_sign_csr(ca):
    from services.cert_service import CertificateService
    csr_row = CertificateService.generate_csr(
        descr='stale count csr', dn={'CN': 'stale-csr.example.test'}, key_type='2048')
    db.session.commit()
    _stale(ca)  # the commit reloaded the CA row
    CertificateService.sign_csr(cert_id=csr_row.id, caref=ca.refid, validity_days=30)


def _by_sign_csr_from_crypto(ca):
    _issue(ca.id, 'stale-crypto.example.test')


def _by_intermediate(ca):
    from services.ca import CAService
    CAService.create_internal_ca(descr='stale count sub', dn={'CN': 'stale count sub'},
                                 key_type='secp256r1', caref=ca.refid, validity_days=365)


def _by_increment_serial(ca):
    from services.ca import CAService
    CAService.increment_serial(ca.id)


@pytest.mark.parametrize('issue', [_by_create_certificate, _by_sign_csr, _by_sign_csr_from_crypto,
                                   _by_intermediate, _by_increment_serial])
def test_every_site_counts_from_the_database_not_from_a_stale_row(app, create_ca, issue):
    """Another worker counted meanwhile: the site adds one to the stored count, not to its copy."""
    ca_id = create_ca(cn=f'Stale count {issue.__name__}')['id']
    with app.app_context():
        db.session.execute(CA.__table__.update().where(CA.__table__.c.id == ca_id).values(serial=10))
        db.session.commit()
        ca = db.session.get(CA, ca_id)
        _stale(ca)
        issue(ca)
        db.session.commit()
        db.session.expire_all()
        assert db.session.get(CA, ca_id).serial == 11


def _race(app, url, ca_id):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy import text
    errors, backends, start = [], set(), threading.Barrier(WORKERS)

    def worker(n):
        engine = create_engine(url, pool_size=1, max_overflow=0)
        try:
            with app.app_context():
                # This thread's db.session is a session on its own engine
                db.session.registry.set(Session(bind=engine))
                backends.add(db.session.execute(text('SELECT pg_backend_pid()')).scalar())
                db.session.commit()
                start.wait(10)
                for i in range(EACH):
                    _issue(ca_id, f'w{n}-{i}.example.test')
                db.session.remove()
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))
        finally:
            engine.dispose()

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(WORKERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(180)
    return errors, backends


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_concurrent_issuance_on_postgresql_keeps_serials_and_count(app):
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

    schema = f'serial_race_{uuid.uuid4().hex[:6]}'
    with _a_schema_of_our_own(schema) as url, _bound_to(app, url, is_postgresql=True):
        with app.app_context():
            ca = _ca_row(*_authority())
            ca_id, caref = ca.id, ca.refid
            db.session.remove()
        errors, backends = _race(app, url, ca_id)
        with app.app_context():
            serials = [s for (s,) in db.session.query(Certificate.serial_number)
                       .filter_by(caref=caref)]
            count = db.session.get(CA, ca_id).serial
            db.session.remove()
    assert errors == []
    assert len(backends) == WORKERS
    assert len(serials) == len(set(serials)) == WORKERS * EACH
    assert count == WORKERS * EACH


def test_next_ca_serial_counts_on_a_dialect_without_update_returning(app, monkeypatch):
    """SQLite before 3.35 (el9 system library) has no UPDATE ... RETURNING: SQLAlchemy says so
    through the dialect, and the counter still counts."""
    from sqlalchemy import event
    from utils.ca_serial_counter import next_ca_serial

    def refuse_returning(conn, cursor, statement, *args):
        if 'RETURNING' in statement.upper():
            raise RuntimeError('RETURNING is not available on this database')

    with app.app_context():
        engine = db.session.get_bind()
        ca = _ca_row(*_authority())
        monkeypatch.setattr(engine.dialect, 'update_returning', False)
        event.listen(engine, 'before_cursor_execute', refuse_returning)
        try:
            assert [next_ca_serial(ca), next_ca_serial(ca)] == [1, 2]
        finally:
            event.remove(engine, 'before_cursor_execute', refuse_returning)
        assert ca.serial == 2 and 'serial' not in db.inspect(ca).committed_state
        db.session.commit()
        db.session.expire_all()
        assert db.session.get(CA, ca.id).serial == 2


def test_increment_serial_returns_its_own_count_not_a_later_one(app):
    """Another worker counts right after this commit: the value returned is still this call's."""
    from sqlalchemy import event
    from services.ca import CAService
    with app.app_context():
        ca_id = _ca_row(*_authority()).id
        session, engine = db.session(), db.engine

        def another_worker_counts(_session):
            with engine.begin() as other:
                other.execute(CA.__table__.update().where(CA.__table__.c.id == ca_id)
                              .values(serial=CA.__table__.c.serial + 1))

        event.listen(session, 'after_commit', another_worker_counts, once=True)
        assert CAService.increment_serial(ca_id) == 1
        db.session.expire_all()
        assert db.session.get(CA, ca_id).serial == 2

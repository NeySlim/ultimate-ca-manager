"""One CRL issuer never publishes two CRLs under the same number (RFC 5280 §5.2.3).

The number continues after a restore on another installation and after the CA
is deleted and imported again, and two generations running at once, in two
processes as the web worker and the scheduler do, get two numbers, the higher
one listing what the lower one did.
"""
import base64
import multiprocessing
import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from models import CA, db
from models.crl import CRLMetadata
from services.crl_service import CRLService

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
_on_pg = [pytest.mark.postgres,
          pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')]


def _authority(common_name=None):
    common_name = common_name or f'CRL number CA {uuid.uuid4().hex[:8]}'
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
                           critical=False)
            .sign(key, hashes.SHA256()))
    return key, cert


def _ca_row(key, cert, refid=None):
    from utils.key_codec import store_pem_bytes
    refid = refid or str(uuid.uuid4())
    ca = CA(refid=refid, descr=f'CRL number {refid[:8]}', url_slug=refid,
            crt=base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode(),
            prv=store_pem_bytes(key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption())),
            subject=cert.subject.rfc4514_string(), issuer=cert.issuer.rfc4514_string(),
            serial_number=format(cert.serial_number, 'x'),
            valid_from=cert.not_valid_before_utc.replace(tzinfo=None),
            valid_to=cert.not_valid_after_utc.replace(tzinfo=None),
            cdp_enabled=True)
    db.session.add(ca)
    db.session.commit()
    return ca


def _an_admin():
    """A replacing restore refuses an archive without accounts."""
    from models import User
    user = User(username=f'crl-admin-{uuid.uuid4().hex[:6]}', email='crl-admin@example.test',
                role='admin')
    user.set_password('Crl-Number-Pass1!')
    db.session.add(user)
    db.session.commit()


def _number_in(crl_metadata):
    crl = x509.load_der_x509_crl(crl_metadata.crl_der)
    return crl.extensions.get_extension_for_class(x509.CRLNumber).value.crl_number


# --------------------------------------------------------------------------
# Restore on another installation
# --------------------------------------------------------------------------

def test_a_restore_on_another_installation_continues_the_numbering(app, tmp_path):
    from tests.test_backup_cross_installation import Keys, PASSWORD, _installation, _service

    source, target = Keys(tmp_path, 'source'), Keys(tmp_path, 'target')
    key, cert = _authority()
    with _installation(app, f"sqlite:///{tmp_path / 'source.db'}", source), app.app_context():
        _an_admin()
        ca = _ca_row(key, cert)
        published = [CRLService.generate_crl(ca.id).crl_number for _ in range(5)]
        assert published == [1, 2, 3, 4, 5]
        blob = _service().create_backup(PASSWORD)
        db.session.remove()

    with _installation(app, f"sqlite:///{tmp_path / 'target.db'}", target), app.app_context():
        _service().restore_backup(blob, PASSWORD)
        restored = CA.query.filter_by(refid=ca.refid).one()
        crl = CRLService.generate_crl(restored.id)
        assert crl.crl_number == 6
        assert _number_in(crl) == 6
        db.session.remove()


def test_a_restore_never_lowers_the_number_reached_here(app, tmp_path):
    """An older archive restored over the same CA keeps the higher number."""
    from tests.test_backup_cross_installation import Keys, PASSWORD, _installation, _service

    keys = Keys(tmp_path, 'only')
    key, cert = _authority()
    with _installation(app, f"sqlite:///{tmp_path / 'only.db'}", keys), app.app_context():
        _an_admin()
        ca = _ca_row(key, cert)
        CRLService.generate_crl(ca.id)
        blob = _service().create_backup(PASSWORD)
        for _ in range(4):
            CRLService.generate_crl(ca.id)
        CRLMetadata.query.filter_by(ca_id=ca.id).delete()
        db.session.commit()
        _service().restore_backup(blob, PASSWORD)
        restored = CA.query.filter_by(refid=ca.refid).one()
        assert CRLService.generate_crl(restored.id).crl_number == 6
        db.session.remove()


def test_a_replacing_restore_keeps_the_number_of_an_issuer_the_archive_lacks(app, tmp_path):
    """An archive older than the CA prunes the CA, never the number it published."""
    from tests.test_backup_cross_installation import Keys, PASSWORD, _installation, _service

    keys = Keys(tmp_path, 'older')
    key, cert = _authority()
    with _installation(app, f"sqlite:///{tmp_path / 'older.db'}", keys), app.app_context():
        _an_admin()
        blob = _service().create_backup(PASSWORD)
        ca = _ca_row(key, cert)
        for _ in range(3):
            CRLService.generate_crl(ca.id)
        refid = ca.refid
        _service().restore_backup(blob, PASSWORD)
        db.session.expunge_all()
        assert CA.query.filter_by(refid=refid).first() is None
        again = _ca_row(key, cert)
        assert CRLService.generate_crl(again.id).crl_number == 4
        db.session.remove()


# --------------------------------------------------------------------------
# Deleted, then imported again
# --------------------------------------------------------------------------

def test_a_deleted_then_reimported_ca_continues_the_numbering(app):
    from services.ca.ca_crud import CAcrudMixin

    key, cert = _authority()
    with app.app_context():
        ca = _ca_row(key, cert)
        for _ in range(3):
            CRLService.generate_crl(ca.id)
        CAcrudMixin.delete_ca(ca.id)
        assert db.session.get(CA, ca.id) is None

        again = _ca_row(key, cert)
        crl = CRLService.generate_crl(again.id)
        assert crl.crl_number == 4
        assert _number_in(crl) == 4


def test_a_delta_continues_the_shared_numbering(app):
    key, cert = _authority()
    with app.app_context():
        ca = _ca_row(key, cert)
        ca.delta_crl_enabled = True
        db.session.commit()
        assert CRLService.generate_crl(ca.id).crl_number == 1   # its delta takes 2
        delta = CRLService.generate_delta_crl(ca.id)
        assert delta.crl_number == 3 and delta.base_crl_number == 1
        assert CRLService.generate_crl(ca.id).crl_number == 4


# --------------------------------------------------------------------------
# Two generations at once
# --------------------------------------------------------------------------

def _generate_in_child(app, url, ca_id, barrier, results):
    """One process of its own, with its own connection, as the scheduler has."""
    import services.crl.generation as generation

    engine = create_engine(url)
    db._app_engines[app][None] = engine
    allocate = generation.allocate_crl_number

    def meet_then_allocate(*args, **kwargs):
        # Both ask for a number at the same moment
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass
        return allocate(*args, **kwargs)

    generation.allocate_crl_number = meet_then_allocate
    try:
        with app.app_context():
            db.session.remove()
            results.put(CRLService.generate_crl(ca_id).crl_number)
            db.session.remove()
    except Exception as exc:  # noqa: BLE001
        results.put(repr(exc))
    finally:
        results.close()
        results.join_thread()
        os._exit(0)


def _race(app, url, ca_id):
    context = multiprocessing.get_context('fork')
    barrier, results = context.Barrier(2, timeout=3), context.Queue()
    children = [context.Process(target=_generate_in_child,
                                args=(app, url, ca_id, barrier, results))
                for _ in range(2)]
    for child in children:
        child.start()
    numbers = [results.get(timeout=30) for _ in children]
    for child in children:
        child.join(10)
    return numbers


def _two_processes(app, url, is_postgresql):
    from tests.test_backup_cross_installation import _bound_to

    key, cert = _authority()
    with _bound_to(app, url, is_postgresql=is_postgresql), app.app_context():
        ca = _ca_row(key, cert)
        CRLService.generate_crl(ca.id)
        ca_id = ca.id
        db.session.remove()
        engine = db.engine
        engine.dispose()  # no connection of the parent's is inherited
        numbers = _race(app, url, ca_id)
        stored = sorted(n for (n,) in db.session.query(CRLMetadata.crl_number)
                        .filter_by(ca_id=ca_id).all())
        db.session.remove()
    return numbers, stored


def test_two_processes_never_publish_the_same_number_on_sqlite(app, tmp_path):
    numbers, stored = _two_processes(app, f"sqlite:///{tmp_path / 'race.db'}", False)
    assert sorted(numbers) == [2, 3], numbers
    assert stored == [1, 2, 3]


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_two_processes_never_publish_the_same_number_on_postgresql(app):
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

    with _a_schema_of_our_own('crl_number_race') as url:
        numbers, stored = _two_processes(app, url, True)
    assert sorted(numbers) == [2, 3], numbers
    assert stored == [1, 2, 3]


def _second_waits_for_the_first(app, url, is_postgresql):
    """The first allocation holds its number uncommitted while the second asks for one."""
    from tests.test_backup_cross_installation import _bound_to
    from services.crl.numbering import allocate_crl_number

    key, cert = _authority()
    locked, asked, result = threading.Event(), threading.Event(), {}

    def allocate(name, before=None, after=None):
        try:
            with app.app_context():
                ca = db.session.get(CA, ca_id)
                if before:
                    before.wait(10)
                number = allocate_crl_number(ca, cert)
                if after:
                    after.set()
                    asked.wait(10)
                    time.sleep(0.5)  # the second is now inside its allocation
                now = datetime(2026, 1, 1)
                db.session.add(CRLMetadata(ca_id=ca_id, crl_number=number, this_update=now,
                                           next_update=now, crl_pem='x', crl_der=b'x'))
                db.session.commit()
                result[name] = number
                db.session.remove()
        except Exception as exc:  # noqa: BLE001
            result[name] = repr(exc)

    with _bound_to(app, url, is_postgresql=is_postgresql), app.app_context():
        ca_id = _ca_row(key, cert).id
        db.session.remove()
        first = threading.Thread(target=allocate, args=('first',), kwargs={'after': locked})
        second = threading.Thread(target=lambda: (locked.wait(10), asked.set(), allocate('second')))
        first.start()
        second.start()
        first.join(30)
        second.join(30)
    return result


def test_a_second_allocation_waits_for_the_first_on_sqlite(app, tmp_path):
    assert _second_waits_for_the_first(app, f"sqlite:///{tmp_path / 'held.db'}", False) \
        == {'first': 1, 'second': 2}


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_a_second_allocation_waits_for_the_first_on_postgresql(app):
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

    with _a_schema_of_our_own('crl_number_held') as url:
        assert _second_waits_for_the_first(app, url, True) == {'first': 1, 'second': 2}


def _leaf_of(ca_key, ca_cert, ca):
    from models import Certificate
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.now(timezone.utc)
    leaf = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'leaf')]))
            .issuer_name(ca_cert.subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=90))
            .sign(ca_key, hashes.SHA256()))
    row = Certificate(
        refid=f'crl-race-{uuid.uuid4().hex[:10]}', descr='race', caref=ca.refid,
        crt=base64.b64encode(leaf.public_bytes(serialization.Encoding.PEM)).decode(),
        serial_number=format(leaf.serial_number, 'x'),
        subject=leaf.subject.rfc4514_string(), issuer=leaf.issuer.rfc4514_string(),
        valid_from=(now - timedelta(days=1)).replace(tzinfo=None),
        valid_to=(now + timedelta(days=90)).replace(tzinfo=None))
    db.session.add(row)
    db.session.commit()
    return row.id, leaf.serial_number


def _revocation_between_read_and_number(app, url, is_postgresql, generate):
    """A reads its revocations; B revokes a serial and publishes; A then publishes.

    RFC 5280 §5.2.3 and §3.3: the CRL with the higher number is the newer one
    and still lists what a lower one listed.
    """
    from models import Certificate
    from services.crl.query import CRLQueryMixin
    from tests.test_backup_cross_installation import _bound_to

    key, cert = _authority()
    a_read, b_done, errors = threading.Event(), threading.Event(), []
    original = CRLQueryMixin._filter_orphan_serials

    def read_then_wait(*args, **kwargs):
        listed = original(*args, **kwargs)
        if threading.current_thread().name == 'A':
            a_read.set()
            b_done.wait(1.5)  # held lock: B cannot publish meanwhile
        return listed

    def run(name, body):
        try:
            with app.app_context():
                body()
                db.session.remove()
        except Exception as exc:  # noqa: BLE001
            errors.append(f'{name}: {exc!r}')

    def b_body():
        a_read.wait(10)
        row = db.session.get(Certificate, cert_id)
        row.revoked, row.revoke_reason = True, 'keyCompromise'
        row.revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.session.commit()
        generate(ca_id)
        b_done.set()

    with _bound_to(app, url, is_postgresql=is_postgresql), app.app_context():
        ca = _ca_row(key, cert)
        ca.delta_crl_enabled = generate is CRLService.generate_delta_crl
        db.session.commit()
        ca_id = ca.id
        cert_id, serial = _leaf_of(key, cert, ca)
        CRLService.generate_crl(ca_id)
        db.session.remove()
        CRLQueryMixin._filter_orphan_serials = staticmethod(read_then_wait)
        try:
            threads = [threading.Thread(name='A', target=run, args=('A', lambda: generate(ca_id))),
                       threading.Thread(name='B', target=run, args=('B', b_body))]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(30)
        finally:
            CRLQueryMixin._filter_orphan_serials = staticmethod(original)
        newest = (CRLMetadata.query.filter_by(ca_id=ca_id)
                  .order_by(CRLMetadata.crl_number.desc()).first())
        served = [newest] + CRLMetadata.query.filter_by(
            ca_id=ca_id, crl_number=newest.base_crl_number).all()  # a delta is read with its base
        listed = {entry.serial_number for row in served
                  for entry in x509.load_der_x509_crl(row.crl_der)}
        db.session.remove()
    assert not errors, errors
    return serial in listed


@pytest.mark.parametrize('kind', ['full', 'delta'])
def test_the_highest_number_lists_a_revocation_made_meanwhile_on_sqlite(app, tmp_path, kind):
    generate = {'full': CRLService.generate_crl, 'delta': CRLService.generate_delta_crl}[kind]
    assert _revocation_between_read_and_number(
        app, f"sqlite:///{tmp_path / 'between.db'}", False, generate)


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
@pytest.mark.parametrize('kind', ['full', 'delta'])
def test_the_highest_number_lists_a_revocation_made_meanwhile_on_postgresql(app, kind):
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

    generate = {'full': CRLService.generate_crl, 'delta': CRLService.generate_delta_crl}[kind]
    with _a_schema_of_our_own(f'crl_number_between_{kind}') as url:
        assert _revocation_between_read_and_number(app, url, True, generate)


def test_the_schema_refuses_two_crls_under_one_number():
    """create_all builds fresh installations: the model carries the index."""
    engine = create_engine('sqlite://')
    CA.__table__.create(engine)
    CRLMetadata.__table__.create(engine)
    now = datetime(2026, 1, 1)
    row = dict(ca_id=1, crl_number=7, this_update=now, next_update=now, crl_pem='x', crl_der=b'x')
    with engine.begin() as conn:
        conn.execute(CRLMetadata.__table__.insert().values(**row))
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(CRLMetadata.__table__.insert().values(**row))
    with engine.connect() as conn:
        indexes = {r[1]: r[2] for r in conn.execute(text("PRAGMA index_list(crl_metadata)"))}
    assert indexes.get('uix_crl_ca_number') == 1


def _write_while_signing(app, url, generate, monkeypatch):
    """Another connection writes while the CRL is being signed (a remote HSM is slow)."""
    import sqlite3
    from services.crl import generation
    from tests.test_backup_cross_installation import _bound_to

    key, cert = _authority()
    signing, written, outcome = threading.Event(), threading.Event(), {}
    original = generation.rsa_padding_for

    def slow_padding(*args, **kwargs):
        if threading.current_thread().name == 'signer':
            signing.set()
            written.wait(5)
        return original(*args, **kwargs)

    def sign():
        try:
            with app.app_context():
                generate(ca_id)
                db.session.remove()
        except Exception as exc:  # noqa: BLE001
            outcome['signer'] = repr(exc)

    with _bound_to(app, url), app.app_context():
        ca = _ca_row(key, cert)
        ca.delta_crl_enabled = True
        db.session.commit()
        ca_id = ca.id
        CRLService.generate_crl(ca_id)
        db.session.remove()
        monkeypatch.setattr(generation, 'rsa_padding_for', slow_padding)
        signer = threading.Thread(name='signer', target=sign)
        signer.start()
        try:
            assert signing.wait(10)
            other = sqlite3.connect(url.removeprefix('sqlite:///'), timeout=0.3)
            try:
                other.execute("UPDATE certificate_authorities SET descr = 'written' WHERE id = ?",
                              (ca_id,))
                other.commit()
                outcome['writer'] = 'ok'
            except sqlite3.OperationalError as exc:
                outcome['writer'] = str(exc)
            finally:
                other.close()
        finally:
            written.set()
            signer.join(30)
    return outcome


@pytest.mark.parametrize('kind', ['full', 'delta'])
def test_the_database_is_not_locked_while_the_crl_is_signed(app, tmp_path, monkeypatch, kind):
    generate = {'full': CRLService.generate_crl, 'delta': CRLService.generate_delta_crl}[kind]
    outcome = _write_while_signing(app, f"sqlite:///{tmp_path / 'signing.db'}", generate,
                                   monkeypatch)
    assert outcome == {'writer': 'ok'}, outcome

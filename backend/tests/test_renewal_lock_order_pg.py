"""A protocol renewal and an in-place renewal of one certificate never deadlock.

Both lock the certificate row before the CA row (its issuance counter), so the
second one waits for the first instead of each holding what the other needs.
"""
import os
import threading
import time
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from models import CA, Certificate, db
from tests.test_crl_number_monotonic import _authority, _ca_row

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
pytestmark = [pytest.mark.postgres,
              pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')]


def _csr(name):
    key = ec.generate_private_key(ec.SECP256R1())
    return (x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
            .sign(key, hashes.SHA256()))


def _own_session(url):
    engine = create_engine(url, pool_size=1, max_overflow=0)
    db.session.registry.set(Session(bind=engine))
    pid = db.session.execute(text('SELECT pg_backend_pid()')).scalar()
    db.session.commit()
    return engine, pid


def _waits_on_a_lock(url, pid, timeout=15):
    probe = create_engine(url, pool_size=1, max_overflow=0)
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with probe.connect() as c:
                if c.execute(text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :p"),
                             {'p': pid}).scalar() == 'Lock':
                    return True
            time.sleep(0.05)
        return False
    finally:
        probe.dispose()


def test_protocol_and_in_place_renewals_of_one_certificate_do_not_deadlock(app, monkeypatch):
    from services.ca import CAService
    from services.cert import renewal
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

    schema = f'renewal_order_{uuid.uuid4().hex[:6]}'
    with _a_schema_of_our_own(schema) as url, _bound_to(app, url, is_postgresql=True):
        with app.app_context():
            ca = _ca_row(*_authority())
            ca_id = ca.id
            from services.cert_service import CertificateService
            cert_id = CertificateService.create_certificate(
                descr='both', caref=ca.refid, dn={'CN': 'both.example.test'},
                key_type='prime256v1', validity_days=30).id
            db.session.remove()

        holds, release = threading.Event(), threading.Event()
        errors, pids = [], {}
        recorded = renewal._record_scts

        def pause_holding_the_row(*args):
            recorded(*args)
            if threading.current_thread().name == 'in-place':
                holds.set()
                release.wait(30)
        monkeypatch.setattr(renewal, '_record_scts', pause_holding_the_row)

        def in_place():
            with app.app_context():
                engine, pids['in-place'] = _own_session(url)
                try:
                    renewal.renew_certificate_in_place(db.session.get(Certificate, cert_id),
                                                       db.session.get(CA, ca_id))
                except Exception as exc:  # noqa: BLE001
                    errors.append(('in-place', repr(exc)))
                finally:
                    holds.set()
                    db.session.remove()
                    engine.dispose()

        def protocol():
            with app.app_context():
                engine, pids['protocol'] = _own_session(url)
                try:
                    row = db.session.get(Certificate, cert_id)
                    CAService.sign_csr_from_crypto(db.session.get(CA, ca_id),
                                                   _csr('both.example.test'), validity_days=30,
                                                   source='test-renewal', supersedes=row)
                except Exception as exc:  # noqa: BLE001
                    errors.append(('protocol', repr(exc)))
                finally:
                    db.session.remove()
                    engine.dispose()

        a = threading.Thread(target=in_place, name='in-place')
        a.start()
        assert holds.wait(30)
        b = threading.Thread(target=protocol, name='protocol')
        b.start()
        # The protocol side blocks on a row the in-place side holds, then that one goes on
        blocked = _waits_on_a_lock(url, _pid_of(pids, 'protocol'))
        release.set()
        a.join(60)
        b.join(60)

        with app.app_context():
            count = db.session.get(CA, ca_id).serial
            db.session.remove()
    assert blocked, errors
    assert errors == []
    assert count == 3


def _pid_of(pids, name, timeout=10):
    deadline = time.monotonic() + timeout
    while name not in pids and time.monotonic() < deadline:
        time.sleep(0.02)
    return pids[name]


def _done_or_waiting(url, pids, name, thread, timeout=15):
    """True once *thread* has finished or waits on a row lock."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not thread.is_alive():
            return True
        if name in pids and _waits_on_a_lock(url, pids[name], timeout=0.2):
            return True
    return False


def test_in_place_renewal_of_a_pair_and_a_protocol_renewal_of_b_do_not_deadlock(app, monkeypatch):
    """The pair locks A then B; the protocol renewal of B locks B then the CA row.
    The CA row must come after both members, or the two wait on each other."""
    from services.ca import CAService
    from services.cert import renewal
    from services.cert_service import CertificateService
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

    schema = f'renewal_pair_{uuid.uuid4().hex[:6]}'
    with _a_schema_of_our_own(schema) as url, _bound_to(app, url, is_postgresql=True):
        with app.app_context():
            ca = _ca_row(*_authority())
            ca_id = ca.id
            a, b = (CertificateService.create_certificate(
                descr=n, caref=ca.refid, dn={'CN': f'{n}.example.test'},
                key_type='prime256v1', validity_days=30) for n in ('pair-a', 'pair-b'))
            a.related_certificate_id, b.related_certificate_id = b.id, a.id
            a_id, b_id = a.id, b.id
            db.session.commit()
            db.session.remove()

        holds, release = threading.Event(), threading.Event()
        errors, pids, rereads = [], {}, []
        reread = renewal._reread

        def pause_before_the_second_member(*args):
            if threading.current_thread().name == 'in-place':
                rereads.append(args[0].id)
                if len(rereads) == 2:
                    holds.set()
                    release.wait(30)
            return reread(*args)
        monkeypatch.setattr(renewal, '_reread', pause_before_the_second_member)

        def in_place():
            with app.app_context():
                engine, pids['in-place'] = _own_session(url)
                try:
                    renewal.renew_certificate_in_place(db.session.get(Certificate, a_id),
                                                       db.session.get(CA, ca_id))
                except Exception as exc:  # noqa: BLE001
                    errors.append(('in-place', repr(exc)))
                finally:
                    holds.set()
                    db.session.remove()
                    engine.dispose()

        def protocol():
            with app.app_context():
                engine, pids['protocol'] = _own_session(url)
                try:
                    row = db.session.get(Certificate, b_id)
                    CAService.sign_csr_from_crypto(db.session.get(CA, ca_id),
                                                   _csr('pair-b.example.test'), validity_days=30,
                                                   source='test-renewal', supersedes=row)
                except Exception as exc:  # noqa: BLE001
                    errors.append(('protocol', repr(exc)))
                finally:
                    db.session.remove()
                    engine.dispose()

        t_a = threading.Thread(target=in_place, name='in-place')
        t_a.start()
        assert holds.wait(30)
        t_b = threading.Thread(target=protocol, name='protocol')
        t_b.start()
        settled = _done_or_waiting(url, pids, 'protocol', t_b)
        release.set()
        t_a.join(60)
        t_b.join(60)

        with app.app_context():
            count = db.session.get(CA, ca_id).serial
            db.session.remove()
    assert settled
    assert rereads == [a_id, b_id]
    assert errors == []
    assert count == 5


def test_in_place_renewal_and_the_responder_task_on_one_responder_do_not_deadlock(app, monkeypatch):
    """The in-place renewal locks the responder row then the CA row; the responder
    task archives that row and must count only afterwards, in the same order."""
    from datetime import timedelta

    from models import SystemConfig
    from services.cert import renewal
    from services.cert_service import CertificateService
    from services.ocsp_responder_renewal import run_ocsp_responder_renewal
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own
    from utils.datetime_utils import utc_now

    schema = f'renewal_responder_{uuid.uuid4().hex[:6]}'
    with _a_schema_of_our_own(schema) as url, _bound_to(app, url, is_postgresql=True):
        with app.app_context():
            ca = _ca_row(*_authority())
            ca_id = ca.id
            row = CertificateService.create_certificate(
                descr='responder', caref=ca.refid, dn={'CN': 'responder.example.test'},
                key_type='prime256v1', validity_days=30)
            row.valid_to = utc_now() + timedelta(hours=1)
            cert_id = row.id
            db.session.add(SystemConfig(key=f'ocsp_responder_cert_{ca_id}', value=str(cert_id)))
            db.session.commit()
            db.session.remove()

        holds, release = threading.Event(), threading.Event()
        errors, pids, stats = [], {}, {}
        recorded = renewal._record_scts

        def pause_holding_the_row(*args):
            recorded(*args)
            if threading.current_thread().name == 'in-place':
                holds.set()
                release.wait(30)
        monkeypatch.setattr(renewal, '_record_scts', pause_holding_the_row)

        def in_place():
            with app.app_context():
                engine, pids['in-place'] = _own_session(url)
                try:
                    renewal.renew_certificate_in_place(db.session.get(Certificate, cert_id),
                                                       db.session.get(CA, ca_id))
                except Exception as exc:  # noqa: BLE001
                    errors.append(('in-place', repr(exc)))
                finally:
                    holds.set()
                    db.session.remove()
                    engine.dispose()

        def responder_task():
            with app.app_context():
                engine, pids['responder'] = _own_session(url)
                try:
                    stats.update(run_ocsp_responder_renewal())
                finally:
                    db.session.remove()
                    engine.dispose()

        t_a = threading.Thread(target=in_place, name='in-place')
        t_a.start()
        assert holds.wait(30)
        t_b = threading.Thread(target=responder_task, name='responder')
        t_b.start()
        # The task waits on the row the in-place renewal holds, then that one goes on
        blocked = _waits_on_a_lock(url, _pid_of(pids, 'responder'))
        release.set()
        t_a.join(60)
        t_b.join(60)

        with app.app_context():
            count = db.session.get(CA, ca_id).serial
            db.session.remove()
    assert blocked
    assert errors == []
    assert (stats.get('renewed'), stats.get('failed')) == (1, 0)
    assert count == 3


def _race_with_an_in_place_renewal(app, url, monkeypatch, held_id, ca_id, other):
    """Renew *held_id* in place, paused while it holds that row, and run *other* meanwhile.
    Returns (other waited on a lock, errors); a lock-order inversion is a deadlock error."""
    from services.cert import renewal
    holds, release = threading.Event(), threading.Event()
    errors, pids = [], {}
    recorded = renewal._record_scts

    def pause_holding_the_row(*args):
        recorded(*args)
        if threading.current_thread().name == 'in-place':
            holds.set()
            release.wait(30)
    monkeypatch.setattr(renewal, '_record_scts', pause_holding_the_row)

    def run(name, work):
        with app.app_context():
            engine, pids[name] = _own_session(url)
            try:
                work()
            except Exception as exc:  # noqa: BLE001
                errors.append((name, repr(exc)))
            finally:
                holds.set()
                db.session.remove()
                engine.dispose()

    t_a = threading.Thread(target=run, name='in-place', args=('in-place', lambda: (
        renewal.renew_certificate_in_place(db.session.get(Certificate, held_id),
                                           db.session.get(CA, ca_id)))))
    t_a.start()
    assert holds.wait(30)
    t_b = threading.Thread(target=run, name='other', args=('other', other))
    t_b.start()
    blocked = _waits_on_a_lock(url, _pid_of(pids, 'other'))
    release.set()
    t_a.join(60)
    t_b.join(60)
    return blocked, errors


def _a_with_its_key(ca, name):
    from cryptography.hazmat.primitives import serialization
    from services.cert_service import CertificateService
    from utils.key_codec import load_pem_bytes
    row = CertificateService.create_certificate(
        descr=name, caref=ca.refid, dn={'CN': f'{name}.example.test'},
        san_dns=[f'{name}.example.test'], key_type='prime256v1', validity_days=30)
    import base64
    cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
    key = serialization.load_pem_private_key(load_pem_bytes(row.prv, context='test'), None)
    return row.id, cert, key


def _csr_naming_a(cert_a, key_a):
    from utils import related_cert
    key_b = ec.generate_private_key(ec.SECP256R1())
    csr = (x509.CertificateSigningRequestBuilder().subject_name(cert_a.subject)
           .add_extension(cert_a.extensions.get_extension_for_class(x509.SubjectAlternativeName).value,
                          critical=False)
           .sign(key_b, hashes.SHA256()))
    request = related_cert.build_request(cert_a, key_a, related_cert.data_url_for([cert_a]))
    return related_cert.csr_with_request(csr, key_b, request)


def test_a_protocol_issuance_naming_a_and_an_in_place_renewal_of_a_do_not_deadlock(app, monkeypatch):
    """The issuance of B writes A's link back: that row is locked before the CA row."""
    from services.ca import CAService
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

    with _a_schema_of_our_own(f'related_protocol_{uuid.uuid4().hex[:6]}') as url, \
            _bound_to(app, url, is_postgresql=True):
        with app.app_context():
            ca = _ca_row(*_authority())
            ca_id = ca.id
            a_id, cert_a, key_a = _a_with_its_key(ca, 'related-a')
            db.session.remove()
        csr = _csr_naming_a(cert_a, key_a)

        blocked, errors = _race_with_an_in_place_renewal(
            app, url, monkeypatch, a_id, ca_id, lambda: CAService.sign_csr_from_crypto(
                db.session.get(CA, ca_id), csr, validity_days=30, source='est'))

        with app.app_context():
            count = db.session.get(CA, ca_id).serial
            db.session.remove()
    assert blocked, errors
    assert errors == []
    assert count == 3


def test_a_signed_csr_naming_a_and_an_in_place_renewal_of_a_do_not_deadlock(app, monkeypatch):
    """Signing a stored CSR that names A writes A's link back before the CA row."""
    from cryptography.hazmat.primitives import serialization
    from services.cert_service import CertificateService
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

    with _a_schema_of_our_own(f'related_csr_{uuid.uuid4().hex[:6]}') as url, \
            _bound_to(app, url, is_postgresql=True):
        with app.app_context():
            ca = _ca_row(*_authority())
            ca_id, ca_refid = ca.id, ca.refid
            a_id, cert_a, key_a = _a_with_its_key(ca, 'related-a')
            pending = Certificate(refid=uuid.uuid4().hex[:8], descr='related-b',
                                  csr=_csr_naming_a(cert_a, key_a).public_bytes(
                                      serialization.Encoding.PEM).decode())
            db.session.add(pending)
            db.session.commit()
            csr_id = pending.id
            db.session.remove()

        blocked, errors = _race_with_an_in_place_renewal(
            app, url, monkeypatch, a_id, ca_id, lambda: CertificateService.sign_csr(
                cert_id=csr_id, caref=ca_refid, validity_days=30))

        with app.app_context():
            count = db.session.get(CA, ca_id).serial
            db.session.remove()
    assert blocked, errors
    assert errors == []
    assert count == 3


def test_a_renewal_that_unlinks_a_row_and_its_in_place_renewal_do_not_deadlock(app, monkeypatch):
    """R renewed alone unlinks the row P that names it: P is locked before the CA row,
    or R holds the CA row while P's own renewal holds P and waits for it."""
    from services.cert import renewal
    from services.cert_service import CertificateService
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

    with _a_schema_of_our_own(f'related_unlink_{uuid.uuid4().hex[:6]}') as url, \
            _bound_to(app, url, is_postgresql=True):
        with app.app_context():
            ca = _ca_row(*_authority())
            ca_id = ca.id
            r, p = (CertificateService.create_certificate(
                descr=n, caref=ca.refid, dn={'CN': f'{n}.example.test'},
                key_type='prime256v1', validity_days=30) for n in ('named-r', 'naming-p'))
            p.related_certificate_id = r.id
            r_id, p_id = r.id, p.id
            db.session.commit()
            db.session.remove()

        blocked, errors = _race_with_an_in_place_renewal(
            app, url, monkeypatch, p_id, ca_id, lambda: renewal.renew_certificate_in_place(
                db.session.get(Certificate, r_id), db.session.get(CA, ca_id)))

        with app.app_context():
            count = db.session.get(CA, ca_id).serial
            db.session.remove()
    assert blocked, errors
    assert errors == []
    assert count == 4

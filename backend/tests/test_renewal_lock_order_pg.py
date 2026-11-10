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

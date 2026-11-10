"""A manual and a scheduled renewal of the same certificate at once: one renews, the other is refused.

The renewal re-reads the row FOR UPDATE and swaps the serial only if it is still
the one it read (services.cert.renewal); on PostgreSQL the two run for real in parallel.
"""
import os
import threading
import uuid

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from models import Certificate, RevokedSerial, db
from tests.test_crl_number_monotonic import _authority, _ca_row
from tests.test_serial_concurrency_pg import _issue
from utils.key_codec import store_pem_bytes

_PG_URL = os.environ.get('UCM_TEST_PG_URL')


def _leaf(app):
    with app.app_context():
        ca = _ca_row(*_authority())
        _issue(ca.id, 'renewed-twice.example.test')
        cert = Certificate.query.filter_by(caref=ca.refid).one()
        # The server holds the key: the in-place renewal path, not the enrollment protocol
        cert.prv = store_pem_bytes(ec.generate_private_key(ec.SECP256R1()).private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
        db.session.commit()
        ids = cert.id, ca.refid, cert.serial_number
        db.session.remove()
    return ids


def _race(app, cert_id):
    from services.auto_renewal_service import AutoRenewalService
    from services.cert.renewal import RenewalError, renew_certificate_in_place

    both_read, outcome = threading.Barrier(2, timeout=10), {}

    def manual():
        with app.app_context():
            cert = db.session.get(Certificate, cert_id)
            both_read.wait()
            try:
                outcome['manual'] = renew_certificate_in_place(
                    cert, username='admin', regenerate_crl=False)['new_serial']
            except RenewalError as e:
                db.session.rollback()
                outcome['manual'] = e.status
            db.session.remove()

    def scheduled():
        with app.app_context():
            cert = db.session.get(Certificate, cert_id)
            both_read.wait()
            outcome['auto'] = AutoRenewalService.renew_certificate(cert, regenerate_crl=False)
            db.session.remove()

    threads = [threading.Thread(target=manual), threading.Thread(target=scheduled)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    return outcome


def _check(app, cert_id, caref, old_serial, outcome):
    manual_won = isinstance(outcome['manual'], str)
    auto_won = outcome['auto'] == (True, cert_id)
    assert manual_won != auto_won, outcome
    if manual_won:
        assert outcome['auto'][0] is False and 'renewed' in outcome['auto'][1].lower(), outcome
    else:
        assert outcome['manual'] == 409, outcome
    with app.app_context():
        row = db.session.get(Certificate, cert_id)
        assert row.renewed_times == 1
        assert row.serial_number != old_serial
        superseded = RevokedSerial.query.filter_by(caref=caref, revoke_reason='superseded').all()
        assert [r.serial_number for r in superseded] == [old_serial]
        db.session.remove()


def test_manual_and_scheduled_renewal_on_sqlite(app, tmp_path):
    from tests.test_backup_cross_installation import _bound_to

    with _bound_to(app, f"sqlite:///{tmp_path / 'renew.db'}"):
        cert_id, caref, old_serial = _leaf(app)
        _check(app, cert_id, caref, old_serial, _race(app, cert_id))


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_manual_and_scheduled_renewal_on_postgresql(app):
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

    with _a_schema_of_our_own(f'renew_race_{uuid.uuid4().hex[:6]}') as url, \
            _bound_to(app, url, is_postgresql=True):
        for _ in range(3):
            cert_id, caref, old_serial = _leaf(app)
            _check(app, cert_id, caref, old_serial, _race(app, cert_id))

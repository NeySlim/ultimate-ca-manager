"""A renewal overtaken by another one is refused as renewed meanwhile, never as revoked.

The winner records the old serial as superseded: a caller still holding the row it read
before must not read that record as a revocation of the certificate.
"""
import os
import threading
import uuid

import pytest

from models import Certificate, db
from tests.test_renewal_concurrency_pg import _leaf

_PG_URL = os.environ.get('UCM_TEST_PG_URL')


def _renew_elsewhere(app, cert_id):
    """Renew ``cert_id`` to completion in a session of its own."""
    from services.cert.renewal import renew_certificate_in_place

    done = {}

    def run():
        with app.app_context():
            try:
                done['serial'] = renew_certificate_in_place(
                    db.session.get(Certificate, cert_id), username='admin',
                    regenerate_crl=False)['new_serial']
            finally:
                db.session.remove()

    thread = threading.Thread(target=run)
    thread.start()
    thread.join(60)
    assert done.get('serial'), done


def _stale_check(app, cert_id):
    from services.cert.renewal import RenewalError, check_renewable
    with app.app_context():
        cert = db.session.get(Certificate, cert_id)
        _renew_elsewhere(app, cert_id)
        with pytest.raises(RenewalError) as e:
            check_renewable(cert)
        db.session.remove()
    return e.value


def test_the_routes_check_on_a_row_renewed_since_read_on_sqlite(app, tmp_path):
    from tests.test_backup_cross_installation import _bound_to
    with _bound_to(app, f"sqlite:///{tmp_path / 'overtaken.db'}"):
        cert_id, _, _ = _leaf(app)
        refusal = _stale_check(app, cert_id)
    assert refusal.status == 409 and 'renewed by another request' in refusal.message, refusal.message


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_the_routes_check_on_a_row_renewed_since_read_on_postgresql(app):
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own
    with _a_schema_of_our_own(f'renew_overtaken_{uuid.uuid4().hex[:6]}') as url, \
            _bound_to(app, url, is_postgresql=True):
        cert_id, _, _ = _leaf(app)
        refusal = _stale_check(app, cert_id)
    assert refusal.status == 409 and 'renewed by another request' in refusal.message, refusal.message


def _overtaken_after(monkeypatch, app, cert_id, step):
    """The other renewal commits right after ``step`` of this one has run (SQLite only:
    on PostgreSQL the row stays locked from the re-read to the commit)."""
    from services.cert import renewal
    real, fired = getattr(renewal, step), []

    def then_overtaken(*args, **kwargs):
        result = real(*args, **kwargs)
        if not fired:
            fired.append(True)
            _renew_elsewhere(app, cert_id)
        return result

    monkeypatch.setattr(renewal, step, then_overtaken)
    return fired


@pytest.mark.parametrize('step', ['_reread', 'check_renewable'])
@pytest.mark.parametrize('trigger', ['manual', 'auto'])
def test_a_renewal_overtaken_midway_says_renewed(app, tmp_path, monkeypatch, step, trigger):
    from services.auto_renewal_service import AutoRenewalService
    from services.cert.renewal import RenewalError, renew_certificate_in_place
    from tests.test_backup_cross_installation import _bound_to

    with _bound_to(app, f"sqlite:///{tmp_path / 'overtaken.db'}"):
        cert_id, _, _ = _leaf(app)
        fired = _overtaken_after(monkeypatch, app, cert_id, step)
        with app.app_context():
            cert = db.session.get(Certificate, cert_id)
            if trigger == 'auto':
                outcome = AutoRenewalService.renew_certificate(cert, regenerate_crl=False)
            else:
                try:
                    renew_certificate_in_place(cert, username='admin', regenerate_crl=False)
                    outcome = None
                except RenewalError as e:
                    db.session.rollback()
                    outcome = (e.status, e.message)
            db.session.remove()
    assert fired
    if trigger == 'auto':
        assert outcome == (False, 'Certificate was renewed by another request'), outcome
    else:
        assert outcome is not None and outcome[0] == 409, outcome
        assert 'renewed by another request' in outcome[1], outcome

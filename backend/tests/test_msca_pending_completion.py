"""The inventory sync finishes UCM's pending AD CS requests the CA shows issued or denied."""
import base64
import re

import pytest

from tests.deploy_leftovers import delete_leftovers
from tests.event_recorder import events  # noqa: F401
from tests.test_msca_inventory import FakeADCS, _make_msca

_cleanup = pytest.fixture(autouse=True)(delete_leftovers)


class DenyingADCS(FakeADCS):
    """FakeADCS that also lists denied requests (Disposition=31)."""

    def __init__(self):
        super().__init__()
        self.denied = []

    def run_ps(self, msca, script):
        if 'Disposition=31' in script:
            start = int(re.search(r'RequestId>=(\d+)', script).group(1))
            lines = ['"id","serial","exp","tpl","cn"']
            lines += [f'"{r}","","","WebServer","x"' for r in self.denied if r >= start]
            return '\n'.join(lines) + '\n'
        return super().run_ps(msca, script)


@pytest.fixture
def ca(monkeypatch):
    from services.msca.admin_channel import MicrosoftCAAdminChannelMixin
    fake = DenyingADCS()
    monkeypatch.setattr(MicrosoftCAAdminChannelMixin, '_run_ps', staticmethod(fake.run_ps))
    return fake


def _pending(app, msca_id, request_id, cn, status='pending', with_csr=True):
    from models import Certificate, MSCARequest, db
    with app.app_context():
        csr_id = None
        if with_csr:
            row = Certificate(refid=f'pc{request_id}', descr=cn, csr=base64.b64encode(b'csr').decode())
            db.session.add(row)
            db.session.flush()
            csr_id = row.id
        req = MSCARequest(msca_id=msca_id, csr_id=csr_id, template='WebServer',
                          status=status, request_id=request_id)
        db.session.add(req)
        db.session.commit()
        return req.id, csr_id


def _sync(app, msca_id, full=True):
    from services.msca_service import MicrosoftCAService
    with app.app_context():
        return MicrosoftCAService.inventory_sync(msca_id, full=full)


def _req(app, req_id):
    from models import MSCARequest, db
    with app.app_context():
        r = db.session.get(MSCARequest, req_id)
        return r.status, r.cert_id, r.error_message


def test_issued_pending_request_is_completed(app, ca):
    msca_id = _make_msca(app, 'PC issued')
    ca.add(4242, 'pc-issued.test.local')
    req_id, csr_id = _pending(app, msca_id, 4242, 'pc-issued.test.local')
    s = _sync(app, msca_id)
    assert (s['completed'], s['imported'], s['failed']) == (1, 0, 0)
    status, cert_id, _ = _req(app, req_id)
    assert (status, cert_id) == ('issued', csr_id)
    from models import Certificate, MSCARequest
    with app.app_context():
        assert Certificate.query.filter_by(subject_cn='pc-issued.test.local').count() == 1
        assert MSCARequest.query.filter_by(msca_id=msca_id).count() == 1


def test_incremental_sync_completes_a_request_below_the_high_water_mark(app, ca):
    msca_id = _make_msca(app, 'PC water')
    ca.add(10, 'pc-water-old.test.local')
    req_id, _ = _pending(app, msca_id, 4, 'pc-water.test.local')
    ca.add(4, 'pc-water.test.local')
    from models import MicrosoftCA, db
    with app.app_context():
        db.session.get(MicrosoftCA, msca_id).last_synced_request_id = 10
        db.session.commit()
    s = _sync(app, msca_id, full=False)
    assert s['completed'] == 1
    assert _req(app, req_id)[0] == 'issued'


def test_denied_pending_request_becomes_denied(app, ca):
    msca_id = _make_msca(app, 'PC denied')
    req_id, _ = _pending(app, msca_id, 77, 'pc-denied.test.local')
    ca.denied.append(77)
    s = _sync(app, msca_id)
    assert (s['denied'], s['completed']) == (1, 0)
    status, cert_id, err = _req(app, req_id)
    assert (status, cert_id) == ('denied', None) and err


def test_still_pending_request_is_untouched(app, ca):
    msca_id = _make_msca(app, 'PC still')
    req_id, _ = _pending(app, msca_id, 88, 'pc-still.test.local')
    s = _sync(app, msca_id)
    assert (s['completed'], s['denied'], s['failed']) == (0, 0, 0)
    assert _req(app, req_id) == ('pending', None, None)


def test_already_completed_request_is_not_imported_twice(app, ca):
    msca_id = _make_msca(app, 'PC twice')
    ca.add(55, 'pc-twice.test.local')
    req_id, _ = _pending(app, msca_id, 55, 'pc-twice.test.local')
    assert _sync(app, msca_id)['completed'] == 1
    s = _sync(app, msca_id)
    assert (s['completed'], s['imported']) == (0, 0)
    from models import Certificate
    with app.app_context():
        assert Certificate.query.filter_by(subject_cn='pc-twice.test.local').count() == 1


def test_csr_deleted_meanwhile_still_completes(app, ca):
    from models import Certificate, db
    msca_id = _make_msca(app, 'PC gone')
    ca.add(66, 'pc-gone.test.local')
    req_id, csr_id = _pending(app, msca_id, 66, 'pc-gone.test.local')
    with app.app_context():
        from sqlalchemy import update
        from models import MSCARequest
        db.session.execute(update(MSCARequest).where(MSCARequest.id == req_id).values(csr_id=None))
        db.session.delete(db.session.get(Certificate, csr_id))
        db.session.commit()
    s = _sync(app, msca_id)
    assert s['completed'] == 1
    status, cert_id, _ = _req(app, req_id)
    assert status == 'issued' and cert_id


def test_completion_announces_the_certificate_once(app, ca, events):
    msca_id = _make_msca(app, 'PC events')
    ca.add(31, 'pc-events.test.local')
    _, csr_id = _pending(app, msca_id, 31, 'pc-events.test.local')
    _sync(app, msca_id)
    assert [e for e, _ in events if e.startswith('certificate.')] == ['certificate.issued']


def test_the_sync_endpoint_and_scheduler_report_completed(app, auth_client, ca):
    msca_id = _make_msca(app, 'PC route')
    ca.add(12, 'pc-route.test.local')
    _pending(app, msca_id, 12, 'pc-route.test.local')
    r = auth_client.post(f'/api/v2/microsoft-cas/{msca_id}/inventory-sync',
                         data='{"full": true}', content_type='application/json')
    assert r.status_code == 200, r.data
    body = r.get_json()
    assert body['data']['completed'] == 1
    assert 'completed' in body['message']


def test_a_request_that_is_not_pending_is_left_alone(app, ca):
    msca_id = _make_msca(app, 'PC failed')
    ca.add(21, 'pc-failed.test.local')
    req_id, _ = _pending(app, msca_id, 21, 'pc-failed.test.local', status='failed')
    s = _sync(app, msca_id)
    assert (s['completed'], s['skipped']) == (0, 1)
    assert _req(app, req_id)[:2] == ('failed', None)


class _Client:
    def __init__(self, pem=None, error=None):
        self.pem, self.error = pem, error

    def get_existing_cert(self, request_id, encoding='b64'):
        if self.error:
            raise self.error
        return self.pem


def _check(app, auth_client, monkeypatch, msca_id, req_id, client):
    from services.msca.connection import MicrosoftCAConnectionMixin
    monkeypatch.setattr(MicrosoftCAConnectionMixin, '_get_client', staticmethod(lambda m: client))
    monkeypatch.setattr(MicrosoftCAConnectionMixin, '_cleanup_client', staticmethod(lambda c: None))
    return auth_client.get(f'/api/v2/microsoft-cas/{msca_id}/requests/{req_id}')


def test_check_route_imports_the_issued_certificate(app, auth_client, monkeypatch):
    from tests.test_msca_inventory import _make_cert
    msca_id = _make_msca(app, 'PC check')
    _, pem = _make_cert('pc-check.test.local')
    req_id, csr_id = _pending(app, msca_id, 5, 'pc-check.test.local')
    r = _check(app, auth_client, monkeypatch, msca_id, req_id, _Client(pem=pem))
    assert r.status_code == 200, r.data
    assert r.get_json()['data']['cert_id'] == csr_id
    assert _req(app, req_id)[:2] == ('issued', csr_id)
    # A second check changes nothing
    assert _check(app, auth_client, monkeypatch, msca_id, req_id, _Client(pem=pem)).status_code == 200
    from models import Certificate
    with app.app_context():
        assert Certificate.query.filter_by(subject_cn='pc-check.test.local').count() == 1


def test_check_route_import_failure_leaves_the_request_pending(app, auth_client, monkeypatch):
    msca_id = _make_msca(app, 'PC check bad')
    req_id, _ = _pending(app, msca_id, 6, 'pc-bad.test.local')
    r = _check(app, auth_client, monkeypatch, msca_id, req_id, _Client(pem='not a certificate'))
    assert r.status_code == 500
    assert _req(app, req_id)[:2] == ('pending', None)
    from tests.test_msca_inventory import _make_cert
    _, pem = _make_cert('pc-bad.test.local')
    r = _check(app, auth_client, monkeypatch, msca_id, req_id, _Client(pem=pem))
    assert r.status_code == 200 and _req(app, req_id)[0] == 'issued'


def test_check_route_needs_write_permission(app, viewer_client, monkeypatch):
    # The import it performs is what the signing route guards with write:certificates
    msca_id = _make_msca(app, 'PC check perm')
    req_id, _ = _pending(app, msca_id, 8, 'pc-perm.test.local')
    r = _check(app, viewer_client, monkeypatch, msca_id, req_id, _Client(error=RuntimeError('x')))
    assert r.status_code == 403


def test_pending_request_whose_certificate_is_already_in_ucm_is_not_imported_again(app, ca):
    from models import Certificate
    msca_id = _make_msca(app, 'PC known')
    serial = ca.add(4300, 'pc-known.test.local')
    pem = ca.rows[-1]['pem']
    req_id, _ = _pending(app, msca_id, 4300, 'pc-known.test.local', with_csr=False)
    with app.app_context():
        from models import db
        db.session.add(Certificate(
            refid='pc-known-manual', descr='manual', crt=base64.b64encode(pem.encode()).decode(),
            subject_cn='pc-known.test.local', serial_number=serial.upper()))
        db.session.commit()
    s = _sync(app, msca_id)
    assert (s['completed'], s['imported'], s['skipped'], s['failed']) == (0, 0, 1, 0)
    with app.app_context():
        assert Certificate.query.filter_by(subject_cn='pc-known.test.local').count() == 1


def test_check_route_completes_a_request_whose_csr_was_deleted(app, auth_client, monkeypatch, ca):
    from models import Certificate
    msca_id = _make_msca(app, 'PC check gone')
    ca.add(910, 'pc-check-gone.test.local')
    pem = ca.rows[-1]['pem']
    req_id, _ = _pending(app, msca_id, 910, 'pc-check-gone.test.local', with_csr=False)
    r = _check(app, auth_client, monkeypatch, msca_id, req_id, _Client(pem=pem))
    assert r.status_code == 200, r.data
    status, cert_id, _ = _req(app, req_id)
    assert status == 'issued' and cert_id
    s = _sync(app, msca_id)
    assert (s['imported'], s['completed']) == (0, 0)
    with app.app_context():
        assert Certificate.query.filter_by(subject_cn='pc-check-gone.test.local').count() == 1


class PanelADCS(DenyingADCS):
    """DenyingADCS that accepts certutil -resubmit and records each script."""

    def __init__(self):
        super().__init__()
        self.scripts = []

    def run_ps(self, msca, script):
        self.scripts.append(script)
        if '-resubmit' in script:
            return 'CertUtil: -resubmit command completed successfully.\n'
        return super().run_ps(msca, script)


@pytest.fixture
def panel_ca(monkeypatch):
    from services.msca.admin_channel import MicrosoftCAAdminChannelMixin
    fake = PanelADCS()
    monkeypatch.setattr(MicrosoftCAAdminChannelMixin, '_run_ps', staticmethod(fake.run_ps))
    return fake


def _set_high_water(app, msca_id, value):
    from models import MicrosoftCA, db
    with app.app_context():
        db.session.get(MicrosoftCA, msca_id).last_synced_request_id = value
        db.session.commit()


def _listing_starts(fake):
    return [int(m.group(1)) for s in fake.scripts
            for m in [re.search(r'Disposition=20,RequestId>=(\d+)', s)] if m]


def test_panel_approval_completes_a_request_whose_csr_was_deleted(app, panel_ca):
    from models import MSCARequest
    from services.msca_service import MicrosoftCAService
    msca_id = _make_msca(app, 'PC panel gone')
    panel_ca.add(902, 'pc-panel-gone.test.local')
    req_id, _ = _pending(app, msca_id, 902, 'pc-panel-gone.test.local', with_csr=False)
    with app.app_context():
        result = MicrosoftCAService.approve_request(msca_id, 902)
        assert result['imported_cert_id']
        rows = MSCARequest.query.filter_by(msca_id=msca_id).all()
        assert [(r.id, r.status, r.cert_id) for r in rows] == [
            (req_id, 'issued', result['imported_cert_id'])]
    _set_high_water(app, msca_id, 5000)
    panel_ca.scripts.clear()
    _sync(app, msca_id, full=False)
    assert _listing_starts(panel_ca) == [5000]


def test_pending_request_with_a_known_serial_is_closed_not_left_pinning(app, panel_ca):
    from models import Certificate, db
    msca_id = _make_msca(app, 'PC known pin')
    serial = panel_ca.add(903, 'pc-known-pin.test.local')
    pem = panel_ca.rows[-1]['pem']
    req_id, _ = _pending(app, msca_id, 903, 'pc-known-pin.test.local', with_csr=False)
    with app.app_context():
        cert = Certificate(refid='pc-known-pin', descr='manual',
                           crt=base64.b64encode(pem.encode()).decode(),
                           subject_cn='pc-known-pin.test.local', serial_number=serial.upper())
        db.session.add(cert)
        db.session.commit()
        cert_id = cert.id
    s = _sync(app, msca_id)
    assert (s['completed'], s['imported'], s['skipped']) == (0, 0, 1)
    assert _req(app, req_id)[:2] == ('issued', cert_id)
    _set_high_water(app, msca_id, 5000)
    panel_ca.scripts.clear()
    _sync(app, msca_id, full=False)
    assert _listing_starts(panel_ca) == [5000]


def _give_row_a_cert(app, csr_id, cn, source):
    from models import Certificate, db
    from tests.test_msca_inventory import _make_cert
    serial, pem = _make_cert(cn)
    with app.app_context():
        row = db.session.get(Certificate, csr_id)
        row.crt = base64.b64encode(pem.encode()).decode()
        row.serial_number = serial
        row.source = source
        db.session.commit()
    return serial


def test_sync_closes_a_request_whose_csr_a_local_ca_signed_meanwhile(app, ca):
    from models import Certificate, db
    msca_id = _make_msca(app, 'PC local')
    req_id, csr_id = _pending(app, msca_id, 904, 'pc-local.test.local')
    local_serial = _give_row_a_cert(app, csr_id, 'pc-local.test.local', 'csr')
    ca.add(904, 'pc-local.test.local')
    s = _sync(app, msca_id)
    # The CA's certificate enters on a row of its own
    assert (s['completed'], s['imported'], s['skipped']) == (0, 1, 0)
    assert _req(app, req_id)[:2] == ('superseded', None)
    with app.app_context():
        stored = str(db.session.get(Certificate, csr_id).serial_number)
        assert stored in (local_serial, str(int(local_serial, 16)))


def test_sync_still_completes_a_renewal_of_a_microsoft_ca_certificate(app, ca):
    from models import Certificate, db
    msca_id = _make_msca(app, 'PC renew')
    req_id, csr_id = _pending(app, msca_id, 905, 'pc-renew.test.local')
    old_serial = _give_row_a_cert(app, csr_id, 'pc-renew.test.local', 'msca')
    new_serial = ca.add(905, 'pc-renew.test.local')
    assert _sync(app, msca_id)['completed'] == 1
    assert _req(app, req_id)[:2] == ('issued', csr_id)
    with app.app_context():
        stored = db.session.get(Certificate, csr_id).serial_number
        assert str(stored) in (new_serial, str(int(new_serial, 16)))
        assert str(stored) not in (old_serial, str(int(old_serial, 16)))


def test_sync_counts_only_the_completion_it_won(app, panel_ca, monkeypatch):
    """Another caller completes the request between the fetch and the claim: the sync
    imported nothing and says so; a known-serial closure earlier in the run survives."""
    from models import Certificate, MSCARequest, db
    from services.msca.inventory import MicrosoftCAInventoryMixin
    msca_id = _make_msca(app, 'PC race')
    serial = panel_ca.add(920, 'pc-race-known.test.local')
    known_pem = panel_ca.rows[-1]['pem']
    known_req, _ = _pending(app, msca_id, 920, 'pc-race-known.test.local', with_csr=False)
    with app.app_context():
        db.session.add(Certificate(refid='pc-race-known', descr='manual',
                                   crt=base64.b64encode(known_pem.encode()).decode(),
                                   subject_cn='pc-race-known.test.local', serial_number=serial.upper()))
        db.session.commit()
    panel_ca.add(921, 'pc-race.test.local')
    race_req, csr_id = _pending(app, msca_id, 921, 'pc-race.test.local')
    real_fetch = MicrosoftCAInventoryMixin._fetch_cert_pem

    def fetch_then_lose(msca, rid):
        pem = real_fetch(msca, rid)
        if rid == 921:
            with db.engine.begin() as conn:
                conn.execute(db.update(MSCARequest).where(MSCARequest.id == race_req)
                             .values(status='issued', cert_id=csr_id))
        return pem

    monkeypatch.setattr(MicrosoftCAInventoryMixin, '_fetch_cert_pem', staticmethod(fetch_then_lose))
    s = _sync(app, msca_id)
    assert (s['completed'], s['imported'], s['skipped']) == (0, 0, 2)
    assert _req(app, known_req)[0] == 'issued'


def test_a_pending_request_skipped_for_its_known_serial_is_logged(app, ca, caplog):
    import logging
    from models import Certificate, db
    msca_id = _make_msca(app, 'PC known log')
    serial = ca.add(930, 'pc-known-log.test.local')
    pem = ca.rows[-1]['pem']
    _pending(app, msca_id, 930, 'pc-known-log.test.local', with_csr=False)
    with app.app_context():
        db.session.add(Certificate(refid='pc-known-log', descr='manual',
                                   crt=base64.b64encode(pem.encode()).decode(),
                                   subject_cn='pc-known-log.test.local', serial_number=serial.upper()))
        db.session.commit()
    with caplog.at_level(logging.INFO, logger='services.msca.inventory'):
        _sync(app, msca_id)
    assert any('skipping RequestId 930' in r.getMessage() and serial in r.getMessage()
               and 'serial already known' in r.getMessage() for r in caplog.records)


def test_a_failed_completion_keeps_an_earlier_known_serial_closure(app, panel_ca):
    from models import Certificate, db
    msca_id = _make_msca(app, 'PC keep')
    serial = panel_ca.add(940, 'pc-keep-known.test.local')
    pem = panel_ca.rows[-1]['pem']
    known_req, _ = _pending(app, msca_id, 940, 'pc-keep-known.test.local', with_csr=False)
    with app.app_context():
        db.session.add(Certificate(refid='pc-keep-known', descr='manual',
                                   crt=base64.b64encode(pem.encode()).decode(),
                                   subject_cn='pc-keep-known.test.local', serial_number=serial.upper()))
        db.session.commit()
    panel_ca.add(941, 'pc-keep-bad.test.local')
    panel_ca.rows[-1]['pem'] = '-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----'
    bad_req, _ = _pending(app, msca_id, 941, 'pc-keep-bad.test.local')
    stale_req, stale_csr = _pending(app, msca_id, 939, 'pc-keep-stale.test.local')
    _give_row_a_cert(app, stale_csr, 'pc-keep-stale.test.local', 'csr')
    s = _sync(app, msca_id)
    assert s['failed'] == 1
    assert _req(app, known_req)[0] == 'issued'
    assert _req(app, stale_req)[0] == 'superseded'
    assert _req(app, bad_req)[:2] == ('pending', None)


def test_a_failed_completion_keeps_the_closure_of_a_request_signed_elsewhere(app, panel_ca):
    msca_id = _make_msca(app, 'PC keep stale')
    stale_req, stale_csr = _pending(app, msca_id, 949, 'pc-stale.test.local')
    _give_row_a_cert(app, stale_csr, 'pc-stale.test.local', 'csr')
    panel_ca.add(950, 'pc-stale-bad.test.local')
    panel_ca.rows[-1]['pem'] = '-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----'
    _pending(app, msca_id, 950, 'pc-stale-bad.test.local')
    assert _sync(app, msca_id)['failed'] == 1
    assert _req(app, stale_req)[0] == 'superseded'



def test_check_leaves_the_session_usable_after_a_failed_statement(app, monkeypatch):
    """A failed statement poisons the transaction (PostgreSQL aborts it): check_request
    rolls back before raising, so its caller can go on with the same session."""
    import api.v2.msca as msca_api
    from models import MSCARequest, db
    from services.msca.connection import MicrosoftCAConnectionMixin
    from services.msca.requests import MSCAImportError
    from services.msca_service import MicrosoftCAService
    from tests.test_msca_inventory import _make_cert
    msca_id = _make_msca(app, 'PC check sql')
    req_id, csr_id = _pending(app, msca_id, 960, 'pc-sql.test.local')
    _, pem = _make_cert('pc-sql.test.local')

    def failing_import(*a, **kw):
        db.session.add(MSCARequest(id=req_id, msca_id=msca_id, template='dup'))
        db.session.flush()

    monkeypatch.setattr(msca_api, '_import_signed_cert', failing_import)
    monkeypatch.setattr(MicrosoftCAConnectionMixin, '_get_client', staticmethod(lambda m: _Client(pem=pem)))
    monkeypatch.setattr(MicrosoftCAConnectionMixin, '_cleanup_client', staticmethod(lambda c: None))
    with app.app_context():
        with pytest.raises(MSCAImportError):
            MicrosoftCAService.check_request(msca_id, req_id)
        req = db.session.get(MSCARequest, req_id)
        assert (req.status, req.cert_id) == ('pending', None)

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

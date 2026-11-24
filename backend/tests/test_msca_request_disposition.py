"""A Microsoft CA request says it waits for approval only while it is pending.

The signing answer gives the same text as the stored request, and every way a pending request
leaves that state (poll, inventory sync, closure as superseded) clears the waiting message.
"""
import base64

import pytest

from tests.deploy_leftovers import delete_leftovers
from tests.test_msca_inventory import _make_cert, _make_msca
from tests.test_msca_localized_pending import (FR_POLL_DENIED, FR_SUBMIT_PENDING, _CertsrvErr,
                                               _FakeClient, _make_conn)
from tests.test_msca_pending_completion import _Client, _check, _pending, _sync, ca  # noqa: F401

_cleanup = pytest.fixture(autouse=True)(delete_leftovers)

WAITING = 'Pending approval on the CA'


def _waiting(app, req_id):
    from models import MSCARequest, db
    with app.app_context():
        db.session.get(MSCARequest, req_id).disposition_message = WAITING
        db.session.commit()


def _state(app, req_id):
    from models import MSCARequest, db
    with app.app_context():
        row = db.session.get(MSCARequest, req_id)
        return row.status, row.to_dict()['disposition_message']


def _client(monkeypatch, client):
    from services.msca.connection import MicrosoftCAConnectionMixin
    monkeypatch.setattr(MicrosoftCAConnectionMixin, '_get_client', staticmethod(lambda msca: client))
    monkeypatch.setattr(MicrosoftCAConnectionMixin, '_cleanup_client', staticmethod(lambda c: None))


def test_the_signing_answer_says_what_the_request_says(app, monkeypatch):
    from models import MSCARequest, db
    from services.msca.certs import PENDING_MESSAGE
    from services.msca_service import MicrosoftCAService
    msca_id = _make_conn(app)
    _client(monkeypatch, _FakeClient(on_get_cert=_CertsrvErr('An unknown error occured', FR_SUBMIT_PENDING)))
    with app.app_context():
        csr_pem = '-----BEGIN CERTIFICATE REQUEST-----\nMIIB\n-----END CERTIFICATE REQUEST-----\n'
        result = MicrosoftCAService.submit_csr(msca_id, csr_pem, 'WebServer')
        stored = db.session.get(MSCARequest, result['request_id']).disposition_message
    assert result['message'] == PENDING_MESSAGE == stored


def test_a_poll_that_imports_the_certificate_clears_the_wait(app, auth_client, monkeypatch):
    msca_id = _make_msca(app, 'Disp import')
    _, pem = _make_cert('disp-import.test.local')
    req_id, _ = _pending(app, msca_id, 9701, 'disp-import.test.local')
    _waiting(app, req_id)
    assert _check(app, auth_client, monkeypatch, msca_id, req_id, _Client(pem=pem)).status_code == 200
    assert _state(app, req_id) == ('issued', None)


def test_a_poll_of_a_request_already_linked_clears_the_wait(app, monkeypatch):
    from models import MSCARequest, db
    from services.msca_service import MicrosoftCAService
    msca_id = _make_msca(app, 'Disp linked')
    _, pem = _make_cert('disp-linked.test.local')
    req_id, csr_id = _pending(app, msca_id, 9702, 'disp-linked.test.local')
    with app.app_context():
        row = db.session.get(MSCARequest, req_id)
        row.cert_id, row.disposition_message = csr_id, WAITING
        db.session.commit()
    _client(monkeypatch, _Client(pem=pem))
    with app.app_context():
        MicrosoftCAService.check_request(msca_id, req_id)
    assert _state(app, req_id) == ('issued', None)


def test_a_poll_that_finds_the_request_denied_clears_the_wait(app, monkeypatch):
    from services.msca_service import MicrosoftCAService
    msca_id = _make_msca(app, 'Disp denied')
    req_id, _ = _pending(app, msca_id, 9703, 'disp-denied.test.local')
    _waiting(app, req_id)
    _client(monkeypatch, _FakeClient(on_get_existing=_CertsrvErr('An unknown error occured', FR_POLL_DENIED)))
    with app.app_context():
        MicrosoftCAService.check_request(msca_id, req_id)
    assert _state(app, req_id) == ('denied', None)


def test_the_inventory_sync_clears_the_wait_of_what_it_closes(app, ca):  # noqa: F811
    from models import Certificate, db
    msca_id = _make_msca(app, 'Disp sync')
    ca.add(4501, 'disp-sync-issued.test.local')
    issued, _ = _pending(app, msca_id, 4501, 'disp-sync-issued.test.local')
    denied, _ = _pending(app, msca_id, 4502, 'disp-sync-denied.test.local')
    ca.denied.append(4502)
    serial = ca.add(4503, 'disp-sync-known.test.local')
    known, _ = _pending(app, msca_id, 4503, 'disp-sync-known.test.local', with_csr=False)
    with app.app_context():
        db.session.add(Certificate(refid='disp-sync-known', descr='manual',
                                   crt=base64.b64encode(ca.rows[-1]['pem'].encode()).decode(),
                                   subject_cn='disp-sync-known.test.local', serial_number=serial.upper()))
        db.session.commit()
    still, _ = _pending(app, msca_id, 4504, 'disp-sync-still.test.local')
    for req_id in (issued, denied, known, still):
        _waiting(app, req_id)
    _sync(app, msca_id)
    assert [_state(app, r) for r in (issued, denied, known, still)] == [
        ('issued', None), ('denied', None), ('issued', None), ('pending', WAITING)]


def test_a_request_closed_as_superseded_no_longer_waits(app):
    from services.msca.requests import SUPERSEDED, supersede
    msca_id = _make_msca(app, 'Disp superseded')
    req_id, _ = _pending(app, msca_id, 9705, 'disp-superseded.test.local')
    _waiting(app, req_id)
    with app.app_context():
        assert supersede([req_id], username='tester') == 1
    assert _state(app, req_id) == (SUPERSEDED, None)

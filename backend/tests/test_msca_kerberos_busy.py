"""A Kerberos sign-in that waited its bound for another one sent nothing to the CA.

Renewal through a Microsoft CA and the poll of a pending request answer 503
with Retry-After, as signing does, and record nothing: no failed request, the
polled request and the renewed certificate are left as they were.
"""
import base64
import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tests.conftest import get_json
from tests.test_msca_lifecycle import _create_msca_cert

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')

BUSY = 'Another Kerberos sign-in to a Microsoft CA is in progress: try again'


@pytest.fixture
def busy_ca(monkeypatch):
    """certsrv whose every CA call meets a busy Kerberos sign-in."""
    from services.msca.client_keytab import KerberosBusy

    def factory(**kwargs):
        client = MagicMock()
        client.get_cert.side_effect = KerberosBusy(BUSY)
        client.get_existing_cert.side_effect = KerberosBusy(BUSY)
        return client

    monkeypatch.setitem(sys.modules, 'certsrv', SimpleNamespace(Certsrv=factory))
    monkeypatch.setitem(sys.modules, 'requests_kerberos', SimpleNamespace(
        HTTPKerberosAuth=type('Auth', (), {'__init__': lambda self, **kw: None}), OPTIONAL=1))


def _kerberos(app, msca_id):
    from models import db
    from models.msca import MicrosoftCA
    with app.app_context():
        row = db.session.get(MicrosoftCA, msca_id)
        row.auth_method, row.kerberos_keytab_path = 'kerberos', '/srv/keytabs/ucm.keytab'
        db.session.commit()


def _requests(app, msca_id):
    from models.msca import MSCARequest
    with app.app_context():
        return sorted((q.id, q.status, q.error_message) for q in MSCARequest.query.filter_by(msca_id=msca_id))


def _busy(r):
    assert r.status_code == 503, r.data
    assert get_json(r)['message'] == BUSY
    assert r.headers.get('Retry-After', '').isdigit()


@pytest.mark.parametrize('with_csr', [True, False], ids=['resubmit', 'rekey'])
def test_a_busy_renewal_is_a_503_that_changes_nothing(app, auth_client, busy_ca, with_csr):
    from models import Certificate, db
    cert_id, msca_id, _req = _create_msca_cert(app, f'busy-renew-{with_csr}.test.local', with_csr=with_csr)
    _kerberos(app, msca_id)
    with app.app_context():
        cert = db.session.get(Certificate, cert_id)
        before = (cert.crt, cert.csr, cert.prv)
    requests_before = _requests(app, msca_id)
    _busy(auth_client.post(f'/api/v2/certificates/{cert_id}/renew', data=json.dumps({}),
                           content_type='application/json'))
    assert _requests(app, msca_id) == requests_before
    with app.app_context():
        cert = db.session.get(Certificate, cert_id)
        assert (cert.crt, cert.csr, cert.prv) == before


def test_a_busy_poll_is_a_503_that_leaves_the_request_pending(app, auth_client, busy_ca):
    from models import db
    from models.msca import MSCARequest
    from services.cert_service import CertificateService
    _cert, msca_id, _req = _create_msca_cert(app, 'busy-poll.test.local')
    _kerberos(app, msca_id)
    with app.app_context():
        csr = CertificateService.generate_csr(descr='busy-poll', dn={'CN': 'busy-poll-csr.test.local'},
                                              key_type='2048')
        db.session.flush()
        pending = MSCARequest(msca_id=msca_id, csr_id=csr.id, template='WebServer', status='pending',
                              request_id=4242)
        db.session.add(pending)
        db.session.commit()
        req_id = pending.id
    before = _requests(app, msca_id)
    _busy(auth_client.get(f'/api/v2/microsoft-cas/{msca_id}/requests/{req_id}'))
    assert _requests(app, msca_id) == before
    assert (req_id, 'pending', None) in before

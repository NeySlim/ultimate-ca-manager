"""A Kerberos sign-in to a Microsoft CA that fails is a 400 naming its cause, never a 500.

The real certsrv client and the real Negotiate handler run against a CA faked at the HTTP
adapter (each request answered by a Negotiate 401) and a GSSAPI faked at its boundary. Signing,
renewal, the poll of a pending request, the template list and both connection tests answer
400 with the Kerberos cause; nothing reached the CA, so nothing is recorded but a failed test.
"""
import base64
import json

import pytest
import requests
import requests.adapters
from requests.structures import CaseInsensitiveDict

from tests.conftest import get_json
from tests.msca_kerberos_support import FakeGssapi
from tests.test_msca_lifecycle import _create_msca_cert

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')

CAUSE = 'Preauthentication failed'


@pytest.fixture
def ca(monkeypatch):
    """Every request to the CA meets a Negotiate challenge; the requests are kept."""
    seen = []

    def send(self, request, **kwargs):
        seen.append(request)
        response = requests.Response()
        response.status_code, response.url, response.request = 401, request.url, request
        response.headers = CaseInsensitiveDict({'WWW-Authenticate': 'Negotiate'})
        response._content, response._content_consumed = b'', True
        response.raw = type('Raw', (), {'release_conn': lambda self: None})()
        response.connection = self
        return response

    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', send)
    return seen


@pytest.fixture
def gss(monkeypatch):
    fake = FakeGssapi().install(monkeypatch)
    fake.acquire_error = CAUSE
    return fake


@pytest.fixture
def keytab(tmp_path):
    path = tmp_path / 'ucm.keytab'
    path.write_bytes(b'\x05\x02')
    return str(path)


def _kerberos(app, msca_id, keytab):
    from models import db
    from models.msca import MicrosoftCA
    with app.app_context():
        row = db.session.get(MicrosoftCA, msca_id)
        row.auth_method, row.kerberos_keytab_path = 'kerberos', keytab
        row.kerberos_principal = 'ucm@TEST.LOCAL'
        db.session.commit()


def _requests(app, msca_id):
    from models.msca import MSCARequest
    with app.app_context():
        return sorted((q.id, q.status, q.error_message) for q in MSCARequest.query.filter_by(msca_id=msca_id))


def _refused(r, cause=CAUSE):
    assert r.status_code == 400, r.data
    message = get_json(r)['message']
    assert 'Kerberos sign-in' in message and cause in message, message


def _connection(app, cn, keytab):
    _cert, msca_id, _req = _create_msca_cert(app, cn)
    _kerberos(app, msca_id, keytab)
    return msca_id


def _csr(app, cn):
    from models import db
    from services.cert_service import CertificateService
    with app.app_context():
        csr_id = CertificateService.generate_csr(descr=cn, dn={'CN': cn}, key_type='2048').id
        db.session.commit()
    return csr_id


# A cause that reads like a CA verdict ("denied") is still a sign-in failure, never a denied request
CAUSES = [CAUSE, 'Permission denied']


@pytest.mark.parametrize('cause', CAUSES)
def test_signing_answers_400_with_the_cause_and_records_nothing(app, auth_client, ca, gss, keytab, cause):
    gss.acquire_error = cause
    msca_id = _connection(app, f'krb-sign-{len(cause)}.test.local', keytab)
    csr_id = _csr(app, f'krb-sign-csr-{len(cause)}.test.local')
    before = _requests(app, msca_id)
    _refused(auth_client.post(f'/api/v2/microsoft-cas/{msca_id}/sign/{csr_id}',
                              data=json.dumps({'template': 'WebServer'}), content_type='application/json'),
             cause=cause)
    assert ca, 'the CA was never asked'
    assert _requests(app, msca_id) == before


def test_a_ticket_the_ca_refuses_answers_400(app, auth_client, ca, gss, keytab):
    gss.acquire_error = None  # the ticket is made, the CA answers 401 again
    msca_id = _connection(app, 'krb-refused.test.local', keytab)
    csr_id = _csr(app, 'krb-refused-csr.test.local')
    r = auth_client.post(f'/api/v2/microsoft-cas/{msca_id}/sign/{csr_id}',
                         data=json.dumps({'template': 'WebServer'}), content_type='application/json')
    _refused(r, cause='refused the ticket')
    assert 'may hold the request' not in get_json(r)['message']  # a 401: the CA did not take it


def test_an_answer_that_fails_mutual_authentication_says_the_ca_may_hold_the_request(
        app, auth_client, gss, keytab, monkeypatch):
    """The CA answered the authenticated POST, so it may have taken the request: UCM cannot trust
    the answer, records nothing, and says so instead of claiming the CA never read it."""
    gss.acquire_error = None
    forged = 'Negotiate ' + base64.b64encode(b'not the server token').decode()
    seen = []

    def send(self, request, **kwargs):
        seen.append(request)
        signed = 'Authorization' in request.headers
        response = requests.Response()
        response.status_code, response.url, response.request = (200 if signed else 401), request.url, request
        response.headers = CaseInsensitiveDict({'WWW-Authenticate': forged if signed else 'Negotiate'})
        response._content, response._content_consumed = b'<html>Certificate Pending</html>', True
        response.raw = type('Raw', (), {'release_conn': lambda self: None})()
        response.connection = self
        return response

    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', send)
    msca_id = _connection(app, 'krb-mutual.test.local', keytab)
    csr_id = _csr(app, 'krb-mutual-csr.test.local')
    before = _requests(app, msca_id)
    r = auth_client.post(f'/api/v2/microsoft-cas/{msca_id}/sign/{csr_id}',
                         data=json.dumps({'template': 'WebServer'}), content_type='application/json')
    _refused(r, cause='mutual authentication')
    assert 'the CA may hold the request' in get_json(r)['message']
    assert any(q.method == 'POST' and 'Authorization' in q.headers for q in seen)
    assert _requests(app, msca_id) == before


@pytest.mark.parametrize('with_csr', [True, False], ids=['resubmit', 'rekey'])
def test_a_renewal_answers_400_and_changes_nothing(app, auth_client, ca, gss, keytab, with_csr):
    from models import Certificate, db
    cert_id, msca_id, _req = _create_msca_cert(app, f'krb-renew-{with_csr}.test.local', with_csr=with_csr)
    _kerberos(app, msca_id, keytab)
    with app.app_context():
        cert = db.session.get(Certificate, cert_id)
        before = (cert.crt, cert.csr, cert.prv)
    requests_before = _requests(app, msca_id)
    _refused(auth_client.post(f'/api/v2/certificates/{cert_id}/renew', data=json.dumps({}),
                              content_type='application/json'))
    assert _requests(app, msca_id) == requests_before
    with app.app_context():
        cert = db.session.get(Certificate, cert_id)
        assert (cert.crt, cert.csr, cert.prv) == before


@pytest.mark.parametrize('cause', CAUSES)
def test_a_poll_answers_400_and_leaves_the_request_pending(app, auth_client, ca, gss, keytab, cause):
    from models import db
    from models.msca import MSCARequest
    gss.acquire_error = cause
    msca_id = _connection(app, f'krb-poll-{len(cause)}.test.local', keytab)
    csr_id = _csr(app, f'krb-poll-csr-{len(cause)}.test.local')
    with app.app_context():
        pending = MSCARequest(msca_id=msca_id, csr_id=csr_id, template='WebServer', status='pending',
                              request_id=4242)
        db.session.add(pending)
        db.session.commit()
        req_id = pending.id
    before = _requests(app, msca_id)
    _refused(auth_client.get(f'/api/v2/microsoft-cas/{msca_id}/requests/{req_id}'), cause=cause)
    assert _requests(app, msca_id) == before
    assert (req_id, 'pending', None) in before


def test_the_template_list_answers_400(app, auth_client, ca, gss, keytab):
    msca_id = _connection(app, 'krb-templates.test.local', keytab)
    _refused(auth_client.get(f'/api/v2/microsoft-cas/{msca_id}/templates'))


def test_a_saved_connection_test_records_the_cause(app, auth_client, ca, gss, keytab):
    from models import db
    from models.msca import MicrosoftCA
    msca_id = _connection(app, 'krb-test.test.local', keytab)
    r = auth_client.post(f'/api/v2/microsoft-cas/{msca_id}/test')
    _refused(r)
    assert b'template_access_denied' not in r.data
    with app.app_context():
        assert CAUSE in db.session.get(MicrosoftCA, msca_id).last_test_result


def test_an_unsaved_connection_test_names_the_cause(auth_client, ca, gss, keytab):
    r = auth_client.post('/api/v2/microsoft-cas/test', json={
        'server': 'ca.test.local', 'ca_name': 'Test CA', 'auth_method': 'kerberos',
        'kerberos_principal': 'ucm@TEST.LOCAL', 'kerberos_keytab_path': keytab})
    _refused(r)
    assert b'template_access_denied' not in r.data


@pytest.mark.parametrize('saved', [True, False], ids=['saved', 'unsaved'])
def test_a_sign_in_refused_at_the_template_page_fails_the_test(app, auth_client, monkeypatch, keytab, saved):
    """The CA certificate came, the template page met a refused ticket: a failure, not 'access denied'."""
    import sys
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from services.msca.kerberos import MSCAKerberosError

    def factory(**kwargs):
        client = MagicMock()
        client.server, client.timeout = 'ca.test.local', 5
        client.session.get.side_effect = MSCAKerberosError('Kerberos sign-in to ca.test.local failed: '
                                                           'the server refused the ticket (HTTP 401)')
        return client
    if saved:
        msca_id = _connection(app, 'krb-tpl.test.local', keytab)
    monkeypatch.setitem(sys.modules, 'certsrv', SimpleNamespace(Certsrv=factory))
    r = auth_client.post(f'/api/v2/microsoft-cas/{msca_id}/test') if saved else auth_client.post(
        '/api/v2/microsoft-cas/test', json={'server': 'ca.test.local', 'auth_method': 'kerberos',
                                            'kerberos_keytab_path': keytab})
    _refused(r, cause='refused the ticket')
    assert b'template_access_denied' not in r.data

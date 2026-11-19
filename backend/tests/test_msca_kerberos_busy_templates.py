"""A busy Kerberos sign-in while templates are listed is a wait, not a refusal.

The template list answers 503 with Retry-After, and a connection test says the
sign-in is busy instead of reporting template access as denied.
"""
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tests.conftest import get_json
from tests.test_msca_kerberos_busy import BUSY, _kerberos
from tests.test_msca_lifecycle import _create_msca_cert

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


@pytest.fixture
def busy_templates(monkeypatch):
    """certsrv that reaches the CA, whose template page meets a busy Kerberos sign-in."""
    from services.msca.client_keytab import KerberosBusy

    def factory(**kwargs):
        client = MagicMock()
        client.server = 'ca.test.local'
        client.timeout = 5
        client.session.get.side_effect = KerberosBusy(BUSY)
        return client

    monkeypatch.setitem(sys.modules, 'certsrv', SimpleNamespace(Certsrv=factory))
    monkeypatch.setitem(sys.modules, 'requests_kerberos', SimpleNamespace(
        HTTPKerberosAuth=type('Auth', (), {'__init__': lambda self, **kw: None}), OPTIONAL=1))


def _connection(app, cn):
    _cert, msca_id, _req = _create_msca_cert(app, cn)
    _kerberos(app, msca_id)
    return msca_id


def _busy(r):
    assert r.status_code == 503, r.data
    assert get_json(r)['message'] == BUSY
    assert r.headers.get('Retry-After', '').isdigit()


def test_a_busy_template_list_is_a_503(app, auth_client, busy_templates):
    msca_id = _connection(app, 'busy-templates.test.local')
    _busy(auth_client.get(f'/api/v2/microsoft-cas/{msca_id}/templates'))


def test_a_busy_connection_test_says_so(app, auth_client, busy_templates):
    from models import db
    from models.msca import MicrosoftCA
    msca_id = _connection(app, 'busy-test.test.local')
    with app.app_context():
        before = db.session.get(MicrosoftCA, msca_id).last_test_result
    r = auth_client.post(f'/api/v2/microsoft-cas/{msca_id}/test')
    _busy(r)
    assert b'template_access_denied' not in r.data
    with app.app_context():
        assert db.session.get(MicrosoftCA, msca_id).last_test_result == before


def test_a_busy_unsaved_connection_test_says_so(auth_client, busy_templates):
    r = auth_client.post('/api/v2/microsoft-cas/test', json={
        'server': 'ca.test.local', 'ca_name': 'Test CA', 'auth_method': 'kerberos',
        'kerberos_principal': 'ucm@TEST.LOCAL', 'kerberos_keytab_path': '/srv/keytabs/ucm.keytab'})
    _busy(r)
    assert b'template_access_denied' not in r.data

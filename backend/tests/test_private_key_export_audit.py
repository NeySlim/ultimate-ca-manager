"""Every export that hands out a private key leaves an audit entry, without the secret."""
import pytest

from models import AuditLog

PASSWORD = 'Export-Passw0rd!'


def _entries(app, resource_type, resource_id):
    with app.app_context():
        return [(e.action, e.details, e.username) for e in AuditLog.query.filter_by(
            action='private_key_exported', resource_type=resource_type,
            resource_id=str(resource_id)).order_by(AuditLog.id).all()]


@pytest.fixture(scope='module')
def cert_id(create_cert):
    return create_cert(cn='key-export-audit.example.com')['id']


@pytest.fixture(scope='module')
def ca_id(create_ca):
    return create_ca(cn='Key Export Audit CA')['id']


@pytest.mark.parametrize('body, details', [
    ({'format': 'key'}, 'KEY (unencrypted)'),
    ({'format': 'key', 'password': PASSWORD}, 'KEY (password-protected)'),
    ({'format': 'pem', 'include_key': True}, 'PEM (unencrypted)'),
    ({'format': 'pkcs12', 'password': PASSWORD}, 'PKCS12 (password-protected)'),
    ({'format': 'pfx', 'password': PASSWORD}, 'PFX (password-protected)'),
    ({'format': 'jks', 'password': PASSWORD}, 'JKS (password-protected)'),
])
@pytest.mark.parametrize('kind', ['certificate', 'ca'])
def test_key_export_is_audited(app, auth_client, cert_id, ca_id, kind, body, details):
    rid = cert_id if kind == 'certificate' else ca_id
    url = f'/api/v2/certificates/{rid}/export' if kind == 'certificate' else f'/api/v2/cas/{rid}/export'
    before = len(_entries(app, kind, rid))
    r = auth_client.post(url, json=body)
    assert r.status_code == 200, r.data
    entries = _entries(app, kind, rid)
    assert len(entries) == before + 1
    action, text, username = entries[-1]
    assert text == f'Private key exported as {details}'
    assert username == 'admin'
    assert PASSWORD not in text


@pytest.mark.parametrize('kind', ['certificate', 'ca'])
@pytest.mark.parametrize('body', [{'format': 'pem'}, {'format': 'der'},
                                  {'format': 'pem', 'include_chain': True}])
def test_export_without_key_is_not_audited_as_key(app, auth_client, cert_id, ca_id, kind, body):
    rid = cert_id if kind == 'certificate' else ca_id
    url = f'/api/v2/certificates/{rid}/export' if kind == 'certificate' else f'/api/v2/cas/{rid}/export'
    before = len(_entries(app, kind, rid))
    assert auth_client.post(url, json=body).status_code == 200
    assert len(_entries(app, kind, rid)) == before


def test_refused_key_export_is_not_audited_as_done(app, auth_client, ca_id):
    before = len(_entries(app, 'ca', ca_id))
    r = auth_client.post(f'/api/v2/cas/{ca_id}/export', json={'format': 'pkcs12'})
    assert r.status_code == 400  # no password
    assert len(_entries(app, 'ca', ca_id)) == before


@pytest.mark.parametrize('body, says_key', [
    ({'format': 'pem', 'include_key': True}, True),
    ({'format': 'pem', 'include_key': False}, False),
])
def test_user_certificate_pem_export_says_whether_the_key_left(
        app, auth_client, create_user, create_cert, body, says_key):
    from tests.test_user_certificate_key_export_guard import _enrolment_for
    username = f'ukey{len(body)}{int(says_key)}'
    create_user(username=username, role='viewer')
    rid, _owner = _enrolment_for(app, create_cert, username, f'{username}-label')
    assert auth_client.post(f'/api/v2/user-certificates/{rid}/export', json=body).status_code == 200
    with app.app_context():
        entry = AuditLog.query.filter_by(action='user_certificate_exported',
                                         resource_id=str(rid)).order_by(AuditLog.id.desc()).first()
    assert ('with private key' in entry.details) is says_key

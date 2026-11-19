"""Hybrid bundle, cross-certificate, SSH and shared-store downloads named outside ASCII (#448)."""
import io
import types

import pytest

from models import CA, Certificate, db
from tests.download_names import NAME_IDS, NAMES, assert_named, disposition_of, plain_stem

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates', 'drop_new_users')


@pytest.mark.parametrize('name', NAMES, ids=NAME_IDS)
def test_hybrid_bundle(app, auth_client, create_ca, name):
    from utils import key_algorithms
    if not key_algorithms.mldsa_supported():
        pytest.skip('this build has no ML-DSA')
    from tests.test_related_certificates_pair import _pair
    a, b = _pair(auth_client, create_ca, 'jp-pair.example.com')
    with app.app_context():
        row = db.session.get(Certificate, b['id'])
        row.descr = name
        plain = plain_stem(name, row.refid)
        db.session.commit()
    assert_named(auth_client.get(f"/api/v2/certificates/{b['id']}/export?format=hybrid-bundle"),
                 name, '_hybrid.zip', plain)


@pytest.mark.parametrize('name', NAMES, ids=NAME_IDS)
def test_cross_certificate_export(app, auth_client, name):
    from tests.test_cross_review_fixes import _x, build_cross_pki, pem, SmartImporter
    pki = build_cross_pki()
    with app.app_context():
        SmartImporter().execute(pem(pki.root_a))
        SmartImporter().execute(pem(pki.root_b))
        b = CA.query.filter_by(descr=pki.name_b).one().id
    made = auth_client.post(_x(b), json={'certificate': pem(pki.cross_b)})
    assert made.status_code == 201, made.data
    xid = made.get_json()['data']['id']
    with app.app_context():
        row = db.session.get(CA, b)
        row.descr = name
        plain = plain_stem(name, row.refid)
        db.session.commit()
    assert_named(auth_client.get(_x(b, xid, '/export')), name, f'-cross-{xid}.pem', plain)
    assert_named(auth_client.get(_x(b, xid, '/export') + '?format=der'), name, f'-cross-{xid}.cer', plain)


@pytest.fixture(params=NAMES, ids=NAME_IDS)
def ssh_ca(app, auth_client, request):
    r = auth_client.post('/api/v2/ssh/cas', json={'descr': 'jp ssh ca', 'ca_type': 'host', 'key_type': 'ed25519'})
    assert r.status_code == 201, r.data
    data = r.get_json()['data']
    from models.ssh import SSHCertificateAuthority
    with app.app_context():
        row = db.session.get(SSHCertificateAuthority, data['id'])
        row.descr = request.param
        db.session.commit()
    return data['id'], data['refid'], request.param


def test_ssh_public_key_download(auth_client, ssh_ca):
    ca_id, refid, name = ssh_ca
    assert_named(auth_client.get(f'/api/v2/ssh/cas/{ca_id}/public-key'), name, '.pub',
                 plain_stem(name, refid), prefix='ssh_ca_')


@pytest.mark.parametrize('platform, ext', [('unix', '.sh'), ('windows', '.ps1')])
def test_ssh_setup_script_download(auth_client, ssh_ca, platform, ext):
    ca_id, refid, name = ssh_ca
    r = auth_client.get(f'/api/v2/ssh/cas/{ca_id}/setup-script?platform={platform}')
    assert_named(r, name, ext, plain_stem(name, refid), prefix='ssh_ca_setup_')


def test_ssh_krl_download(auth_client, ssh_ca):
    ca_id, refid, name = ssh_ca
    assert_named(auth_client.get(f'/api/v2/ssh/cas/{ca_id}/krl'), name, '_krl', plain_stem(name, refid), prefix='ssh_ca_')


def test_public_ssh_setup_endpoints(app, ssh_ca):
    ca_id, refid, name = ssh_ca
    client = app.test_client()
    r = client.get(f'/ssh/setup/{refid}?type=host&hostname=web01.example.com')
    assert_named(r, name, '.sh', plain_stem(name, refid), prefix='ssh_ca_setup_')
    r = client.get(f'/ssh/setup/{refid}/public-key')
    assert_named(r, name, '_ca.pub', plain_stem(name, refid), disposition='inline')


def test_ssh_ascii_names_keep_their_historical_header(auth_client, app):
    r = auth_client.post('/api/v2/ssh/cas', json={'descr': 'plain ssh ca', 'ca_type': 'host', 'key_type': 'ed25519'})
    ca_id = r.get_json()['data']['id']
    assert auth_client.get(f'/api/v2/ssh/cas/{ca_id}/public-key').headers['Content-Disposition'] == \
        'attachment; filename="ssh_ca_plain_ssh_ca.pub"'
    assert auth_client.get(f'/api/v2/ssh/cas/{ca_id}/krl').headers['Content-Disposition'] == \
        'attachment; filename="ssh_ca_plain_ssh_ca_krl"'
    assert auth_client.get(f'/api/v2/ssh/cas/{ca_id}/setup-script').headers['Content-Disposition'] == \
        'attachment; filename="ssh_ca_setup_plain_ssh_ca.sh"'


def test_shared_store_download_header_is_quoted_ascii(app, monkeypatch):
    from datetime import datetime
    from services.backup import shared_store
    row = types.SimpleNamespace(size=3, chunk_size=3, sha256='00' * 32, created_at=datetime(2026, 1, 1))
    monkeypatch.setattr(shared_store, '_open', lambda name: (io.BufferedReader(io.BytesIO(b'abc')), row))
    with app.test_request_context('/'):
        response = shared_store.download_response('ucm_backup_20260101.ucmbkp')
        assert response.headers['Content-Disposition'] == 'attachment; filename="ucm_backup_20260101.ucmbkp"'
        assert disposition_of(types.SimpleNamespace(status_code=200, headers=response.headers, data=b''))


@pytest.mark.parametrize('name', NAMES, ids=NAME_IDS)
def test_email_attachment_with_a_non_ascii_name_is_a_valid_message(app, monkeypatch, name):
    import email
    from services import email_service as email_module
    from services.email_service import EmailService
    config = types.SimpleNamespace(enabled=True, smtp_content_type='html', smtp_from='ucm@example.test',
                                   smtp_from_name='UCM', smtp_host='mail.example.test', smtp_port=25)
    captured = {}

    class FakeServer:
        def sendmail(self, sender, recipients, message):
            captured['message'] = message

        def quit(self):
            pass

    monkeypatch.setattr(EmailService, 'get_smtp_config', staticmethod(lambda: config))
    monkeypatch.setattr(email_module, '_smtp_connect', lambda cfg, timeout: FakeServer())
    monkeypatch.setattr(email_module, '_smtp_authenticate', lambda server, cfg: None)
    with app.app_context():
        ok, _ = EmailService.send_email(
            recipients=['ops@example.test'], subject='Report', body_html='<p>hi</p>', body_text='hi',
            notification_type='report', attachments=[(f'{name}.csv', b'a,b', 'text/csv')])
    assert ok
    wire = captured['message'] if isinstance(captured['message'], bytes) else captured['message'].encode('utf-8')
    assert wire.isascii()
    msg = email.message_from_bytes(wire)
    assert [p.get_filename() for p in msg.walk() if p.get_filename()] == [f'{name}.csv']

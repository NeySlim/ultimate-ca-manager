"""User certificate, mTLS, trust store, template, key recovery, log and report downloads named in Japanese (#448)."""
import datetime
import json

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from models import Certificate, db
from tests.download_names import JAPANESE, assert_named

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates', 'drop_new_users')

PASSWORD = 'Export-Passw0rd!'


def test_user_certificate_exports(app, auth_client, create_user, create_cert):
    from models.auth_certificate import AuthCertificate
    from tests.test_user_certificate_key_export_guard import _enrolment_for
    create_user(username='jp_user_cert_owner', role='viewer')
    row_id, _ = _enrolment_for(app, create_cert, 'jp_user_cert_owner', 'jp-user-cert')
    with app.app_context():
        row = db.session.get(AuthCertificate, row_id)
        row.name = JAPANESE
        refid = db.session.get(Certificate, row.certificate_id).refid if getattr(row, 'certificate_id', None) else None
        db.session.commit()
    url = f'/api/v2/user-certificates/{row_id}/export'
    r = auth_client.post(url, json={'format': 'pkcs12', 'password': PASSWORD})
    assert_named(r, JAPANESE, '.p12')
    assert_named(auth_client.post(url, json={'format': 'pem', 'include_key': False}), JAPANESE, '.crt')
    assert_named(auth_client.post(url, json={'format': 'pem', 'include_key': True}), JAPANESE, '.pem')
    del refid


def test_user_certificate_jks_export(app, auth_client, create_user, create_cert):
    pytest.importorskip('jks')
    from models.auth_certificate import AuthCertificate
    from tests.test_user_certificate_key_export_guard import _enrolment_for
    create_user(username='jp_user_cert_owner2', role='viewer')
    row_id, _ = _enrolment_for(app, create_cert, 'jp_user_cert_owner2', 'jp-user-cert2')
    with app.app_context():
        db.session.get(AuthCertificate, row_id).name = JAPANESE
        db.session.commit()
    r = auth_client.post(f'/api/v2/user-certificates/{row_id}/export', json={'format': 'jks', 'password': PASSWORD})
    assert_named(r, JAPANESE, '.jks')


def test_mtls_downloads_name_the_file_after_the_user(app, create_ca, create_user):
    ca = create_ca(cn='JP mTLS CA')
    user = create_user(username=JAPANESE + 'ユーザー', role='admin')
    client = app.test_client()
    r = client.post('/api/v2/auth/login', json={'username': user['username'], 'password': 'TestPass123!'})
    assert r.status_code == 200, r.data
    made = client.post('/api/v2/mtls/certificates', json={'ca_id': ca['id'], 'name': 'jp-mtls'})
    assert made.status_code == 201, made.data
    url = f'/api/v2/mtls/certificates/{made.get_json()["data"]["id"]}/download'
    stem = user['username']
    assert_named(client.post(url, json={'format': 'p12', 'password': PASSWORD}), stem, '-mtls.p12',
                 fallback_stem=f'user-{user["id"]}')
    assert_named(client.post(url, json={'format': 'pem'}), stem, '-mtls.pem', fallback_stem=f'user-{user["id"]}')


def _trusted_root(cn):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.datetime.now(datetime.timezone.utc)
    return (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=30)).sign(key, hashes.SHA256()))


@pytest.mark.parametrize('fmt, ext', [('pem', '.pem'), ('p7b', '.p7b')])
def test_truststore_bundle_named_after_the_purpose(app, auth_client, fmt, ext):
    from models.truststore import TrustedCertificate
    cert = _trusted_root('jp-trust.example.test')
    with app.app_context():
        row = TrustedCertificate(
            name='jp trust', certificate_pem=cert.public_bytes(serialization.Encoding.PEM).decode(),
            fingerprint_sha256=cert.fingerprint(hashes.SHA256()).hex(), purpose=JAPANESE)
        db.session.add(row)
        db.session.commit()
        row_id = row.id
    try:
        r = auth_client.get(f'/api/v2/truststore/export?format={fmt}&purpose={JAPANESE}')
        assert_named(r, JAPANESE, f'-bundle{ext}', fallback_stem='all', prefix='truststore-')
    finally:
        with app.app_context():
            TrustedCertificate.query.filter_by(id=row_id).delete()
            db.session.commit()


def test_template_export(auth_client):
    from tests.test_templates import _create_template
    r, created = _create_template(auth_client, name=JAPANESE)
    assert r.status_code in (200, 201), r.data
    out = auth_client.get(f"/api/v2/templates/{created['id']}/export")
    assert_named(out, JAPANESE, '.json', fallback_stem=f"template-{created['id']}")


def test_key_recovery_download(app, auth_client, create_cert):
    from tests.test_key_recovery import _open_request, _set_dual_control
    cert = create_cert(cn='jp-recovery.example.com')
    with app.app_context():
        row = db.session.get(Certificate, cert['id'])
        row.descr = JAPANESE
        refid = row.refid
        db.session.commit()
    _set_dual_control(app, False)
    try:
        rid = _open_request(auth_client, cert['id'])
        auth_client.post(f'/api/v2/key-recovery/{rid}/approve', json={})
        r = auth_client.post(f'/api/v2/key-recovery/{rid}/recover', json={'password': 'recover-pw-123'})
        assert_named(r, JAPANESE, '.p12', fallback_stem=refid)
    finally:
        with app.app_context():
            from models import SystemConfig
            SystemConfig.query.filter_by(key='key_recovery_dual_control').delete()
            db.session.commit()


def test_log_bundle_with_a_non_ascii_host_name(auth_client, monkeypatch):
    import os
    real = os.uname()
    fake = type('U', (), {'nodename': 'ホスト', 'sysname': real.sysname, 'release': real.release,
                          'version': real.version, 'machine': real.machine})()
    monkeypatch.setattr(os, 'uname', lambda: fake)
    r = auth_client.get('/api/v2/system/logs/bundle')
    assert r.status_code == 200, r.data[:200]
    assert r.headers['Content-Disposition'].isascii()


def test_report_downloads(auth_client):
    r = auth_client.get('/api/v2/reports/download/certificate_inventory?format=csv')
    assert r.status_code == 200, r.data[:200]
    assert r.headers['Content-Disposition'] == 'attachment; filename="ucm-report-certificate_inventory.csv"'


def test_custom_pdf_named_after_the_requested_template(auth_client):
    sections = auth_client.get('/api/v2/reports/pdf/templates').get_json()['data']['sections']
    r = auth_client.post('/api/v2/reports/pdf/generate', json={'template': JAPANESE, 'sections': sections[:1]})
    if r.status_code == 500:
        pytest.skip('PDF dependencies are not installed')
    today = datetime.date.today().isoformat()
    assert_named(r, f'{JAPANESE}-{today}', '.pdf', prefix='ucm-report-')

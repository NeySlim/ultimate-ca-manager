"""A certificate whose extensions cannot be read is refused with a 400 on every import entry, nothing stored."""
import datetime as dt
import ssl
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from models import CA, Certificate, db
from tests.conftest import get_json


def _pem_with_repeated_extension(cn, ca=True):
    """A certificate that loads but whose extensions do not: its KeyUsage OID is rewritten to the SKI's."""
    key = rsa.generate_private_key(65537, 2048)
    name = x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, cn)])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(uuid.uuid4().int >> 66)
            .not_valid_before(dt.datetime(2026, 1, 1)).not_valid_after(dt.datetime(2036, 1, 1))
            .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(not ca, False, False, False, False, ca, ca, False, False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .sign(key, hashes.SHA256()))
    der = cert.public_bytes(serialization.Encoding.DER)
    key_usage, ski = bytes.fromhex('0603551d0f'), bytes.fromhex('0603551d0e')
    assert der.count(key_usage) == 1
    bad = der.replace(key_usage, ski)
    with pytest.raises(x509.DuplicateExtension):
        x509.load_der_x509_certificate(bad).extensions
    return ssl.DER_cert_to_PEM_cert(bad)


def _counts(app, cn):
    with app.app_context():
        return (CA.query.filter(CA.subject.contains(cn)).count(),
                Certificate.query.filter(Certificate.subject.contains(cn)).count())


@pytest.mark.parametrize('route', ['/api/v2/cas/import', '/api/v2/certificates/import'])
@pytest.mark.parametrize('ca', [True, False])
@pytest.mark.parametrize('as_file', [False, True])
def test_a_certificate_whose_extensions_cannot_be_read_is_refused_with_400(app, auth_client, route, ca, as_file):
    cn = f'Dup Ext {uuid.uuid4().hex[:8]}'
    pem = _pem_with_repeated_extension(cn, ca=ca)
    if as_file:
        import io
        data = {'file': (io.BytesIO(pem.encode()), 'dup.pem')}
    else:
        data = {'pem_content': pem}
    r = auth_client.post(route, data=data, content_type='multipart/form-data')
    assert r.status_code == 400, r.data
    message = get_json(r)['message'].lower()
    assert 'extension' in message, message
    assert _counts(app, cn) == (0, 0)


@pytest.mark.parametrize('step', ['analyze', 'execute'])
def test_the_smart_import_names_the_unreadable_certificate_and_stores_nothing(app, auth_client, step):
    cn = f'Dup Smart {uuid.uuid4().hex[:8]}'
    pem = _pem_with_repeated_extension(cn)
    r = auth_client.post(f'/api/v2/import/{step}', json={'content': pem, 'options': {}})
    assert r.status_code == 400, r.data
    assert 'extension' in get_json(r)['message'].lower()
    assert _counts(app, cn) == (0, 0)


def _opnsense_row(pem, descr):
    import base64
    return {'uuid': str(uuid.uuid4()), 'refid': uuid.uuid4().hex[:13], 'descr': descr,
            'crt': base64.b64encode(pem.encode()).decode(), 'serial': '1'}


@pytest.mark.parametrize('ca', [True, False])
def test_the_opnsense_import_skips_the_unreadable_row_and_names_why(app, auth_client, monkeypatch, ca):
    from api.v2 import import_opnsense
    from tests.test_opnsense_import import _Session
    cn = f'Dup Opn {uuid.uuid4().hex[:8]}'
    rows = [_opnsense_row(_pem_with_repeated_extension(cn, ca=ca), cn)]
    session = _Session(rows, []) if ca else _Session([], rows)
    monkeypatch.setattr(import_opnsense, 'create_session', lambda verify_ssl=True: session)
    r = auth_client.post('/api/v2/import/opnsense/import', json={
        'host': '192.0.2.10', 'port': 443, 'api_key': 'k', 'api_secret': 's', 'verify_ssl': False, 'items': []})
    assert r.status_code == 200, r.data
    data = get_json(r)['data']
    assert data['skipped'] == 1 and data['imported'] == {'cas': 0, 'certificates': 0}
    assert len(data['errors']) == 1 and cn in data['errors'][0] and 'extension' in data['errors'][0]
    with app.app_context():
        assert CA.query.filter_by(refid=rows[0]['refid']).count() == 0
        assert Certificate.query.filter_by(refid=rows[0]['refid']).count() == 0


@pytest.mark.parametrize('ca', [True, False])
def test_the_opnsense_file_importer_refuses_the_unreadable_row(app, monkeypatch, tmp_path, ca):
    from services.opnsense import importer
    cn = f'Dup File {uuid.uuid4().hex[:8]}'
    row = {**_opnsense_row(_pem_with_repeated_extension(cn, ca=ca), cn), 'is_root': True,
           'subject': f'CN={cn}', 'issuer': f'CN={cn}', 'serial_number': '1'}
    with app.app_context():
        mixin = importer.ImportMixin()
        stats = mixin.import_cas([row]) if ca else mixin.import_certificates([row])
        assert stats['imported'] == 0 and stats['failed'] == 1
        assert 'extension' in stats['errors'][0] and cn in stats['errors'][0]
        assert CA.query.filter_by(refid=row['refid']).count() == 0
        assert Certificate.query.filter_by(refid=row['refid']).count() == 0


def test_installing_an_unreadable_certificate_on_a_ca_says_why(app, auth_client):
    cn = f'Dup Host {uuid.uuid4().hex[:8]}'
    with app.app_context():
        ca = CA(refid=uuid.uuid4().hex, descr=cn, crt='', prv=None, serial=0)
        db.session.add(ca)
        db.session.commit()
        ca_id = ca.id
    try:
        pem = _pem_with_repeated_extension(f'{cn} new')
        r = auth_client.post(f'/api/v2/cas/{ca_id}/certificate', data={'pem_content': pem},
                             content_type='multipart/form-data')
        assert r.status_code == 400, r.data
        assert 'extension' in get_json(r)['message'].lower()
    finally:
        with app.app_context():
            CA.query.filter_by(id=ca_id).delete()
            db.session.commit()


def test_the_converter_names_the_unreadable_certificate(auth_client):
    pem = _pem_with_repeated_extension(f'Dup Conv {uuid.uuid4().hex[:8]}')
    r = auth_client.post('/api/v2/tools/convert', json={'pem': pem, 'output_format': 'der'})
    assert r.status_code == 400, r.data
    assert 'extension' in get_json(r)['message'].lower()


def _ca_record(app, cn, crt=''):
    with app.app_context():
        ca = CA(refid=uuid.uuid4().hex, descr=cn, crt=crt, prv=None, serial=0)
        db.session.add(ca)
        db.session.commit()
        return ca.id


def _drop_ca(app, ca_id):
    from models.ca_cross_certificate import CACrossCertificate
    with app.app_context():
        CACrossCertificate.query.filter_by(ca_id=ca_id).delete()
        CA.query.filter_by(id=ca_id).delete()
        db.session.commit()


def _ca_pem(cn, signer=None, issuer_cn=None):
    """A CA certificate for *cn*, self-signed unless *signer* (another key) issues it."""
    key = rsa.generate_private_key(65537, 2048)
    name = x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, cn)])
    issuer = x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, issuer_cn)]) if signer else name
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(issuer)
            .public_key(key.public_key()).serial_number(uuid.uuid4().int >> 66)
            .not_valid_before(dt.datetime(2026, 1, 1)).not_valid_after(dt.datetime(2036, 1, 1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(signer or key, hashes.SHA256()))
    import base64
    return base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode()


def test_attaching_an_unreadable_cross_certificate_is_refused_with_400(app, auth_client):
    from models.ca_cross_certificate import CACrossCertificate
    cn = f'Dup Cross {uuid.uuid4().hex[:8]}'
    ca_id = _ca_record(app, cn, _ca_pem(cn))
    try:
        r = auth_client.post(f'/api/v2/cas/{ca_id}/cross-certificates',
                             json={'certificate': _pem_with_repeated_extension(cn)})
        assert r.status_code == 400, r.data
        assert 'extension' in get_json(r)['message'].lower()
        with app.app_context():
            assert CACrossCertificate.query.filter_by(ca_id=ca_id).count() == 0
    finally:
        _drop_ca(app, ca_id)


def test_restoring_an_unreadable_primary_certificate_is_refused_with_400(app, auth_client):
    cn = f'Dup Restore {uuid.uuid4().hex[:8]}'
    crt = _ca_pem(cn, signer=rsa.generate_private_key(65537, 2048), issuer_cn=f'{cn} other')
    ca_id = _ca_record(app, cn, crt)
    try:
        r = auth_client.post(f'/api/v2/cas/{ca_id}/restore-primary',
                             json={'certificate': _pem_with_repeated_extension(cn)})
        assert r.status_code == 400, r.data
        assert 'extension' in get_json(r)['message'].lower()
        with app.app_context():
            assert db.session.get(CA, ca_id).crt == crt
    finally:
        _drop_ca(app, ca_id)


@pytest.mark.parametrize('as_file', [True, False])
def test_the_trust_store_refuses_an_unreadable_certificate(app, auth_client, as_file):
    import io
    from models.truststore import TrustedCertificate
    cn = f'Dup Trust {uuid.uuid4().hex[:8]}'
    pem = _pem_with_repeated_extension(cn)
    if as_file:
        r = auth_client.post('/api/v2/truststore/import', content_type='multipart/form-data',
                             data={'file': (io.BytesIO(pem.encode()), 'dup.pem'), 'name': cn})
    else:
        r = auth_client.post('/api/v2/truststore', json={'name': cn, 'certificate_pem': pem})
    assert r.status_code == 400, r.data
    assert 'extension' in get_json(r)['message'].lower()
    with app.app_context():
        assert TrustedCertificate.query.filter(TrustedCertificate.subject.contains(cn)).count() == 0
        assert TrustedCertificate.query.filter_by(name=cn).count() == 0


def _signed_leaf_with_repeated_extension(cn, ca_cn, ca_key):
    """A leaf that *ca_key* really signed, whose KeyUsage OID is rewritten to the SKI's before signing."""
    from cryptography.hazmat.primitives.asymmetric import padding
    key = rsa.generate_private_key(65537, 2048)
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, cn)]))
            .issuer_name(x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, ca_cn)]))
            .public_key(key.public_key()).serial_number(uuid.uuid4().int >> 66)
            .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=365))
            .add_extension(x509.KeyUsage(True, False, False, False, False, False, False, False, False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256()))
    tbs = cert.tbs_certificate_bytes
    bad_tbs = tbs.replace(bytes.fromhex('0603551d0f'), bytes.fromhex('0603551d0e'))
    signature = ca_key.sign(bad_tbs, padding.PKCS1v15(), hashes.SHA256())
    der = cert.public_bytes(serialization.Encoding.DER).replace(tbs, bad_tbs).replace(cert.signature, signature)
    bad = x509.load_der_x509_certificate(der)
    with pytest.raises(x509.DuplicateExtension):
        bad.extensions
    return ssl.DER_cert_to_PEM_cert(der)


@pytest.mark.parametrize('route', ['user-import', 'enroll-import'])
def test_the_mtls_imports_refuse_an_unreadable_certificate(app, auth_client, route):
    from models.auth_certificate import AuthCertificate
    from tests.test_backfill_cross_dupes import _cert, _row
    tag = uuid.uuid4().hex[:8]
    ca_cn, cn = f'Dup mTLS CA {tag}', f'Dup mTLS {tag}'
    ca_key = rsa.generate_private_key(65537, 2048)
    with app.app_context():
        ca_id = _row(_cert(ca_key, ca_cn), ca_key)
    try:
        pem = _signed_leaf_with_repeated_extension(cn, ca_cn, ca_key)
        url, body = (('/api/v2/mtls/enroll-import', {'pem': pem}) if route == 'enroll-import'
                     else ('/api/v2/users/1/mtls/certificates', {'mode': 'import', 'pem': pem}))
        r = auth_client.post(url, json=body)
        assert r.status_code == 400, r.data
        assert 'extension' in get_json(r)['message'].lower()
        assert _counts(app, cn) == (0, 0)
        with app.app_context():
            assert AuthCertificate.query.filter(AuthCertificate.cert_subject.contains(cn)).count() == 0
    finally:
        with app.app_context():
            db.session.rollback()
            AuthCertificate.query.filter(AuthCertificate.cert_subject.contains(cn)).delete(synchronize_session=False)
            Certificate.query.filter(Certificate.subject.contains(cn)).delete(synchronize_session=False)
            CA.query.filter_by(id=ca_id).delete()
            db.session.commit()

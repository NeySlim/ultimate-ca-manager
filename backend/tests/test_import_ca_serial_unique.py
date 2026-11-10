"""Importers skip a certificate already stored under the same (CA, serial) pair.

The unique index uix_certificates_ca_serial refuses that row; every importer
checks the pair first, so a re-import neither aborts the bundle nor shows SQL.
"""
import base64
import json
import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from models import db, CA, Certificate
from tests.test_opnsense_import import _Session


def _cert_pem(subject_cn, issuer_cn, key, issuer_key=None, serial=1, ca=False):
    import datetime
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.x509.oid import NameOID
    issuer_key = issuer_key or key
    now = datetime.datetime.now(datetime.timezone.utc)
    builder = (x509.CertificateBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject_cn)]))
               .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_cn)]))
               .public_key(key.public_key()).serial_number(serial)
               .not_valid_before(now - datetime.timedelta(days=1))
               .not_valid_after(now + datetime.timedelta(days=365))
               .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
               .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
               .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_key.public_key()),
                              critical=False))
    return builder.sign(issuer_key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM)


def _pki():
    tag = uuid.uuid4().hex[:8]
    ca_key = rsa.generate_private_key(65537, 2048)
    leaf_key = rsa.generate_private_key(65537, 2048)
    ca_pem = _cert_pem(f'Serial Root {tag}', f'Serial Root {tag}', ca_key, serial=7, ca=True)
    leaf_pem = _cert_pem(f'leaf-{tag}.example.test', f'Serial Root {tag}', leaf_key,
                         issuer_key=ca_key, serial=4242)
    return ca_pem, leaf_pem


def _cleanup(caref):
    Certificate.query.filter_by(caref=caref).delete()
    CA.query.filter_by(refid=caref).delete()
    db.session.commit()


def _smart_import_twice(app):
    from services.smart_import.importer import SmartImporter
    ca_pem, leaf_pem = _pki()
    first = SmartImporter().execute((ca_pem + leaf_pem).decode())
    assert first.success, first.errors
    ca = CA.query.filter_by(refid=Certificate.query.get(
        first.imported_ids['certificates'][0]).caref).first()
    assert ca is not None
    return ca, leaf_pem


def test_smart_import_without_skip_duplicates_keeps_one_row(app):
    from services.smart_import.importer import SmartImporter
    with app.app_context():
        ca, leaf_pem = _smart_import_twice(app)
        try:
            again = SmartImporter().execute(leaf_pem.decode(), options={'skip_duplicates': False})
            assert again.success, again.errors
            assert again.certificates_imported == 0
            assert any('already stored under this CA' in w for w in again.warnings)
            assert Certificate.query.filter_by(caref=ca.refid, serial_number='4242').count() == 1
        finally:
            _cleanup(ca.refid)


def test_smart_import_never_shows_the_sql_of_a_unique_violation(app, monkeypatch):
    from services.smart_import.importer import SmartImporter
    with app.app_context():
        ca, leaf_pem = _smart_import_twice(app)
        try:
            # Without the pre-check the index refuses the row (a concurrent import does the same)
            monkeypatch.setattr(Certificate, 'stored_under', classmethod(lambda cls, caref, serial: None))
            again = SmartImporter().execute(leaf_pem.decode(), options={'skip_duplicates': False})
            assert not again.success
            text = ' '.join(again.errors)
            assert 'already stored under this CA' in text
            assert 'INSERT' not in text and 'IntegrityError' not in text and 'UNIQUE' not in text
        finally:
            monkeypatch.undo()
            _cleanup(ca.refid)


def test_opnsense_route_skips_a_second_row_with_the_same_ca_serial(app, auth_client, monkeypatch):
    from api.v2 import import_opnsense
    ca_pem, leaf_pem = _pki()
    ca_refid = uuid.uuid4().hex[:13]
    ca_rows = [{'uuid': str(uuid.uuid4()), 'refid': ca_refid, 'descr': f'Root {ca_refid}',
                'crt': base64.b64encode(ca_pem).decode(), 'serial': '1'}]
    cert_rows = [{'uuid': str(uuid.uuid4()), 'refid': uuid.uuid4().hex[:13], 'caref': ca_refid,
                  'descr': f'copy {i} {ca_refid}', 'crt_payload': leaf_pem.decode(),
                  'cert_type': 'server_cert'} for i in range(2)]
    monkeypatch.setattr(import_opnsense, 'create_session',
                        lambda verify_ssl=True: _Session(ca_rows, cert_rows))
    try:
        r = auth_client.post('/api/v2/import/opnsense/import', json={
            'host': '192.168.1.254', 'port': 443, 'api_key': 'k', 'api_secret': 's',
            'verify_ssl': False, 'items': []})
        assert r.status_code == 200, r.data
        body = json.loads(r.data)['data']
        assert body['imported'] == {'cas': 1, 'certificates': 1}
        assert any('already stored under this CA' in e for e in body['errors'])
        with app.app_context():
            assert Certificate.query.filter_by(caref=ca_refid).count() == 1
    finally:
        with app.app_context():
            _cleanup(ca_refid)


def test_opnsense_service_skips_a_second_row_with_the_same_ca_serial(app, monkeypatch, tmp_path):
    from services.opnsense import importer
    monkeypatch.setattr(importer, '__file__', str(tmp_path / 'services' / 'opnsense' / 'importer.py'))
    ca_pem, leaf_pem = _pki()
    ca_refid = uuid.uuid4().hex[:13]
    rows = [{'refid': uuid.uuid4().hex[:13], 'caref': ca_refid, 'descr': f'copy {i}',
             'crt': base64.b64encode(leaf_pem).decode(), 'serial_number': '4242'} for i in range(2)]
    with app.app_context():
        try:
            assert importer.ImportMixin().import_cas(
                [{'refid': ca_refid, 'descr': 'root', 'crt': base64.b64encode(ca_pem).decode(),
                  'is_root': True}])['imported'] == 1
            stats = importer.ImportMixin().import_certificates(rows)
            assert stats['imported'] == 1 and stats['skipped'] == 1 and stats['failed'] == 0, stats
            assert any('already stored under this CA' in e for e in stats['errors'])
            assert Certificate.query.filter_by(caref=ca_refid).count() == 1
        finally:
            db.session.rollback()
            _cleanup(ca_refid)

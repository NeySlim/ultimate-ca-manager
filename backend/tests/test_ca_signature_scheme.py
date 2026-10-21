"""A CA signs RSA-PSS when it is set to, and only RSA CAs can be.

The scheme is a per-CA choice (default PKCS#1 v1.5) that can be switched
either way; certificates already issued keep their signature.
"""
import base64
import importlib
import json
import os
import shutil
import sqlite3
import subprocess

import asn1crypto.x509
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import SignatureAlgorithmOID
from sqlalchemy import create_engine, text

from models import CA, Certificate, db

PG_URL = os.getenv('UCM_TEST_PG_URL')


def _post_ca(auth_client, **kwargs):
    data = {'type': 'root', 'commonName': kwargs.pop('cn'), 'keyAlgo': 'RSA', 'keySize': 2048,
            'validityYears': 5, 'hashAlgorithm': 'sha256'}
    data.update(kwargs)
    return auth_client.post('/api/v2/cas', data=json.dumps(data), content_type='application/json')


def _ca_cert(app, ca_id):
    with app.app_context():
        return x509.load_pem_x509_certificate(base64.b64decode(db.session.get(CA, ca_id).crt))


def _issue(auth_client, app, ca_id, cn):
    r = auth_client.post('/api/v2/certificates', content_type='application/json',
                         data=json.dumps({'cn': cn, 'ca_id': ca_id, 'validity_days': 30}))
    assert r.status_code == 201, r.get_json()
    with app.app_context():
        row = db.session.get(Certificate, r.get_json()['data']['id'])
        return x509.load_pem_x509_certificate(base64.b64decode(row.crt))


def _pss_salt(cert):
    params = asn1crypto.x509.Certificate.load(cert.public_bytes(serialization.Encoding.DER))
    return params['signature_algorithm']['parameters']['salt_length'].native


@pytest.fixture(scope='module')
def pss_ca(auth_client):
    r = _post_ca(auth_client, cn='PSS scheme root', signatureScheme='pss')
    assert r.status_code == 201, r.get_json()
    return r.get_json()['data']


def test_a_pss_root_signs_itself_in_pss(app, pss_ca):
    assert pss_ca['signature_scheme'] == 'pss'
    cert = _ca_cert(app, pss_ca['id'])
    assert cert.signature_algorithm_oid == SignatureAlgorithmOID.RSASSA_PSS
    assert _pss_salt(cert) == 32
    cert.verify_directly_issued_by(cert)


def test_a_pss_ca_issues_pss_leaves(app, auth_client, pss_ca):
    leaf = _issue(auth_client, app, pss_ca['id'], 'pss-leaf.example.test')
    assert leaf.signature_algorithm_oid == SignatureAlgorithmOID.RSASSA_PSS
    assert _pss_salt(leaf) == 32
    leaf.verify_directly_issued_by(_ca_cert(app, pss_ca['id']))


@pytest.mark.skipif(not shutil.which('openssl'), reason='openssl not installed')
def test_openssl_verifies_the_pss_chain(app, auth_client, pss_ca, tmp_path):
    leaf = _issue(auth_client, app, pss_ca['id'], 'pss-openssl.example.test')
    (tmp_path / 'ca.pem').write_bytes(_ca_cert(app, pss_ca['id']).public_bytes(serialization.Encoding.PEM))
    (tmp_path / 'leaf.pem').write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    out = subprocess.run(['openssl', 'verify', '-CAfile', str(tmp_path / 'ca.pem'), str(tmp_path / 'leaf.pem')],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr


def test_sha384_pss_salt_is_48():
    from utils.signing_hash import PssBoundRSAKey, rsa_padding_for
    pad = rsa_padding_for(PssBoundRSAKey(rsa.generate_private_key(65537, 2048)), hashes.SHA384())
    assert isinstance(pad, padding.PSS) and pad._salt_length == 48
    assert rsa_padding_for(rsa.generate_private_key(65537, 2048), hashes.SHA384()) is None


def test_the_bound_key_refuses_a_v15_signature(app, pss_ca):
    from services.hsm.ca_key_loader import get_ca_signing_key
    with app.app_context():
        key = get_ca_signing_key(db.session.get(CA, pss_ca['id']))
    with pytest.raises(ValueError, match='RSA-PSS'):
        key.sign(b'tbs', padding.PKCS1v15(), hashes.SHA256())


def test_an_ec_ca_cannot_be_pss(auth_client):
    r = _post_ca(auth_client, cn='EC PSS refused', keyAlgo='ECDSA', keySize='prime256v1',
                 signatureScheme='pss')
    assert r.status_code == 400 and 'RSA key' in r.get_json()['message']


def test_an_unknown_scheme_is_refused(auth_client):
    r = _post_ca(auth_client, cn='Scheme typo', signatureScheme='pss-max')
    assert r.status_code == 400 and 'signatureScheme' in r.get_json()['message']


def test_switching_changes_what_is_signed_next_only(app, auth_client, create_ca):
    ca = create_ca(cn='Scheme switch CA')
    assert ca['signature_scheme'] == 'pkcs1v15'
    before = _issue(auth_client, app, ca['id'], 'before-switch.example.test')
    assert before.signature_algorithm_oid == SignatureAlgorithmOID.RSA_WITH_SHA256

    r = auth_client.patch(f"/api/v2/cas/{ca['id']}", content_type='application/json',
                          data=json.dumps({'signatureScheme': 'pss'}))
    assert r.status_code == 200 and r.get_json()['data']['signature_scheme'] == 'pss'
    after = _issue(auth_client, app, ca['id'], 'after-switch.example.test')
    assert after.signature_algorithm_oid == SignatureAlgorithmOID.RSASSA_PSS
    # The CA's certificate and its key are untouched
    assert _ca_cert(app, ca['id']).signature_algorithm_oid == SignatureAlgorithmOID.RSA_WITH_SHA256

    with app.app_context():
        from models.audit_log import AuditLog
        entry = AuditLog.query.filter_by(action='ca_updated', resource_id=str(ca['id'])) \
            .order_by(AuditLog.id.desc()).first()
        assert 'signature_scheme pkcs1v15 -> pss' in entry.details

    r = auth_client.patch(f"/api/v2/cas/{ca['id']}", content_type='application/json',
                          data=json.dumps({'signatureScheme': 'pkcs1v15'}))
    assert r.status_code == 200
    back = _issue(auth_client, app, ca['id'], 'back-switch.example.test')
    assert back.signature_algorithm_oid == SignatureAlgorithmOID.RSA_WITH_SHA256


def test_an_ec_ca_is_not_switched(app, auth_client, create_ca):
    ca = create_ca(cn='EC switch refused', keyType='ECDSA', keySize='prime256v1')
    r = auth_client.patch(f"/api/v2/cas/{ca['id']}", content_type='application/json',
                          data=json.dumps({'signatureScheme': 'pss', 'name': 'renamed by a refused patch'}))
    assert r.status_code == 400
    with app.app_context():
        row = db.session.get(CA, ca['id'])
        assert row.signature_scheme == 'pkcs1v15' and row.descr != 'renamed by a refused patch'


def test_an_hsm_provider_without_pss_is_refused():
    from services.ca.signature_scheme import pss_refusal
    assert 'does not sign RSA-PSS' in pss_refusal(True, 'azure-keyvault')
    assert 'does not sign RSA-PSS' in pss_refusal(True, 'google-kms')
    assert pss_refusal(True, None) is None


def test_an_external_csr_ca_requests_in_pss(app, auth_client):
    r = _post_ca(auth_client, cn='PSS external', type='external', signatureScheme='pss')
    assert r.status_code == 201, r.get_json()
    with app.app_context():
        csr = x509.load_pem_x509_csr(base64.b64decode(db.session.get(CA, r.get_json()['data']['id']).csr))
    assert csr.signature_algorithm_oid == SignatureAlgorithmOID.RSASSA_PSS
    assert csr.is_signature_valid


def test_backups_keep_the_scheme(app, pss_ca):
    from services.backup.backup_service import BackupService
    from services.backup.restore_core import RestoreCoreMixin as RestoreCore
    with app.app_context():
        exported = next(row for row in BackupService()._export_cas(True) if row['refid'] == pss_ca['refid'])
        assert exported['signature_scheme'] == 'pss'
        row = db.session.get(CA, pss_ca['id'])
        row.signature_scheme = 'pkcs1v15'
        RestoreCore._apply_ca_fields(row, {'refid': row.refid, 'signature_scheme': 'pss'})
        assert row.signature_scheme == 'pss'
        RestoreCore._apply_ca_fields(row, {'refid': row.refid, 'signature_scheme': 'bogus'})
        assert row.signature_scheme == 'pss'
        db.session.commit()


def test_sqlite_migration_defaults_existing_cas_to_v15():
    m = importlib.import_module('migrations.106_ca_signature_scheme')
    conn = sqlite3.connect(':memory:')
    conn.execute(f"CREATE TABLE {CA.__tablename__} (id INTEGER PRIMARY KEY, descr TEXT)")
    conn.execute(f"INSERT INTO {CA.__tablename__} VALUES (1, 'old')")
    m.upgrade(conn)
    m.upgrade(conn)
    assert conn.execute(f"SELECT signature_scheme FROM {CA.__tablename__} WHERE id = 1").fetchone()[0] == 'pkcs1v15'


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_migration_defaults_existing_cas_to_v15():
    m = importlib.import_module('migrations.106_ca_signature_scheme')
    schema = f"migtest_106_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        table = CA.__tablename__
        conn.execute(text(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, descr TEXT)"))
        conn.execute(text(f"INSERT INTO {table} VALUES (1, 'old')"))
        m.upgrade(conn)
        m.upgrade(conn)
        assert conn.execute(text(f"SELECT signature_scheme FROM {table} WHERE id = 1")).scalar() == 'pkcs1v15'
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()

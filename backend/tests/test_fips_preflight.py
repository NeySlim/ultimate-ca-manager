"""FIPS preflight: each detector finds what FIPS mode will refuse, on SQLite
and on PostgreSQL, and a clean standard instance has nothing to report.

Every case seeds an installation of its own (a SQLite file, or a schema of
this file's own on the PostgreSQL bench) inside a transaction it rolls back.
"""
import base64
import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from cryptography.x509.oid import NameOID
from sqlalchemy import create_engine, text

from config.settings import Config
from models import (CA, AcmeClientOrder, Certificate, CertificatePolicy, CertificateTemplate,
                    DeployTarget, DnsProvider, HsmKey, HsmProvider, MicrosoftCA, SSHCertificate,
                    SSHCertificateAuthority, SystemConfig, User, db)
from services import fips_preflight
from tests.test_backup_cross_installation import _bound_to
from utils.datetime_utils import utc_now
from utils.db_url import postgres_gssenc_problem, postgres_tls_problem
from utils.password_hash import hash_password

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
SCRYPT_HASH = 'scrypt:32768:8:1$abcdefgh$' + 'ab' * 64

BACKENDS = [
    pytest.param('sqlite', id='sqlite'),
    pytest.param('postgresql', id='postgresql', marks=[
        pytest.mark.postgres,
        pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')]),
]


@contextmanager
def _pg_schema():
    name = f'fips_preflight_{os.getpid()}'
    admin = create_engine(_PG_URL, pool_pre_ping=True)
    try:
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS {name} CASCADE'))
            connection.execute(text(f'CREATE SCHEMA {name}'))
        separator = '&' if '?' in _PG_URL else '?'
        yield f'{_PG_URL}{separator}options=-csearch_path%3D{name}'
    finally:
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS {name} CASCADE'))
        admin.dispose()


@pytest.fixture(scope='module', params=BACKENDS)
def installation(request, app, tmp_path_factory):
    if request.param == 'sqlite':
        url = f"sqlite:///{tmp_path_factory.mktemp('fips-preflight') / 'ucm.db'}"
        with _bound_to(app, url):
            yield request.param
    else:
        with _pg_schema() as url, _bound_to(app, url, is_postgresql=True):
            yield request.param


@pytest.fixture
def session(app, installation, monkeypatch, tmp_path):
    """An app context on the installation; nothing seeded survives the test."""
    monkeypatch.setattr(Config, 'BACKUP_DIR', tmp_path / 'backups', raising=False)
    (tmp_path / 'backups').mkdir()
    monkeypatch.setitem(app.config, 'HTTPS_CERT_PATH', tmp_path / 'absent.pem')
    monkeypatch.setitem(app.config, 'SQLALCHEMY_DATABASE_URI', 'sqlite:///:memory:')
    with app.app_context():
        assert db.engine.dialect.name == installation
        try:
            yield db.session
        finally:
            db.session.rollback()


def _finding(report, detector_id):
    found = [f for f in report['findings'] if f['id'] == detector_id]
    return found[0] if found else None


def _assert_found(detector_id, count, *needles):
    report = fips_preflight.run()
    assert report['errors'] == []
    finding = _finding(report, detector_id)
    assert finding is not None, f'{detector_id} found nothing'
    assert finding['count'] == count
    for needle in needles:
        assert any(needle in example for example in finding['examples']), finding['examples']
    return finding


# --- material ---------------------------------------------------------------

def _certificate(key, cn='preflight.test', days=365):
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.now(timezone.utc)
    builder = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
               .public_key(key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=days)))
    digest = None if isinstance(key, ed25519.Ed25519PrivateKey) else hashes.SHA256()
    return builder.sign(key, digest)


def _stored(cert):
    return base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode()


def _ca(key, descr):
    ca = CA(refid=str(uuid.uuid4()), descr=descr, crt=_stored(_certificate(key, descr)))
    db.session.add(ca)
    db.session.flush()
    return ca


def _ed25519():
    return ed25519.Ed25519PrivateKey.generate()


def _rsa(bits):
    return rsa.generate_private_key(public_exponent=65537, key_size=bits)


def _leaf(descr, key=None, untyped=False, **extra):
    """An active certificate; key_algo follows crt, as on every issuance path."""
    cert = Certificate(refid=str(uuid.uuid4()), descr=descr, subject_cn=descr,
                       crt=_stored(_certificate(key or ec.generate_private_key(ec.SECP256R1()))),
                       valid_to=utc_now() + timedelta(days=30), **extra)
    if untyped:
        cert.key_algo = None
    db.session.add(cert)
    db.session.flush()
    return cert


def _config(key, value):
    db.session.add(SystemConfig(key=key, value=value))
    db.session.flush()


def _openssh_public(key):
    return key.public_key().public_bytes(serialization.Encoding.OpenSSH,
                                         serialization.PublicFormat.OpenSSH).decode()


def _ssh_ca(descr, key_type, key):
    ca = SSHCertificateAuthority(descr=descr, ca_type='user', public_key=_openssh_public(key),
                                 private_key='unused', key_type=key_type, fingerprint=descr)
    db.session.add(ca)
    db.session.flush()
    return ca


# --- one case per detector ----------------------------------------------------

@pytest.mark.parametrize('spelling, approved', [
    ('RSA 2048', True), ('RSA-4096', True), ('RSA 8192', True), ('EC secp256r1', True),
    ('EC-P384', True), ('RSA 1024', False), ('RSA-1024', False), ('Ed25519', False),
    ('ED448', False), ('EC brainpoolP256r1', False), ('DSA 2048', False), ('', False),
])
def test_stored_label_approved(spelling, approved):
    assert fips_preflight.stored_label_approved(spelling) is approved


def test_users_password_scrypt(session):
    session.add(User(username='scrypt-user', email='s@example.com', password_hash=SCRYPT_HASH))
    session.add(User(username='pbkdf2-user', email='p@example.com',
                     password_hash=hash_password('a long password')))
    session.add(User(username='sso-user', email='o@example.com', password_hash=SCRYPT_HASH,
                     auth_source='sso'))
    session.flush()
    _assert_found('users.password_scrypt', 1, 'scrypt-user')


def test_users_backup_codes_scrypt(session):
    session.add(User(username='codes-user', email='c@example.com',
                     password_hash=hash_password('a long password'),
                     backup_codes=json.dumps([SCRYPT_HASH, hash_password('code')])))
    session.flush()
    _assert_found('users.backup_codes_scrypt', 1, 'codes-user')


def test_protocol_secrets_scrypt(session):
    _config('est_password', SCRYPT_HASH)
    _config('wstep_password', hash_password('pbkdf2 secret'))
    _config('xcep_password', 'legacy plaintext')
    finding = _assert_found('protocols.secret_scrypt', 1, 'EST')
    assert finding['severity'] == 'blocker'


def test_ca_eddsa_key(session):
    _ca(ed25519.Ed25519PrivateKey.generate(), 'Edwards Root')
    _ca(ec.generate_private_key(ec.SECP384R1()), 'EC Root')
    _assert_found('ca.eddsa_key', 1, 'Edwards Root')


def test_ca_weak_key(session):
    _ca(rsa.generate_private_key(public_exponent=65537, key_size=1024), 'Short RSA Root')
    _ca(ec.generate_private_key(ec.BrainpoolP256R1()), 'Brainpool Root')
    _ca(rsa.generate_private_key(public_exponent=65537, key_size=3072), 'RSA Root')
    _assert_found('ca.weak_key', 2, 'Short RSA Root (#', 'RSA 1024', 'EC brainpoolP256r1')


def test_eddsa_is_told_without_loading_the_key(session, monkeypatch):
    _ca(ed25519.Ed25519PrivateKey.generate(), 'Unloadable Root')

    def refuse(*_a, **_k):
        raise AssertionError('the key was loaded')
    monkeypatch.setattr(x509.Certificate, 'public_key', refuse, raising=False)
    names = fips_preflight._ca_eddsa()
    assert any('Unloadable Root' in n for n in names)


def test_ssh_ca_eddsa_key(session):
    _ssh_ca('Edwards SSH CA', 'ed25519', ed25519.Ed25519PrivateKey.generate())
    _ssh_ca('ECDSA SSH CA', 'ecdsa-p256', ec.generate_private_key(ec.SECP256R1()))
    _assert_found('ssh_ca.eddsa_key', 1, 'Edwards SSH CA')


def test_ssh_certificates_eddsa_key(session):
    ca = _ssh_ca('Signer', 'ecdsa-p256', ec.generate_private_key(ec.SECP256R1()))
    for key_id, key_type, valid_to in (('alice-ed', 'ed25519', 1), ('bob-ec', 'ecdsa-p256', 1),
                                       ('old-ed', 'ed25519', -1)):
        session.add(SSHCertificate(ssh_ca_id=ca.id, cert_type='user', key_id=key_id,
                                   public_key='k', certificate='c', principals='[]', serial=1,
                                   valid_from=utc_now() - timedelta(days=2),
                                   valid_to=utc_now() + timedelta(days=valid_to),
                                   key_type=key_type, fingerprint=key_id))
    session.flush()
    finding = _assert_found('ssh_certificates.eddsa_key', 1, 'alice-ed')
    assert finding['severity'] == 'info'


def test_deploy_ssh_eddsa_key(session):
    session.add(DeployTarget(name='edwards-host', host='h1', username='u', private_key='x',
                             public_key=_openssh_public(ed25519.Ed25519PrivateKey.generate())))
    session.add(DeployTarget(name='ecdsa-host', host='h2', username='u', private_key='x',
                             public_key=_openssh_public(ec.generate_private_key(ec.SECP256R1()))))
    session.flush()
    _assert_found('deploy.ssh_eddsa_key', 1, 'edwards-host')


def test_ocsp_responder_unapproved_key(session):
    responder = _leaf('ocsp-responder', _ed25519())
    _config('ocsp_responder_cert_1', str(responder.id))
    _assert_found('ocsp.responder_unapproved_key', 1, 'ocsp-responder')


def test_tsa_signer_unapproved_key(session):
    signer = _leaf('tsa-signer', _rsa(1024))
    _config('tsa_signer_cert_refid', signer.refid)
    _config('tsa_enabled', 'true')
    _assert_found('tsa.signer_unapproved_key', 1, 'tsa-signer')


def test_certificates_unapproved_key(session):
    _leaf('ed-leaf', _ed25519())
    _leaf('short-leaf', _rsa(1024))
    _leaf('untyped-ed-leaf', _ed25519(), untyped=True)
    _leaf('rsa-leaf', _rsa(3072))
    _leaf('ec-leaf')
    _leaf('revoked-ed-leaf', _ed25519(), revoked=True)
    _leaf('archived-ed-leaf', _ed25519(), archived=True)
    finding = _assert_found('certificates.unapproved_key', 3, 'ed-leaf', 'short-leaf',
                            'untyped-ed-leaf')
    assert finding['severity'] == 'info'


def test_templates_unapproved_key_type(session):
    for name, key_type in (('ed-template', 'ED25519'), ('rsa-template', 'RSA-2048'),
                           ('rsa1024-template', 'RSA-1024')):
        session.add(CertificateTemplate(name=name, template_type='custom', key_type=key_type,
                                        extensions_template='{}'))
    session.flush()
    _assert_found('templates.unapproved_key_type', 2, 'ed-template', 'rsa1024-template')


def test_policies_unapproved_key_type(session):
    session.add(CertificatePolicy(name='mixed', rules=json.dumps(
        {'allowed_key_types': ['RSA-2048', 'ED25519', 'ED448']})))
    session.add(CertificatePolicy(name='approved', rules=json.dumps(
        {'allowed_key_types': ['RSA-2048', 'EC-P384']})))
    session.flush()
    _assert_found('policies.unapproved_key_type', 1, 'mixed (#', 'ED25519, ED448')


def test_acme_client_unapproved_key_type(session):
    _config('acme.client.key_type', 'ED25519')
    source = _leaf('acme-source', _ed25519())
    session.add(AcmeClientOrder(domains=json.dumps(['reuse.example']), key_source='reuse',
                                source_certificate_id=source.id))
    session.add(AcmeClientOrder(domains=json.dumps(['fresh.example']), key_type='EC-P256'))
    session.flush()
    _assert_found('acme_client.unapproved_key_type', 2, 'acme.client.key_type', 'reuse.example')


def test_hsm_softhsm(session):
    session.add(HsmProvider(name='Soft', type='pkcs11',
                            config=json.dumps({'module_path': '/usr/lib/softhsm/libsofthsm2.so'})))
    session.add(HsmProvider(name='Hardware', type='pkcs11',
                            config=json.dumps({'module_path': '/usr/lib/vendor/libhsm.so'})))
    session.flush()
    _assert_found('hsm.softhsm', 1, 'Soft')


def test_hsm_gcp_grpc(session):
    session.add(HsmProvider(name='Cloud KMS', type='google-kms', config='{}'))
    session.flush()
    _assert_found('hsm.gcp_grpc', 1, 'Cloud KMS')


def test_hsm_unapproved_keys(session):
    provider = HsmProvider(name='Bao', type='openbao', config='{}')
    session.add(provider)
    session.flush()
    for label, algorithm in (('ed-key', 'Ed25519'), ('chacha-key', 'ChaCha20'),
                             ('rsa-key', 'RSA-3072'), ('aes-key', 'AES-256'),
                             ('unreadable', 'UNKNOWN'), ('azure-oct', 'oct-HSM')):
        session.add(HsmKey(provider_id=provider.id, key_identifier=label, label=label,
                           algorithm=algorithm, key_type='asymmetric', purpose='signing'))
    session.flush()
    _assert_found('hsm.unapproved_keys', 2, 'ed-key', 'chacha-key')


def test_dns_tsig_hmac_md5(session):
    for name, algorithm in (('md5-dns', 'hmac-md5'), ('sha-dns', 'hmac-sha256')):
        provider = DnsProvider(name=name, provider_type='rfc2136')
        provider.credentials = json.dumps({'server': 'ns', 'tsig_key_name': 'k',
                                           'tsig_key_secret': 's', 'tsig_algorithm': algorithm})
        session.add(provider)
    session.flush()
    _assert_found('dns.tsig_hmac_md5', 1, 'md5-dns')


def test_msca_winrm_ntlm(session):
    for name, transport, enabled in (('ntlm-ca', 'ntlm', True), ('krb-ca', 'kerberos', True),
                                     ('off-ca', 'ntlm', False)):
        session.add(MicrosoftCA(name=name, server='adcs', auth_method='basic',
                                winrm_enabled=enabled, winrm_transport=transport))
    session.flush()
    _assert_found('msca.winrm_ntlm', 1, 'ntlm-ca')


@pytest.mark.parametrize('kdf, flagged', [('argon2id', True), ('pbkdf2', False)])
def test_backup_schedule_argon2id(session, kdf, flagged):
    _config('auto_backup_enabled', 'true')
    _config('backup_kdf', kdf)
    finding = _finding(fips_preflight.run(), 'backup.schedule_argon2id')
    assert (finding is not None) is flagged


def test_backup_archives_argon2id(session):
    from services.backup import container
    directory = Config.BACKUP_DIR
    for name, kdf_id in (('ucm_backup_a.ucmbkp', container.KDF_ARGON2ID),
                         ('ucm_backup_b.ucmbkp', container.KDF_PBKDF2)):
        header = container.build_header(format_version=3, flags=0, kdf_id=kdf_id, metadata={})
        (directory / name).write_bytes(header + b'ciphertext')
    _assert_found('backup.archives_argon2id', 1, 'ucm_backup_a.ucmbkp')


def test_database_postgres_without_tls(session, app, monkeypatch):
    monkeypatch.setitem(app.config, 'SQLALCHEMY_DATABASE_URI',
                        'postgresql+psycopg2://ucm:pw@db.example:5432/ucm')
    monkeypatch.delenv('PGSSLMODE', raising=False)
    _assert_found('database.postgres_without_tls', 1, 'sslmode=prefer')


@pytest.mark.parametrize('url, env, problem', [
    ('postgresql://u:p@db.example/ucm', {}, 'sslmode=prefer'),
    ('postgresql://u:p@db.example/ucm?sslmode=disable', {}, 'sslmode=disable'),
    ('postgresql://u:p@db.example/ucm?sslmode=require', {}, None),
    ('postgresql://u:p@db.example/ucm?sslmode=verify-full', {}, None),
    ('postgresql://u:p@db.example/ucm', {'PGSSLMODE': 'verify-ca'}, None),
    ('postgresql://u:p@/ucm?host=/var/run/postgresql', {}, None),
    ('postgresql://u:p@/ucm', {}, None),
    ('postgresql://u:p@/ucm', {'PGHOST': 'db.example'}, 'sslmode=prefer'),
    ('sqlite:////opt/ucm/data/ucm.db', {}, None),
])
def test_postgres_tls_problem(url, env, problem):
    assert postgres_tls_problem(url, env) == problem


@pytest.mark.parametrize('url, env, problem', [
    ('postgresql://u@db/ucm?sslmode=require', {}, None),
    ('postgresql://u@db/ucm?gssencmode=disable', {'PGGSSENCMODE': 'prefer'}, None),
    ('postgresql://u@db/ucm?gssencmode=prefer', {}, 'gssencmode=prefer'),
    ('postgresql://u@db/ucm', {'PGGSSENCMODE': 'require'}, 'gssencmode=require'),
    ('postgresql://u@/ucm?host=/run/postgresql&gssencmode=require', {}, None),
    ('sqlite:////var/lib/ucm/ucm.db', {'PGGSSENCMODE': 'require'}, None),
])
def test_postgres_gssenc_problem(url, env, problem):
    assert postgres_gssenc_problem(url, env) == problem


def test_https_unapproved_key(session, app, tmp_path, monkeypatch):
    path = tmp_path / 'https_cert.pem'
    path.write_bytes(_certificate(ed25519.Ed25519PrivateKey.generate()).public_bytes(
        serialization.Encoding.PEM))
    monkeypatch.setitem(app.config, 'HTTPS_CERT_PATH', path)
    _assert_found('https.unapproved_key', 1, 'https_cert.pem: Ed25519')


# --- the whole run ------------------------------------------------------------

def test_a_clean_instance_has_nothing_to_report(session, app, tmp_path, monkeypatch):
    from services.template_service import TemplateService
    TemplateService.seed_system_templates()
    session.add(User(username='admin-clean', email='a@example.com',
                     password_hash=hash_password('a long password')))
    _ca(ec.generate_private_key(ec.SECP256R1()), 'Clean Root')
    _leaf('clean-leaf', _rsa(2048))
    _ssh_ca('Clean SSH CA', 'ecdsa-p256', ec.generate_private_key(ec.SECP256R1()))
    session.add(CertificatePolicy(name='clean-policy', rules=json.dumps(
        {'allowed_key_types': ['RSA-2048', 'RSA-4096', 'EC-P256', 'EC-P384']})))
    _config('auto_backup_enabled', 'true')
    _config('backup_kdf', 'pbkdf2')
    https = tmp_path / 'https_cert.pem'
    https.write_bytes(_certificate(ec.generate_private_key(ec.SECP384R1())).public_bytes(
        serialization.Encoding.PEM))
    monkeypatch.setitem(app.config, 'HTTPS_CERT_PATH', https)
    session.flush()

    report = fips_preflight.run()
    assert report['errors'] == []
    assert report['findings'] == []
    assert report['ready'] is True
    assert report['summary'] == {'blocker': 0, 'warning': 0, 'info': 0}
    assert set(report['checked']) == {d.id for d in fips_preflight.DETECTORS}


def test_findings_are_ordered_and_counted(session):
    _leaf('info-leaf', _ed25519())
    session.add(HsmProvider(name='Cloud', type='google-kms', config='{}'))
    session.add(User(username='blocked', email='b@example.com', password_hash=SCRYPT_HASH))
    session.flush()
    report = fips_preflight.run()
    severities = [f['severity'] for f in report['findings']]
    assert severities == sorted(severities, key=fips_preflight.SEVERITIES.index)
    assert report['summary'] == {'blocker': 1, 'warning': 1, 'info': 1}
    assert report['ready'] is False


def test_examples_are_capped(session):
    for i in range(fips_preflight.MAX_EXAMPLES + 3):
        session.add(User(username=f'many-{i}', email=f'm{i}@example.com', password_hash=SCRYPT_HASH))
    session.flush()
    finding = _assert_found('users.password_scrypt', fips_preflight.MAX_EXAMPLES + 3)
    assert len(finding['examples']) == fips_preflight.MAX_EXAMPLES


def test_a_failing_check_is_reported_and_the_others_still_run(session):
    def broken():
        raise RuntimeError('boom')
    detectors = [fips_preflight.Detector('test.broken', 'blocker', 't', 'r', broken),
                 fips_preflight.Detector('test.ok', 'info', 't', 'r', lambda: ['x'])]
    report = fips_preflight.run(detectors)
    assert report['errors'] == [{'id': 'test.broken', 'error': 'RuntimeError: boom'}]
    assert [f['id'] for f in report['findings']] == ['test.ok']
    assert report['ready'] is False


def test_detector_ids_are_unique_and_severities_known():
    ids = [d.id for d in fips_preflight.DETECTORS]
    assert len(ids) == len(set(ids))
    assert {d.severity for d in fips_preflight.DETECTORS} <= set(fips_preflight.SEVERITIES)
    assert all(d.remedy and d.title for d in fips_preflight.DETECTORS)

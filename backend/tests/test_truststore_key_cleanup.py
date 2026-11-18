"""Trust store rows an older version stored with a private key: the start-up pass removes the key and
keeps the certificates and the row, and a restored archive never brings a key back. Both run on
SQLite and, with UCM_TEST_PG_URL, on PostgreSQL."""
import datetime
import logging
import os
import uuid
from contextlib import contextmanager

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from sqlalchemy import text

from models import AuditLog, db
from models.truststore import TrustedCertificate
from tests.test_backup_cross_installation import Keys, _installation

ACTION = 'truststore_private_key_removed'
_PG_URL = os.environ.get('UCM_TEST_PG_URL')
ENGINES = ['sqlite', pytest.param('postgresql', marks=[
    pytest.mark.postgres, pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')])]


def _issue(cn):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=30)).sign(key, hashes.SHA256()))
    return (cert.public_bytes(serialization.Encoding.PEM).decode(),
            key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                              serialization.NoEncryption()).decode(),
            cert.fingerprint(hashes.SHA256()).hex())


@contextmanager
def _database(engine, tmp_path):
    if engine == 'sqlite':
        yield f"sqlite:///{tmp_path / 'trust-keys.db'}"
        return
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own
    with _a_schema_of_our_own(f'trust_keys_{uuid.uuid4().hex[:6]}') as url:
        yield url


@pytest.fixture(params=ENGINES)
def here(app, tmp_path, request):
    """An installation of its own, so the rows written here meet no other test's."""
    with _database(request.param, tmp_path) as url, \
            _installation(app, url, Keys(tmp_path, 'trust'), is_postgresql=request.param != 'sqlite'), \
            app.app_context():
        yield request.param
        db.session.rollback()


def _row(name, pem, fp):
    row = TrustedCertificate(name=name, certificate_pem=pem, fingerprint_sha256=fp, purpose='custom')
    db.session.add(row)
    db.session.commit()
    return row.id


def _stored():
    db.session.expire_all()
    return {r.id: r.certificate_pem for r in TrustedCertificate.query.all()}


def _audited(after):
    return AuditLog.query.filter(AuditLog.id > after, AuditLog.action == ACTION).all()


def _last_audit():
    return db.session.query(db.func.max(AuditLog.id)).scalar() or 0


# ---------------------------------------------------------------- start-up cleanup

def test_the_start_removes_stored_keys_once_and_keeps_the_rows(here, caplog):
    from utils.trust_pem import strip_stored_private_keys
    kc, kc_key, kc_fp = _issue('key-then-certificate')
    ck, ck_key, ck_fp = _issue('certificate-then-key')
    legacy, legacy_key, legacy_fp = _issue('legacy-label')
    sane, _, sane_fp = _issue('sane')
    chain_a, _, chain_fp = _issue('chain-a')
    chain_b, _, _ = _issue('chain-b')
    old = legacy.replace('BEGIN CERTIFICATE', 'BEGIN X509 CERTIFICATE').replace('END CERTIFICATE',
                                                                               'END X509 CERTIFICATE')
    ids = {
        'kc': _row('server.pem', kc_key + kc, kc_fp),
        'ck': _row('cert and key', ck + ck_key, ck_fp),
        'legacy': _row('legacy label', legacy_key + old, legacy_fp),
        'sane': _row('sane', 'subject=CN=sane\n' + sane, sane_fp),
        'chain': _row('chain', chain_a + chain_b, chain_fp),
    }
    before = _last_audit()
    with caplog.at_level(logging.WARNING):
        assert strip_stored_private_keys() == 3
    stored = _stored()
    assert stored[ids['kc']] == kc and stored[ids['ck']] == ck and stored[ids['legacy']] == legacy
    assert stored[ids['sane']] == 'subject=CN=sane\n' + sane
    assert stored[ids['chain']] == chain_a + chain_b
    audited = _audited(before)
    assert sorted(int(e.resource_id) for e in audited) == sorted([ids['kc'], ids['ck'], ids['legacy']])
    assert all(e.username == 'system' and 'compromised' in e.details for e in audited)
    warned = [m for m in caplog.messages if 'held a private key' in m]
    assert len(warned) == 3 and all('compromised' in m for m in warned)
    assert any(f'Trust store entry {ids["kc"]} "server.pem"' in m for m in warned)
    for key in (kc_key, ck_key, legacy_key):
        body = key.splitlines()[1]
        assert not any(body in m for m in caplog.messages)
        assert not any(body in (e.details or '') for e in audited)

    # A second start finds nothing left to do
    again = _last_audit()
    with caplog.at_level(logging.WARNING):
        caplog.clear()
        assert strip_stored_private_keys() == 0
    assert _stored() == stored
    assert _audited(again) == [] and not caplog.messages


def test_a_row_the_start_cannot_read_is_left_and_named(here, caplog):
    """A value that is not text (SQLite stores what it is given) stops neither the pass nor the start."""
    from utils.trust_pem import strip_stored_private_keys
    if here != 'sqlite':
        pytest.skip('only SQLite stores a value of another type in a text column')
    kc, kc_key, kc_fp = _issue('readable')
    keyed_id = _row('readable', kc_key + kc, kc_fp)
    odd = b'\xff\xfe-----BEGIN PRIVATE KEY-----\n\x00'
    db.session.execute(text("INSERT INTO trusted_certificates (name, certificate_pem, fingerprint_sha256, purpose) "
                            "VALUES ('odd', :p, :f, 'custom')"), {'p': odd, 'f': 'f' * 64})
    db.session.commit()
    odd_id = db.session.execute(text("SELECT id FROM trusted_certificates WHERE name = 'odd'")).scalar()
    with caplog.at_level(logging.WARNING):
        assert strip_stored_private_keys() == 1
    assert _stored()[keyed_id] == kc
    assert db.session.execute(text('SELECT certificate_pem FROM trusted_certificates WHERE id = :i'),
                              {'i': odd_id}).scalar() == odd
    assert any(f'Trust store entry {odd_id} ' in m and 'left as is' in m for m in caplog.messages)


def test_a_row_changed_since_it_was_read_is_not_overwritten(here, monkeypatch):
    """Two starts racing: the row is written only while it still holds the text read."""
    import utils.trust_pem as trust_pem
    kc, kc_key, kc_fp = _issue('raced')
    row_id = _row('raced', kc_key + kc, kc_fp)
    other, _, _ = _issue('written-meanwhile')
    real = trust_pem.served_certificates

    def meanwhile(stored):
        db.session.execute(text('UPDATE trusted_certificates SET certificate_pem = :p WHERE id = :i'),
                           {'p': other, 'i': row_id})
        return real(stored)

    monkeypatch.setattr(trust_pem, 'served_certificates', meanwhile)
    before = _last_audit()
    assert trust_pem.strip_stored_private_keys() == 0
    db.session.rollback()
    assert _audited(before) == []


def test_the_housekeeping_runs_the_cleanup(app, monkeypatch):
    import app as app_module
    import utils.trust_pem as trust_pem
    ran = []
    monkeypatch.setattr(trust_pem, 'strip_stored_private_keys', lambda: ran.append(True) or 0)
    app_module.run_startup_housekeeping(app)
    assert ran == [True]


def test_a_failing_cleanup_does_not_stop_the_start(app, monkeypatch, caplog):
    import app as app_module
    import utils.trust_pem as trust_pem

    def boom():
        raise RuntimeError('database gone')

    monkeypatch.setattr(trust_pem, 'strip_stored_private_keys', boom)
    with caplog.at_level(logging.WARNING):
        app_module.run_startup_housekeeping(app)
    assert any('non-fatal' in m and 'private key' in m for m in caplog.messages)


# ---------------------------------------------------------------- restore of an archive made before

def test_an_archived_entry_holding_a_key_is_restored_without_it(here, caplog):
    from tests.test_backup_hostile_corpus import PASSWORD, _forged, _service
    keyed, key, keyed_fp = _issue('archived-with-key')
    clean, _, clean_fp = _issue('archived-clean')

    def entries(data):
        data['trusted_certificates'] = [
            {'name': 'server.pem', 'certificate_pem': key + keyed, 'fingerprint_sha256': keyed_fp,
             'purpose': 'custom'},
            {'name': 'clean', 'certificate_pem': clean, 'fingerprint_sha256': clean_fp, 'purpose': 'custom'},
        ]

    blob = _forged(['trusted_certificates'], mutate=entries)
    before = _last_audit()
    with caplog.at_level('WARNING'):
        results = _service().restore_backup(blob, PASSWORD, mode='merge')
    db.session.expire_all()
    stored = {r.fingerprint_sha256: r for r in TrustedCertificate.query.all()}
    assert stored[keyed_fp].certificate_pem == keyed
    assert stored[clean_fp].certificate_pem == clean
    assert [e['id'] for e in results['truststore_private_keys_removed']] == [stored[keyed_fp].id]
    warned = [m for m in caplog.messages if 'held a private key' in m]
    assert warned and all('"server.pem"' in m for m in warned)
    body = key.splitlines()[1]
    assert not any(body in m for m in caplog.messages) and body not in str(results)
    (entry,) = _audited(before)
    assert entry.resource_id == str(stored[keyed_fp].id) and 'compromised' in entry.details

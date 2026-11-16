"""Upgrade step 166: every trust store row of a 2.254 database keeps its certificate blocks only; a
row a private key is removed from is logged and listed, never the key, and the next start turns
the list into audit entries."""
import datetime
import importlib
import json

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from tests.upgrade_2254_support import BACKENDS, make_base
from utils.trust_pem import REMOVED_ACTION, REMOVED_KEY

STEP = '166_trust_store_certificates_only'


def _issue(cn):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=30)).sign(key, hashes.SHA256()))
    pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
    return pem, key_pem, cert.fingerprint(hashes.SHA256()).hex()


_MADE = {}


def _rows():
    """(id, name, stored, expected after the step, key removed): made once for every backend."""
    if not _MADE:
        sane, _, _ = _issue('sane')
        kc, kc_key, _ = _issue('key-then-certificate')
        ck, ck_key, _ = _issue('certificate-then-key')
        text, _, _ = _issue('after-text')
        first, _, _ = _issue('chain-first')
        second, _, _ = _issue('chain-second')
        _, only_key, _ = _issue('key-only')
        old, old_key, _ = _issue('legacy-label')
        old = old.replace('BEGIN CERTIFICATE', 'BEGIN X509 CERTIFICATE').replace('END CERTIFICATE', 'END X509 CERTIFICATE')
        _MADE['rows'] = [
            (1, 'sane', sane, sane, False),
            (2, 'server.pem', kc_key + kc, kc, True),
            (3, 'cert and key', ck + ck_key, ck, True),
            (4, 'after text', 'subject=CN=after-text\nissuer=CN=after-text\n' + text, text, False),
            (5, 'chain', first + second, first + second, False),
            (6, 'key only', only_key, '', True),
            (7, 'legacy label', old_key + old, old, True),
        ]
        _MADE['keys'] = (kc_key, ck_key, only_key, old_key)
    return _MADE['rows']


def _populate(db):
    for row_id, name, stored, _, _ in _rows():
        db.run("INSERT INTO trusted_certificates (id, name, certificate_pem, fingerprint_sha256, purpose) "
               "VALUES (:i, :n, :p, :f, 'custom')", {'i': row_id, 'n': name, 'p': stored, 'f': f'{row_id:064x}'})


def _stored(db):
    return dict(db.run("SELECT id, certificate_pem FROM trusted_certificates ORDER BY id"))


def _listed(db):
    rows = db.run("SELECT value FROM system_config WHERE key = :k", {'k': REMOVED_KEY})
    return json.loads(rows[0][0]) if rows else None


def test_the_step_is_part_of_the_upgrade():
    from migrations._from_2_254 import STEPS
    assert STEPS.index(STEP) == STEPS.index('165_sso_ldap_group_base_dn') + 1


@pytest.mark.parametrize('dialect', BACKENDS)
def test_a_2254_trust_store_keeps_its_certificates_only(dialect, tmp_path, monkeypatch, caplog):
    for db in make_base(dialect, tmp_path, monkeypatch, 'ts'):
        _populate(db)
        with caplog.at_level('WARNING'):
            assert db.upgrade()
        after = _stored(db)
        assert after == {row_id: expected for row_id, _, _, expected, _ in _rows()}
        listed = _listed(db)
        keyed = [row_id for row_id, _, _, _, removed in _rows() if removed]
        assert sorted(e['id'] for e in listed) == keyed == [2, 3, 6, 7]
        assert {e['name'] for e in listed} == {'server.pem', 'cert and key', 'key only', 'legacy label'}
        # A row that held a key and no certificate has no fingerprint to give
        assert {e['id']: e['fingerprint_sha256'] and len(e['fingerprint_sha256']) for e in listed} == {
            2: 64, 3: 64, 6: None, 7: 64}
        warned = [m for m in caplog.messages if 'held a private key' in m]
        assert len(warned) == len(keyed) and all('replace that key' in m for m in warned)
        for key in _MADE['keys']:
            body = key.splitlines()[1]
            assert not any(body in m for m in caplog.messages)
            assert body not in json.dumps(listed)

        # Run again: nothing changes, nothing is listed twice
        step = importlib.import_module(f'migrations._from_2_254.{STEP}')
        if dialect == 'sqlite':
            conn = db.connection()
            step.upgrade(conn)
            conn.close()
        else:
            with db.connection() as conn:
                step.upgrade(conn)
        assert _stored(db) == after
        assert _listed(db) == listed


@pytest.mark.parametrize('dialect', BACKENDS)
def test_a_2254_trust_store_without_a_key_lists_nothing(dialect, tmp_path, monkeypatch):
    for db in make_base(dialect, tmp_path, monkeypatch, 'tc'):
        sane, _, _ = _issue('clean')
        db.run("INSERT INTO trusted_certificates (id, name, certificate_pem, fingerprint_sha256) "
               "VALUES (1, 'clean', :p, :f)", {'p': sane, 'f': '1' * 64})
        assert db.upgrade()
        assert _stored(db) == {1: sane}
        assert _listed(db) is None


def test_the_next_start_reports_each_removed_key_once(app, caplog):
    from models import db, AuditLog, SystemConfig
    from utils.trust_pem import report_removed_keys
    listed = [{'id': 902, 'name': 'server.pem', 'fingerprint_sha256': 'ab' * 32},
              {'id': 903, 'name': 'other', 'fingerprint_sha256': 'cd' * 32}]
    with app.app_context():
        before = db.session.query(db.func.max(AuditLog.id)).scalar() or 0
        db.session.add(SystemConfig(key=REMOVED_KEY, value=json.dumps(listed)))
        db.session.commit()
    try:
        with caplog.at_level('WARNING'):
            assert report_removed_keys(app) == 2
        assert report_removed_keys(app) == 0
        with app.app_context():
            assert SystemConfig.query.filter_by(key=REMOVED_KEY).first() is None
            entries = AuditLog.query.filter(AuditLog.id > before, AuditLog.action == REMOVED_ACTION).all()
            assert sorted(e.resource_id for e in entries) == ['902', '903']
            assert all('ab' * 32 in e.details or 'cd' * 32 in e.details for e in entries)
            assert all('replace that key' in e.details for e in entries)
        assert sum('held a private key' in m for m in caplog.messages) == 2
    finally:
        with app.app_context():
            SystemConfig.query.filter_by(key=REMOVED_KEY).delete()
            db.session.commit()


def test_the_list_never_leaves_the_installation():
    from services.backup import installation
    assert installation.is_local_setting(REMOVED_KEY)

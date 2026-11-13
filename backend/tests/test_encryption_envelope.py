"""Envelope encryption: the KEK wraps data-encryption keys stored in the database.

An upgraded database reads as it is (its key is DEK version 1), a rotation rewrites every
value under a new DEK and can be interrupted anywhere, a wrong KEK is safe mode without a
write, a KEK changed by hand rewraps the DEKs only, and the audit chain key never moves
with the DEK. Runs on the session database (SQLite, or PostgreSQL in the PG job).
"""
import base64
import uuid

import pytest
from cryptography.fernet import Fernet, InvalidToken

from config.settings import Config
from models import db, SharedFile, SystemConfig
from services import shared_files
from security.dek_rotation import GRACE_KEY
from tests import pg_app_harness
from tests.windows_profile_support import windows_profiles_restored  # noqa: F401

@pytest.fixture(autouse=True)
def _dek_refresh(dek_refresh_now, dek_retire_at_once):
    """No process here lags: rotations and disables wait for none, and the previous DEK
    goes at the end (the grace tests set a period of their own)."""


@pytest.fixture(autouse=True)
def _bystander_stays_plaintext(app):
    """A plaintext key of the session database outside this file's rows (the default CA's,
    say) is still plaintext once every fixture of a test has torn down."""
    from models.deploy import DeployTarget
    with app.app_context():
        row = DeployTarget(name=f'bystander {uuid.uuid4().hex[:8]}', host='h.example',
                           username='u', private_key=PEM)
        db.session.add(row)
        db.session.commit()
        row_id = row.id
    yield
    with app.app_context():
        db.session.rollback()
        row = db.session.get(DeployTarget, row_id)
        stored = row.private_key
        db.session.delete(row)
        db.session.commit()
    assert stored == PEM, 'a plaintext key outside this test was left encrypted or dropped'


PEM = '-----BEGIN PRIVATE KEY-----\nenvelope\n-----END PRIVATE KEY-----\n'
KEYTAB = b'\x05\x02envelope-keytab'
SSH_KEY = base64.b64encode(b'-----BEGIN OPENSSH PRIVATE KEY-----\nenv\n-----END OPENSSH PRIVATE KEY-----\n').decode()


def _token(value):
    from security.encryption import ENCRYPTED_MARKER
    return base64.b64decode(value)[len(ENCRYPTED_MARKER):]


@pytest.fixture
def envelope_keys(app):
    """encryption_keys and this file's cluster rows are emptied before and after each test;
    the audit ledger is put back as it was (entries sealed under a test KEK would make
    a later first start believe a master key was lost)."""
    from models import AuditLog, ClusterCommand, ClusterNode, EncryptionKey
    ledger = AuditLog.__table__

    def clean():
        with app.app_context():
            EncryptionKey.query.delete()
            SystemConfig.query.filter_by(key=GRACE_KEY).delete()
            ClusterCommand.query.delete()
            ClusterNode.query.filter(ClusterNode.node_id.like('envtest-%')).delete(
                synchronize_session=False)
            db.session.commit()
    clean()
    with app.app_context():
        saved = [dict(row._mapping) for row in db.session.execute(ledger.select())]
    yield
    clean()
    with app.app_context():
        db.session.rollback()
        db.session.execute(ledger.delete())
        if saved:
            db.session.execute(ledger.insert(), saved)
        db.session.commit()
    from security.encryption import key_encryption
    key_encryption.reload()


@pytest.fixture
def set_env(encryption_enabled):
    """Environment changes undone before encryption_enabled's own teardown restores its key."""
    patch = pytest.MonkeyPatch()

    def apply(name, value):
        if value is None:
            patch.delenv(name, raising=False)
        else:
            patch.setenv(name, value)
    yield apply
    patch.undo()


@pytest.fixture
def values(app, encryption_enabled, envelope_keys):
    """One value of each format under the current key, the only ones the rewrite sees."""
    from models.deploy import DeployTarget
    from models.ssh import SSHCertificateAuthority
    from models.sso import SSOProvider
    # Imported before a test patches them
    from security.encryption import (
        decrypt_all_keys, encrypt_private_key, encrypt_text, key_encryption,
    )

    tag = uuid.uuid4().hex[:8]
    with app.app_context():
        ssh = SSHCertificateAuthority(
            descr=f'env {tag}', ca_type='user', public_key='ssh-ed25519 AAAA',
            private_key=encrypt_private_key(SSH_KEY), key_type='ed25519',
            fingerprint=f'SHA256:env{tag}')
        target = DeployTarget(name=f'env {tag}', host='h.example', username='u',
                              private_key=encrypt_text(PEM))
        provider = SSOProvider(name=f'env ldap {tag}', provider_type='ldap')
        provider.ldap_bind_password = encrypt_text('bind-secret')
        config = SystemConfig(key=f'acme.account.env{tag}.private_key', value=encrypt_text(PEM))
        rows = [ssh, target, provider, config]
        db.session.add_all(rows)
        # A shared file (Kerberos keytab, HTTPS pair) is keyed by its name
        shared = f'envtest-{tag}.keytab'
        shared_files.store_file(shared, KEYTAB)
        db.session.commit()
        ids = {type(r): r.id for r in rows}

    yield {'ids': ids, 'tag': tag, 'shared': shared}
    with app.app_context():
        # An enable encrypts every key of the session database under this throwaway KEK:
        # back in the clear while the KEK is still loaded (a no-op when it cannot open them)
        db.session.rollback()
        key_encryption.reload()
        decrypt_all_keys(dry_run=False)
        for model, row_id in ids.items():
            row = db.session.get(model, row_id)
            if row is not None:
                db.session.delete(row)
        shared_files.drop_file(shared)
        db.session.commit()


def _stored(app, values):
    """The raw column values, as the database holds them."""
    from models.deploy import DeployTarget
    from models.ssh import SSHCertificateAuthority
    from models.sso import SSOProvider
    ids = values['ids']
    with app.app_context():
        db.session.expire_all()
        return {
            'ssh': db.session.get(SSHCertificateAuthority, ids[SSHCertificateAuthority]).private_key,
            'target': db.session.get(DeployTarget, ids[DeployTarget]).private_key,
            'bind': db.session.get(SSOProvider, ids[SSOProvider])._ldap_bind_password,
            'config': db.session.get(SystemConfig, ids[SystemConfig]).value,
            'shared': db.session.get(SharedFile, values['shared']).content,
        }


def _read(app, values):
    """Every value decrypted through the readers the application uses."""
    from models.deploy import DeployTarget
    from models.ssh import SSHCertificateAuthority
    from models.sso import SSOProvider
    from security.encryption import decrypt_master_key_value
    ids = values['ids']
    with app.app_context():
        db.session.expire_all()
        return {
            'ssh': decrypt_master_key_value(
                db.session.get(SSHCertificateAuthority, ids[SSHCertificateAuthority]).private_key, 'b64'),
            'target': decrypt_master_key_value(
                db.session.get(DeployTarget, ids[DeployTarget]).private_key, 'text'),
            'bind': decrypt_master_key_value(
                db.session.get(SSOProvider, ids[SSOProvider]).ldap_bind_password, 'text'),
            'config': decrypt_master_key_value(
                db.session.get(SystemConfig, ids[SystemConfig]).value, 'text'),
            'shared': shared_files.read_file(values['shared']),
        }


CLEAR = {'ssh': SSH_KEY, 'target': PEM, 'bind': 'bind-secret', 'config': PEM, 'shared': KEYTAB}


def _kek(enc):
    import os  # the fixture's variable, read as the key file would be
    return os.environ['KEY_ENCRYPTION_KEY'].encode()


def _rows(app):
    from models import EncryptionKey
    with app.app_context():
        return [(r.version, r.state, r.kek_id, r.wrapped)
                for r in EncryptionKey.query.order_by(EncryptionKey.version).all()]


def _start(app):
    from security.master_key_bootstrap import check_master_key_at_start
    with app.app_context():
        check_master_key_at_start(app)
        db.session.commit()


# --- upgrade -------------------------------------------------------------


def test_an_upgraded_database_reads_as_it_is_and_nothing_is_rewritten(app, values, encryption_enabled):
    """Values written by the single-key versions: the key is DEK version 1, no write at start."""
    before = _stored(app, values)
    _start(app)
    assert _stored(app, values) == before
    assert _rows(app) == []
    assert encryption_enabled.key_encryption.active_version == 1
    assert _read(app, values) == CLEAR
    assert app.config['SAFE_MODE'] is False
    # Still the KEK's own Fernet token: readable with the bare key, as before the envelope
    assert Fernet(_kek(encryption_enabled)).decrypt(_token(before['target'])) == PEM.encode()


def test_the_status_reports_fingerprint_and_version_never_a_key(app, auth_client, values,
                                                                 encryption_enabled):
    data = auth_client.get('/api/v2/system/security/encryption-status').get_json()['data']
    fingerprint = encryption_enabled.key_encryption.kek_fingerprint()
    assert data['kek_fingerprint'] == fingerprint and len(fingerprint) == 16
    assert data['dek_version'] == 1 and data['rotation_in_progress'] is False
    raw = auth_client.get('/api/v2/system/security/encryption-status').data.decode()
    assert _kek(encryption_enabled).decode() not in raw


# --- rotation ------------------------------------------------------------


def test_rotation_rewrites_every_value_under_a_new_dek(app, auth_client, values, encryption_enabled):
    before = _stored(app, values)
    r = auth_client.post('/api/v2/system/security/rotate-encryption-key')
    assert r.status_code == 200, r.data
    assert r.get_json()['data']['version'] == 2
    after = _stored(app, values)
    assert all(after[k] != before[k] for k in before)
    assert _read(app, values) == CLEAR
    # Under the new DEK: the KEK alone no longer opens them
    with pytest.raises(InvalidToken):
        Fernet(_kek(encryption_enabled)).decrypt(_token(after['target']))
    rows = _rows(app)
    assert [(v, s) for v, s, _, _ in rows] == [(2, 'active')]
    assert rows[0][3].startswith('1:') and rows[0][2] == encryption_enabled.key_encryption.kek_fingerprint()
    # Another process starting now reads them from the stored, wrapped DEK
    with app.app_context():
        encryption_enabled.key_encryption.reload()
    assert _read(app, values) == CLEAR
    from models import AuditLog
    with app.app_context():
        assert AuditLog.query.filter_by(action='encryption_key_rotated').order_by(
            AuditLog.id.desc()).first().success


def test_a_second_rotation_drops_the_first_wrapped_key(app, values):
    from security import dek_rotation
    with app.app_context():
        assert dek_rotation.rotate()['version'] == 2
        assert dek_rotation.rotate()['version'] == 3
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(3, 'active')]
    assert _read(app, values) == CLEAR


def test_an_interrupted_rotation_stays_readable_then_resumes(app, values, monkeypatch,
                                                             encryption_enabled):
    """Stopped after one rewritten value: each value opens with the old or the new DEK."""
    from security import dek_rotation, encryption
    monkeypatch.setattr(dek_rotation, 'BATCH', 1)
    real = encryption.encrypt_master_key_value
    calls = []

    def dies_on_the_second(value, fmt):
        calls.append(fmt)
        if len(calls) == 2:
            raise RuntimeError('process killed')
        return real(value, fmt)
    monkeypatch.setattr(encryption, 'encrypt_master_key_value', dies_on_the_second)
    before = _stored(app, values)
    with app.app_context(), pytest.raises(RuntimeError):
        dek_rotation.rotate()
    with app.app_context():
        db.session.rollback()
    monkeypatch.setattr(encryption, 'encrypt_master_key_value', real)

    assert [(v, s) for v, s, _, _ in _rows(app)] == [(1, 'previous'), (2, 'active')]
    mid = _stored(app, values)
    assert sum(mid[k] != before[k] for k in before) >= 1
    assert sum(mid[k] == before[k] for k in before) >= 1
    # A process (re)started now holds both DEKs
    with app.app_context():
        encryption_enabled.key_encryption.reload()
        assert encryption_enabled.key_encryption.dek_versions == (1, 2)
    assert _read(app, values) == CLEAR

    # The next start resumes it outside HA
    _start(app)
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(2, 'active')]
    assert _read(app, values) == CLEAR
    end = _stored(app, values)
    with pytest.raises(InvalidToken):
        Fernet(_kek(encryption_enabled)).decrypt(_token(end['config']))


def test_a_value_written_during_the_rotation_is_not_overwritten(app, values, monkeypatch):
    """The rewrite updates a row only if it still holds what was read."""
    from models.deploy import DeployTarget
    from security import dek_rotation, encryption
    real = encryption.decrypt_master_key_value
    target_id = values['ids'][DeployTarget]
    fresh = []

    def concurrent_write(value, fmt):
        plain = real(value, fmt)
        if plain == PEM and not fresh:
            # Another request stores a new key for the target between read and update
            fresh.append(encryption.encrypt_text('NEW-KEY'))
            db.session.execute(DeployTarget.__table__.update()
                               .where(DeployTarget.__table__.c.id == target_id)
                               .values(private_key=fresh[0]))
        return plain
    monkeypatch.setattr(encryption, 'decrypt_master_key_value', concurrent_write)
    with app.app_context():
        dek_rotation.start()
        dek_rotation.rewrite()
    monkeypatch.setattr(encryption, 'decrypt_master_key_value', real)
    with app.app_context():
        db.session.expire_all()
        stored = db.session.get(DeployTarget, target_id).private_key
        assert encryption.decrypt_text(stored) == 'NEW-KEY'


def test_rotation_keeps_the_previous_key_while_a_value_opens_with_none(app, values, auth_client):
    from security import encryption
    foreign = base64.b64encode(encryption.ENCRYPTED_MARKER
                               + Fernet(Fernet.generate_key()).encrypt(b'x')).decode()
    with app.app_context():
        db.session.add(SystemConfig(key=f"acme.account.foreign{values['tag']}.private_key",
                                    value=foreign))
        db.session.commit()
    try:
        r = auth_client.post('/api/v2/system/security/rotate-encryption-key')
        assert r.status_code == 409, r.data
        assert 'SystemConfig' in r.get_json()['message']
        assert [(v, s) for v, s, _, _ in _rows(app)] == [(1, 'previous'), (2, 'active')]
        assert _read(app, values) == CLEAR
    finally:
        with app.app_context():
            SystemConfig.query.filter_by(
                key=f"acme.account.foreign{values['tag']}.private_key").delete()
            db.session.commit()
    r = auth_client.post('/api/v2/system/security/rotate-encryption-key')
    assert r.status_code == 200, r.data
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(2, 'active')]


def test_encrypt_all_encrypts_a_shared_file_left_in_the_clear(app, auth_client, values,
                                                             encryption_enabled):
    with app.app_context():
        db.session.get(SharedFile, values['shared']).content = base64.b64encode(KEYTAB).decode()
        db.session.commit()
    r = auth_client.post('/api/v2/system/security/encrypt-all-keys', json={'dry_run': False})
    assert r.status_code == 200, r.data
    assert encryption_enabled.key_encryption.is_encrypted(_stored(app, values)['shared'])
    assert _read(app, values) == CLEAR


def test_a_keytab_rotated_on_another_node_is_written_by_reload_and_at_start(
        app, values, monkeypatch, tmp_path, encryption_enabled):
    """This process held only the first DEK when another node rotated: it re-reads the rows."""
    from security import dek_rotation, encryption
    from services import cluster_commands as cc
    from services.kerberos import negotiate_auth
    key_encryption = encryption_enabled.key_encryption
    path = tmp_path / 'kerberos.keytab'
    monkeypatch.setattr(negotiate_auth, 'KEYTAB_PATH', path)
    monkeypatch.setattr(encryption, 'REFRESH_SECONDS', 2.0)
    monkeypatch.setattr(dek_rotation.time, 'sleep', lambda seconds: None)
    try:
        with app.app_context():
            shared_files.store_file(shared_files.KERBEROS_KEYTAB, KEYTAB)
            db.session.commit()
            key_encryption.is_enabled
            stale = {name: getattr(key_encryption, name) for name in key_encryption._FIELDS}
            dek_rotation.rotate()
            assert [(v, s) for v, s, _, _ in _rows(app)] == [(2, 'active')]
            key_encryption.__dict__.update(stale)
            key_encryption._read_at -= 2 * encryption.REFRESH_SECONDS
            cc.HANDLERS[cc.RELOAD_KEYTAB]({})
            assert path.read_bytes() == KEYTAB and key_encryption.active_version == 2
            path.unlink()
        negotiate_auth.restore_keytab_at_start(app)
        assert path.read_bytes() == KEYTAB
    finally:
        with app.app_context():
            shared_files.drop_file(shared_files.KERBEROS_KEYTAB)
            db.session.commit()


@pytest.mark.skipif(not pg_app_harness.ENABLED,
                    reason='needs UCM_TEST_APP_PG_URL (HA runs on PostgreSQL)')
def test_on_postgresql_node_b_writes_the_keytab_a_rotated(app, auth_client, values, monkeypatch,
                                                          tmp_path, encryption_enabled):
    """Node B is a second applier on its own connection; A rotates, B reads under the new DEK."""
    import time
    from datetime import timedelta
    from services import cluster_commands as cc
    from services.kerberos import negotiate_auth
    from utils.datetime_utils import utc_now
    _ha(monkeypatch)
    monkeypatch.setattr(cc, 'GAP_GRACE_SECONDS', 0.3)
    on_b = tmp_path / 'b.keytab'
    monkeypatch.setattr(negotiate_auth, 'KEYTAB_PATH', on_b)
    with app.app_context():
        shared_files.store_file(shared_files.KERBEROS_KEYTAB, KEYTAB)
        db.session.commit()
    node_b = cc.CommandApplier(app, 'envtest-b', tick=0.05, restart_action=lambda: None,
                               started_at=utc_now() - timedelta(seconds=30)).start()
    try:
        r = auth_client.post('/api/v2/system/security/rotate-encryption-key')
        assert r.status_code == 200, r.data
        assert r.get_json()['data']['state'] == 'done'
        with app.app_context():
            assert cc.emit_committed(cc.RELOAD_KEYTAB)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and not on_b.exists():
            time.sleep(0.02)
        assert on_b.read_bytes() == KEYTAB
    finally:
        node_b.stop()
        with app.app_context():
            shared_files.drop_file(shared_files.KERBEROS_KEYTAB)
            db.session.commit()


# --- grace period of the previous DEK -------------------------------------

DAY = 86400
WEEK = 7 * DAY


@pytest.fixture
def grace(monkeypatch):
    """A grace period of ten minutes; ``later(seconds)`` moves the cluster clock on."""
    from datetime import timedelta
    from security import dek_rotation
    from services import scheduler_leader
    monkeypatch.setattr(dek_rotation, 'GRACE_SECONDS', 600.0)
    real = scheduler_leader.cluster_utc_now
    offset = [timedelta(0)]
    monkeypatch.setattr(scheduler_leader, 'cluster_utc_now',
                        lambda executor=None: real(executor) + offset[0])

    def later(seconds):
        offset[0] += timedelta(seconds=seconds)
    return later


def _late_write(app, values, fernet):
    """A process that encrypted under ``fernet`` before it re-read the rows commits now."""
    from models.deploy import DeployTarget
    from security import encryption
    with app.app_context():
        db.session.get(DeployTarget, values['ids'][DeployTarget]).private_key = base64.b64encode(
            encryption.ENCRYPTED_MARKER + fernet.encrypt(PEM.encode())).decode()
        db.session.commit()


def test_a_write_under_the_old_dek_after_the_final_sweep_stays_readable(app, values, grace,
                                                                       encryption_enabled):
    from security import dek_rotation
    with app.app_context():
        old = encryption_enabled.key_encryption._fernet
        result = dek_rotation.rotate()
    assert result['state'] == 'done' and result['dropped'] == 0
    assert result['rotation_available_after']
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(1, 'previous'), (2, 'active')]
    _late_write(app, values, old)
    assert _read(app, values) == CLEAR
    with app.app_context():
        assert dek_rotation.retire_if_due() == 0  # not due
    grace(601)
    with app.app_context():
        # The end-of-grace sweep finds the late value: rewritten, the old DEK kept a day
        assert dek_rotation.retire_if_due() == 0
    with pytest.raises(InvalidToken):
        old.decrypt(_token(_stored(app, values)['target']))
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(1, 'previous'), (2, 'active')]
    assert _read(app, values) == CLEAR
    grace(DAY + 1)
    with app.app_context():
        dek_rotation.scheduled_retire()
        assert dek_rotation.retiring() is None
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(2, 'active')]
    assert _read(app, values) == CLEAR


def test_a_restart_during_the_grace_period_keeps_the_previous_dek(app, values, grace,
                                                                  encryption_enabled):
    from security import dek_rotation
    with app.app_context():
        old = encryption_enabled.key_encryption._fernet
        dek_rotation.rotate()
    _late_write(app, values, old)
    _start(app)
    assert app.config['SAFE_MODE'] is False
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(1, 'previous'), (2, 'active')]
    with app.app_context():
        encryption_enabled.key_encryption.reload()
        assert encryption_enabled.key_encryption.dek_versions == (1, 2)
    assert _read(app, values) == CLEAR
    grace(601)
    _start(app)  # the late value rewritten, then a second period
    grace(DAY + 1)
    _start(app)
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(2, 'active')]
    assert _read(app, values) == CLEAR


def test_during_the_grace_period_rotate_and_disable_name_its_end(app, auth_client, values, grace):
    from security import dek_rotation
    with app.app_context():
        dek_rotation.rotate()
    status = auth_client.get('/api/v2/system/security/encryption-status').get_json()['data']
    assert status['rotation_in_progress'] is False and status['rotation_available_after']
    end = status['rotation_available_after'].removesuffix('Z')
    for route, action in (('rotate-encryption-key', 'rotate again'),
                          ('disable-encryption', 'disable encryption')):
        r = auth_client.post(f'/api/v2/system/security/{route}')
        assert r.status_code == 409, r.data
        assert (f'A data-encryption key rotation just ended: {action} after {end} UTC.'
                in r.get_json()['message'])
    grace(601)
    r = auth_client.post('/api/v2/system/security/rotate-encryption-key')
    assert r.status_code == 200, r.data
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(2, 'previous'), (3, 'active')]


def test_in_ha_the_previous_dek_waits_for_every_live_node(app, values, grace, monkeypatch):
    from models import ClusterNode
    from security import dek_rotation
    from services.scheduler_leader import cluster_utc_now
    _ha(monkeypatch)
    with app.app_context():
        dek_rotation.rotate()
        command = dek_rotation.retiring()['command']
        assert command
    grace(601)
    with app.app_context():
        now = cluster_utc_now()
        db.session.add(ClusterNode(node_id='envtest-lag', started_at=now, heartbeat_at=now,
                                   is_leader=False, command_seen=command - 1))
        db.session.commit()
        assert dek_rotation.retire_if_due() == 0
        db.session.get(ClusterNode, 'envtest-lag').command_seen = command
        db.session.commit()
        assert dek_rotation.retire_if_due() == 1
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(2, 'active')]


@pytest.mark.skipif(not pg_app_harness.ENABLED, reason='needs UCM_TEST_APP_PG_URL')
def test_on_postgresql_a_transaction_open_across_the_rotation_stays_readable(
        app, values, grace, encryption_enabled):
    """A second connection encrypts under the old DEK, the rotation ends, then it commits."""
    from sqlalchemy import text
    from security import dek_rotation, encryption
    key = f"acme.account.late{values['tag']}.private_key"
    with app.app_context():
        old = encryption_enabled.key_encryption._fernet
        late = base64.b64encode(encryption.ENCRYPTED_MARKER + old.encrypt(PEM.encode())).decode()
        other = db.engine.connect()
        transaction = other.begin()
        other.execute(text("INSERT INTO system_config (key, value) VALUES (:k, :v)"),
                      {'k': key, 'v': late})
    try:
        with app.app_context():
            assert dek_rotation.rotate()['dropped'] == 0
        transaction.commit()
        with app.app_context():
            stored = SystemConfig.query.filter_by(key=key).one().value
            assert encryption.decrypt_master_key_value(stored, 'text') == PEM
        grace(601)
        with app.app_context():
            assert dek_rotation.retire_if_due() == 0
            db.session.expire_all()
            stored = SystemConfig.query.filter_by(key=key).one().value
            assert encryption.decrypt_master_key_value(stored, 'text') == PEM
            with pytest.raises(InvalidToken):
                old.decrypt(_token(stored))
        grace(DAY + 1)
        with app.app_context():
            assert dek_rotation.retire_if_due() == 1
            db.session.expire_all()
            stored = SystemConfig.query.filter_by(key=key).one().value
            assert encryption.decrypt_master_key_value(stored, 'text') == PEM
    finally:
        other.close()
        with app.app_context():
            SystemConfig.query.filter_by(key=key).delete()
            db.session.commit()


def test_rotation_refused_without_encryption(auth_client, envelope_keys):
    r = auth_client.post('/api/v2/system/security/rotate-encryption-key')
    assert r.status_code == 400


# --- audit chain ---------------------------------------------------------


def test_the_audit_chain_key_does_not_move_with_the_dek(app, values, encryption_enabled):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from security import dek_rotation
    from services.audit.chain import chain_key
    with app.app_context():
        before = chain_key()
        dek_rotation.rotate()
        assert chain_key() == before
    # The same derivation the single-key versions sealed with: existing seals verify
    legacy = HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                  info=b'ucm audit chain v2').derive(base64.urlsafe_b64decode(_kek(encryption_enabled)))
    assert before[0] == legacy


# --- wrong KEK -----------------------------------------------------------


def test_a_wrong_kek_is_safe_mode_and_writes_nothing(set_env, app, values, monkeypatch, encryption_enabled):
    from security import dek_rotation
    with app.app_context():
        dek_rotation.rotate()
    rows, stored = _rows(app), _stored(app, values)
    set_env('KEY_ENCRYPTION_KEY', Fernet.generate_key().decode())
    _start(app)
    try:
        assert app.config['SAFE_MODE'] is True
        assert app.config['SAFE_MODE_REASON'] == 'encryption_key_mismatch'
        assert not encryption_enabled.key_encryption.is_enabled
        # Unloaded: not even the audit chain is sealed under the wrong key
        assert encryption_enabled.key_encryption.derive_key(b'x') is None
        assert _rows(app) == rows and _stored(app, values) == stored
    finally:
        app.config['SAFE_MODE'] = False


# --- manual KEK change ---------------------------------------------------


def test_a_kek_changed_by_hand_rewraps_the_deks_and_nothing_else(set_env, app, values, monkeypatch,
                                                                  encryption_enabled):
    from security import dek_rotation
    old = _kek(encryption_enabled).decode()
    with app.app_context():
        dek_rotation.rotate()
    stored = _stored(app, values)
    new = Fernet.generate_key().decode()
    set_env('KEY_ENCRYPTION_KEY', new)
    set_env('KEY_ENCRYPTION_KEY_PREVIOUS', old)
    _start(app)
    assert app.config['SAFE_MODE'] is False
    rows = _rows(app)
    assert [(v, s) for v, s, _, _ in rows] == [(2, 'active')]
    assert rows[0][2] == encryption_enabled.key_encryption.kek_fingerprint()
    assert _stored(app, values) == stored
    assert _read(app, values) == CLEAR
    # The previous key is no longer needed
    set_env('KEY_ENCRYPTION_KEY_PREVIOUS', None)
    _start(app)
    assert app.config['SAFE_MODE'] is False and _read(app, values) == CLEAR


def test_a_kek_changed_by_hand_before_any_rotation_stores_dek_version_1(set_env, app, values, monkeypatch,
                                                                         encryption_enabled):
    old = _kek(encryption_enabled).decode()
    stored = _stored(app, values)
    set_env('KEY_ENCRYPTION_KEY', Fernet.generate_key().decode())
    set_env('KEY_ENCRYPTION_KEY_PREVIOUS', old)
    _start(app)
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(1, 'active')]
    assert _stored(app, values) == stored
    assert _read(app, values) == CLEAR


def test_a_kek_changed_without_the_previous_one_is_safe_mode(set_env, app, values, monkeypatch):
    stored = _stored(app, values)
    set_env('KEY_ENCRYPTION_KEY', Fernet.generate_key().decode())
    _start(app)
    try:
        assert app.config['SAFE_MODE'] is True
        assert _rows(app) == [] and _stored(app, values) == stored
    finally:
        app.config['SAFE_MODE'] = False


# --- HA ------------------------------------------------------------------


def _ha(monkeypatch):
    monkeypatch.setattr(Config, 'HA_MODE', True)


def _commands(app):
    from models import ClusterCommand
    with app.app_context():
        return [(c.kind, c.payload) for c in ClusterCommand.query.order_by(ClusterCommand.id)]


def test_in_ha_rotation_runs_and_tells_every_node(app, auth_client, values, monkeypatch):
    _ha(monkeypatch)
    r = auth_client.post('/api/v2/system/security/rotate-encryption-key')
    assert r.status_code == 200, r.data
    kinds = _commands(app)
    assert [k for k, _ in kinds] == ['reload_encryption', 'reload_encryption']
    # The payload names a version, never key material
    assert all(p == '{"version": 2}' for _, p in kinds)


def test_in_ha_disable_then_enable_keep_the_kek_and_tell_every_node(app, auth_client, values,
                                                                     monkeypatch, encryption_enabled):
    _ha(monkeypatch)
    r = auth_client.post('/api/v2/system/security/disable-encryption')
    assert r.status_code == 200, r.data
    key_encryption = encryption_enabled.key_encryption
    with app.app_context():
        key_encryption.reload()
        assert not key_encryption.is_enabled and key_encryption.kek_loaded
    stored = _stored(app, values)
    assert (stored['ssh'], stored['target'], stored['config']) == (SSH_KEY, PEM, PEM)
    assert stored['shared'] == base64.b64encode(KEYTAB).decode()
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(0, 'disabled')]
    r = auth_client.post('/api/v2/system/security/enable-encryption')
    assert r.status_code == 200, r.data
    assert r.get_json()['data']['master_key'] is None
    assert _rows(app) == []
    stored = _stored(app, values)
    assert all(key_encryption.is_encrypted(stored[k]) for k in ('ssh', 'target', 'config', 'shared'))
    assert _read(app, values) == CLEAR
    # Disable: decrypt-only, the markers and the grace, then the DEKs dropped; enable
    assert [k for k, _ in _commands(app)] == ['reload_encryption'] * 4
    r = auth_client.post('/api/v2/system/security/encrypt-all-keys', json={'dry_run': True})
    assert r.status_code == 200, r.data


def test_the_reload_command_brings_a_node_onto_the_new_dek(app, values, encryption_enabled):
    """Node B's memory still holds the old DEK only; the command's handler loads the new one."""
    from security import dek_rotation, envelope
    from services import cluster_commands as cc
    key_encryption = encryption_enabled.key_encryption
    with app.app_context():
        dek_rotation.rotate()
        # B, started before the rotation: DEK version 1 (the KEK) only
        key_encryption._set_deks({1: Fernet(_kek(encryption_enabled))}, 1)
        with pytest.raises(ValueError):
            _read(app, values)
        app.config['SAFE_MODE'] = True  # what B computed before; re-evaluated by the command
        cc.HANDLERS[cc.RELOAD_ENCRYPTION]({'version': 2})
    try:
        assert key_encryption.active_version == 2
        assert app.config['SAFE_MODE'] is False
        assert _read(app, values) == CLEAR
    finally:
        app.config['SAFE_MODE'] = False
    assert envelope.ACTIVE == 'active'


def test_a_reload_after_a_peer_enabled_under_another_kek_stays_in_safe_mode(set_env, app, values,
                                                                           encryption_enabled):
    """No DEK row: the KEK is DEK version 1, so the values must open with it, as at start."""
    from security.master_key_bootstrap import reload_encryption_state
    set_env('KEY_ENCRYPTION_KEY', Fernet.generate_key().decode())  # this node's, not the peer's
    with app.app_context():
        try:
            reload_encryption_state(app)
            assert app.config['SAFE_MODE'] is True
            assert app.config['SAFE_MODE_REASON'] == 'encryption_key_mismatch'
            assert not encryption_enabled.key_encryption.is_encrypting
        finally:
            app.config['SAFE_MODE'] = False


def test_a_reload_after_a_peer_disabled_under_another_kek_stays_in_safe_mode(app, values,
                                                                            encryption_enabled):
    from models import EncryptionKey
    from security import envelope
    from security.master_key_bootstrap import reload_encryption_state
    from utils.datetime_utils import utc_now
    with app.app_context():
        db.session.add(EncryptionKey(version=0, state=envelope.DISABLED, kek_id='f' * 16,
                                     wrapped=None, created_at=utc_now()))
        db.session.commit()
        try:
            reload_encryption_state(app)
            assert app.config['SAFE_MODE'] is True
            assert app.config['SAFE_MODE_REASON'] == 'encryption_key_mismatch'
            assert encryption_enabled.key_encryption.encrypt_string('x') == 'x'
        finally:
            app.config['SAFE_MODE'] = False


def test_a_reload_with_the_database_kek_and_no_dek_row_leaves_safe_mode(app, values,
                                                                       encryption_enabled):
    from security.master_key_bootstrap import reload_encryption_state
    with app.app_context():
        app.config['SAFE_MODE'] = True
        try:
            reload_encryption_state(app)
            assert app.config['SAFE_MODE'] is False
            assert encryption_enabled.key_encryption.is_encrypting
        finally:
            app.config['SAFE_MODE'] = False


def test_a_reload_scans_the_stored_values_only_when_encryption_is_off(app, values, monkeypatch,
                                                                    encryption_enabled):
    """Each node and process runs it on every enable, disable and rotation."""
    from security import dek_rotation, encryption
    from security.master_key_bootstrap import reload_encryption_state
    real = encryption.has_encrypted_keys_in_db
    scans = []
    monkeypatch.setattr(encryption, 'has_encrypted_keys_in_db',
                        lambda: scans.append(1) or real())
    with app.app_context():
        dek_rotation.rotate()
        reload_encryption_state(app)
        assert scans == [] and app.config['SAFE_MODE'] is False
        encryption_enabled.key_encryption.unload()
        monkeypatch.setattr(encryption_enabled.key_encryption, 'reload', lambda: None)
        try:
            reload_encryption_state(app)
            assert scans == [1] and app.config['SAFE_MODE'] is True
        finally:
            app.config['SAFE_MODE'] = False


def test_a_node_whose_kek_differs_from_a_live_peer_does_not_start(app, values, monkeypatch,
                                                                  encryption_enabled):
    from models import ClusterNode
    from services.scheduler_leader import cluster_utc_now
    from datetime import timedelta
    from security.master_key_bootstrap import refuse_kek_mismatch_with_peers
    _ha(monkeypatch)
    mine = encryption_enabled.key_encryption.kek_fingerprint()
    with app.app_context():
        now = cluster_utc_now()
        db.session.add_all([
            ClusterNode(node_id='envtest-same', started_at=now, heartbeat_at=now,
                        is_leader=False, kek_fingerprint=mine),
            ClusterNode(node_id='envtest-gone', started_at=now, heartbeat_at=now - timedelta(hours=1),
                        is_leader=False, kek_fingerprint='0' * 16),
        ])
        db.session.commit()
        refuse_kek_mismatch_with_peers()  # same key, and a dead peer: no refusal
        db.session.add(ClusterNode(node_id='envtest-other', started_at=now, heartbeat_at=now,
                                   is_leader=True, kek_fingerprint='f' * 16))
        db.session.commit()
        with pytest.raises(SystemExit, match='envtest-other'):
            refuse_kek_mismatch_with_peers()
        monkeypatch.setattr(Config, 'HA_MODE', False)
        refuse_kek_mismatch_with_peers()


def test_the_heartbeat_publishes_the_kek_fingerprint(app, values, monkeypatch, encryption_enabled):
    from models import ClusterNode
    from services.scheduler_leader import cluster_utc_now, write_heartbeat
    with app.app_context():
        write_heartbeat('envtest-me', False, cluster_utc_now())
        row = db.session.get(ClusterNode, 'envtest-me')
        assert row.kek_fingerprint == encryption_enabled.key_encryption.kek_fingerprint()
        assert _kek(encryption_enabled).decode() not in row.kek_fingerprint


def test_a_reload_never_shows_encryption_off_to_a_concurrent_writer(app, values, monkeypatch,
                                                                    encryption_enabled):
    """The DEKs are read from the database while other requests run: they keep the old keys."""
    from security import envelope
    key_encryption = encryption_enabled.key_encryption
    real = envelope.stored_rows
    seen = []

    def concurrent_request():
        # Another thread, no app context of its own: it reads only what is published
        import threading
        writer = threading.Thread(
            target=lambda: seen.append(key_encryption.encrypt_string('written meanwhile')))
        writer.start()
        writer.join()
        return real()
    monkeypatch.setattr(envelope, 'stored_rows', concurrent_request)
    with app.app_context():
        key_encryption.reload()
    assert seen and key_encryption.is_string_encrypted(seen[0])
    assert key_encryption.decrypt_string(seen[0]) == 'written meanwhile'


def test_enabling_never_drops_dek_rows_the_kek_cannot_open(set_env, app, auth_client, values, monkeypatch,
                                                           encryption_enabled):
    from security import dek_rotation
    with app.app_context():
        dek_rotation.rotate()
    rows = _rows(app)
    set_env('KEY_ENCRYPTION_KEY', Fernet.generate_key().decode())
    with app.app_context():
        encryption_enabled.key_encryption.reload()
        assert encryption_enabled.key_encryption.dek_error == 'kek_mismatch'
    r = auth_client.post('/api/v2/system/security/enable-encryption')
    assert r.status_code == 409, r.data
    assert _rows(app) == rows


def test_enabling_with_the_configured_kek_purges_the_plaintext_key_files(app, auth_client, values,
                                                                       encryption_enabled):
    """Disabling writes the .key mirrors in the clear: enabling again removes them (#320)."""
    r = auth_client.post('/api/v2/system/security/disable-encryption')
    assert r.status_code == 200, r.data
    mirror = Config.PRIVATE_DIR / f"envtest-{values['tag']}.key"
    mirror.write_text(PEM)
    try:
        r = auth_client.post('/api/v2/system/security/enable-encryption')
        assert r.status_code == 200, r.data
        assert not mirror.exists()
        assert r.get_json()['data']['key_files_removed'] >= 1
    finally:
        mirror.unlink(missing_ok=True)


def _db_error(message):
    from sqlalchemy.exc import OperationalError
    return OperationalError('SELECT encryption_keys', {}, Exception(message))


def test_a_failed_read_of_the_deks_keeps_the_loaded_ones(app, values, monkeypatch, encryption_enabled):
    """Only a missing table means a database before the envelope; any other error changes nothing."""
    from security import dek_rotation, envelope
    key_encryption = encryption_enabled.key_encryption
    with app.app_context():
        dek_rotation.rotate()
        assert key_encryption.active_version == 2

        def broken():
            raise _db_error('server closed the connection unexpectedly')
        with monkeypatch.context() as patch:
            patch.setattr(envelope, 'stored_rows', broken)
            with pytest.raises(Exception, match='server closed'):
                key_encryption.reload()
        assert key_encryption.active_version == 2 and key_encryption.is_enabled
    assert _read(app, values) == CLEAR


def test_a_database_before_the_envelope_reads_the_kek_as_version_1(app, values, monkeypatch,
                                                                 encryption_enabled):
    from security import envelope
    key_encryption = encryption_enabled.key_encryption

    def missing():
        raise _db_error('no such table: encryption_keys')
    with monkeypatch.context() as patch, app.app_context():
        patch.setattr(envelope, 'stored_rows', missing)
        key_encryption.reload()
        assert key_encryption.active_version == 1 and key_encryption.is_enabled


def test_a_process_that_loaded_the_deks_before_a_rotation_follows_it(app, values, monkeypatch,
                                                                    encryption_enabled):
    """The scheduler process gets no command outside HA: it re-reads the rows before a use."""
    from security import dek_rotation, encryption
    key_encryption = encryption_enabled.key_encryption
    monkeypatch.setattr(encryption, 'REFRESH_SECONDS', 2.0)
    with app.app_context():
        key_encryption.is_enabled  # rows read: this is what the other process holds
        stale = {name: getattr(key_encryption, name) for name in key_encryption._FIELDS}
        slept = []
        monkeypatch.setattr(dek_rotation.time, 'sleep', slept.append)
        dek_rotation.rotate()
        # The rotation rewrote nothing before every process's bound had passed
        assert slept and slept[0] >= encryption.REFRESH_SECONDS
        key_encryption.__dict__.update(stale)
        key_encryption._read_at -= slept[0]
        assert _read(app, values) == CLEAR
        written = key_encryption.encrypt_string('scheduler write')
        assert key_encryption.active_version == 2
        # Its write is under the DEK that stays, not the one the rotation dropped
        key_encryption.reload()
        assert encryption.decrypt_master_key_value(written, 'text') == 'scheduler write'


# --- disable -------------------------------------------------------------


def test_while_disabling_every_value_opens_and_nothing_new_is_encrypted(app, auth_client, values,
                                                                       monkeypatch, encryption_enabled):
    """Phase 1 is committed before the decryption: a process still writing writes in the clear."""
    from security import dek_rotation, encryption
    with app.app_context():
        dek_rotation.rotate()  # a DEK of version 2, the one a premature drop would lose
    real = encryption.decrypt_all_keys
    seen = {}

    def decrypt_phase(dry_run=True):
        seen['rows'] = [(v, s) for v, s, _, _ in _rows(app)]
        seen['written'] = encryption.key_encryption.encrypt_string('written meanwhile')
        seen['read'] = _read(app, values)
        return real(dry_run=dry_run)
    monkeypatch.setattr(encryption, 'decrypt_all_keys', decrypt_phase)
    r = auth_client.post('/api/v2/system/security/disable-encryption')
    assert r.status_code == 200, r.data
    assert seen['rows'] == [(0, 'disabled'), (2, 'active')]
    assert seen['written'] == 'written meanwhile'
    assert seen['read'] == CLEAR


def test_a_value_encrypted_during_the_disable_keeps_the_deks(app, auth_client, values, monkeypatch,
                                                            encryption_enabled):
    """A process that encrypted under the old state before it re-read: its value stays readable."""
    from models.deploy import DeployTarget
    from security import dek_rotation, encryption
    with app.app_context():
        dek_rotation.rotate()
        stale = encryption.key_encryption._fernet  # the DEK that process still encrypts with
    real = encryption.decrypt_all_keys
    target_id = values['ids'][DeployTarget]

    def late_write(dry_run=True):
        result = real(dry_run=dry_run)
        with app.app_context():
            db.session.get(DeployTarget, target_id).private_key = base64.b64encode(
                encryption.ENCRYPTED_MARKER + stale.encrypt(PEM.encode())).decode()
            db.session.commit()
        return result
    monkeypatch.setattr(encryption, 'decrypt_all_keys', late_write)
    r = auth_client.post('/api/v2/system/security/disable-encryption')
    assert r.status_code == 409, r.data
    assert (2, 'active') in [(v, s) for v, s, _, _ in _rows(app)]
    assert _stored(app, values)['config'] == PEM  # the others were decrypted
    with app.app_context():
        assert encryption.decrypt_master_key_value(_stored(app, values)['target'], 'text') == PEM


def test_a_disable_left_half_way_is_reported_and_named_by_the_rotation(app, auth_client, values):
    from security import dek_rotation
    with app.app_context():
        dek_rotation.begin_disable()  # decrypt errors stopped the disable after its first phase
    status = auth_client.get('/api/v2/system/security/encryption-status').get_json()['data']
    assert status['enabled'] is True and status['disabling'] is True
    r = auth_client.post('/api/v2/system/security/rotate-encryption-key')
    assert r.status_code == 409, r.data
    assert 'disable' in r.get_json()['message'].lower()
    assert 'not enabled' not in r.get_json()['message']
    r = auth_client.post('/api/v2/system/security/disable-encryption')
    assert r.status_code == 200, r.data


def test_a_rotation_never_undoes_a_disable_committed_meanwhile(app, values, monkeypatch,
                                                              encryption_enabled):
    """The process's state may be stale before the lock; the database's under it decides."""
    from models import EncryptionKey
    from security import dek_rotation, envelope
    from utils.datetime_utils import utc_now
    key_encryption = encryption_enabled.key_encryption
    monkeypatch.setattr(encryption_enabled, 'REFRESH_SECONDS', 3600.0)
    with app.app_context():
        key_encryption.reload()
        assert key_encryption.is_enabled
        db.session.add(EncryptionKey(version=0, state=envelope.DISABLED,
                                     kek_id=key_encryption.kek_fingerprint(), wrapped=None,
                                     created_at=utc_now()))
        db.session.commit()  # disabled by another process
        with pytest.raises(dek_rotation.RotationError):
            dek_rotation.start()
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(0, 'disabled')]


def test_a_disable_never_drops_the_deks_of_a_rotation_started_meanwhile(app, auth_client, values,
                                                                       monkeypatch, encryption_enabled):
    """The rotation check is made under the lock: one committed just before it is seen."""
    from security import dek_rotation
    real = dek_rotation.lock_key_state
    started = []

    def rotation_first(session=None):
        if not started:
            started.append(True)
            with app.app_context():
                dek_rotation.start()  # another node's rotation, committed before the lock
        return real(session)
    monkeypatch.setattr(dek_rotation, 'lock_key_state', rotation_first)
    r = auth_client.post('/api/v2/system/security/disable-encryption')
    assert r.status_code == 409, r.data
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(1, 'previous'), (2, 'active')]
    assert _read(app, values) == CLEAR


@pytest.mark.parametrize('with_variable', [False, True], ids=['file', 'file-and-variable'])
def test_a_process_that_missed_a_file_disable_writes_in_the_clear(app, auth_client, envelope_keys,
                                                                  set_env, encryption_enabled,
                                                                  with_variable):
    """Outside HA the scheduler gets no command: the master.key removed must not arm it again."""
    key_encryption = encryption_enabled.key_encryption
    encryption_enabled.MASTER_KEY_PATH.write_text(Fernet.generate_key().decode())
    if not with_variable:
        set_env('KEY_ENCRYPTION_KEY', None)
    with app.app_context():
        key_encryption.reload()
        assert key_encryption.key_source == 'file' and key_encryption.is_enabled
        stale = {name: getattr(key_encryption, name) for name in key_encryption._FIELDS}
    r = auth_client.post('/api/v2/system/security/disable-encryption')
    assert r.status_code == 200, r.data
    assert not encryption_enabled.MASTER_KEY_PATH.exists()
    with app.app_context():
        key_encryption.__dict__.update(stale)  # the other process, KEK still in memory
        key_encryption._read_at = float('-inf')
        assert key_encryption.encrypt_string('renewed key') == 'renewed key'
        # A fresh start, on the variable when there is one, is off too
        key_encryption.reload()
        assert not key_encryption.is_enabled


# --- grace period of a disable --------------------------------------------


def _late_value_opens(app, values):
    from models.deploy import DeployTarget
    from security.encryption import decrypt_master_key_value
    with app.app_context():
        db.session.expire_all()
        stored = db.session.get(DeployTarget, values['ids'][DeployTarget]).private_key
        return decrypt_master_key_value(stored, 'text') == PEM


def _rotate_at_once(monkeypatch):
    """A DEK of version 2, its rotation over: the one a premature drop at disable would lose."""
    from security import dek_rotation
    with monkeypatch.context() as patch:
        patch.setattr(dek_rotation, 'GRACE_SECONDS', 0.0)
        dek_rotation.rotate()


def test_a_value_encrypted_before_the_disable_was_seen_stays_readable(app, auth_client, values,
                                                                     grace, monkeypatch,
                                                                     encryption_enabled):
    """It commits after the disable: the DEKs open it until the end-of-grace sweep decrypts it."""
    from security import dek_rotation
    key_encryption = encryption_enabled.key_encryption
    with app.app_context():
        _rotate_at_once(monkeypatch)
        stale = key_encryption._fernet
    r = auth_client.post('/api/v2/system/security/disable-encryption')
    assert r.status_code == 200, r.data
    assert r.get_json()['data']['keys_kept_until']
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(0, 'disabled'), (2, 'active')]
    _late_write(app, values, stale)
    with app.app_context():
        key_encryption.reload()
        assert key_encryption.encrypt_string('x') == 'x'
    assert _late_value_opens(app, values)
    status = auth_client.get('/api/v2/system/security/encryption-status').get_json()['data']
    assert status['enabled'] is False and status['disabling'] is False
    assert status['enable_available_after'] and not status['rotation_available_after']
    with app.app_context():
        assert dek_rotation.retire_if_due() == 0  # not due
    grace(601)
    with app.app_context():
        # The sweep finds the late value: decrypted in place, the DEKs kept a day
        assert dek_rotation.retire_if_due() == 0
    assert _stored(app, values)['target'] == PEM
    assert (2, 'active') in [(v, s) for v, s, _, _ in _rows(app)]
    grace(DAY + 1)
    with app.app_context():
        dek_rotation.scheduled_retire()
        assert dek_rotation.retiring() is None
        key_encryption.reload()
        assert not key_encryption.is_enabled and key_encryption.kek_loaded
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(0, 'disabled')]
    assert _stored(app, values)['target'] == PEM


def test_a_restart_during_the_grace_of_a_disable_keeps_the_deks(app, auth_client, values, grace,
                                                               monkeypatch, encryption_enabled):
    key_encryption = encryption_enabled.key_encryption
    with app.app_context():
        _rotate_at_once(monkeypatch)
        stale = key_encryption._fernet
    assert auth_client.post('/api/v2/system/security/disable-encryption').status_code == 200
    _late_write(app, values, stale)
    _start(app)
    assert app.config['SAFE_MODE'] is False
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(0, 'disabled'), (2, 'active')]
    assert _late_value_opens(app, values)
    grace(601)
    _start(app)  # the late value decrypted, then a second period
    assert _stored(app, values)['target'] == PEM
    grace(DAY + 1)
    _start(app)
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(0, 'disabled')]
    assert app.config['SAFE_MODE'] is False and not key_encryption.is_enabled


def test_a_file_disable_keeps_the_master_key_until_the_grace_ends(app, auth_client, envelope_keys,
                                                                 set_env, grace,
                                                                 encryption_enabled):
    """The DEK rows are wrapped by the file's KEK: removing it first would make them useless."""
    from security import dek_rotation
    key_encryption = encryption_enabled.key_encryption
    path = encryption_enabled.MASTER_KEY_PATH
    path.write_text(Fernet.generate_key().decode())
    set_env('KEY_ENCRYPTION_KEY', None)
    with app.app_context():
        key_encryption.reload()
        assert key_encryption.key_source == 'file'
    assert auth_client.post('/api/v2/system/security/disable-encryption').status_code == 200
    assert path.exists()
    grace(601)
    with app.app_context():
        assert dek_rotation.retire_if_due() == 1
        assert not key_encryption.is_enabled
    assert not path.exists()
    assert [s for _, s, _, _ in _rows(app)] == ['disabled']


def test_in_ha_the_deks_of_a_disable_wait_for_every_live_node(app, auth_client, values, grace,
                                                             monkeypatch):
    from models import ClusterNode
    from security import dek_rotation
    from services.scheduler_leader import cluster_utc_now
    _ha(monkeypatch)
    assert auth_client.post('/api/v2/system/security/disable-encryption').status_code == 200
    with app.app_context():
        command = dek_rotation.retiring()['command']
        assert command
    grace(601)
    with app.app_context():
        now = cluster_utc_now()
        db.session.add(ClusterNode(node_id='envtest-lag', started_at=now, heartbeat_at=now,
                                   is_leader=False, command_seen=command - 1))
        db.session.commit()
        assert dek_rotation.retire_if_due() == 0
        db.session.get(ClusterNode, 'envtest-lag').command_seen = command
        db.session.commit()
        assert dek_rotation.retire_if_due() == 1
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(0, 'disabled')]


def test_enable_and_rotate_during_the_grace_of_a_disable_name_its_end(app, auth_client, values,
                                                                      grace):
    assert auth_client.post('/api/v2/system/security/disable-encryption').status_code == 200
    for route in ('enable-encryption', 'rotate-encryption-key'):
        r = auth_client.post(f'/api/v2/system/security/{route}')
        assert r.status_code == 409, r.data
        # A rotation is refused (400) after the grace too: the way on is to enable
        message = r.get_json()['message']
        assert 'Encryption was just disabled: enable it again after ' in message
        assert message.endswith(' UTC.') and 'Try again' not in message
    grace(601)
    assert auth_client.post('/api/v2/system/security/rotate-encryption-key').status_code == 400
    r = auth_client.post('/api/v2/system/security/enable-encryption')
    assert r.status_code == 200, r.data
    assert _rows(app) == []
    assert _read(app, values) == CLEAR


def test_the_dashboard_and_the_preflight_read_a_disable_in_its_grace_as_the_status_does(
        app, auth_client, values, grace):
    """The DEKs are still loaded, but nothing is encrypted: every reader says off."""
    from services import fips_preflight

    def readers():
        status = auth_client.get('/api/v2/system/security/encryption-status').get_json()['data']
        board = auth_client.get('/api/v2/dashboard/system-status').get_json()['data']
        with app.app_context():
            findings = {f['id'] for f in fips_preflight.run()['findings']}
        return (status['enabled'], board['key_encryption']['status'],
                'keys.no_master_key' in findings)

    assert readers() == (True, 'online', False)
    assert auth_client.post('/api/v2/system/security/disable-encryption').status_code == 200
    assert readers() == (False, 'warning', True)


@pytest.mark.skipif(not pg_app_harness.ENABLED, reason='needs UCM_TEST_APP_PG_URL')
def test_on_postgresql_a_transaction_open_across_the_disable_stays_readable(
        app, auth_client, values, grace, monkeypatch, encryption_enabled):
    """A second connection encrypts under the DEK, the disable ends, then it commits."""
    from sqlalchemy import text
    from security import dek_rotation, encryption
    key = f"acme.account.late{values['tag']}.private_key"
    with app.app_context():
        _rotate_at_once(monkeypatch)
        stale = encryption_enabled.key_encryption._fernet
        late = base64.b64encode(encryption.ENCRYPTED_MARKER + stale.encrypt(PEM.encode())).decode()
        other = db.engine.connect()
        transaction = other.begin()
        other.execute(text("INSERT INTO system_config (key, value) VALUES (:k, :v)"),
                      {'k': key, 'v': late})
    try:
        assert auth_client.post('/api/v2/system/security/disable-encryption').status_code == 200
        transaction.commit()
        with app.app_context():
            encryption_enabled.key_encryption.reload()
            stored = SystemConfig.query.filter_by(key=key).one().value
            assert encryption.decrypt_master_key_value(stored, 'text') == PEM
        grace(601)
        with app.app_context():
            assert dek_rotation.retire_if_due() == 0
            db.session.expire_all()
            assert SystemConfig.query.filter_by(key=key).one().value == PEM
        grace(DAY + 1)
        with app.app_context():
            assert dek_rotation.retire_if_due() == 1
    finally:
        other.close()
        with app.app_context():
            SystemConfig.query.filter_by(key=key).delete()
            db.session.commit()


def test_a_grace_retired_and_a_rotation_started_before_the_lock_is_not_retired_again(
        app, values, grace, monkeypatch, encryption_enabled):
    """Another node ends the grace and starts a rotation between the read and the lock."""
    from security import dek_rotation
    with app.app_context():
        dek_rotation.rotate()
    grace(601)
    real = dek_rotation.lock_key_state
    raced = []

    def other_node_first(session=None):
        if not raced:
            raced.append(True)
            with monkeypatch.context() as patch:
                patch.setattr(dek_rotation, 'lock_key_state', real)
                with app.app_context():
                    assert dek_rotation.retire_if_due() == 1
                    dek_rotation.start()  # previous v2, active v3, nothing rewritten yet
        return real(session)
    monkeypatch.setattr(dek_rotation, 'lock_key_state', other_node_first)
    with app.app_context():
        assert dek_rotation.retire_if_due() == 0
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(2, 'previous'), (3, 'active')]
    stored = _stored(app, values)
    with app.app_context():
        # Nothing was rewritten under v3 before the peers could have loaded it
        assert not dek_rotation._under_active(stored['target'])


def test_in_ha_a_start_under_a_kek_another_disabled_does_not_encrypt(app, values, monkeypatch,
                                                                    encryption_enabled):
    """The cluster was disabled under another KEK, and no peer is live to compare with."""
    from models import EncryptionKey
    from security import envelope
    from utils.datetime_utils import utc_now
    key_encryption = encryption_enabled.key_encryption
    with app.app_context():
        db.session.add(EncryptionKey(version=0, state=envelope.DISABLED, kek_id='f' * 16,
                                     wrapped=None, created_at=utc_now()))
        db.session.commit()
    try:
        # Outside HA it is a disable followed by a new KEK: off until enabled again
        _start(app)
        assert not key_encryption.is_encrypting
        _ha(monkeypatch)
        _start(app)
        assert app.config['SAFE_MODE'] is True
        assert app.config['SAFE_MODE_REASON'] == 'encryption_key_mismatch'
        assert key_encryption.encrypt_string('x') == 'x'
    finally:
        app.config['SAFE_MODE'] = False


def test_the_scheduled_retire_says_once_that_the_key_is_kept(app, values, grace, caplog,
                                                            encryption_enabled):
    import logging
    from security import dek_rotation
    with app.app_context():
        dek_rotation.rotate()
    # A value no DEK opens: the end-of-grace sweep stops with the previous key kept
    _late_write(app, values, Fernet(Fernet.generate_key()))
    grace(601)
    with caplog.at_level(logging.ERROR, logger='security.dek_rotation'), app.app_context():
        dek_rotation.scheduled_retire()
    lines = [r.getMessage() for r in caplog.records
             if r.name == 'security.dek_rotation' and r.levelno >= logging.ERROR]
    assert len(lines) == 1 and 'decrypt with no data-encryption key' in lines[0]
    assert lines[0].count('kept') == 1
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(1, 'previous'), (2, 'active')]
    _late_write(app, values, Fernet(_kek(encryption_enabled)))  # readable again for teardown


def test_the_retire_after_a_disable_names_the_disable(app, auth_client, values, grace, caplog,
                                                     encryption_enabled):
    import logging
    from security import dek_rotation
    assert auth_client.post('/api/v2/system/security/disable-encryption').status_code == 200
    _late_write(app, values, Fernet(Fernet.generate_key()))
    grace(601)
    with caplog.at_level(logging.ERROR, logger='security.dek_rotation'), app.app_context():
        dek_rotation.scheduled_retire()
    lines = [r.getMessage() for r in caplog.records
             if r.name == 'security.dek_rotation' and r.levelno >= logging.ERROR]
    assert len(lines) == 1 and 'previous key' not in lines[0]
    assert 'keys of the disable are kept' in lines[0]
    _late_write(app, values, Fernet(_kek(encryption_enabled)))  # readable again for teardown


def test_in_ha_a_kek_changed_by_hand_after_a_disable_keeps_the_cluster_off(
        app, auth_client, values, monkeypatch, set_env, encryption_enabled):
    """The documented manual KEK change, encryption disabled: the marker follows the new KEK."""
    from security import envelope
    key_encryption = encryption_enabled.key_encryption
    _ha(monkeypatch)
    assert auth_client.post('/api/v2/system/security/disable-encryption').status_code == 200
    old = _kek(encryption_enabled)
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(0, 'disabled')]
    new = Fernet.generate_key()
    set_env('KEY_ENCRYPTION_KEY', new.decode())
    set_env('KEY_ENCRYPTION_KEY_PREVIOUS', old.decode())
    try:
        _start(app)
        assert app.config['SAFE_MODE'] is False
        assert not key_encryption.is_enabled and key_encryption.kek_loaded
        new_id = envelope.kek_id(base64.urlsafe_b64decode(new))
        assert _rows(app) == [(0, 'disabled', new_id, None)]
        assert _stored(app, values)['target'] == PEM
    finally:
        app.config['SAFE_MODE'] = False


def test_in_ha_a_node_without_the_previous_kek_names_the_foreign_disable(
        app, auth_client, values, monkeypatch, set_env, encryption_enabled):
    """Nothing is encrypted, so no key is "undecryptable": the node is told its KEK is not the
    cluster's, and writes nothing (started off, an enable from it would encrypt under it)."""
    from security.master_key_bootstrap import reload_encryption_state
    key_encryption = encryption_enabled.key_encryption
    _ha(monkeypatch)
    assert auth_client.post('/api/v2/system/security/disable-encryption').status_code == 200
    set_env('KEY_ENCRYPTION_KEY', Fernet.generate_key().decode())
    try:
        _start(app)
        assert app.config['SAFE_MODE'] is True
        assert app.config['SAFE_MODE_REASON'] == 'encryption_kek_not_the_clusters'
        assert key_encryption.encrypt_string('x') == 'x'
        assert [(v, s) for v, s, _, _ in _rows(app)] == [(0, 'disabled')]
        # A peer's reload command reaches the same verdict
        app.config['SAFE_MODE_REASON'] = None
        with app.app_context():
            reload_encryption_state(app)
        assert app.config['SAFE_MODE'] is True
        assert app.config['SAFE_MODE_REASON'] == 'encryption_kek_not_the_clusters'
    finally:
        app.config['SAFE_MODE'] = False


def _foreign_start(app, auth_client, monkeypatch, set_env):
    """HA, the cluster disabled under the fixture's KEK, this node started with another one."""
    _ha(monkeypatch)
    assert auth_client.post('/api/v2/system/security/disable-encryption').status_code == 200
    foreign = Fernet.generate_key()
    set_env('KEY_ENCRYPTION_KEY', foreign.decode())
    _start(app)
    assert app.config['SAFE_MODE_REASON'] == 'encryption_kek_not_the_clusters'
    from security import envelope
    return envelope.kek_id(base64.urlsafe_b64decode(foreign))


def test_in_ha_a_node_started_under_a_foreign_kek_stays_off_when_a_peer_enables(
        app, auth_client, values, monkeypatch, set_env, encryption_enabled):
    """A peer's enable drops the markers: the reload must not take this KEK for DEK version 1."""
    from models import ClusterNode, EncryptionKey
    from security.master_key_bootstrap import reload_encryption_state
    from services.scheduler_leader import cluster_utc_now, write_heartbeat
    key_encryption = encryption_enabled.key_encryption
    try:
        foreign_id = _foreign_start(app, auth_client, monkeypatch, set_env)
        with app.app_context():
            EncryptionKey.query.delete()
            db.session.commit()
            reload_encryption_state(app)
            assert app.config['SAFE_MODE'] is True
            assert not key_encryption.is_encrypting
            assert key_encryption.encrypt_string('x') == 'x'
            key_encryption.reload()  # any later reload of this process (a retire, a rotation)
            assert not key_encryption.is_encrypting and not key_encryption.kek_loaded
            # Unloaded, the node still tells its peers which KEK it holds
            write_heartbeat('envtest-b', False, cluster_utc_now())
            assert db.session.get(ClusterNode, 'envtest-b').kek_fingerprint == foreign_id
        # A new start (the process restarted) evaluates the KEK again
        _start(app)
        assert key_encryption.kek_loaded
    finally:
        app.config['SAFE_MODE'] = False


def test_in_ha_enable_is_refused_while_a_live_node_holds_another_kek(
        app, auth_client, values, monkeypatch, encryption_enabled):
    from models import ClusterNode
    from services.scheduler_leader import cluster_utc_now
    _ha(monkeypatch)
    assert auth_client.post('/api/v2/system/security/disable-encryption').status_code == 200
    with app.app_context():
        now = cluster_utc_now()
        db.session.add(ClusterNode(node_id='envtest-b', started_at=now, heartbeat_at=now,
                                   is_leader=False, kek_fingerprint='f' * 16))
        db.session.commit()
    r = auth_client.post('/api/v2/system/security/enable-encryption')
    assert r.status_code == 409 and 'envtest-b' in r.get_json()['message']
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(0, 'disabled')]
    assert _stored(app, values)['target'] == PEM


def test_in_ha_a_reload_never_encrypts_under_a_kek_no_live_peer_shares(
        app, values, monkeypatch, encryption_enabled):
    """No DEK row names this KEK, and the live peers publish another: it is not the cluster's."""
    from models import ClusterNode
    from security.master_key_bootstrap import reload_encryption_state
    from services.scheduler_leader import cluster_utc_now
    key_encryption = encryption_enabled.key_encryption
    _ha(monkeypatch)
    with app.app_context():
        now = cluster_utc_now()
        db.session.add(ClusterNode(node_id='envtest-a', started_at=now, heartbeat_at=now,
                                   is_leader=True, kek_fingerprint='f' * 16))
        db.session.commit()
        try:
            reload_encryption_state(app)
            assert app.config['SAFE_MODE'] is True
            assert key_encryption.encrypt_string('x') == 'x'
        finally:
            app.config['SAFE_MODE'] = False


def test_in_ha_a_start_is_not_refused_by_a_peer_whose_kek_the_database_does_not_name(
        app, auth_client, values, monkeypatch, encryption_enabled):
    """The markers name this node's KEK: the live peer that differs is the stranger."""
    from models import ClusterNode
    from security.master_key_bootstrap import refuse_kek_mismatch_with_peers
    from services.scheduler_leader import cluster_utc_now
    _ha(monkeypatch)
    assert auth_client.post('/api/v2/system/security/disable-encryption').status_code == 200
    with app.app_context():
        now = cluster_utc_now()
        db.session.add(ClusterNode(node_id='envtest-b', started_at=now, heartbeat_at=now,
                                   is_leader=False, kek_fingerprint='f' * 16))
        db.session.commit()
        encryption_enabled.key_encryption.reload()
        refuse_kek_mismatch_with_peers()


def test_a_start_during_a_disable_left_half_way_logs_no_encryption_resumed(
        app, values, caplog, monkeypatch, encryption_enabled):
    """Nothing is encrypted while disabling: no "now encrypted" nor "still unencrypted" line."""
    import logging
    from security import dek_rotation
    from security.encryption import decrypt_all_keys
    from security import master_key_bootstrap
    monkeypatch.setattr(master_key_bootstrap, 'auto_master_key_allowed', lambda app: True)
    with app.app_context():
        dek_rotation.begin_disable()
        decrypt_all_keys(dry_run=False)
    with caplog.at_level(logging.WARNING, logger='security.master_key_bootstrap'):
        _start(app)
    lines = [r.getMessage() for r in caplog.records if r.name == 'security.master_key_bootstrap']
    assert not any('now encrypted' in line or 'still stored unencrypted' in line for line in lines)


def test_a_key_the_end_of_grace_sweep_decrypts_gets_its_mirror(app, auth_client, values, grace,
                                                                 monkeypatch, create_ca,
                                                                 encryption_enabled):
    """The disable wrote the mirrors before the late value came: the sweep writes its own."""
    from models import CA
    from security import dek_rotation, encryption
    from utils.file_naming import ca_key_path
    key_encryption = encryption_enabled.key_encryption
    ca_id = create_ca()['id']
    with app.app_context():
        _rotate_at_once(monkeypatch)
        stale = key_encryption._fernet
    assert auth_client.post('/api/v2/system/security/disable-encryption').status_code == 200
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        plain, path = ca.prv, ca_key_path(ca)
        # A process still encrypting commits the key late, and drops the mirror as it does
        ca.prv = base64.b64encode(encryption.ENCRYPTED_MARKER
                                  + stale.encrypt(base64.b64decode(plain))).decode()
        db.session.commit()
    path.unlink()
    grace(601)
    with app.app_context():
        assert dek_rotation.retire_if_due() == 0
        assert db.session.get(CA, ca_id).prv == plain
    assert path.read_bytes() == base64.b64decode(plain)


def test_outside_ha_a_kek_replaced_without_the_previous_one_after_a_disable_stays_off(
        app, auth_client, values, set_env, encryption_enabled):
    """The marker names the old KEK: the new one never turns encryption back on by itself."""
    key_encryption = encryption_enabled.key_encryption
    assert auth_client.post('/api/v2/system/security/disable-encryption').status_code == 200
    rows = _rows(app)
    assert [(v, s) for v, s, _, _ in rows] == [(0, 'disabled')]
    set_env('KEY_ENCRYPTION_KEY', Fernet.generate_key().decode())
    try:
        _start(app)
        assert app.config['SAFE_MODE'] is False
        with app.app_context():
            assert not key_encryption.is_enabled and key_encryption.kek_loaded
            assert key_encryption.encrypt_string('x') == 'x'
        assert _rows(app) == rows and _stored(app, values)['target'] == PEM
        # Enabling is the operator's choice: under the new KEK
        r = auth_client.post('/api/v2/system/security/enable-encryption')
        assert r.status_code == 200, r.data
        assert key_encryption.is_encrypted(_stored(app, values)['target'])
        assert _read(app, values) == CLEAR
    finally:
        app.config['SAFE_MODE'] = False
        with app.app_context():
            # Back in the clear while the new KEK is loaded: the teardown holds the old one
            encryption_enabled.decrypt_all_keys(dry_run=False)


# --- short grace: every live node acknowledged, then a margin ------------


def _margin():
    from security import dek_rotation
    return dek_rotation.ACK_MARGIN_SECONDS


def test_the_previous_dek_goes_a_margin_after_every_node_acknowledged(app, auth_client, values,
                                                                       grace):
    """Outside HA no node acknowledges: the margin counts from the end of the rotation."""
    from datetime import datetime
    from security import dek_rotation
    from services.scheduler_leader import cluster_utc_now
    with app.app_context():
        before = cluster_utc_now()
        result = dek_rotation.rotate()
    end = datetime.fromisoformat(result['rotation_available_after'])
    assert -1 <= (end - before).total_seconds() - _margin() < 30
    status = auth_client.get('/api/v2/system/security/encryption-status').get_json()['data']
    assert status['rotation_available_after'] == result['rotation_available_after'] + 'Z'
    assert status['rotation_waits_for_nodes'] is False
    grace(_margin() - 5)
    with app.app_context():
        assert dek_rotation.retire_if_due() == 0
    grace(36)
    with app.app_context():
        assert dek_rotation.retire_if_due() == 1
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(2, 'active')]


def _lagging_disable(app, auth_client, monkeypatch):
    """HA, a live node that applies no command: the disable goes on without waiting for it."""
    from models import ClusterNode
    from security import dek_rotation
    from services.scheduler_leader import cluster_utc_now
    _ha(monkeypatch)
    monkeypatch.setattr(dek_rotation, 'ACK_TIMEOUT_SECONDS', 0.0)
    with app.app_context():
        now = cluster_utc_now()
        db.session.add(ClusterNode(node_id='envtest-lag', started_at=now, heartbeat_at=now,
                                   is_leader=False, command_seen=0))
        db.session.commit()
    r = auth_client.post('/api/v2/system/security/disable-encryption')
    assert r.status_code == 200, r.data
    return r.get_json()['data']


def _node_acknowledges(app, acknowledged=True):
    from models import ClusterNode
    from security import dek_rotation
    from services.scheduler_leader import cluster_utc_now
    node = db.session.get(ClusterNode, 'envtest-lag')
    node.heartbeat_at = cluster_utc_now()
    if acknowledged:
        node.command_seen = dek_rotation.retiring()['command']
    db.session.commit()


def test_in_ha_the_grace_waits_for_a_lagging_node_then_a_margin(app, auth_client, values, grace,
                                                                monkeypatch):
    from security import dek_rotation
    from services.scheduler_leader import cluster_utc_now
    data = _lagging_disable(app, auth_client, monkeypatch)
    # No time is announced before every live node has reloaded
    assert data['enable_available_after'] is None
    status = auth_client.get('/api/v2/system/security/encryption-status').get_json()['data']
    assert status['enable_available_after'] is None and status['enable_waits_for_nodes']
    r = auth_client.post('/api/v2/system/security/enable-encryption')
    assert r.status_code == 409 and 'every node' in r.get_json()['message']
    grace(300)
    with app.app_context():
        _node_acknowledges(app, acknowledged=False)
        assert dek_rotation.retire_if_due() == 0  # still lagging
        _node_acknowledges(app)
        assert dek_rotation.retire_if_due() == 0  # acknowledged now: the margin starts
        end = dek_rotation.grace_end(dek_rotation.retiring())
        assert abs((end - cluster_utc_now()).total_seconds() - _margin()) < 30
    status = auth_client.get('/api/v2/system/security/encryption-status').get_json()['data']
    assert status['enable_available_after'] == end.isoformat(timespec='seconds') + 'Z'
    assert status['enable_waits_for_nodes'] is False
    grace(_margin() + 1)
    with app.app_context():
        _node_acknowledges(app)
        assert dek_rotation.retire_if_due() == 1


def test_in_ha_a_node_acknowledging_late_ends_the_grace_at_its_cap(app, auth_client, values,
                                                                   grace, monkeypatch):
    """Ten minutes stay the cap: past them only a node still lagging holds the DEKs."""
    from security import dek_rotation
    _lagging_disable(app, auth_client, monkeypatch)
    grace(590)
    with app.app_context():
        _node_acknowledges(app, acknowledged=False)
        assert dek_rotation.retire_if_due() == 0
        _node_acknowledges(app)
        assert dek_rotation.retire_if_due() == 0
    grace(11)
    with app.app_context():
        _node_acknowledges(app)
        assert dek_rotation.retire_if_due() == 1


def test_in_ha_past_the_cap_a_node_still_lagging_keeps_the_deks(app, auth_client, values, grace,
                                                                monkeypatch):
    from security import dek_rotation
    _lagging_disable(app, auth_client, monkeypatch)
    grace(1200)
    with app.app_context():
        _node_acknowledges(app, acknowledged=False)
        assert dek_rotation.retire_if_due() == 0
        _node_acknowledges(app)
        assert dek_rotation.retire_if_due() == 1


def test_a_value_written_under_the_old_dek_during_the_margin_is_swept(app, values, grace,
                                                                      encryption_enabled):
    from security import dek_rotation
    with app.app_context():
        old = encryption_enabled.key_encryption._fernet
        dek_rotation.rotate()
    grace(_margin() / 2)
    _late_write(app, values, old)
    grace(_margin())
    with app.app_context():
        assert dek_rotation.retire_if_due() == 0  # rewritten, kept until the next sweep
    with pytest.raises(InvalidToken):
        old.decrypt(_token(_stored(app, values)['target']))
    assert _read(app, values) == CLEAR
    grace(DAY + 1)
    with app.app_context():
        assert dek_rotation.retire_if_due() == 1
    assert _read(app, values) == CLEAR


def test_in_ha_a_process_the_acknowledgement_does_not_cover_re_reads_before_it_encrypts(
        app, values, monkeypatch, encryption_enabled):
    """The node's ack is its web worker's; its scheduler process re-reads the rows on its own
    once they are REFRESH_SECONDS old, so it encrypts under the new DEK before the margin."""
    from security import dek_rotation, encryption
    key_encryption = encryption_enabled.key_encryption
    _ha(monkeypatch)
    monkeypatch.setattr(encryption, 'REFRESH_SECONDS', 2.0)
    with app.app_context():
        key_encryption.is_enabled
        stale = {name: getattr(key_encryption, name) for name in key_encryption._FIELDS}
        dek_rotation.rotate()
        key_encryption.__dict__.update(stale)  # applied no command: still DEK version 1
        key_encryption._read_at -= encryption.REFRESH_SECONDS
        written = key_encryption.encrypt_string('scheduler write')
        assert key_encryption.active_version == 2
        key_encryption.reload()
        assert encryption.decrypt_master_key_value(written, 'text') == 'scheduler write'
        assert dek_rotation.ACK_MARGIN_SECONDS > encryption.REFRESH_SECONDS


def test_the_disable_announces_the_end_of_its_grace(app, auth_client, values, grace):
    """Outside HA no node acknowledges: the margin counts from the end of the disable."""
    from security import dek_rotation
    from services.scheduler_leader import cluster_utc_now
    r = auth_client.post('/api/v2/system/security/disable-encryption')
    with app.app_context():
        end = dek_rotation.grace_end(dek_rotation.retiring())
    assert r.get_json()['data']['enable_available_after'] == end.isoformat(timespec='seconds') + 'Z'
    assert abs((end - cluster_utc_now()).total_seconds() - _margin()) < 30
    status = auth_client.get('/api/v2/system/security/encryption-status').get_json()['data']
    assert status['enable_available_after'] == r.get_json()['data']['enable_available_after']
    assert status['enable_waits_for_nodes'] is False
    grace(_margin() + 1)
    r = auth_client.post('/api/v2/system/security/enable-encryption')
    assert r.status_code == 200, r.data


# --- retention: old DEKs kept for reading, dropped after a clean sweep ---------



@pytest.fixture
def retention(monkeypatch, grace):
    """The default week of retention after the ten-minute grace; returns ``later``."""
    from security import dek_rotation
    monkeypatch.setattr(dek_rotation, 'RETENTION_SECONDS', float(WEEK))
    monkeypatch.setattr(dek_rotation, 'SWEEP_SECONDS', float(DAY))
    return grace


def _retain_after(app):
    from models import EncryptionKey
    with app.app_context():
        return {r.version: r.retire_after for r in EncryptionKey.query.all()}


def _write_under(app, model, row_id, attribute, fernet, plain):
    from security import encryption
    with app.app_context():
        setattr(db.session.get(model, row_id), attribute, base64.b64encode(
            encryption.ENCRYPTED_MARKER + fernet.encrypt(plain)).decode())
        db.session.commit()


def test_a_value_committed_under_the_old_dek_days_after_the_grace_is_read_then_swept(
        app, values, retention, encryption_enabled):
    """A long transaction encrypted under DEK 1 and commits three days after the rotation."""
    from security import dek_rotation
    with app.app_context():
        old = encryption_enabled.key_encryption._fernet
        dek_rotation.rotate()
    retention(601)
    with app.app_context():
        assert dek_rotation.retire_if_due() == 0
        assert dek_rotation.retiring() is None  # the next rotation is possible
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(1, 'previous'), (2, 'active')]
    retention(3 * DAY)
    _late_write(app, values, old)
    assert _read(app, values) == CLEAR
    with app.app_context():
        dek_rotation.scheduled_sweep()
    with pytest.raises(InvalidToken):
        old.decrypt(_token(_stored(app, values)['target']))
    assert _read(app, values) == CLEAR
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(1, 'previous'), (2, 'active')]
    retention(WEEK)
    with app.app_context():
        dek_rotation.scheduled_retire()
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(2, 'active')]
    assert _read(app, values) == CLEAR


def test_two_rotations_within_the_retention_leave_three_keys_readable(
        app, auth_client, values, retention, encryption_enabled):
    from models.deploy import DeployTarget
    from models.ssh import SSHCertificateAuthority
    from security import dek_rotation
    key_encryption = encryption_enabled.key_encryption
    with app.app_context():
        first = key_encryption._fernet
        dek_rotation.rotate()
        second = key_encryption._fernet
    retention(601)
    r = auth_client.post('/api/v2/system/security/rotate-encryption-key')
    assert r.status_code == 200, r.data
    assert r.get_json()['data']['version'] == 3
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(1, 'previous'), (2, 'previous'),
                                                     (3, 'active')]
    _write_under(app, DeployTarget, values['ids'][DeployTarget], 'private_key', first,
                 PEM.encode())
    _write_under(app, SSHCertificateAuthority, values['ids'][SSHCertificateAuthority],
                 'private_key', second, base64.b64decode(SSH_KEY))
    with app.app_context():
        key_encryption.reload()
        assert key_encryption.dek_versions == (1, 2, 3)
    assert _read(app, values) == CLEAR
    retained = _retain_after(app)
    assert retained[3] is None and retained[2] > retained[1]


def test_a_retained_key_a_sweep_still_finds_a_value_under_is_kept(app, values, retention,
                                                                  encryption_enabled):
    from security import dek_rotation
    with app.app_context():
        old = encryption_enabled.key_encryption._fernet
        dek_rotation.rotate()
    retention(601)
    with app.app_context():
        dek_rotation.retire_if_due()
    retention(WEEK)
    _late_write(app, values, old)
    with app.app_context():
        assert dek_rotation.retire_if_due() == 0
    # Rewritten under the current DEK, the old one kept until the next sweep finds none
    with pytest.raises(InvalidToken):
        old.decrypt(_token(_stored(app, values)['target']))
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(1, 'previous'), (2, 'active')]
    retention(DAY + 1)
    with app.app_context():
        assert dek_rotation.retire_if_due() == 1
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(2, 'active')]
    assert _read(app, values) == CLEAR


def test_a_retained_key_is_kept_while_a_value_opens_with_no_key(app, values, retention,
                                                                encryption_enabled):
    from security import dek_rotation
    with app.app_context():
        dek_rotation.rotate()
    retention(601)
    with app.app_context():
        dek_rotation.retire_if_due()
    retention(WEEK)
    _late_write(app, values, Fernet(Fernet.generate_key()))
    try:
        with app.app_context(), pytest.raises(dek_rotation.RotationError):
            dek_rotation.retire_if_due()
        assert [(v, s) for v, s, _, _ in _rows(app)] == [(1, 'previous'), (2, 'active')]
    finally:
        _late_write(app, values, Fernet(_kek(encryption_enabled)))  # readable for teardown


def test_the_status_says_rotation_possible_once_the_short_grace_ends(app, auth_client, values,
                                                                    retention):
    from security import dek_rotation
    with app.app_context():
        dek_rotation.rotate()
    status = auth_client.get('/api/v2/system/security/encryption-status').get_json()['data']
    assert status['rotation_available'] is False and status['rotation_available_after']
    retention(601)
    with app.app_context():
        dek_rotation.retire_if_due()
    status = auth_client.get('/api/v2/system/security/encryption-status').get_json()['data']
    assert status['rotation_available'] is True and status['rotation_available_after'] is None
    assert status['rotation_in_progress'] is False
    kept = status['retained_keys']
    assert [k['version'] for k in kept] == [1]
    assert kept[0]['retire_after'] == (_retain_after(app)[1].isoformat(timespec='seconds')
                                       + 'Z')


def test_a_grace_replaced_by_another_node_is_not_ended_here(app, values, grace, monkeypatch):
    """Between the acknowledgement check and its record, a peer set a grace of its own."""
    from security import dek_rotation
    with app.app_context():
        dek_rotation.rotate()
        # As in HA while a node lags: no acknowledgement recorded yet
        current = dek_rotation.retiring()
        dek_rotation._set_grace(current['version'], current['command'], until=current['until'])
        db.session.commit()
    grace(601)
    real = dek_rotation.wait_for_nodes

    def peer_replaces_the_grace(command, timeout=None):
        dek_rotation._set_grace(99, None)
        db.session.commit()
        return real(command, timeout)
    monkeypatch.setattr(dek_rotation, 'wait_for_nodes', peer_replaces_the_grace)
    with app.app_context():
        assert dek_rotation.retire_if_due() == 0
        assert dek_rotation.retiring()['version'] == 99


def test_a_disable_keeps_its_keys_for_the_retention_and_its_late_values_are_decrypted(
        app, auth_client, values, retention, monkeypatch, encryption_enabled):
    from security import dek_rotation
    key_encryption = encryption_enabled.key_encryption
    with app.app_context():
        _rotate_at_once(monkeypatch)
        stale = key_encryption._fernet
    r = auth_client.post('/api/v2/system/security/disable-encryption')
    assert r.status_code == 200, r.data
    retention(601)
    with app.app_context():
        dek_rotation.retire_if_due()
    status = auth_client.get('/api/v2/system/security/encryption-status').get_json()['data']
    assert status['enabled'] is False and status['disabling'] is False
    assert status['enable_available_after'] is None
    # Version 1 from the rotation before, version 2 from the disable
    assert [k['version'] for k in status['retained_keys']] == [1, 2]
    retention(2 * DAY)
    _late_write(app, values, stale)
    assert _late_value_opens(app, values)
    with app.app_context():
        dek_rotation.scheduled_sweep()
    assert _stored(app, values)['target'] == PEM
    retention(WEEK)
    with app.app_context():
        dek_rotation.scheduled_retire()
        key_encryption.reload()
        assert not key_encryption.is_enabled and key_encryption.kek_loaded
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(0, 'disabled')]


def _file_kek(app, set_env, encryption_enabled):
    """master.key holds the KEK, no variable: the case a disable removes the file for."""
    key_encryption = encryption_enabled.key_encryption
    path = encryption_enabled.MASTER_KEY_PATH
    path.write_text(Fernet.generate_key().decode())
    set_env('KEY_ENCRYPTION_KEY', None)
    with app.app_context():
        key_encryption.reload()
        assert key_encryption.key_source == 'file'
    return path


def test_a_file_disable_removes_the_master_key_with_the_last_retained_key(
        app, auth_client, envelope_keys, set_env, retention, encryption_enabled):
    """The file's KEK wraps the retained DEKs: it goes in the step that drops the last one."""
    from security import dek_rotation
    key_encryption = encryption_enabled.key_encryption
    path = _file_kek(app, set_env, encryption_enabled)
    with app.app_context():
        dek_rotation.rotate()  # DEK 1 retained a week from now
    retention(DAY)
    assert auth_client.post('/api/v2/system/security/disable-encryption').status_code == 200
    status = auth_client.get('/api/v2/system/security/encryption-status').get_json()['data']
    assert status['key_file_kept_for_retained_keys'] is True
    retention(601)
    with app.app_context():
        assert dek_rotation.retire_if_due() == 0
    assert path.exists()
    retention(WEEK - DAY)
    with app.app_context():
        assert dek_rotation.retire_if_due() == 1  # DEK 1; DEK 2 a day more
    assert path.exists()
    retention(DAY)
    with app.app_context():
        assert dek_rotation.retire_if_due() == 1
        assert not key_encryption.is_enabled
    assert not path.exists()
    assert [s for _, s, _, _ in _rows(app)] == ['disabled']


def test_enabling_with_a_new_master_key_is_refused_while_keys_are_retained(
        app, auth_client, envelope_keys, set_env, retention, encryption_enabled):
    """master.key was removed by hand during the retention: a new one could not open them."""
    key_encryption = encryption_enabled.key_encryption
    path = _file_kek(app, set_env, encryption_enabled)
    assert auth_client.post('/api/v2/system/security/disable-encryption').status_code == 200
    retention(601)
    rows = _rows(app)
    path.unlink()
    with app.app_context():
        key_encryption.reload()
        assert not key_encryption.kek_loaded
    r = auth_client.post('/api/v2/system/security/enable-encryption')
    assert r.status_code == 409, r.data
    assert not path.exists() and _rows(app) == rows


def test_a_retention_sweep_never_runs_while_a_rotation_waits_for_its_nodes(
        app, values, retention, encryption_enabled):
    """A new DEK may not be loaded everywhere yet: nothing is written under it before then."""
    from security import dek_rotation
    with app.app_context():
        dek_rotation.rotate()
    retention(601)
    with app.app_context():
        dek_rotation.retire_if_due()
        dek_rotation.start()  # DEK 2 being rewritten, DEK 3 active, nothing rewritten yet
    retention(WEEK)
    with app.app_context():
        assert dek_rotation.retire_if_due(sweep=True) == 0
        assert not dek_rotation._under_active(_stored(app, values)['target'])
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(1, 'previous'), (2, 'previous'),
                                                     (3, 'active')]


def test_enabling_during_the_retention_of_a_disable_keeps_its_keys_readable(
        app, auth_client, values, retention, monkeypatch, encryption_enabled):
    from security import dek_rotation
    key_encryption = encryption_enabled.key_encryption
    with app.app_context():
        _rotate_at_once(monkeypatch)
        stale = key_encryption._fernet
    assert auth_client.post('/api/v2/system/security/disable-encryption').status_code == 200
    retention(601)
    r = auth_client.post('/api/v2/system/security/enable-encryption')
    assert r.status_code == 200, r.data
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(1, 'previous'), (2, 'previous'),
                                                     (3, 'active')]
    assert _read(app, values) == CLEAR
    _late_write(app, values, stale)
    assert _read(app, values) == CLEAR
    with app.app_context():
        assert key_encryption.is_encrypting and key_encryption.active_version == 3
        dek_rotation.scheduled_sweep()
    with pytest.raises(InvalidToken):
        stale.decrypt(_token(_stored(app, values)['target']))
    retention(WEEK)
    with app.app_context():
        assert dek_rotation.retire_if_due() == 2
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(3, 'active')]
    assert _read(app, values) == CLEAR


def test_a_kek_changed_by_hand_rewraps_the_retained_keys_too(set_env, app, values, retention,
                                                             encryption_enabled):
    from security import dek_rotation
    old = _kek(encryption_enabled).decode()
    with app.app_context():
        dek_rotation.rotate()
    retention(601)
    with app.app_context():
        dek_rotation.rotate()
    kept = _retain_after(app)
    new = Fernet.generate_key().decode()
    set_env('KEY_ENCRYPTION_KEY', new)
    set_env('KEY_ENCRYPTION_KEY_PREVIOUS', old)
    _start(app)
    assert app.config['SAFE_MODE'] is False
    rows = _rows(app)
    assert [(v, s) for v, s, _, _ in rows] == [(1, 'previous'), (2, 'previous'), (3, 'active')]
    assert {k for _, _, k, _ in rows} == {encryption_enabled.key_encryption.kek_fingerprint()}
    assert _retain_after(app) == kept
    with app.app_context():
        encryption_enabled.key_encryption.reload()
        assert encryption_enabled.key_encryption.dek_versions == (1, 2, 3)
    set_env('KEY_ENCRYPTION_KEY_PREVIOUS', None)
    _start(app)
    assert app.config['SAFE_MODE'] is False and _read(app, values) == CLEAR


def _grace_row(app):
    with app.app_context():
        row = SystemConfig.query.filter_by(key=GRACE_KEY).first()
        return row.value if row else None


def test_a_rotation_after_a_disable_done_says_encryption_is_off(app, auth_client, values,
                                                                retention):
    """Not 'left half-way': the disable went to its end, its DEKs only kept for reading."""
    from security import dek_rotation
    assert auth_client.post('/api/v2/system/security/disable-encryption').status_code == 200
    retention(601)
    with app.app_context():
        dek_rotation.retire_if_due()
        assert dek_rotation.disable_done() and dek_rotation.retained()
    rows = _rows(app)
    r = auth_client.post('/api/v2/system/security/rotate-encryption-key')
    assert r.status_code == 400, r.data
    assert r.get_json()['message'] == 'Encryption is not enabled'
    assert _rows(app) == rows


@pytest.mark.parametrize('after_grace', [False, True, 'expired_stored'])
def test_a_second_disable_after_a_disable_done_changes_nothing(app, auth_client, values,
                                                               retention, after_grace):
    """A second disable within the retention neither rewrites the markers nor restarts a
    grace that would hold the next enable again. A grace over but still stored is ended by
    the route itself (retire_if_due) before it answers."""
    from security import dek_rotation
    assert auth_client.post('/api/v2/system/security/disable-encryption').status_code == 200
    if after_grace:
        retention(601)
    if after_grace is True:
        with app.app_context():
            dek_rotation.retire_if_due()
    rows, kept, grace_row = _rows(app), _retain_after(app), _grace_row(app)
    assert (grace_row is None) == (after_grace is True)
    r = auth_client.post('/api/v2/system/security/disable-encryption')
    assert r.status_code == 400, r.data
    assert r.get_json()['message'] == 'Encryption is not enabled'
    assert _rows(app) == rows and _retain_after(app) == kept
    assert _grace_row(app) == (None if after_grace else grace_row)


def test_a_restart_resumes_an_interrupted_rotation_before_an_old_key_past_its_retention(
        app, values, retention, encryption_enabled):
    """DEK 1 is past its retention while the rotation to DEK 3 was cut off: the start ends
    the rotation, then DEK 1 goes once the grace of that rotation is over."""
    from security import dek_rotation
    with app.app_context():
        dek_rotation.rotate()
    retention(601)
    with app.app_context():
        dek_rotation.retire_if_due()
        dek_rotation.start()  # interrupted: DEK 2 not rewritten yet
    retention(WEEK)
    _start(app)
    with app.app_context():
        assert not dek_rotation.rotation_in_progress()
        assert dek_rotation._under_active(_stored(app, values)['target'])
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(1, 'previous'), (2, 'previous'),
                                                     (3, 'active')]
    assert _read(app, values) == CLEAR
    retention(601)
    with app.app_context():
        assert dek_rotation.retire_if_due() == 1
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(2, 'previous'), (3, 'active')]
    assert _read(app, values) == CLEAR


def test_a_grace_refusal_names_its_end_or_what_it_waits_for():
    from datetime import datetime
    from security.dek_rotation import grace_refusal
    until = datetime(2026, 1, 2, 3, 4, 5)
    acked = datetime(2026, 1, 2, 3, 0, 0)
    rotation = {'until': until, 'acked': None}
    disable = {'until': until, 'acked': None, 'disable': True}
    assert grace_refusal(rotation) == ('A data-encryption key rotation just ended: rotate again '
                                       'two minutes after every node has loaded the new key.')
    assert grace_refusal(disable, 'disable encryption') == (
        'Encryption was just disabled: enable it again two minutes after every node has '
        'stopped encrypting.')
    assert grace_refusal({**rotation, 'acked': acked}, 'disable encryption') == (
        'A data-encryption key rotation just ended: disable encryption after '
        '2026-01-02T03:02:00 UTC.')
    assert grace_refusal({**disable, 'acked': acked}) == (
        'Encryption was just disabled: enable it again after 2026-01-02T03:02:00 UTC.')


def test_a_sweep_never_drops_the_dek_values_are_encrypted_under(app, values, retention,
                                                                encryption_enabled):
    """Built in the database (no normal path dates the active DEK while it encrypts): the
    guard keeps it whatever its date."""
    from datetime import timedelta
    from models import EncryptionKey
    from security import dek_rotation
    key_encryption = encryption_enabled.key_encryption
    with app.app_context():
        dek_rotation.rotate()
    retention(601)
    with app.app_context():
        dek_rotation.retire_if_due()
        row = db.session.get(EncryptionKey, 2)
        row.retire_after = row.created_at - timedelta(days=1)
        db.session.commit()
        key_encryption.reload()
        assert key_encryption.is_encrypting and key_encryption.active_version == 2
        assert dek_rotation.retire_if_due(sweep=True) == 0
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(1, 'previous'), (2, 'active')]
    assert _read(app, values) == CLEAR


def test_enabling_refuses_a_kept_dek_another_node_rewrapped_since_the_last_read(
        app, auth_client, values, retention, monkeypatch, encryption_enabled):
    """The rows read under the lock decide, not the DEKs this process loaded before."""
    from models import EncryptionKey
    from security import dek_rotation, encryption
    assert auth_client.post('/api/v2/system/security/disable-encryption').status_code == 200
    retention(601)
    with app.app_context():
        dek_rotation.retire_if_due()
        encryption_enabled.key_encryption.reload()
    monkeypatch.setattr(encryption, 'REFRESH_SECONDS', 3600.0)
    with app.app_context():
        EncryptionKey.query.filter(EncryptionKey.version > 0).update(
            {'kek_id': '0' * 16}, synchronize_session=False)
        db.session.commit()
    rows = _rows(app)
    r = auth_client.post('/api/v2/system/security/enable-encryption')
    assert r.status_code == 409, r.data
    assert 'do not open with the configured' in r.get_json()['message']
    assert _rows(app) == rows


def test_a_key_file_not_written_keeps_the_disabled_markers(app, monkeypatch):
    # Without them a KEK configured later would turn encryption on by itself
    from models import EncryptionKey
    from security import encryption, envelope
    from security.master_key_bootstrap import activate_new_master_key
    from utils.datetime_utils import utc_now

    def refuse(*a, **k):
        raise PermissionError('read-only config directory')
    monkeypatch.setattr(encryption.KeyEncryption, 'write_key_file', staticmethod(refuse))
    with app.app_context():
        db.session.add(EncryptionKey(version=0, state=envelope.DISABLED, kek_id='e' * 16,
                                     wrapped=None, created_at=utc_now()))
        db.session.commit()
        try:
            with pytest.raises(PermissionError):
                activate_new_master_key(exclusive=False)
            db.session.rollback()
            assert [(r.state, r.kek_id) for r in EncryptionKey.query.filter_by(version=0)] == [
                (envelope.DISABLED, 'e' * 16)]
        finally:
            db.session.rollback()
            EncryptionKey.query.filter_by(version=0).delete()
            db.session.commit()

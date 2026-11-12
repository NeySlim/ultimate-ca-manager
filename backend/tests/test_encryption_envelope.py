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
from models import db, SystemConfig

PEM = '-----BEGIN PRIVATE KEY-----\nenvelope\n-----END PRIVATE KEY-----\n'
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
    from security.encryption import encrypt_private_key, encrypt_text

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
        db.session.commit()
        ids = {type(r): r.id for r in rows}

    yield {'ids': ids, 'tag': tag}
    with app.app_context():
        for model, row_id in ids.items():
            row = db.session.get(model, row_id)
            if row is not None:
                db.session.delete(row)
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
        }


CLEAR = {'ssh': SSH_KEY, 'target': PEM, 'bind': 'bind-secret', 'config': PEM}


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
    assert [(v, s) for v, s, _, _ in _rows(app)] == [(0, 'disabled')]
    r = auth_client.post('/api/v2/system/security/enable-encryption')
    assert r.status_code == 200, r.data
    assert r.get_json()['data']['master_key'] is None
    assert _rows(app) == []
    stored = _stored(app, values)
    assert all(key_encryption.is_encrypted(stored[k]) for k in ('ssh', 'target', 'config'))
    assert _read(app, values) == CLEAR
    assert [k for k, _ in _commands(app)] == ['reload_encryption', 'reload_encryption']
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

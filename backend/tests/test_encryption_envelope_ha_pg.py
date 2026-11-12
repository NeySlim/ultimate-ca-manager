"""Envelope encryption in HA, on PostgreSQL: node A rotates the DEK, node B's applier loads it.

The key singleton is per process, so node B is this process with its memory put back to
what it held before the rotation; its CommandApplier then replays reload_encryption from
cluster_commands over a connection of its own, as on a second host.
"""
import base64
import secrets
import time
from datetime import timedelta

import pytest
from cryptography.fernet import Fernet

from config.settings import Config
from models import db, SystemConfig
from services import cluster_commands as cc
from tests import pg_app_harness
from utils.datetime_utils import utc_now

pytestmark = pytest.mark.skipif(not pg_app_harness.ENABLED,
                                reason='needs UCM_TEST_APP_PG_URL (HA runs on PostgreSQL)')


@pytest.fixture(autouse=True)
def _dek_refresh(dek_refresh_now):
    """No process here lags: rotations and disables wait for none."""


PREFIX = f'env-{secrets.token_hex(3)}-'
PEM = '-----BEGIN PRIVATE KEY-----\nha\n-----END PRIVATE KEY-----\n'


def wait_for(predicate, timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


@pytest.fixture
def ha(app, monkeypatch, encryption_enabled):
    from models import ClusterCommand, ClusterNode, EncryptionKey
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr(cc, 'GAP_GRACE_SECONDS', 0.3)

    def clean():
        with app.app_context():
            ClusterCommand.query.delete()
            EncryptionKey.query.delete()
            ClusterNode.query.filter(ClusterNode.node_id.like(PREFIX + '%')).delete(
                synchronize_session=False)
            SystemConfig.query.filter(SystemConfig.key.like(f'acme.account.{PREFIX}%')).delete(
                synchronize_session=False)
            db.session.commit()
    clean()
    made = []

    def make(name):
        applier = cc.CommandApplier(app, PREFIX + name, tick=0.05,
                                    started_at=utc_now() - timedelta(seconds=30))
        made.append(applier)
        return applier
    yield make
    for applier in made:
        applier.stop()
    clean()
    encryption_enabled.key_encryption.reload()


def _value(app, key):
    from security.encryption import decrypt_master_key_value
    with app.app_context():
        db.session.expire_all()
        return decrypt_master_key_value(SystemConfig.query.filter_by(key=key).one().value, 'text')


def test_rotation_on_a_reaches_b_through_the_command(app, auth_client, ha, encryption_enabled):
    from security.encryption import encrypt_text
    key = f'acme.account.{PREFIX}a.private_key'
    with app.app_context():
        db.session.add(SystemConfig(key=key, value=encrypt_text(PEM)))
        db.session.commit()
    r = auth_client.post('/api/v2/system/security/rotate-encryption-key')
    assert r.status_code == 200, r.data
    assert r.get_json()['data']['version'] == 2

    # Node B as it was before the rotation: DEK version 1 (the KEK) only
    key_encryption = encryption_enabled.key_encryption
    kek = base64.urlsafe_b64encode(key_encryption.kek_bytes_for_envelope())
    key_encryption._set_deks({1: Fernet(kek)}, 1)
    with pytest.raises(ValueError):
        _value(app, key)
    ha('b').start()
    assert wait_for(lambda: key_encryption.active_version == 2)
    assert _value(app, key) == PEM


def test_a_node_whose_kek_differs_from_a_live_peer_does_not_start(app, ha, encryption_enabled):
    from models import ClusterNode
    from services.scheduler_leader import cluster_utc_now
    from security.master_key_bootstrap import refuse_kek_mismatch_with_peers
    with app.app_context():
        now = cluster_utc_now()
        db.session.add(ClusterNode(node_id=PREFIX + 'peer', started_at=now, heartbeat_at=now,
                                   is_leader=True,
                                   kek_fingerprint=encryption_enabled.key_encryption.kek_fingerprint()))
        db.session.commit()
        refuse_kek_mismatch_with_peers()
        db.session.get(ClusterNode, PREFIX + 'peer').kek_fingerprint = 'e' * 16
        db.session.commit()
        with pytest.raises(SystemExit, match=PREFIX + 'peer'):
            refuse_kek_mismatch_with_peers()


def test_rotation_waits_for_a_live_node_then_resumes(app, auth_client, ha, monkeypatch):
    """A live node that has not applied the command holds the rewrite back (202), never the data."""
    from models import ClusterNode
    from security import dek_rotation
    from services.scheduler_leader import cluster_utc_now
    monkeypatch.setattr(dek_rotation, 'ACK_TIMEOUT_SECONDS', 0.5)
    with app.app_context():
        now = cluster_utc_now()
        db.session.add(ClusterNode(node_id=PREFIX + 'slow', started_at=now, heartbeat_at=now,
                                   is_leader=False, command_seen=0))
        db.session.commit()
    r = auth_client.post('/api/v2/system/security/rotate-encryption-key')
    assert r.status_code == 202, r.data
    assert r.get_json()['data']['waiting_for'] == [PREFIX + 'slow']
    b = ha('slow').start()
    assert wait_for(lambda: b.seen and b.seen >= 1)
    r = auth_client.post('/api/v2/system/security/rotate-encryption-key')
    assert r.status_code == 200, r.data

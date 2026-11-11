"""The Kerberos keytab lives in the database, under the master key; every node writes it.

The upload stores it and queues reload_keytab (HA) in one transaction; the start writes it,
and imports once the file of a single node from before it was stored.
"""
import io

import pytest

from config.settings import Config
from services import cluster_commands as cc
from services import shared_files
from services.kerberos import negotiate_auth

KEYTAB = b'\x05\x02keytab-of-the-cluster'


@pytest.fixture
def keytab_on(monkeypatch, tmp_path, app):
    """This node's keytab path; the stored row and the commands are dropped afterwards."""
    def point(name):
        path = tmp_path / name / 'kerberos.keytab'
        path.parent.mkdir(exist_ok=True)
        monkeypatch.setattr(negotiate_auth, 'KEYTAB_PATH', path)
        return path
    monkeypatch.setattr(negotiate_auth, 'inspect_keytab', lambda path=None: {
        'valid': True, 'principal': 'HTTP/ucm.example.test@EXAMPLE.TEST', 'error': None})
    yield point
    from models import ClusterCommand, db
    with app.app_context():
        shared_files.drop(shared_files.KERBEROS_KEYTAB)
        ClusterCommand.query.filter_by(kind=cc.RELOAD_KEYTAB).delete()
        db.session.commit()


def _upload(client, data=KEYTAB):
    return client.post('/api/v2/kerberos/keytab', data={'file': (io.BytesIO(data), 'ucm.keytab')},
                       content_type='multipart/form-data')


def _stored_content(app):
    from models import SharedFile, db
    with app.app_context():
        row = db.session.get(SharedFile, shared_files.KERBEROS_KEYTAB)
        return row.content if row else None


def test_upload_stores_the_keytab_under_the_master_key(app, auth_client, keytab_on, encryption_enabled):
    path = keytab_on('a')
    assert _upload(auth_client).status_code == 200
    assert path.read_bytes() == KEYTAB
    content = _stored_content(app)
    assert content and encryption_enabled.key_encryption.is_encrypted(content)
    with app.app_context():
        assert shared_files.get(shared_files.KERBEROS_KEYTAB) == KEYTAB


def test_upload_in_ha_queues_reload_keytab_with_no_payload(app, auth_client, keytab_on, monkeypatch):
    from models import ClusterCommand
    monkeypatch.setattr(Config, 'HA_MODE', True)
    keytab_on('a')
    assert _upload(auth_client).status_code == 200
    with app.app_context():
        commands = ClusterCommand.query.filter_by(kind=cc.RELOAD_KEYTAB).all()
        assert [c.payload for c in commands] == [None]


def test_a_failed_store_queues_nothing_and_writes_no_file(app, auth_client, keytab_on, monkeypatch):
    from models import ClusterCommand
    monkeypatch.setattr(Config, 'HA_MODE', True)
    path = keytab_on('a')

    def broken(*a, **k):
        raise RuntimeError('database gone')
    with monkeypatch.context() as patch:
        patch.setattr('utils.db_transaction.db.session.commit', broken)
        assert _upload(auth_client).status_code == 500
    assert not path.exists()
    with app.app_context():
        assert ClusterCommand.query.filter_by(kind=cc.RELOAD_KEYTAB).count() == 0
    assert _stored_content(app) is None


def test_reload_writes_the_stored_keytab_then_removes_it_once_dropped(app, keytab_on):
    from models import db
    path = keytab_on('b')
    with app.app_context():
        shared_files.put(shared_files.KERBEROS_KEYTAB, KEYTAB)
        db.session.commit()
        cc.HANDLERS[cc.RELOAD_KEYTAB](None)
        assert path.read_bytes() == KEYTAB
        assert path.stat().st_mode & 0o777 == 0o600
        assert negotiate_auth.write_stored_keytab() == 'unchanged'
        shared_files.drop(shared_files.KERBEROS_KEYTAB)
        db.session.commit()
        cc.HANDLERS[cc.RELOAD_KEYTAB](None)
    assert not path.exists()


def test_start_imports_the_file_of_a_single_node_once(app, keytab_on, monkeypatch):
    monkeypatch.setattr(Config, 'HA_MODE', False)
    path = keytab_on('single')
    path.write_bytes(KEYTAB)
    negotiate_auth.restore_keytab_at_start(app)
    with app.app_context():
        assert shared_files.get(shared_files.KERBEROS_KEYTAB) == KEYTAB
    path.write_bytes(b'changed by hand')
    negotiate_auth.restore_keytab_at_start(app)  # the database wins from now on
    assert path.read_bytes() == KEYTAB


def test_start_in_ha_never_shares_a_local_file(app, keytab_on, monkeypatch):
    monkeypatch.setattr(Config, 'HA_MODE', True)
    path = keytab_on('ha')
    path.write_bytes(KEYTAB)
    negotiate_auth.restore_keytab_at_start(app)
    assert _stored_content(app) is None
    assert path.read_bytes() == KEYTAB


def test_start_writes_the_stored_keytab_on_a_node_without_it(app, keytab_on):
    from models import db
    with app.app_context():
        shared_files.put(shared_files.KERBEROS_KEYTAB, KEYTAB)
        db.session.commit()
    path = keytab_on('new-node')
    negotiate_auth.restore_keytab_at_start(app)
    assert path.read_bytes() == KEYTAB


def test_start_without_the_master_key_keeps_the_file(app, keytab_on, encryption_enabled, monkeypatch):
    from models import db
    with app.app_context():
        shared_files.put(shared_files.KERBEROS_KEYTAB, KEYTAB)
        db.session.commit()
    path = keytab_on('keyless')
    path.write_bytes(b'previous keytab')
    # Within the test only: the fixture's own teardown reloads the key afterwards
    with monkeypatch.context() as patch:
        patch.setattr(encryption_enabled.key_encryption, '_enabled', False)
        negotiate_auth.restore_keytab_at_start(app)
    assert path.read_bytes() == b'previous keytab'

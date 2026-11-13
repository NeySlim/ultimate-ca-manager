"""The Kerberos keytab lives in the database, under the master key; every node writes it.

The upload stores it and queues reload_keytab (HA) in one transaction; the start writes it,
and imports once the file of a single node from before it was stored.
"""

import pytest

from config.settings import Config
from services import cluster_commands as cc
from services import shared_files
from services.kerberos import negotiate_auth
from tests.keytab_support import keytab
from tests.windows_profile_support import default_profile_id, upload_keytab
from tests.windows_profile_support import windows_profiles_restored  # noqa: F401

KEYTAB = keytab('HTTP/ucm.example.test@EXAMPLE.TEST')


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
    from models import ClusterCommand, db
    from tests.windows_profile_support import default_profile
    with app.app_context():
        # The default profile holds the realm of the keytab uploaded here, whatever SPN or
        # connector another file left to name one
        made = default_profile() is None
        profile = default_profile(create=True)
        realm, profile.realm = profile.realm, 'EXAMPLE.TEST'
        db.session.commit()
    yield point
    with app.app_context():
        shared_files.drop_file(shared_files.KERBEROS_KEYTAB)
        ClusterCommand.query.filter_by(kind=cc.RELOAD_KEYTAB).delete()
        profile = default_profile()
        if profile is not None and made:
            db.session.delete(profile)
        elif profile is not None:
            profile.keytab, profile.realm = None, realm
        db.session.commit()


def _upload(client, data=KEYTAB):
    return upload_keytab(client, data)


def _stored_content(app):
    from models import SharedFile, db
    with app.app_context():
        row = db.session.get(SharedFile, shared_files.KERBEROS_KEYTAB)
        return row.content if row else None


def test_upload_stores_the_keytab_under_the_master_key(app, auth_client, keytab_on, encryption_enabled):
    path = keytab_on('a')
    r = _upload(auth_client)
    assert r.status_code == 200, r.data
    assert path.read_bytes() == KEYTAB
    content = _stored_content(app)
    assert content and encryption_enabled.key_encryption.is_encrypted(content)
    with app.app_context():
        assert shared_files.read_file(shared_files.KERBEROS_KEYTAB) == KEYTAB


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
    profile_id = default_profile_id(auth_client)
    with monkeypatch.context() as patch:
        patch.setattr('utils.db_transaction.db.session.commit', broken)
        assert upload_keytab(auth_client, KEYTAB, profile_id).status_code == 500
    assert not path.exists()
    with app.app_context():
        assert ClusterCommand.query.filter_by(kind=cc.RELOAD_KEYTAB).count() == 0
    assert _stored_content(app) is None


def test_reload_writes_the_stored_keytab_then_removes_it_once_dropped(app, keytab_on):
    from models import db
    path = keytab_on('b')
    with app.app_context():
        shared_files.store_file(shared_files.KERBEROS_KEYTAB, KEYTAB)
        db.session.commit()
        cc.HANDLERS[cc.RELOAD_KEYTAB](None)
        assert path.read_bytes() == KEYTAB
        assert path.stat().st_mode & 0o777 == 0o600
        assert negotiate_auth.write_stored_keytab() == 'unchanged'
        shared_files.drop_file(shared_files.KERBEROS_KEYTAB)
        db.session.commit()
        cc.HANDLERS[cc.RELOAD_KEYTAB](None)
    assert not path.exists()


def test_start_imports_the_file_of_a_single_node_once(app, keytab_on, monkeypatch):
    monkeypatch.setattr(Config, 'HA_MODE', False)
    path = keytab_on('single')
    path.write_bytes(KEYTAB)
    negotiate_auth.restore_keytab_at_start(app)
    with app.app_context():
        assert shared_files.read_file(shared_files.KERBEROS_KEYTAB) == KEYTAB
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
        shared_files.store_file(shared_files.KERBEROS_KEYTAB, KEYTAB)
        db.session.commit()
    path = keytab_on('new-node')
    negotiate_auth.restore_keytab_at_start(app)
    assert path.read_bytes() == KEYTAB


def test_start_without_the_master_key_keeps_the_file(app, keytab_on, encryption_enabled, monkeypatch):
    from models import db
    with app.app_context():
        shared_files.store_file(shared_files.KERBEROS_KEYTAB, KEYTAB)
        db.session.commit()
    path = keytab_on('keyless')
    path.write_bytes(b'previous keytab')
    # Within the test only: the fixture's own teardown reloads the key afterwards
    with monkeypatch.context() as patch:
        patch.setattr(encryption_enabled.key_encryption, '_enabled', False)
        negotiate_auth.restore_keytab_at_start(app)
    assert path.read_bytes() == b'previous keytab'


def test_encrypt_all_and_decrypt_all_cover_the_stored_keytab(app, keytab_on, encryption_enabled, monkeypatch):
    import base64
    from models import SharedFile, db
    enc = encryption_enabled
    # Only this row: the shared database holds other tests' keys under other keys
    every = enc.master_key_values
    monkeypatch.setattr(enc, 'master_key_values', lambda: (
        v for v in every() if isinstance(v[1], SharedFile) and v[1].name == shared_files.KERBEROS_KEYTAB))
    plain = base64.b64encode(KEYTAB).decode()
    with app.app_context():
        db.session.add(SharedFile(name=shared_files.KERBEROS_KEYTAB, content=plain))
        db.session.commit()
        assert [label for label, *_ in enc.master_key_values()] == [f'SharedFile {shared_files.KERBEROS_KEYTAB}']
        assert enc.encrypt_all_keys(dry_run=False)[0] == 1
    content = _stored_content(app)
    assert enc.key_encryption.is_encrypted(content)
    with app.app_context():
        assert shared_files.read_file(shared_files.KERBEROS_KEYTAB) == KEYTAB
        assert enc.decrypt_all_keys(dry_run=False) == (1, 0, [])
    assert _stored_content(app) == plain


def test_an_unencrypted_stored_keytab_is_reported(app, keytab_on, encryption_enabled, monkeypatch):
    import base64
    from models import SharedFile, db
    enc = encryption_enabled
    with app.app_context():
        db.session.add(SharedFile(name=shared_files.KERBEROS_KEYTAB, content=base64.b64encode(KEYTAB).decode()))
        db.session.commit()
        monkeypatch.setattr(enc, 'MASTER_KEY_COLUMNS', tuple(
            c for c in enc.MASTER_KEY_COLUMNS if c[1] == 'SharedFile'))
        monkeypatch.setattr(enc, '_is_master_key_config', lambda key: False)
        assert enc.has_unencrypted_master_key_values()


def test_a_keytab_unreadable_without_the_master_key_says_so(app, keytab_on, encryption_enabled, monkeypatch):
    from models import db
    with app.app_context():
        shared_files.store_file(shared_files.KERBEROS_KEYTAB, KEYTAB)
        db.session.commit()
        with monkeypatch.context() as patch:
            patch.setattr(encryption_enabled.key_encryption, '_enabled', False)
            with pytest.raises(ValueError) as missing:
                shared_files.read_file(shared_files.KERBEROS_KEYTAB)
        assert 'private key' not in str(missing.value)
        assert 'master key' in str(missing.value) and 'kerberos.keytab' in str(missing.value)


def test_a_keytab_under_another_master_key_says_so(app, keytab_on, encryption_enabled):
    import base64
    from models import SharedFile, db
    with app.app_context():
        db.session.add(SharedFile(name=shared_files.KERBEROS_KEYTAB,
                                  content=base64.b64encode(b'ENC:not-a-fernet-token').decode()))
        db.session.commit()
        with pytest.raises(ValueError) as wrong:
            shared_files.read_file(shared_files.KERBEROS_KEYTAB)
    assert 'private key' not in str(wrong.value)
    assert 'different KEY_ENCRYPTION_KEY' in str(wrong.value)

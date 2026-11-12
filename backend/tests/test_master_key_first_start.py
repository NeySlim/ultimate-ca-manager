"""An installation without a master key creates one at its first start and
encrypts the private keys and secrets still stored without it."""
import base64
import json
import os
import stat

import pytest
from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization

from tests.conftest import _drop_unreadable_key_material
from tests.fresh_app import fresh_app, fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures('function')

NAMED_VOLUME = ('1200 1100 254:1 /var/lib/docker/volumes/ucm_ucm-config/_data /etc/ucm '
                'rw,relatime master:1 - ext4 /dev/vda1 rw\n')
ANONYMOUS_VOLUME = ('1200 1100 254:1 /var/lib/docker/volumes/'
                    + 'a3' * 32 + '/_data /etc/ucm rw,relatime - ext4 /dev/vda1 rw\n')
ROOT_ONLY = '1100 1 0:52 / / rw,relatime - overlay overlay rw,lowerdir=/x\n'


@pytest.fixture
def no_key(monkeypatch, tmp_path, app):
    """An installation as a package leaves it: no master.key, no KEY_ENCRYPTION_KEY."""
    from security import encryption as enc
    from security import master_key_bootstrap as boot

    with monkeypatch.context() as patch:
        patch.setattr(enc, 'MASTER_KEY_PATH', tmp_path / 'etc' / 'master.key')
        for var in ('KEY_ENCRYPTION_KEY', 'KEY_ENCRYPTION_KEY_FILE', 'UCM_REQUIRE_KEY_ENCRYPTION'):
            patch.delenv(var, raising=False)
        patch.setattr(boot, 'in_container', lambda: False)
        patch.setitem(app.config, 'AUTO_MASTER_KEY', True)
        enc.key_encryption.start_over()
        assert not enc.key_encryption.is_enabled
        yield enc
    enc.key_encryption.start_over()
    _drop_unreadable_key_material(app)


def _ca_prv(app, ca_id):
    from models import CA
    with app.app_context():
        return CA.query.get(ca_id).prv


def test_first_start_creates_the_key_and_encrypts_existing_keys(app, create_ca, no_key):
    from security.master_key_bootstrap import check_master_key_at_start

    ca = create_ca()
    assert not no_key.key_encryption.is_encrypted(_ca_prv(app, ca['id']))

    with app.app_context():
        check_master_key_at_start(app)
        unencrypted = no_key.count_master_key_values()[1]

    path = no_key.MASTER_KEY_PATH
    assert path.is_file()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert no_key.key_encryption.is_enabled and no_key.key_encryption.key_source == 'file'
    assert no_key.key_encryption.is_encrypted(_ca_prv(app, ca['id']))
    assert unencrypted == 0
    assert app.config['SAFE_MODE'] is False


def test_restart_reads_the_created_key_back(app, auth_client, create_ca, no_key):
    from security.master_key_bootstrap import check_master_key_at_start

    ca = create_ca()
    with app.app_context():
        check_master_key_at_start(app)
    created = no_key.MASTER_KEY_PATH.read_bytes()

    # A new process: the singleton reads the file again, the start check runs again
    no_key.key_encryption.reload()
    with app.app_context():
        check_master_key_at_start(app)
    assert no_key.MASTER_KEY_PATH.read_bytes() == created
    assert app.config['SAFE_MODE'] is False

    pem = base64.b64decode(no_key.decrypt_private_key(_ca_prv(app, ca['id'])))
    key = serialization.load_pem_private_key(pem, password=None)
    from models import CA
    with app.app_context():
        cert = x509.load_pem_x509_certificate(base64.b64decode(CA.query.get(ca['id']).crt))
    assert key.public_key().public_numbers() == cert.public_key().public_numbers()

    r = auth_client.post('/api/v2/certificates', data=json.dumps({
        'cn': 'after-restart.example.com', 'ca_id': ca['id'], 'validity_days': 30,
    }), content_type='application/json')
    assert r.status_code in (200, 201), r.data


def test_key_from_environment_is_left_alone(app, create_ca, no_key, monkeypatch):
    from security.master_key_bootstrap import check_master_key_at_start

    monkeypatch.setenv('KEY_ENCRYPTION_KEY', Fernet.generate_key().decode('ascii'))
    no_key.key_encryption.reload()
    ca = create_ca()
    before = _ca_prv(app, ca['id'])

    with app.app_context():
        check_master_key_at_start(app)

    assert not no_key.MASTER_KEY_PATH.exists()
    assert no_key.key_encryption.key_source == 'env'
    assert _ca_prv(app, ca['id']) == before


def test_encrypted_rows_without_a_key_get_no_new_key(app, create_ca, no_key, monkeypatch):
    """A missing key with encrypted rows is a lost key: safe mode, never a replacement."""
    from security.master_key_bootstrap import check_master_key_at_start

    with monkeypatch.context() as patch:
        patch.setenv('KEY_ENCRYPTION_KEY', Fernet.generate_key().decode('ascii'))
        no_key.key_encryption.reload()
        ca = create_ca()
    no_key.key_encryption.reload()
    assert not no_key.key_encryption.is_enabled

    with app.app_context():
        check_master_key_at_start(app)

    assert not no_key.MASTER_KEY_PATH.exists()
    assert app.config['SAFE_MODE'] is True
    app.config['SAFE_MODE'] = False
    assert no_key.key_encryption.is_encrypted(_ca_prv(app, ca['id']))


def test_unreadable_key_file_is_never_replaced(app, create_ca, no_key):
    from security.master_key_bootstrap import check_master_key_at_start

    ca = create_ca()
    path = no_key.MASTER_KEY_PATH
    path.parent.mkdir(parents=True)
    path.write_text('not a fernet key\n')
    no_key.key_encryption.reload()

    with app.app_context():
        check_master_key_at_start(app)

    assert path.read_text() == 'not a fernet key\n'
    assert not no_key.key_encryption.is_enabled
    assert not no_key.key_encryption.is_encrypted(_ca_prv(app, ca['id']))


def test_opt_out_creates_no_key(app, create_ca, no_key):
    from security.master_key_bootstrap import check_master_key_at_start

    app.config['AUTO_MASTER_KEY'] = False
    create_ca()
    with app.app_context():
        check_master_key_at_start(app)
    assert not no_key.MASTER_KEY_PATH.exists()


def test_container_without_a_volume_of_its_own_gets_no_key(app, create_ca, no_key, monkeypatch):
    """A key in an anonymous volume would be lost when the container is recreated."""
    from security import master_key_bootstrap as boot

    monkeypatch.setattr(boot, 'in_container', lambda: True)
    monkeypatch.setattr(boot, '_read_mountinfo', lambda: ANONYMOUS_VOLUME)
    ca = create_ca()
    with app.app_context():
        boot.check_master_key_at_start(app)
    assert not no_key.MASTER_KEY_PATH.exists()
    assert not no_key.key_encryption.is_encrypted(_ca_prv(app, ca['id']))


@pytest.mark.parametrize('mountinfo, persistent', [
    (NAMED_VOLUME, True),
    ('1200 1100 8:1 /srv/ucm/config /etc/ucm rw - ext4 /dev/sda1 rw\n', True),
    ('1200 1100 0:61 /var/lib/kubelet/pods/u/volumes/kubernetes.io~csi/pvc-1/mount '
     '/etc/ucm rw - ext4 /dev/rbd0 rw\n', True),
    (ANONYMOUS_VOLUME, False),
    ('1200 1100 8:1 /var/lib/kubelet/pods/u/volumes/kubernetes.io~empty-dir/etc '
     '/etc/ucm rw - ext4 /dev/sda1 rw\n', False),
    ('1200 1100 0:70 / /etc/ucm rw - tmpfs tmpfs rw\n', False),
    (ROOT_ONLY, False),
    # The last mount on a path is the one in use
    (NAMED_VOLUME + ANONYMOUS_VOLUME, False),
    (ROOT_ONLY + '1300 1100 8:1 /srv/ucm /etc rw - ext4 /dev/sda1 rw\n', False),
])
def test_container_key_directory_persistence(mountinfo, persistent):
    from security.master_key_bootstrap import container_dir_is_persistent

    assert container_dir_is_persistent('/etc/ucm', ROOT_ONLY + mountinfo)[0] is persistent


def test_create_app_creates_the_key(monkeypatch, tmp_path):
    from config.settings import TestingConfig
    from security import encryption as enc
    from security import master_key_bootstrap as boot

    with monkeypatch.context() as patch:
        patch.setattr(enc, 'MASTER_KEY_PATH', tmp_path / 'etc' / 'master.key')
        for var in ('KEY_ENCRYPTION_KEY', 'KEY_ENCRYPTION_KEY_FILE', 'UCM_REQUIRE_KEY_ENCRYPTION'):
            patch.delenv(var, raising=False)
        patch.setattr(boot, 'in_container', lambda: False)
        patch.setattr(TestingConfig, 'AUTO_MASTER_KEY', True, raising=False)
        enc.key_encryption.reload()
        try:
            with fresh_app():
                assert enc.MASTER_KEY_PATH.is_file()
                assert enc.key_encryption.is_enabled
        finally:
            patch.undo()
            enc.key_encryption.reload()


def test_testing_config_creates_no_key():
    from config.settings import TestingConfig

    assert TestingConfig.AUTO_MASTER_KEY is False


def test_dashboard_warns_while_no_key_is_loaded(app, auth_client, no_key):
    r = auth_client.get('/api/v2/dashboard/system-status')
    assert r.status_code == 200
    assert json.loads(r.data)['data']['key_encryption']['status'] == 'warning'

    with app.app_context():
        from security.master_key_bootstrap import check_master_key_at_start
        check_master_key_at_start(app)
    r = auth_client.get('/api/v2/dashboard/system-status')
    assert json.loads(r.data)['data']['key_encryption']['status'] == 'online'


def test_enable_encryption_keeps_a_key_that_already_encrypted_values(
        app, auth_client, create_ca, no_key, monkeypatch):
    """A failure after the keys were encrypted must not remove the only key that reads them."""
    from security import master_key_bootstrap as boot

    def fail(auto):
        raise RuntimeError('commit failed')

    monkeypatch.setattr(boot, 'record_operator_choice', fail)
    ca = create_ca()
    r = auth_client.post('/api/v2/system/security/enable-encryption')
    assert r.status_code == 500
    assert no_key.MASTER_KEY_PATH.is_file()
    prv = _ca_prv(app, ca['id'])
    assert no_key.key_encryption.is_encrypted(prv)
    serialization.load_pem_private_key(base64.b64decode(no_key.decrypt_private_key(prv)), None)


def test_exclusive_write_never_replaces_a_key(no_key):
    """Two processes starting together: the second keeps the first one's key."""
    path = no_key.MASTER_KEY_PATH
    no_key.KeyEncryption.write_key_file('first', exclusive=True)
    with pytest.raises(FileExistsError):
        no_key.KeyEncryption.write_key_file('second', exclusive=True)
    assert path.read_text() == 'first\n'
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert [p.name for p in path.parent.iterdir()] == ['master.key']


# A restart after the grace (master.key and DEKs gone): the disable ends it at once
@pytest.mark.usefixtures('dek_retire_at_once')
def test_disabled_encryption_stays_disabled_after_restart(app, auth_client, create_ca, no_key):
    """Disabling from the UI leaves nothing encrypted: the next start must not take it for a new installation."""
    from security.master_key_bootstrap import bootstrap_master_key, check_master_key_at_start

    ca = create_ca()
    with app.app_context():
        check_master_key_at_start(app)
    assert no_key.key_encryption.is_enabled
    r = auth_client.post('/api/v2/system/security/disable-encryption')
    assert r.status_code == 200, r.data
    assert not no_key.MASTER_KEY_PATH.exists()
    from models import SystemConfig
    from security.master_key_bootstrap import OPT_OUT_KEY
    with app.app_context():
        assert SystemConfig.query.filter_by(key=OPT_OUT_KEY).first().value == 'false'

    no_key.key_encryption.reload()
    with app.app_context():
        assert bootstrap_master_key(app) == 'disabled'
        check_master_key_at_start(app)
    assert not no_key.MASTER_KEY_PATH.exists()
    assert not no_key.key_encryption.is_enabled
    assert not no_key.key_encryption.is_encrypted(_ca_prv(app, ca['id']))

    # Enabling again from the UI lifts the choice
    r = auth_client.post('/api/v2/system/security/enable-encryption')
    assert r.status_code == 200, r.data
    from security.master_key_bootstrap import auto_master_key_allowed
    with app.app_context():
        assert auto_master_key_allowed(app)


def test_key_written_by_another_process_is_loaded(app, no_key):
    """The key can appear between the start reload and the bootstrap: load it, never run without it."""
    from security.master_key_bootstrap import bootstrap_master_key

    no_key.KeyEncryption.write_key_file(no_key.KeyEncryption.generate_key(), exclusive=True)
    assert not no_key.key_encryption.is_enabled
    with app.app_context():
        assert bootstrap_master_key(app) == 'present'
    assert no_key.key_encryption.is_enabled


def _without_hard_links(monkeypatch):
    def no_link(*_args):
        raise PermissionError(1, 'Operation not permitted')
    monkeypatch.setattr(os, 'link', no_link)


def test_exclusive_write_without_hard_links_is_synced_and_owned(no_key, monkeypatch):
    import pwd
    from types import SimpleNamespace

    path = no_key.MASTER_KEY_PATH
    _without_hard_links(monkeypatch)
    synced, owned = [], []
    real_fsync = os.fsync
    monkeypatch.setattr(os, 'fsync', lambda fd: (synced.append(os.fstat(fd).st_ino), real_fsync(fd)))
    monkeypatch.setattr(os, 'fchown', lambda fd, uid, gid: owned.append(os.fstat(fd).st_ino))
    monkeypatch.setattr(pwd, 'getpwnam',
                        lambda name: SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid()))

    no_key.KeyEncryption.write_key_file('only', exclusive=True)
    assert path.read_text() == 'only\n'
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.stat().st_ino in synced and path.stat().st_ino in owned
    assert [p.name for p in path.parent.iterdir()] == ['master.key']


def test_failed_exclusive_write_without_hard_links_leaves_no_key_file(no_key, monkeypatch):
    path = no_key.MASTER_KEY_PATH
    _without_hard_links(monkeypatch)
    real_fsync = os.fsync

    def fsync(fd):
        if path.exists() and os.fstat(fd).st_ino == path.stat().st_ino:
            raise OSError(28, 'No space left on device')
        real_fsync(fd)

    monkeypatch.setattr(os, 'fsync', fsync)
    with pytest.raises(OSError):
        no_key.KeyEncryption.write_key_file('lost', exclusive=True)
    assert list(path.parent.iterdir()) == []


def test_keyed_audit_chain_without_a_key_gets_no_new_key(app, no_key, monkeypatch):
    """Audit entries sealed under a master key would no longer verify under a new one."""
    from security.master_key_bootstrap import bootstrap_master_key
    from services.audit_service import AuditService

    with monkeypatch.context() as patch:
        patch.setenv('KEY_ENCRYPTION_KEY', Fernet.generate_key().decode('ascii'))
        no_key.key_encryption.reload()
        with app.app_context():
            AuditService.log_action(action='test_keyed', resource_type='system',
                                    resource_name='x', details='sealed', success=True)
    no_key.key_encryption.reload()
    from services.audit.chain import keyring_path
    keyring_path().unlink(missing_ok=True)

    with app.app_context():
        assert not no_key.has_encrypted_keys_in_db()
        assert bootstrap_master_key(app) == 'lost'
    assert not no_key.MASTER_KEY_PATH.exists()


def test_audit_keyring_without_a_key_gets_no_new_key(app, no_key):
    from security.master_key_bootstrap import bootstrap_master_key
    from services.audit.chain import keyring_path

    keyring_path().parent.mkdir(parents=True, exist_ok=True)
    keyring_path().write_text('{"current": "abc", "history": ["abc"]}')
    with app.app_context():
        assert bootstrap_master_key(app) == 'lost'
    assert not no_key.MASTER_KEY_PATH.exists()


def test_first_start_logs_no_disabled_error_before_creating_the_key(app, no_key, caplog):
    import logging
    from security.master_key_bootstrap import check_master_key_at_start

    caplog.set_level(logging.INFO)
    no_key.key_encryption.reload()
    with app.app_context():
        check_master_key_at_start(app)
    assert no_key.key_encryption.is_enabled
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR], caplog.text


def test_opt_out_still_logs_the_disabled_error(app, no_key, caplog):
    import logging
    from security.master_key_bootstrap import check_master_key_at_start

    app.config['AUTO_MASTER_KEY'] = False
    caplog.set_level(logging.INFO)
    with app.app_context():
        check_master_key_at_start(app)
    assert any(r.levelno >= logging.ERROR and 'UNENCRYPTED' in r.getMessage()
               for r in caplog.records), caplog.text


def test_dashboard_key_status_is_for_system_admins_only(app, create_user, no_key):
    create_user(username='kviewer', role='viewer')
    client = app.test_client()
    r = client.post('/api/v2/auth/login', data=json.dumps(
        {'username': 'kviewer', 'password': 'TestPass123!'}), content_type='application/json')
    assert r.status_code == 200, r.data
    r = client.get('/api/v2/dashboard/system-status')
    assert r.status_code == 200
    assert 'key_encryption' not in json.loads(r.data)['data']


def test_enable_encryption_writes_the_key_file_0600(app, auth_client, no_key):
    r = auth_client.post('/api/v2/system/security/enable-encryption')
    assert r.status_code == 200, r.data
    assert stat.S_IMODE(no_key.MASTER_KEY_PATH.stat().st_mode) == 0o600


def test_replacing_write_keeps_the_key_file_0600(no_key):
    path = no_key.MASTER_KEY_PATH
    path.parent.mkdir(parents=True)
    path.write_text('old\n')
    os.chmod(path, 0o644)
    no_key.KeyEncryption.write_key_file('new')
    assert path.read_text() == 'new\n'
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_encryption_disabled_before_upgrade_stays_disabled(app, create_ca, no_key, monkeypatch, tmp_path):
    """A version without the opt-out row recorded the choice in the audit log only."""
    from config.settings import Config
    from models import SystemConfig
    from security.master_key_bootstrap import OPT_OUT_KEY, bootstrap_master_key
    from services.audit_service import AuditService
    from services.file_regen_service import regenerate_all_files

    monkeypatch.setattr(Config, 'PRIVATE_DIR', tmp_path / 'private')
    ca = create_ca()
    with app.app_context():
        AuditService.log_action(action='encryption_enabled', resource_type='system',
                                resource_name='Private Key Encryption', details='on', success=True)
        AuditService.log_action(action='encryption_disabled', resource_type='system',
                                resource_name='Private Key Encryption', details='off', success=True)
        regenerate_all_files()
        mirrors = sorted(p.name for p in Config.PRIVATE_DIR.glob('*.key'))
        assert mirrors
        assert bootstrap_master_key(app) == 'disabled'
        assert SystemConfig.query.filter_by(key=OPT_OUT_KEY).first().value == 'false'
    assert not no_key.MASTER_KEY_PATH.exists()
    assert sorted(p.name for p in Config.PRIVATE_DIR.glob('*.key')) == mirrors
    assert not no_key.key_encryption.is_encrypted(_ca_prv(app, ca['id']))


def test_encryption_enabled_after_a_disable_still_allows_the_key(app, no_key):
    from security.master_key_bootstrap import auto_master_key_allowed
    from services.audit_service import AuditService

    with app.app_context():
        for action in ('encryption_disabled', 'encryption_enabled'):
            AuditService.log_action(action=action, resource_type='system',
                                    resource_name='Private Key Encryption', details='', success=True)
        assert auto_master_key_allowed(app)


def test_interrupted_first_encryption_resumes_at_next_start(app, create_ca, no_key, monkeypatch, caplog):
    import logging
    from security import encryption as enc
    from security.master_key_bootstrap import bootstrap_master_key

    ca = create_ca()
    real = enc.encrypt_all_keys
    monkeypatch.setattr(enc, 'encrypt_all_keys', lambda dry_run=True: (0, 0, ['CA x: boom']))
    caplog.set_level(logging.WARNING)
    with app.app_context():
        assert bootstrap_master_key(app) == 'generated'
    assert any(r.name == 'security.master_key_bootstrap' and r.levelno >= logging.ERROR
               and '1 value' in r.getMessage() for r in caplog.records), caplog.text
    monkeypatch.setattr(enc, 'encrypt_all_keys', real)

    no_key.key_encryption.reload()
    with app.app_context():
        assert no_key.count_master_key_values()[1] > 0
        assert bootstrap_master_key(app) == 'present'
        assert no_key.count_master_key_values()[1] == 0
    assert no_key.key_encryption.is_encrypted(_ca_prv(app, ca['id']))


def test_bootstrap_never_overwrites_a_key_another_process_wrote(app, no_key, monkeypatch):
    """The guard runs before the write: a key written in between must survive."""
    from security import master_key_bootstrap as boot

    other = no_key.KeyEncryption.generate_key()

    def written_meanwhile():
        no_key.KeyEncryption.write_key_file(other, exclusive=True)
        return False

    monkeypatch.setattr(boot, '_master_key_was_used', written_meanwhile)
    with app.app_context():
        assert boot.bootstrap_master_key(app) == 'present'
    assert no_key.MASTER_KEY_PATH.read_text().strip() == other


def test_a_key_that_does_not_read_the_database_enters_safe_mode(app, create_ca, no_key, monkeypatch):
    """A database copied onto a new installation keeps the key it was encrypted under:
    the key created there must neither run UCM nor encrypt what is left in the clear."""
    from models import db, SystemConfig
    from security.master_key_bootstrap import check_master_key_at_start

    with app.app_context():
        check_master_key_at_start(app)
    path = no_key.MASTER_KEY_PATH
    created = path.read_bytes()

    old = Fernet.generate_key().decode('ascii')
    aside = path.with_name('aside')
    path.rename(aside)
    with monkeypatch.context() as patch:
        patch.setenv('KEY_ENCRYPTION_KEY', old)
        no_key.key_encryption.reload()
        ca = create_ca()
    aside.rename(path)
    with app.app_context():
        db.session.add(SystemConfig(key='acme.proxy.eab_hmac_key', value='hmac-in-clear'))
        db.session.commit()

    no_key.key_encryption.reload()
    assert no_key.key_encryption.is_enabled
    try:
        with app.app_context():
            check_master_key_at_start(app)
            secret = SystemConfig.query.filter_by(key='acme.proxy.eab_hmac_key').first().value
        assert app.config['SAFE_MODE'] is True
        health = json.loads(app.test_client().get('/api/health').data)
        assert health['safe_mode_reason'] == 'encryption_key_mismatch'
    finally:
        app.config['SAFE_MODE'] = False
        app.config.pop('SAFE_MODE_REASON', None)
    assert secret == 'hmac-in-clear'
    assert not no_key.key_encryption.is_enabled
    assert path.read_bytes() == created
    Fernet(old.encode()).decrypt(base64.b64decode(_ca_prv(app, ca['id']))[len(b'ENC:'):])


def test_enable_encryption_refuses_a_container_without_a_volume_of_its_own(
        app, auth_client, no_key, monkeypatch):
    from security import master_key_bootstrap as boot

    monkeypatch.setattr(boot, 'in_container', lambda: True)
    monkeypatch.setattr(boot, '_read_mountinfo', lambda: ANONYMOUS_VOLUME)
    r = auth_client.post('/api/v2/system/security/enable-encryption')
    assert r.status_code == 409, r.data
    assert 'lost with the container' in json.loads(r.data)['message']
    assert not no_key.MASTER_KEY_PATH.exists()
    assert not no_key.key_encryption.is_enabled


def test_the_encryption_choice_stays_with_its_installation(app, no_key, monkeypatch):
    """A backup taken where encryption was disabled must not disable it where it is restored."""
    from types import SimpleNamespace
    from models import db, SystemConfig
    from security.master_key_bootstrap import OPT_OUT_KEY, record_operator_choice
    from services.backup import BackupService, export_core
    from services.backup.restore.settings import restore_encrypted_settings

    with app.app_context():
        record_operator_choice(auto=False)
        db.session.commit()
        row = SystemConfig.query.filter_by(key=OPT_OUT_KEY).first()
        monkeypatch.setattr(export_core, 'SystemConfig', SimpleNamespace(
            query=SimpleNamespace(all=lambda: [row])))
        exported = BackupService()._export_configuration(True)
        monkeypatch.undo()
        assert OPT_OUT_KEY not in exported['settings']

        db.session.delete(row)
        db.session.commit()
        configuration = {'settings': {OPT_OUT_KEY: 'false'}, 'encrypted_settings': [OPT_OUT_KEY]}
        BackupService()._restore_settings({'configuration': configuration}, {'settings': 0})
        restore_encrypted_settings(configuration, configuration['encrypted_settings'])
        db.session.commit()
        assert SystemConfig.query.filter_by(key=OPT_OUT_KEY).first() is None


def test_enable_encryption_reports_success_when_only_the_mirror_purge_fails(
        app, auth_client, create_ca, no_key, monkeypatch):
    """The key encrypts the database: the operator must get it back to save it."""
    import services.file_regen_service as regen
    from models import AuditLog, SystemConfig
    from security.master_key_bootstrap import OPT_OUT_KEY, record_operator_choice

    def fail():
        raise RuntimeError('purge failed')

    with app.app_context():
        record_operator_choice(auto=False)
        from models import db
        db.session.commit()
    monkeypatch.setattr(regen, 'purge_private_key_files', fail)
    create_ca()
    r = auth_client.post('/api/v2/system/security/enable-encryption')
    assert r.status_code == 200, r.data
    data = json.loads(r.data)['data']
    assert data['master_key'] == no_key.MASTER_KEY_PATH.read_text().strip()
    with app.app_context():
        assert SystemConfig.query.filter_by(key=OPT_OUT_KEY).first().value == 'true'
        assert AuditLog.query.filter_by(action='encryption_enabled').count() == 1


def test_audit_entries_restored_later_do_not_decide_the_key(app, no_key):
    """The audit log decides once, at the first start of this version; a restore
    appends another installation's entries afterwards."""
    from models import SystemConfig
    from security.master_key_bootstrap import OPT_OUT_KEY, auto_master_key_allowed, bootstrap_master_key
    from services.audit_service import AuditService

    with app.app_context():
        assert auto_master_key_allowed(app)
        assert SystemConfig.query.filter_by(key=OPT_OUT_KEY).first().value == 'true'
        AuditService.log_action(action='encryption_disabled', resource_type='system',
                                resource_name='Private Key Encryption', details='restored',
                                success=True)
        assert bootstrap_master_key(app) == 'generated'
    assert no_key.MASTER_KEY_PATH.exists()


def test_start_with_everything_encrypted_loads_no_stored_value(app, create_ca, no_key, monkeypatch, caplog):
    """The leftover check runs at every start: it must not read every key row."""
    import logging
    from security import encryption as enc
    from security import master_key_bootstrap as boot

    create_ca()
    with app.app_context():
        assert boot.bootstrap_master_key(app) == 'generated'

    def loads_every_row():
        raise AssertionError('every stored value loaded')

    calls = []
    caplog.set_level(logging.WARNING)
    with monkeypatch.context() as patch, app.app_context():
        patch.setattr(enc, 'master_key_values', loads_every_row)
        patch.setattr(enc, 'encrypt_all_keys', lambda dry_run=True: calls.append(1) or (0, 0, []))
        boot._resume_encryption()
    assert not calls
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR], caplog.text


def test_leftover_check_finds_each_unencrypted_value(app, create_ca, no_key):
    from models import db, CA, SystemConfig
    from security import encryption as enc
    from security.master_key_bootstrap import bootstrap_master_key

    ca = create_ca()
    with app.app_context():
        assert bootstrap_master_key(app) == 'generated'
        assert not enc.has_unencrypted_master_key_values()
        row = CA.query.get(ca['id'])
        encrypted = row.prv
        # Same letters as the ENC: prefix, another case: SQLite's LIKE would take it for one
        row.prv = encrypted[:5].lower() + encrypted[5:]
        db.session.commit()
        assert enc.has_unencrypted_master_key_values()
        row.prv = encrypted
        db.session.add(SystemConfig(key='acme.proxy.eab_hmac_key', value='plain'))
        db.session.commit()
        assert enc.has_unencrypted_master_key_values()

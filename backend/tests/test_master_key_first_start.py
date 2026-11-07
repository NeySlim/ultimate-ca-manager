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
        enc.key_encryption.reload()
        assert not enc.key_encryption.is_enabled
        yield enc
    enc.key_encryption.reload()
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
    import services.file_regen_service as regen

    def fail():
        raise RuntimeError('purge failed')

    monkeypatch.setattr(regen, 'purge_private_key_files', fail)
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

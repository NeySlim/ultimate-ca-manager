"""Fields of an archive a restore reads itself: refused by name, before or without any write.

A private key that does not decrypt, an encrypted key whose parts are empty or of the wrong
length, a key field the export never writes, a NUL byte in a text: each is an answer of the
archive (400, nothing written), on SQLite and PostgreSQL alike, never a driver error (500).
"""
import io
import os

import pytest

from models import db
from services.backup.errors import BackupSchemaError
from services.backup.restore import RestoreValidationError

from tests.fresh_app import fresh_app_fixtures
from tests.test_backup_hostile_corpus import _forged, _service
from tests.test_restore_sso_one_per_type import target  # noqa: F401  (SQLite and PostgreSQL)

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

PASSWORD = 'Correct-Horse-Battery-9'
RESTORE_URL = '/api/v2/system/restore'
MODES = ['merge', 'replace']

# Well formed (a 32-byte salt, a 12-byte nonce) and encrypted under a key nobody here has
UNREADABLE_KEY = {'algorithm': 'AES-256-GCM', 'salt': '11' * 32, 'nonce': '22' * 12,
                  'ciphertext': '33' * 48}
ROWS = {
    'certificate_authorities': {'refid': 'af-ca', 'descr': 'af-ca'},
    'certificates': {'refid': 'af-cert', 'descr': 'af-cert'},
    'ssh_cas': {'refid': 'af-ssh-ca', 'descr': 'af-ssh-ca', 'ca_type': 'user',
                'key_type': 'ed25519', 'fingerprint': 'SHA256:af',
                'public_key': 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIArchiveFields'},
}


def _counts():
    from models import CA, Certificate
    from models.deploy import DeployTarget
    from models.ssh import SSHCertificateAuthority
    return {'cas': CA.query.count(), 'certificates': Certificate.query.count(),
            'ssh_cas': SSHCertificateAuthority.query.count(),
            'deploy_targets': DeployTarget.query.count()}


def _refused(payload, mode, error=(BackupSchemaError, RestoreValidationError)):
    before = _counts()
    with pytest.raises(error) as refusal:
        _service()._restore_payload(payload, os.urandom(32), mode)
    db.session.rollback()
    assert _counts() == before
    return str(refusal.value)


# --- A key that does not decrypt -----------------------------------------------------------------

@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('section', ['certificate_authorities', 'certificates'])
def test_a_key_that_does_not_decrypt_is_an_archive_error(target, section, mode):
    payload = {section: [dict(ROWS[section], private_key_pem_encrypted=UNREADABLE_KEY)]}
    message = _refused(payload, mode, BackupSchemaError)
    assert ROWS[section]['refid'] in message and 'could not be decrypted' in message, message
    assert 'Nothing has been changed' in message
    assert 'InvalidTag' not in message


@pytest.mark.parametrize('section', ['certificate_authorities', 'certificates'])
def test_the_route_answers_400_for_a_key_that_does_not_decrypt(app, auth_client, section):
    from models import CA, Certificate
    with app.app_context():
        blob = _forged(['deploy_targets'], **{section: [
            dict(ROWS[section], private_key_pem_encrypted=UNREADABLE_KEY)]})
        before = _counts()
    response = auth_client.post(RESTORE_URL, content_type='multipart/form-data', data={
        'password': PASSWORD, 'file': (io.BytesIO(blob), 'fields.ucmbkp')})
    body = response.get_json(silent=True) or {}
    message = str(body.get('message') or body.get('error') or '')
    assert response.status_code == 400, response.data
    assert ROWS[section]['refid'] in message and 'could not be decrypted' in message, message
    with app.app_context():
        assert _counts() == before
        assert CA.query.filter_by(refid='af-ca').count() == 0
        assert Certificate.query.filter_by(refid='af-cert').count() == 0

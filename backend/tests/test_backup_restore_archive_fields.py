"""Fields of an archive a restore reads itself: refused by name, before or without any write.

A private key that does not decrypt, an encrypted key whose parts are empty or of the wrong
length, a key field the export never writes: each is an answer of the archive (400, nothing
written), on SQLite and PostgreSQL alike, never a driver error (500).
"""
import io
import os

import pytest

from models import db
from services.backup import manifest
from services.backup.errors import BackupSchemaError
from services.backup.restore import RestoreValidationError

from tests.fresh_app import fresh_app_fixtures
from tests.restore_support import post_to_the_end
from tests.test_backup_cross_installation import (_authority, _leaf, _stored_certificate,
                                                  _stored_key)
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
    response = post_to_the_end(auth_client, RESTORE_URL, content_type='multipart/form-data', data={
        'password': PASSWORD, 'file': (io.BytesIO(blob), 'fields.ucmbkp')})
    body = response.get_json(silent=True) or {}
    message = str(body.get('message') or body.get('error') or '')
    assert response.status_code == 400, response.data
    assert ROWS[section]['refid'] in message and 'could not be decrypted' in message, message
    with app.app_context():
        assert _counts() == before
        assert CA.query.filter_by(refid='af-ca').count() == 0
        assert Certificate.query.filter_by(refid='af-cert').count() == 0


# --- The parts of an encrypted key ---------------------------------------------------------------

BAD_PARTS = {
    'empty parts': {'salt': '', 'nonce': '', 'ciphertext': ''},
    'empty ciphertext': {**UNREADABLE_KEY, 'ciphertext': ''},
    'short salt': {**UNREADABLE_KEY, 'salt': '11' * 16},
    'long nonce': {**UNREADABLE_KEY, 'nonce': '22' * 16},
    'short nonce': {**UNREADABLE_KEY, 'nonce': '22' * 8},
}


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('parts', sorted(BAD_PARTS))
@pytest.mark.parametrize('section', sorted(ROWS))
def test_key_parts_the_export_never_writes_are_refused_before_any_write(target, section, parts,
                                                                        mode):
    payload = {section: [dict(ROWS[section], private_key_pem_encrypted=BAD_PARTS[parts])]}
    message = _refused(payload, mode, RestoreValidationError)
    assert f'{section}.private_key_pem_encrypted' in message, message
    assert 'holds an object that is not an encrypted key' in message, message


def test_a_real_backup_and_the_form_of_2_254_pass_the_check(target):
    """The export writes a 32-byte salt and a 12-byte nonce, as every release has."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from models import CA, Certificate
    from services.backup.restore.apply import refuse_containers_in_columns
    key, certificate = _authority('archive fields CA')
    leaf_key, leaf = _leaf('fields.example.test', key, certificate)
    for model, refid, material, cert in ((CA, 'af-real-ca', key, certificate),
                                         (Certificate, 'af-real-cert', leaf_key, leaf)):
        db.session.add(model(refid=refid, descr=refid, crt=_stored_certificate(cert),
                             prv=_stored_key(material),
                             **({'caref': 'af-real-ca'} if model is Certificate else {})))
    db.session.commit()
    svc = _service()
    sections = {name: name in ('certificate_authorities', 'certificates')
                for name in manifest.SECTIONS}
    blob = svc.create_backup(PASSWORD, include=sections)
    _master, data = svc._decrypt_framed(blob, PASSWORD)
    blobs = [row['private_key_pem_encrypted'] for name in ('certificate_authorities', 'certificates')
             for row in data[name]]
    assert len(blobs) == 2 and all(set(b) == {'algorithm', 'salt', 'nonce', 'ciphertext'}
                                   for b in blobs), blobs
    refuse_containers_in_columns(data)
    # 2.254.6 wrote the same object: hex of a 32-byte salt, a 12-byte nonce, AES-GCM output
    legacy = {'algorithm': 'AES-256-GCM', 'salt': os.urandom(32).hex(),
              'nonce': os.urandom(12).hex(),
              'ciphertext': AESGCM(os.urandom(32)).encrypt(os.urandom(12), b'k', None).hex()}
    refuse_containers_in_columns({'certificates': [dict(ROWS['certificates'],
                                                        private_key_pem_encrypted=legacy)]})
    results = svc.restore_backup(blob, PASSWORD, mode='replace')
    db.session.expire_all()
    assert results['cas'] == 1 and results['certificates'] == 1
    assert CA.query.filter_by(refid='af-real-ca').one().prv


# --- A field the export never writes -------------------------------------------------------------

PLAINTEXT_SHAPES = {'integer': 987654321, 'list': ['af-marker'],
                    'text': '-----BEGIN OPENSSH PRIVATE KEY-----\naf-marker\n'}


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('shape', sorted(PLAINTEXT_SHAPES))
def test_an_archived_plaintext_ssh_key_is_never_read(target, shape, mode):
    from models.ssh import SSHCertificateAuthority
    from security.encryption import decrypt_private_key
    row = dict(ROWS['ssh_cas'], _private_key_plaintext=PLAINTEXT_SHAPES[shape])
    _service()._restore_payload({'ssh_cas': [row]}, os.urandom(32), mode)
    db.session.expire_all()
    stored = SSHCertificateAuthority.query.filter_by(refid='af-ssh-ca').one().private_key
    assert not stored or 'af-marker' not in decrypt_private_key(stored)

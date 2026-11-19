"""A restore that cannot apply a row stops, instead of logging and going on.

The extended restorers used to wrap every row in `except Exception`: an SSH
CA whose key could not be decrypted was created without one, a row missing a
mandatory column was dropped, a whole section could disappear behind a single
warning — and the route still answered "Backup restored successfully". These
tests pin the opposite property, for one case per file that used to swallow:
the restore raises, the message names the object, and the database is exactly
as it was, because the restore is one transaction.

The archives here carry only the section under test (`_only`, as in
test_backup_export_manifest): the session database is shared by the whole
suite, and restoring a full archive would rewrite rows other tests watch.
"""
import base64
import gzip
import hashlib
import json
import struct

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from models import db
from services.backup import manifest
from services.backup.errors import BackupSchemaError

from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

PASSWORD = 'Correct-Horse-Battery-9'


def _service():
    from services.backup_service import BackupService
    return BackupService()


def _only(*names):
    """An include map that carries just these sections."""
    return {name: name in names for name in manifest.SECTIONS}


def _reseal(original_blob, data):
    """Rewrite an archive's payload, keeping its container and password.

    Counts and per-section digests are recomputed from the payload being
    written: the reader checks both before the first write, so a forged row
    would otherwise be refused as a corrupted archive rather than by the
    restorer under test.
    """
    svc = _service()
    metadata_len = struct.unpack('>H', original_blob[8:10])[0]
    header = original_blob[:10 + metadata_len]
    metadata = json.loads(header[10:].decode())
    salt = base64.b64decode(metadata['salt_b64'])
    nonce = base64.b64decode(metadata['nonce_b64'])

    if metadata['kdf']['type'] == 'argon2id':
        key = svc._derive_argon2id(
            PASSWORD, salt,
            time_cost=metadata['kdf']['time_cost'],
            memory_cost=metadata['kdf']['memory_cost'],
            parallelism=metadata['kdf']['parallelism'],
            hash_len=metadata['kdf']['hash_len'])
    else:
        key = svc._derive_pbkdf2(PASSWORD, salt, metadata['kdf']['iterations'])

    data.pop('checksum', None)
    payload_metadata = data.setdefault('metadata', {})
    payload_metadata['sections'] = {
        name: len(value) for name, value in data.items()
        if name != 'metadata' and isinstance(value, (list, dict))}
    payload_metadata['section_digests'] = svc._section_digests(data)

    digest = hashlib.sha256(
        json.dumps(data, indent=2, sort_keys=True).encode()).hexdigest()
    data['checksum'] = {'algorithm': 'SHA256', 'value': digest}
    plaintext = gzip.compress(json.dumps(data, indent=2, sort_keys=True).encode())
    return header + AESGCM(key).encrypt(nonce, plaintext, header)


def _forged(sections, **rows):
    """A real archive of `sections`, with these rows added to its payload.

    Must be called inside an application context: the sections are exported
    from the database, so the archive is one this server could have written.
    """
    svc = _service()
    blob = svc.create_backup(PASSWORD, include=_only(*sections))
    _key, data = svc._decrypt_framed(blob, PASSWORD)
    for name, extra in rows.items():
        data.setdefault(name, []).extend(extra)
    return _reseal(blob, data)


# Key material encrypted under a key nobody here has: decrypting it fails
# exactly as it would for a corrupted archive, or one whose key material was
# written by another installation.
UNREADABLE_KEY = {
    'algorithm': 'AES-256-GCM',
    'salt': '11' * 32,
    'nonce': '22' * 12,
    'ciphertext': '33' * 48,
}

SSH_PUBLIC_KEY = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFailFast'


class TestAnSshCaWithoutItsKeyIsNotRestored:
    """The finding, in one sentence: a key that could not be decrypted was a
    warning, and the authority was created and committed without it."""

    def test_an_undecryptable_key_stops_the_restore(self, app):
        from models.ssh import SSHCertificateAuthority

        with app.app_context():
            blob = _forged(['ssh_cas'], ssh_cas=[{
                'refid': 'failfast-ssh-ca',
                'descr': 'Fail-fast SSH CA',
                'ca_type': 'user',
                'key_type': 'ed25519',
                'public_key': SSH_PUBLIC_KEY,
                'fingerprint': 'SHA256:failfast',
                'serial_counter': 0,
                'private_key_pem_encrypted': UNREADABLE_KEY,
            }])

            try:
                with pytest.raises(BackupSchemaError) as refusal:
                    _service().restore_backup(blob, PASSWORD)
                assert 'failfast-ssh-ca' in str(refusal.value), \
                    'the refusal does not name the authority it is about'

                assert SSHCertificateAuthority.query.filter_by(
                    refid='failfast-ssh-ca').first() is None, \
                    'an SSH CA was created without the key it signs with'
            finally:
                SSHCertificateAuthority.query.filter_by(
                    refid='failfast-ssh-ca').delete()
                db.session.commit()


class TestARowMissingAMandatoryColumnIsNotDropped:
    def test_an_ssh_certificate_without_its_authority_stops_the_restore(self, app):
        """It used to raise KeyError inside the per-row `except`, so the
        certificate vanished and the restore reported the ones that worked.

        The refusal now happens while the plan is being built, before the
        first write rather than at the insert: a column the row needs and
        does not carry is named there, so either refusal is the contract
        being kept.
        """
        from services.backup.restore.plan import RestoreValidationError
        from models.ssh import SSHCertificate

        with app.app_context():
            blob = _forged(['ssh_certificates'], ssh_certificates=[{
                'refid': 'failfast-ssh-cert',
                'descr': 'Fail-fast SSH certificate',
                'cert_type': 'user',
                'key_id': 'failfast',
                'public_key': SSH_PUBLIC_KEY,
                'certificate': 'ssh-ed25519-cert-v01@openssh.com AAAA',
                'principals': '["failfast"]',
                'serial': 4242,
                # no ssh_ca_id: nothing says which authority signed it
            }])

            try:
                with pytest.raises(
                        (BackupSchemaError, RestoreValidationError)) as refusal:
                    _service().restore_backup(blob, PASSWORD)
                assert 'ssh_ca_id' in str(refusal.value)

                assert SSHCertificate.query.filter_by(
                    refid='failfast-ssh-cert').first() is None
            finally:
                SSHCertificate.query.filter_by(
                    refid='failfast-ssh-cert').delete()
                db.session.commit()

    def test_an_authentication_certificate_that_is_not_a_certificate_stops_it(
            self, app):
        """restore_auth used to decode the column as base64 and, when that
        failed, store the text as bytes: a login certificate nobody could
        ever present, restored as a success."""
        from models.auth_certificate import AuthCertificate

        with app.app_context():
            blob = _forged(['auth_certificates'], auth_certificates=[{
                'user_id': 1,
                'cert_serial': 'failfast-auth-serial',
                'cert_subject': 'CN=fail-fast',
                'cert_issuer': 'CN=fail-fast issuer',
                'cert_fingerprint': 'failfast-auth-fingerprint',
                'name': 'Fail-fast client certificate',
                'enabled': True,
                'cert_pem': 'not-a-certificate!',
            }])

            try:
                with pytest.raises(BackupSchemaError) as refusal:
                    _service().restore_backup(blob, PASSWORD)
                assert 'failfast-auth-serial' in str(refusal.value)

                assert AuthCertificate.query.filter_by(
                    cert_serial='failfast-auth-serial').first() is None
            finally:
                AuthCertificate.query.filter_by(
                    cert_serial='failfast-auth-serial').delete()
                db.session.commit()


class TestAnUnreadableDateIsNotSilentlyDropped:
    def test_an_eab_credential_with_an_unreadable_expiry_stops_the_restore(
            self, app):
        """The whole section sat inside one `except Exception`, and inside it
        an unparsable date became None: the binding came back never expiring,
        which is not what the archive said."""
        from models.acme_models import AcmeEabCredential

        with app.app_context():
            blob = _forged(['acme_eab_credentials'], acme_eab_credentials=[{
                'kid': 'failfast-eab',
                'hmac_key_b64': base64.b64encode(b'failfast-secret').decode(),
                'label': 'Fail-fast EAB',
                'status': 'active',
                'expires_at': 'not-a-date',
            }])

            try:
                with pytest.raises(BackupSchemaError) as refusal:
                    _service().restore_backup(blob, PASSWORD)
                message = str(refusal.value)
                assert 'failfast-eab' in message and 'expires_at' in message

                assert AcmeEabCredential.query.filter_by(
                    kid='failfast-eab').first() is None, \
                    'the credential was restored without the expiry it carried'
            finally:
                AcmeEabCredential.query.filter_by(kid='failfast-eab').delete()
                db.session.commit()


class TestTheFailureTakesTheSectionsBeforeItWithIt:
    def test_a_later_section_failing_leaves_the_earlier_one_unwritten(self, app):
        """The restore is one transaction: the SSH CA of the first section is
        applied before the certificate of the second is even read, and must be
        gone once that one is refused. Row-by-row commits used to leave it."""
        from models.ssh import SSHCertificate, SSHCertificateAuthority

        with app.app_context():
            blob = _forged(
                ['ssh_cas', 'ssh_certificates'],
                ssh_cas=[{
                    'refid': 'failfast-rollback-ca',
                    'descr': 'Fail-fast rollback SSH CA',
                    'ca_type': 'user',
                    'key_type': 'ed25519',
                    'public_key': SSH_PUBLIC_KEY,
                    'fingerprint': 'SHA256:failfast-rollback',
                    'serial_counter': 0,
                }],
                ssh_certificates=[{
                    'refid': 'failfast-rollback-cert',
                    'descr': 'Fail-fast rollback SSH certificate',
                    'cert_type': 'user',
                    'key_id': 'failfast-rollback',
                    'public_key': SSH_PUBLIC_KEY,
                    'certificate': 'ssh-ed25519-cert-v01@openssh.com AAAA',
                    'principals': '["failfast"]',
                    'serial': 4343,
                    'ssh_ca_id': 1,
                    'valid_from': 'not-a-date',
                }],
            )

            before = SSHCertificateAuthority.query.count()
            try:
                with pytest.raises(ValueError):
                    _service().restore_backup(blob, PASSWORD)

                db.session.expire_all()
                assert SSHCertificateAuthority.query.filter_by(
                    refid='failfast-rollback-ca').first() is None, \
                    'the SSH CA of the earlier section survived the failure'
                assert SSHCertificateAuthority.query.count() == before
                assert SSHCertificate.query.filter_by(
                    refid='failfast-rollback-cert').first() is None
            finally:
                SSHCertificate.query.filter_by(
                    refid='failfast-rollback-cert').delete()
                SSHCertificateAuthority.query.filter_by(
                    refid='failfast-rollback-ca').delete()
                db.session.commit()

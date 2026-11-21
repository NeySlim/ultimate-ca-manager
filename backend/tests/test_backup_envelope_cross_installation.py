"""An archive written under a rotated DEK restores onto another installation (other KEK).

The archive carries private keys in the clear, under the backup password, and never the
encryption_keys table: the target encrypts what it restores under its own DEK. What the
envelope changes is only where the source read the keys from.
"""
import base64

import pytest
from cryptography.fernet import Fernet

from models import db
from tests.test_backup_cross_installation import (
    PASSWORD, Keys, _authority, _installation, _only, _pem, _service, _stored_certificate,
    _stored_key,
)


@pytest.fixture(autouse=True)
def _dek_refresh(dek_refresh_now):
    """No process here lags: rotations and disables wait for none."""


def _add_authority(refid):
    from models import CA
    key, certificate = _authority(refid)
    db.session.add(CA(
        refid=refid, descr=refid, url_slug=refid, crt=_stored_certificate(certificate),
        prv=_stored_key(key), subject=certificate.subject.rfc4514_string(),
        issuer=certificate.issuer.rfc4514_string(),
        serial_number=format(certificate.serial_number, 'x'),
        valid_from=certificate.not_valid_before, valid_to=certificate.not_valid_after))
    db.session.commit()
    return key


def test_an_archive_under_a_rotated_dek_restores_under_the_target_kek(app, tmp_path,
                                                                     dek_retire_at_once):
    from models import CA, EncryptionKey
    from security import dek_rotation
    from security.encryption import ENCRYPTED_MARKER, key_encryption
    from utils.key_codec import load_pem_bytes

    source, target = Keys(tmp_path, 'source'), Keys(tmp_path, 'target')
    with _installation(app, f"sqlite:///{tmp_path / 'source.db'}", source), app.app_context():
        key = _add_authority('envelope-ca')
        assert dek_rotation.rotate()['state'] == 'done'
        assert [r.state for r in EncryptionKey.query.all()] == ['active']
        stored = CA.query.filter_by(refid='envelope-ca').one().prv
        # Under the rotated DEK: the source's KEK alone does not open it
        token = base64.b64decode(stored)[len(ENCRYPTED_MARKER):]
        assert not _opens(source.master, token)
        blob = _service().create_backup(PASSWORD, include=_only('certificate_authorities'))

    with _installation(app, f"sqlite:///{tmp_path / 'target.db'}", target), app.app_context():
        _service().restore_backup(blob, PASSWORD)
        restored = CA.query.filter_by(refid='envelope-ca').one()
        assert EncryptionKey.query.count() == 0  # the source's DEK never travels
        assert key_encryption.is_encrypted(restored.prv)
        token = base64.b64decode(restored.prv)[len(ENCRYPTED_MARKER):]
        assert _opens(target.master, token)  # the target's DEK version 1 is its KEK
        assert load_pem_bytes(restored.prv, context='envelope-ca') == _pem(key)


def _opens(kek, token):
    try:
        Fernet(kek.encode()).decrypt(token)
        return True
    except Exception:
        return False


def test_characterization_an_archive_taken_during_the_retention_restores_readable(
        app, tmp_path, monkeypatch):
    """Characterization test, no guard of the retention change behind it: a key committed
    under a retained DEK goes into the archive in the clear, the restore needs no old DEK."""
    from models import CA, EncryptionKey
    from security import dek_rotation
    from security.encryption import ENCRYPTED_MARKER, key_encryption
    from utils.key_codec import load_pem_bytes
    monkeypatch.setattr(dek_rotation, 'GRACE_SECONDS', 0.0)
    monkeypatch.setattr(dek_rotation, 'RETENTION_SECONDS', 7 * 86400.0)

    source, target = Keys(tmp_path, 'source'), Keys(tmp_path, 'target')
    with _installation(app, f"sqlite:///{tmp_path / 'source.db'}", source), app.app_context():
        key = _add_authority('retained-ca')
        old = key_encryption._fernet
        assert dek_rotation.rotate()['state'] == 'done'
        assert [(r.version, r.state) for r in EncryptionKey.query.order_by(
            EncryptionKey.version)] == [(1, 'previous'), (2, 'active')]
        # A long transaction commits the key under the retained DEK
        ca = CA.query.filter_by(refid='retained-ca').one()
        ca.prv = base64.b64encode(ENCRYPTED_MARKER + old.encrypt(_pem(key))).decode()
        db.session.commit()
        blob = _service().create_backup(PASSWORD, include=_only('certificate_authorities'))

    with _installation(app, f"sqlite:///{tmp_path / 'target.db'}", target), app.app_context():
        _service().restore_backup(blob, PASSWORD)
        restored = CA.query.filter_by(refid='retained-ca').one()
        assert EncryptionKey.query.count() == 0
        assert load_pem_bytes(restored.prv, context='retained-ca') == _pem(key)

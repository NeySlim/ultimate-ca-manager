"""Tests for the SSH CA service (previously 0 coverage)."""
import pytest

from models import db, SSHCertificateAuthority
from services.ssh_ca_service import SSHCAService
from tests.ssh_cleanup import ssh_rows_stay_in_their_module  # noqa: F401


class TestCreateCA:
    def test_create_ed25519_user_ca(self, app):
        with app.app_context():
            ca = SSHCAService.create_ca(descr='Test SSH User CA', ca_type='user',
                                        key_type='ed25519', username='tester')
            assert ca.id is not None
            assert ca.ca_type == 'user'
            pub = SSHCAService.get_public_key(ca.id)
            assert pub and pub.startswith('ssh-ed25519 ')

    def test_create_rejects_bad_type(self, app):
        with app.app_context():
            with pytest.raises(ValueError, match='CA type'):
                SSHCAService.create_ca(descr='x', ca_type='banana', username='t')

    def test_create_rejects_bad_key_type(self, app):
        with app.app_context():
            with pytest.raises(ValueError, match='key type'):
                SSHCAService.create_ca(descr='x', ca_type='user', key_type='magic', username='t')


class TestSerial:
    def test_serial_increments(self, app):
        with app.app_context():
            ca = SSHCAService.create_ca(descr='Serial CA', ca_type='host',
                                        key_type='ed25519', username='t')
            s1 = SSHCAService.get_next_serial(ca.id)
            s2 = SSHCAService.get_next_serial(ca.id)
            assert s2 == s1 + 1


class TestImportAndDelete:
    def test_import_ca_from_private_key(self, app):
        from cryptography.hazmat.primitives.asymmetric import ed25519
        from cryptography.hazmat.primitives import serialization
        with app.app_context():
            key = ed25519.Ed25519PrivateKey.generate()
            pem = key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.OpenSSH,
                encryption_algorithm=serialization.NoEncryption(),
            ).decode()
            ca = SSHCAService.import_ca(descr='Imported SSH CA', ca_type='user',
                                        private_key_pem=pem, username='t')
            assert ca.id is not None
            assert SSHCAService.get_public_key(ca.id).startswith('ssh-ed25519 ')

    def test_delete_ca(self, app):
        with app.app_context():
            ca = SSHCAService.create_ca(descr='Doomed CA', ca_type='user',
                                        key_type='ed25519', username='t')
            cid = ca.id
            assert SSHCAService.delete_ca(cid) == 'Doomed CA'  # returns the deleted CA's name
            assert db.session.get(SSHCertificateAuthority, cid) is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

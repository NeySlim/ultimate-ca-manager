"""Tests for SSH certificate signing / revocation (previously 0 coverage)."""
import pytest

from models import db, SSHCertificate
from services.ssh_ca_service import SSHCAService
from services.ssh_cert import SSHCertificateService


def _client_pubkey():
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.hazmat.primitives import serialization
    key = ed25519.Ed25519PrivateKey.generate()
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode()


class TestSignCertificate:
    def test_sign_user_cert(self, app):
        with app.app_context():
            ca = SSHCAService.create_ca(descr='Sign CA', ca_type='user',
                                        key_type='ed25519', username='t')
            cert = SSHCertificateService.sign_certificate(
                ca.id, _client_pubkey(), 'user', ['alice'], validity_seconds=3600)
            assert cert.id is not None
            assert cert.serial > 0
            assert 'alice' in cert.key_id

    def test_rejects_invalid_cert_type(self, app):
        with app.app_context():
            ca = SSHCAService.create_ca(descr='Type CA', ca_type='user',
                                        key_type='ed25519', username='t')
            with pytest.raises(ValueError, match='certificate type'):
                SSHCertificateService.sign_certificate(
                    ca.id, _client_pubkey(), 'banana', ['alice'])

    def test_rejects_empty_principals(self, app):
        with app.app_context():
            ca = SSHCAService.create_ca(descr='Princ CA', ca_type='user',
                                        key_type='ed25519', username='t')
            with pytest.raises(ValueError):
                SSHCertificateService.sign_certificate(
                    ca.id, _client_pubkey(), 'user', [])

    def test_allowed_principal_shell_pattern_matches(self, app):
        with app.app_context():
            ca = SSHCAService.create_ca(
                descr='Pattern CA', ca_type='user', key_type='ed25519',
                username='t', allowed_principals=['team-*', 'deploy?'],
            )
            cert = SSHCertificateService.sign_certificate(
                ca.id, _client_pubkey(), 'user', ['team-alice', 'deploy1']
            )
            assert cert.get_principals() == ['team-alice', 'deploy1']

    def test_allowed_principal_shell_pattern_rejects_non_match(self, app):
        with app.app_context():
            ca = SSHCAService.create_ca(
                descr='Restricted CA', ca_type='user', key_type='ed25519',
                username='t', allowed_principals=['team-*'],
            )
            with pytest.raises(ValueError, match='allowed principals'):
                SSHCertificateService.sign_certificate(
                    ca.id, _client_pubkey(), 'user', ['admin']
                )

    def test_rejects_certificate_type_mismatching_ca_type(self, app):
        with app.app_context():
            ca = SSHCAService.create_ca(
                descr='Host CA', ca_type='host', key_type='ed25519', username='t'
            )
            with pytest.raises(ValueError, match='cannot sign user certificates'):
                SSHCertificateService.sign_certificate(
                    ca.id, _client_pubkey(), 'user', ['alice']
                )


class TestRevokeAndKrl:
    def test_revoke_marks_revoked(self, app):
        with app.app_context():
            ca = SSHCAService.create_ca(descr='Rev CA', ca_type='user',
                                        key_type='ed25519', username='t')
            cert = SSHCertificateService.sign_certificate(
                ca.id, _client_pubkey(), 'user', ['bob'])
            SSHCertificateService.revoke_certificate(cert.id, reason='superseded', username='t')
            assert db.session.get(SSHCertificate, cert.id).revoked is True

    def test_krl_generation(self, app):
        import shutil
        if not shutil.which('ssh-keygen'):
            pytest.skip('ssh-keygen not available')
        from services.ssh_krl_service import SSHKRLService
        with app.app_context():
            ca = SSHCAService.create_ca(descr='KRL CA', ca_type='user',
                                        key_type='ed25519', username='t')
            cert = SSHCertificateService.sign_certificate(
                ca.id, _client_pubkey(), 'user', ['carol'])
            SSHCertificateService.revoke_certificate(cert.id, username='t')
            krl = SSHKRLService.generate_krl(ca.id)
            assert isinstance(krl, (bytes, bytearray))


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

"""SSH certificates: the KRL keeps a revoked certificate until it expires, critical
options follow PROTOCOL.certkeys, validity starts slightly in the past and the
KRL version grows (PROTOCOL.krl)."""
import json
import shutil
import subprocess
import time
from datetime import datetime, timedelta, timezone

import pytest

from models import db
from models.ssh import SSHCertificate
from services.ssh_ca_service import SSHCAService
from services.ssh_cert import SSHCertificateService
from services.ssh_krl_service import SSHKRLService
from utils.datetime_utils import utc_now
from tests.test_ssh import _create_ssh_ca, _generate_test_ssh_key, post_json
from tests.test_ssh_cert_service import _client_pubkey

needs_ssh_keygen = pytest.mark.skipif(not shutil.which('ssh-keygen'),
                                      reason='ssh-keygen not available')


def _query(tmp_path, krl, certificate, list_version=False):
    """``ssh-keygen -Q`` against a KRL, as sshd's RevokedKeys reads it."""
    krl_path, cert_path = tmp_path / 'krl', tmp_path / 'id-cert.pub'
    krl_path.write_bytes(krl)
    cert_path.write_text(certificate)
    args = ['ssh-keygen', '-Q'] + (['-l'] if list_version else []) + ['-f', str(krl_path)]
    return subprocess.run(args + ([] if list_version else [str(cert_path)]),
                          capture_output=True, text=True, timeout=30)


def _issue_and_revoke(auth_client):
    ca = _create_ssh_ca(auth_client, descr='KRL keep CA')
    r = post_json(auth_client, '/api/v2/ssh/certificates', {
        'ca_id': ca['id'], 'public_key': _generate_test_ssh_key(),
        'cert_type': 'user', 'principals': ['keep'], 'validity_seconds': 3600,
    })
    assert r.status_code == 201
    cert = r.get_json()['data']
    post_json(auth_client, f"/api/v2/ssh/certificates/{cert['id']}/revoke",
              {'reason': 'key_compromise'})
    return ca, cert


@needs_ssh_keygen
class TestRevokedCertificateStaysInTheKrl:
    def test_a_revoked_unexpired_certificate_cannot_be_deleted(self, app, auth_client, tmp_path):
        ca, cert = _issue_and_revoke(auth_client)
        r = auth_client.delete(f"/api/v2/ssh/certificates/{cert['id']}")
        assert r.status_code == 409
        with app.app_context():
            assert db.session.get(SSHCertificate, cert['id']) is not None
        krl = auth_client.get(f"/api/v2/ssh/cas/{ca['id']}/krl")
        assert krl.status_code == 200
        query = _query(tmp_path, krl.data, cert['certificate'])
        assert query.returncode != 0 and 'REVOKED' in query.stdout

    def test_it_can_be_deleted_once_expired(self, app, auth_client):
        _ca, cert = _issue_and_revoke(auth_client)
        with app.app_context():
            row = db.session.get(SSHCertificate, cert['id'])
            row.valid_to = utc_now() - timedelta(seconds=1)
            db.session.commit()
        assert auth_client.delete(f"/api/v2/ssh/certificates/{cert['id']}").status_code == 204

    def test_krl_version_grows_with_each_revocation(self, app, tmp_path):
        def version(krl):
            out = _query(tmp_path, krl, '', list_version=True).stdout
            return int(next(line for line in out.splitlines()
                            if line.startswith('# KRL version')).split()[-1])

        with app.app_context():
            ca = SSHCAService.create_ca(descr='KRL version CA', ca_type='user',
                                        key_type='ed25519', username='t',
                                        allow_any_principal=True)
            first = version(SSHKRLService.generate_krl(ca.id))
            assert first > 0
            cert = SSHCertificateService.sign_certificate(ca.id, _client_pubkey(), 'user', ['v'])
            SSHCertificateService.revoke_certificate(cert.id, username='t')
            time.sleep(0.002)
            assert version(SSHKRLService.generate_krl(ca.id)) > first


class TestCriticalOptions:
    @pytest.fixture()
    def user_ca(self, app):
        with app.app_context():
            ca = SSHCAService.create_ca(descr='Options user CA', ca_type='user',
                                        key_type='ed25519', username='t',
                                        allow_any_principal=True)
            yield ca.id

    @pytest.fixture()
    def host_ca(self, app):
        with app.app_context():
            ca = SSHCAService.create_ca(descr='Options host CA', ca_type='host',
                                        key_type='ed25519', username='t',
                                        allow_any_principal=True)
            yield ca.id

    def _sign(self, ca_id, cert_type, options):
        return SSHCertificateService.sign_certificate(
            ca_id, _client_pubkey(), cert_type, ['opt.example.com'], critical_options=options)

    def test_host_certificates_carry_none(self, app, host_ca):
        # "No critical options are defined for host certificates at present"
        with pytest.raises(ValueError, match='host certificates'):
            self._sign(host_ca, 'host', {'force-command': '/bin/x'})
        assert SSHCertificate.query.filter_by(ssh_ca_id=host_ca).count() == 0

    def test_user_options_defined_by_openssh_are_signed(self, app, user_ca):
        cert = self._sign(user_ca, 'user', {
            'force-command': '/usr/bin/rsync', 'source-address': '10.0.0.0/8,2001:db8::/32',
            'verify-required': ''})
        assert json.loads(cert.critical_options)['source-address'] == '10.0.0.0/8,2001:db8::/32'

    def test_a_vendor_option_named_with_a_domain_is_signed(self, app, user_ca):
        assert self._sign(user_ca, 'user', {'restrict@example.com': 'x'}).id

    @pytest.mark.parametrize('options', [
        {'permit-pty': ''},                       # an extension, not a critical option
        {'no-such-option': 'x'},
        {'source-address': '10.0.0.1/8'},         # ssh-keygen: inconsistent mask length
        {'source-address': '10.0.0.*'},
        {'source-address': '10.0.0.0/8,'},
        {'force-command': ''},
        {'verify-required': 'yes'},
    ])
    def test_unknown_or_malformed_user_options_are_refused(self, app, user_ca, options):
        with pytest.raises(ValueError):
            self._sign(user_ca, 'user', options)

    def test_the_api_answers_400(self, auth_client):
        ca = _create_ssh_ca(auth_client, ca_type='host', descr='Options API host CA')
        r = post_json(auth_client, '/api/v2/ssh/certificates', {
            'ca_id': ca['id'], 'public_key': _generate_test_ssh_key(), 'cert_type': 'host',
            'principals': ['h.example.com'], 'critical_options': {'force-command': '/bin/x'},
        })
        assert r.status_code == 400


def test_validity_starts_five_minutes_back(app):
    """A server whose clock lags behind the CA's accepts the certificate at once."""
    from cryptography.hazmat.primitives.serialization import load_ssh_public_identity
    with app.app_context():
        ca = SSHCAService.create_ca(descr='Backdate CA', ca_type='user', key_type='ed25519',
                                    username='t', allow_any_principal=True)
        before = int(time.time())
        cert = SSHCertificateService.sign_certificate(
            ca.id, _client_pubkey(), 'user', ['skew'], validity_seconds=3600)
        after = int(time.time())
        signed = load_ssh_public_identity(cert.certificate.encode())
        assert before - 300 <= signed.valid_after <= after - 300
        assert before + 3600 <= signed.valid_before <= after + 3600   # lifetime counts from now
        stored = cert.valid_from.replace(tzinfo=None)
        assert stored == datetime.fromtimestamp(signed.valid_after, timezone.utc).replace(tzinfo=None)

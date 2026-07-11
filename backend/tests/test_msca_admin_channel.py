"""
Microsoft CA WinRM admin channel tests (#185 phase A)

Covers serial validation / injection defense, the reason-code mapping, the
revoke-on-CA propagation wired into the certificate revoke endpoint, and the
CRUD for the winrm_* fields. The WinRM transport itself is monkeypatched — no
real Windows host is contacted.
"""
import json

import pytest

from tests.conftest import get_json

CONTENT_JSON = 'application/json'
BASE = '/api/v2/microsoft-cas'
CERTS = '/api/v2/certificates'


def post_json(client, url, data=None):
    return client.post(url, data=json.dumps(data or {}), content_type=CONTENT_JSON)


def put_json(client, url, data):
    return client.put(url, data=json.dumps(data), content_type=CONTENT_JSON)


def _make_msca_cert(app, cn, winrm=True):
    """A connection (optionally with admin channel) + an msca-sourced cert."""
    import base64
    from datetime import timedelta
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    from utils.datetime_utils import utc_now

    with app.app_context():
        from models import Certificate, db
        from models.msca import MicrosoftCA, MSCARequest

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
        now = utc_now()
        cert_obj = (x509.CertificateBuilder()
                    .subject_name(name).issuer_name(name)
                    .public_key(key.public_key())
                    .serial_number(0x3E00000012ABCDEF)
                    .not_valid_before(now - timedelta(hours=1))
                    .not_valid_after(now + timedelta(days=365))
                    .sign(key, hashes.SHA256()))
        pem = cert_obj.public_bytes(serialization.Encoding.PEM).decode()

        msca = MicrosoftCA(name=f'AC {cn}', server='adcs.test.local',
                           auth_method='basic', username='u', enabled=True)
        msca.password = 'p'
        if winrm:
            msca.winrm_enabled = True
            msca.winrm_transport = 'ntlm'
            msca.winrm_use_ssl = False
            msca.winrm_port = 5985
        db.session.add(msca)
        db.session.flush()

        cert = Certificate(
            refid=f'ac-{cn[:12]}', descr=f'MSCA: {cn}',
            crt=base64.b64encode(pem.encode()).decode(),
            cert_type='server', subject=f'CN={cn}', subject_cn=cn,
            serial_number=format(cert_obj.serial_number, 'X'),
            source='msca', imported_from=f'msca:{msca.name}',
        )
        db.session.add(cert)
        db.session.flush()
        db.session.add(MSCARequest(msca_id=msca.id, cert_id=cert.id,
                                   template='WebServer', status='issued'))
        db.session.commit()
        return msca.id, cert.id, cert.serial_number


class TestSerialValidation:

    def test_accepts_hex_with_colons(self):
        from services.msca.admin_channel import MicrosoftCAAdminChannelMixin as A
        assert A._validate_serial('3E:00:0F') == '3e000f'

    @pytest.mark.parametrize('bad', ['3E; certutil -x', '../../x', 'ZZZ', '', '3E 00'])
    def test_rejects_non_hex(self, bad):
        from services.msca.admin_channel import (
            MicrosoftCAAdminChannelMixin as A, MSCAAdminChannelError)
        with pytest.raises(MSCAAdminChannelError):
            A._validate_serial(bad)

    def test_reason_code_mapping(self):
        from services.msca.admin_channel import _CERTUTIL_REASON
        assert _CERTUTIL_REASON['keyCompromise'] == 1
        assert _CERTUTIL_REASON['certificateHold'] == 6
        assert _CERTUTIL_REASON['unspecified'] == 0

    def test_ca_config_rejects_injection(self, app):
        from services.msca.admin_channel import (
            MicrosoftCAAdminChannelMixin as A, MSCAAdminChannelError)
        from types import SimpleNamespace
        with pytest.raises(MSCAAdminChannelError):
            A._config_arg(SimpleNamespace(ca_config='CA" ; del'))
        assert A._config_arg(SimpleNamespace(ca_config=None)) == ''
        assert A._config_arg(SimpleNamespace(ca_config='HOST\\CA Name')) == '-config "HOST\\CA Name" '


class TestRevokePropagation:

    def test_revoke_msca_propagates_to_ca(self, app, auth_client, monkeypatch):
        msca_id, cert_id, serial = _make_msca_cert(app, 'revoke-ca.test.local')

        calls = {}

        def fake_run_ps(msca, script):
            calls['script'] = script
            return 'ok'
        from services.msca.admin_channel import MicrosoftCAAdminChannelMixin
        monkeypatch.setattr(MicrosoftCAAdminChannelMixin, '_run_ps',
                            staticmethod(fake_run_ps))

        r = post_json(auth_client, f'{CERTS}/{cert_id}/revoke', {'reason': 'keyCompromise'})
        assert r.status_code == 200, r.data
        body = get_json(r)
        assert body['meta'].get('msca_ca_revoked') is True
        # serial lowercased, reason code 1, CRL published
        assert f'-revoke {serial.lower()} 1' in calls['script']
        assert '-crl' in calls['script']

        with app.app_context():
            from models import Certificate, db
            assert db.session.get(Certificate, cert_id).revoked is True

    def test_revoke_without_channel_is_local_only(self, app, auth_client):
        _, cert_id, _ = _make_msca_cert(app, 'revoke-nochan.test.local', winrm=False)
        r = post_json(auth_client, f'{CERTS}/{cert_id}/revoke', {'reason': 'unspecified'})
        assert r.status_code == 200
        body = get_json(r)
        assert body['meta'].get('msca_local_only') is True

    def test_revoke_ca_failure_still_revokes_locally(self, app, auth_client, monkeypatch):
        msca_id, cert_id, _ = _make_msca_cert(app, 'revoke-cafail.test.local')

        from services.msca.admin_channel import (
            MicrosoftCAAdminChannelMixin, MSCAAdminChannelError)

        def boom(msca, script):
            raise MSCAAdminChannelError('WinRM refused')
        monkeypatch.setattr(MicrosoftCAAdminChannelMixin, '_run_ps', staticmethod(boom))

        r = post_json(auth_client, f'{CERTS}/{cert_id}/revoke', {'reason': 'unspecified'})
        assert r.status_code == 200
        body = get_json(r)
        assert body['meta'].get('msca_local_only') is True
        assert 'msca_ca_error' in body['meta']
        with app.app_context():
            from models import Certificate, db
            assert db.session.get(Certificate, cert_id).revoked is True


class TestAdminChannelEndpoints:

    def test_test_channel_success(self, app, auth_client, monkeypatch):
        msca_id, _, _ = _make_msca_cert(app, 'chan-test.test.local')
        from services.msca.admin_channel import MicrosoftCAAdminChannelMixin
        monkeypatch.setattr(MicrosoftCAAdminChannelMixin, '_run_ps',
                            staticmethod(lambda msca, script: 'UCM_CERTSVC=Running\n'))
        r = post_json(auth_client, f'{BASE}/{msca_id}/admin-channel/test')
        assert r.status_code == 200, r.data
        assert get_json(r)['data']['certsvc_status'] == 'Running'

    def test_test_channel_requires_enabled(self, app, auth_client):
        msca_id, _, _ = _make_msca_cert(app, 'chan-disabled.test.local', winrm=False)
        r = post_json(auth_client, f'{BASE}/{msca_id}/admin-channel/test')
        assert r.status_code == 400

    def test_publish_crl(self, app, auth_client, monkeypatch):
        msca_id, _, _ = _make_msca_cert(app, 'chan-crl.test.local')
        from services.msca.admin_channel import MicrosoftCAAdminChannelMixin
        seen = {}
        monkeypatch.setattr(MicrosoftCAAdminChannelMixin, '_run_ps',
                            staticmethod(lambda msca, script: seen.setdefault('s', script) or 'CRL published'))
        r = post_json(auth_client, f'{BASE}/{msca_id}/publish-crl')
        assert r.status_code == 200, r.data
        assert '-crl' in seen['s']


class TestWinrmCrud:

    def test_create_and_update_winrm_fields(self, auth_client):
        r = post_json(auth_client, BASE, {
            'name': 'WinRM CRUD', 'server': 'adcs.test.local',
            'auth_method': 'basic', 'username': 'u', 'password': 'p',
            'winrm_enabled': True, 'winrm_transport': 'kerberos',
            'winrm_port': 5986,
        })
        assert r.status_code == 201, r.data
        data = get_json(r)['data']
        assert data['winrm_enabled'] is True
        assert data['winrm_transport'] == 'kerberos'
        mid = data['id']

        # password is write-only (masked on read)
        r = put_json(auth_client, f'{BASE}/{mid}', {'winrm_password': 'secret'})
        assert r.status_code == 200
        assert get_json(r)['data']['winrm_password'] == '***'

    def test_invalid_transport_rejected(self, auth_client):
        r = post_json(auth_client, BASE, {
            'name': 'WinRM Bad Transport', 'server': 'adcs.test.local',
            'auth_method': 'basic', 'username': 'u', 'password': 'p',
            'winrm_enabled': True, 'winrm_transport': 'telnet',
        })
        assert r.status_code == 400

    def test_ca_config_injection_rejected(self, auth_client):
        r = post_json(auth_client, BASE, {
            'name': 'WinRM Bad Config', 'server': 'adcs.test.local',
            'auth_method': 'basic', 'username': 'u', 'password': 'p',
            'ca_config': 'HOST\\CA"; certutil -shutdown',
        })
        assert r.status_code == 400

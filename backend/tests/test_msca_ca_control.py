"""
Microsoft CA CA-control tests (#185 phase C)

Pending-request management (list / approve / deny) and the CA health snapshot,
all over the WinRM admin channel. The WinRM layer is monkeypatched: the fake
inspects the certutil script and serves the pending CSV, resubmit/deny output,
a RawCertificate PEM, or the certsvc marker. For health, the connector client
and the CRL-sync helpers are patched too — no network, no Windows host.
"""
import base64
import json
import re
from datetime import timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from tests.conftest import get_json

CONTENT_JSON = 'application/json'
BASE = '/api/v2/microsoft-cas'


def post_json(client, url, data=None):
    return client.post(url, data=json.dumps(data or {}), content_type=CONTENT_JSON)


# ---------------------------------------------------------------------------
# Fake CA-side data + WinRM mock
# ---------------------------------------------------------------------------

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _make_cert(cn):
    """Self-signed cert with a random serial. Returns (serial_hex_lower, pem)."""
    from utils.datetime_utils import utc_now

    now = utc_now()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    serial = x509.random_serial_number()
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name)
            .public_key(_KEY.public_key())
            .serial_number(serial)
            .not_valid_before(now - timedelta(hours=1))
            .not_valid_after(now + timedelta(days=365))
            .sign(_KEY, hashes.SHA256()))
    pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    return format(serial, 'x'), pem


class FakeCAControl:
    """Serves certutil output for pending requests, approve/deny and health."""

    def __init__(self):
        self.pending = []   # dicts: request_id, requester, cn, template, submitted
        self.certs = {}     # request_id -> issued PEM (served on RawCertificate)
        self.calls = []

    def add_pending(self, request_id, cn, requester='UCMTEST\\alice',
                    template='WebServer', submitted='01/07/2026 10:00'):
        self.pending.append({'request_id': request_id, 'requester': requester,
                             'cn': cn, 'template': template,
                             'submitted': submitted})

    def issue(self, request_id, cn):
        """Register the cert served once the request is approved."""
        serial, pem = _make_cert(cn)
        self.certs[request_id] = pem
        return serial, pem

    def run_ps(self, msca, script):
        self.calls.append(script)
        if 'Disposition=9' in script:
            # Localized header (ignored by the parser), then positional columns.
            lines = ['"ID de la demande","Demandeur","Nom commun","Modèle","Date"']
            for row in self.pending:
                lines.append(
                    f'"{row["request_id"]}","{row["requester"]}","{row["cn"]}",'
                    f'"{row["template"]}","{row["submitted"]}"'
                )
            return '\n'.join(lines) + '\n'
        if 'RawCertificate' in script:
            rid = int(re.search(r'RequestId=(\d+)', script).group(1))
            pem = self.certs.get(rid)
            if pem:
                return (f'Row 1:\n  RawCertificate:\n{pem}\n'
                        'CertUtil: -view command completed successfully.\n')
            return 'CertUtil: no rows\n'
        if '-resubmit' in script:
            return 'Certificate issued.\n'
        if '-deny' in script:
            return 'Certificate request denied.\n'
        if 'Get-Service certsvc' in script:
            return 'UCM_CERTSVC=Running\n'
        return 'ok\n'


@pytest.fixture
def fake_ca(monkeypatch):
    """A FakeCAControl instance wired into the WinRM admin channel."""
    from services.msca.admin_channel import MicrosoftCAAdminChannelMixin

    fake = FakeCAControl()
    monkeypatch.setattr(MicrosoftCAAdminChannelMixin, '_run_ps',
                        staticmethod(fake.run_ps))
    return fake


def _make_msca(app, name, winrm=True):
    """Connector with (optionally) a usable WinRM admin channel."""
    with app.app_context():
        from models import db
        from models.msca import MicrosoftCA

        msca = MicrosoftCA(name=name, server='adcs.test.local',
                           auth_method='basic', username='u', enabled=True)
        msca.password = 'p'
        if winrm:
            msca.winrm_enabled = True
            msca.winrm_transport = 'ntlm'
            msca.winrm_use_ssl = False
            msca.winrm_port = 5985
        db.session.add(msca)
        db.session.commit()
        return msca.id


def _add_ucm_cert(app, msca_id, name, cn, serial_hex_lower, pem):
    """Insert an msca-sourced cert as if UCM already knew it."""
    with app.app_context():
        from models import Certificate, db
        from models.msca import MSCARequest

        cert = Certificate(
            refid=f'cac-{cn[:10]}-{serial_hex_lower[:6]}',
            descr=f'MSCA: {cn}',
            crt=base64.b64encode(pem.encode()).decode(),
            cert_type='server',
            subject=f'CN={cn}', subject_cn=cn,
            serial_number=serial_hex_lower.upper(),
            source='msca',
            imported_from=f'msca:{name}',
        )
        db.session.add(cert)
        db.session.flush()
        db.session.add(MSCARequest(msca_id=msca_id, cert_id=cert.id,
                                   template='WebServer', status='issued'))
        db.session.commit()
        return cert.id


# ---------------------------------------------------------------------------
# Health-side fakes (CA cert via connector client + CRL via crl_sync helpers)
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def health_material():
    """A CA cert (long-lived) and a fresh CRL with one revoked entry."""
    from utils.datetime_utils import utc_now

    now = utc_now()
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'CAControl Root')])
    ca_cert = (x509.CertificateBuilder()
               .subject_name(ca_name).issuer_name(ca_name)
               .public_key(ca_key.public_key())
               .serial_number(x509.random_serial_number())
               .not_valid_before(now - timedelta(days=1))
               .not_valid_after(now + timedelta(days=3650))
               .add_extension(x509.BasicConstraints(ca=True, path_length=None),
                              critical=True)
               .sign(ca_key, hashes.SHA256()))
    entry = (x509.RevokedCertificateBuilder()
             .serial_number(x509.random_serial_number())
             .revocation_date(now - timedelta(minutes=30))
             .build())
    crl = (x509.CertificateRevocationListBuilder()
           .issuer_name(ca_name)
           .last_update(now - timedelta(minutes=10))
           .next_update(now + timedelta(days=7))
           .add_revoked_certificate(entry)
           .sign(ca_key, hashes.SHA256()))
    return {
        'ca_cert_pem': ca_cert.public_bytes(serialization.Encoding.PEM).decode(),
        'crl': crl,
    }


@pytest.fixture
def patched_health(monkeypatch, health_material):
    """CA cert + CRL sources mocked so ca_health has a fully green path."""
    from services.msca.connection import MicrosoftCAConnectionMixin
    from services.msca.crl_sync import MicrosoftCACRLSyncMixin

    class FakeClient:
        def get_ca_cert(self, encoding='b64'):
            return health_material['ca_cert_pem']

    monkeypatch.setattr(MicrosoftCAConnectionMixin, '_get_client',
                        staticmethod(lambda msca: FakeClient()))
    monkeypatch.setattr(MicrosoftCAConnectionMixin, '_cleanup_client',
                        staticmethod(lambda client: None))
    monkeypatch.setattr(MicrosoftCACRLSyncMixin, '_resolve_crl_url',
                        staticmethod(lambda msca: 'https://crl.test.local/fake.crl'))
    monkeypatch.setattr(MicrosoftCACRLSyncMixin, '_fetch_crl',
                        staticmethod(lambda msca, url: health_material['crl']))
    return health_material


# ---------------------------------------------------------------------------
# Pending requests — service level
# ---------------------------------------------------------------------------

class TestListPendingService:

    def test_parses_pending_csv(self, app, fake_ca):
        msca_id = _make_msca(app, 'CAC List A')
        fake_ca.add_pending(101, 'pend-a1.test.local')
        fake_ca.add_pending(102, 'pend-a2.test.local',
                            requester='UCMTEST\\bob', template='Machine',
                            submitted='02/07/2026 09:30')

        with app.app_context():
            from services.msca_service import MicrosoftCAService
            rows = MicrosoftCAService.list_pending_requests(msca_id)

        assert rows == [
            {'request_id': 101, 'requester_name': 'UCMTEST\\alice',
             'subject_cn': 'pend-a1.test.local', 'template': 'WebServer',
             'submitted_when': '01/07/2026 10:00'},
            {'request_id': 102, 'requester_name': 'UCMTEST\\bob',
             'subject_cn': 'pend-a2.test.local', 'template': 'Machine',
             'submitted_when': '02/07/2026 09:30'},
        ]

    def test_empty_csv_header_only(self, app, fake_ca):
        msca_id = _make_msca(app, 'CAC List Empty B')
        with app.app_context():
            from services.msca_service import MicrosoftCAService
            assert MicrosoftCAService.list_pending_requests(msca_id) == []

    def test_no_admin_channel_raises(self, app, fake_ca):
        msca_id = _make_msca(app, 'CAC List NoChan C', winrm=False)
        with app.app_context():
            from services.msca_service import MicrosoftCAService, MSCAAdminChannelError
            with pytest.raises(MSCAAdminChannelError):
                MicrosoftCAService.list_pending_requests(msca_id)


# ---------------------------------------------------------------------------
# Approve / deny — service level
# ---------------------------------------------------------------------------

class TestApproveDenyService:

    def test_approve_imports_issued_cert(self, app, fake_ca):
        msca_id = _make_msca(app, 'CAC Approve D')
        fake_ca.add_pending(201, 'appr-d.test.local')
        serial, _ = fake_ca.issue(201, 'appr-d.test.local')

        with app.app_context():
            from services.msca_service import MicrosoftCAService
            result = MicrosoftCAService.approve_request(msca_id, 201)

            assert result['success'] is True
            assert result['request_id'] == 201
            assert 'import_error' not in result
            assert result['imported_cert_id'] is not None

            from models import Certificate, db
            cert = db.session.get(Certificate, result['imported_cert_id'])
            assert cert is not None
            assert cert.source == 'msca'
            assert cert.subject_cn == 'appr-d.test.local'
            assert (cert.serial_number or '').lower() == serial

        # certutil got the resubmit for the right request id
        assert any('-resubmit 201' in s for s in fake_ca.calls)

    def test_approve_known_serial_no_duplicate(self, app, fake_ca):
        msca_id = _make_msca(app, 'CAC Approve Dup E')
        fake_ca.add_pending(202, 'appr-e.test.local')
        serial, pem = fake_ca.issue(202, 'appr-e.test.local')
        pre_id = _add_ucm_cert(app, msca_id, 'CAC Approve Dup E',
                               'appr-e.test.local', serial, pem)

        with app.app_context():
            from services.msca_service import MicrosoftCAService
            result = MicrosoftCAService.approve_request(msca_id, 202)

            assert result['success'] is True
            assert result['imported_cert_id'] is None
            assert 'import_error' not in result

            from models import Certificate
            matches = [c for c in Certificate.query.all()
                       if (c.serial_number or '').lower() == serial]
            assert len(matches) == 1
            assert matches[0].id == pre_id

    def test_approve_without_import(self, app, fake_ca):
        msca_id = _make_msca(app, 'CAC Approve NoImp F')
        fake_ca.add_pending(203, 'appr-f.test.local')
        # No cert registered: import_issued=False must never ask for it.

        with app.app_context():
            from services.msca_service import MicrosoftCAService
            result = MicrosoftCAService.approve_request(msca_id, 203,
                                                        import_issued=False)
            assert result['success'] is True
            assert result['imported_cert_id'] is None
        assert not any('RawCertificate' in s for s in fake_ca.calls)

    def test_deny_success(self, app, fake_ca):
        msca_id = _make_msca(app, 'CAC Deny G')
        fake_ca.add_pending(301, 'deny-g.test.local')

        with app.app_context():
            from services.msca_service import MicrosoftCAService
            result = MicrosoftCAService.deny_request(msca_id, 301)

        assert result['success'] is True
        assert result['request_id'] == 301
        assert 'denied' in result['output'].lower()
        assert any('-deny 301' in s for s in fake_ca.calls)

    @pytest.mark.parametrize('bad', ['abc', '1; certutil -x', '', '-1', '1.5'])
    def test_validate_request_id_rejects_non_integer(self, bad):
        from services.msca_service import MicrosoftCAService, MSCAAdminChannelError
        with pytest.raises(MSCAAdminChannelError):
            MicrosoftCAService._validate_request_id(bad)

    def test_validate_request_id_accepts_integer(self):
        from services.msca_service import MicrosoftCAService
        assert MicrosoftCAService._validate_request_id(42) == 42
        assert MicrosoftCAService._validate_request_id(' 42 ') == 42


# ---------------------------------------------------------------------------
# CA health — service level
# ---------------------------------------------------------------------------

class TestCaHealthService:

    def test_health_full_green_path(self, app, fake_ca, patched_health):
        msca_id = _make_msca(app, 'CAC Health H')
        fake_ca.add_pending(401, 'health-h1.test.local')
        fake_ca.add_pending(402, 'health-h2.test.local')

        with app.app_context():
            from services.msca_service import MicrosoftCAService
            health = MicrosoftCAService.ca_health(msca_id)

        assert health['certsvc_status'] == 'Running'
        assert health['pending_count'] == 2
        assert health['warnings'] == []

        assert health['ca_cert']['subject'] == 'CN=CAControl Root'
        assert health['ca_cert']['days_until_expiry'] > 3000
        assert health['ca_cert']['not_after']

        assert health['crl']['url'] == 'https://crl.test.local/fake.crl'
        assert health['crl']['revoked_count'] == 1
        assert health['crl']['expired'] is False
        assert health['crl']['last_update']
        assert health['crl']['next_update']

    def test_health_degraded_sources_populate_warnings(self, app, fake_ca,
                                                       monkeypatch):
        from services.msca.connection import MicrosoftCAConnectionMixin
        from services.msca.crl_sync import MicrosoftCACRLSyncMixin

        msca_id = _make_msca(app, 'CAC Health Warn I')
        fake_ca.add_pending(403, 'health-i.test.local')

        def boom(*args, **kwargs):
            raise RuntimeError('source down')
        monkeypatch.setattr(MicrosoftCAConnectionMixin, '_get_client',
                            staticmethod(boom))
        monkeypatch.setattr(MicrosoftCACRLSyncMixin, '_resolve_crl_url',
                            staticmethod(boom))

        with app.app_context():
            from services.msca_service import MicrosoftCAService
            health = MicrosoftCAService.ca_health(msca_id)

        # Broken sources degrade to warnings, the rest keeps working.
        assert health['certsvc_status'] == 'Running'
        assert health['pending_count'] == 1
        assert health['ca_cert'] is None
        assert health['crl'] is None
        assert any('CA certificate unavailable' in w for w in health['warnings'])
        assert any('CRL unavailable' in w for w in health['warnings'])

    def test_health_no_admin_channel_raises(self, app, fake_ca):
        msca_id = _make_msca(app, 'CAC Health NoChan J', winrm=False)
        with app.app_context():
            from services.msca_service import MicrosoftCAService, MSCAAdminChannelError
            with pytest.raises(MSCAAdminChannelError):
                MicrosoftCAService.ca_health(msca_id)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

class TestCaControlEndpoints:

    def test_get_pending(self, app, auth_client, fake_ca):
        msca_id = _make_msca(app, 'CAC EP Pending K')
        fake_ca.add_pending(501, 'ep-k.test.local')

        r = auth_client.get(f'{BASE}/{msca_id}/ca/pending')
        assert r.status_code == 200, r.data
        data = get_json(r)['data']
        assert len(data) == 1
        assert data[0]['request_id'] == 501
        assert data[0]['subject_cn'] == 'ep-k.test.local'
        assert data[0]['template'] == 'WebServer'
        assert data[0]['requester_name'] == 'UCMTEST\\alice'

    def test_get_health(self, app, auth_client, fake_ca, patched_health):
        msca_id = _make_msca(app, 'CAC EP Health L')
        r = auth_client.get(f'{BASE}/{msca_id}/ca/health')
        assert r.status_code == 200, r.data
        data = get_json(r)['data']
        assert data['certsvc_status'] == 'Running'
        assert data['pending_count'] == 0
        assert data['ca_cert']['subject'] == 'CN=CAControl Root'
        assert data['crl']['revoked_count'] == 1
        assert data['warnings'] == []

    def test_post_approve(self, app, auth_client, fake_ca):
        msca_id = _make_msca(app, 'CAC EP Approve M')
        fake_ca.add_pending(502, 'ep-m.test.local')
        serial, _ = fake_ca.issue(502, 'ep-m.test.local')

        r = post_json(auth_client, f'{BASE}/{msca_id}/ca/pending/502/approve')
        assert r.status_code == 200, r.data
        data = get_json(r)['data']
        assert data['success'] is True
        assert data['request_id'] == 502
        assert data['imported_cert_id'] is not None

        with app.app_context():
            from models import Certificate, db
            cert = db.session.get(Certificate, data['imported_cert_id'])
            assert cert.source == 'msca'
            assert (cert.serial_number or '').lower() == serial

    def test_post_deny(self, app, auth_client, fake_ca):
        msca_id = _make_msca(app, 'CAC EP Deny N')
        fake_ca.add_pending(503, 'ep-n.test.local')

        r = post_json(auth_client, f'{BASE}/{msca_id}/ca/pending/503/deny')
        assert r.status_code == 200, r.data
        data = get_json(r)['data']
        assert data['success'] is True
        assert data['request_id'] == 503

    def test_endpoints_400_without_admin_channel(self, app, auth_client, fake_ca):
        msca_id = _make_msca(app, 'CAC EP NoChan O', winrm=False)
        for method, url in (
            ('get', f'{BASE}/{msca_id}/ca/health'),
            ('get', f'{BASE}/{msca_id}/ca/pending'),
            ('post', f'{BASE}/{msca_id}/ca/pending/1/approve'),
            ('post', f'{BASE}/{msca_id}/ca/pending/1/deny'),
        ):
            r = getattr(auth_client, method)(url)
            assert r.status_code == 400, (url, r.data)
            assert 'admin channel' in get_json(r)['message'].lower()

    def test_endpoints_404_unknown_connection(self, auth_client, fake_ca):
        assert auth_client.get(f'{BASE}/999999/ca/health').status_code == 404
        assert auth_client.get(f'{BASE}/999999/ca/pending').status_code == 404
        assert auth_client.post(f'{BASE}/999999/ca/pending/1/approve').status_code == 404
        assert auth_client.post(f'{BASE}/999999/ca/pending/1/deny').status_code == 404

    def test_endpoints_require_auth(self, app, client, fake_ca):
        msca_id = _make_msca(app, 'CAC EP Anon P')
        assert client.get(f'{BASE}/{msca_id}/ca/health').status_code == 401
        assert client.get(f'{BASE}/{msca_id}/ca/pending').status_code == 401
        assert client.post(f'{BASE}/{msca_id}/ca/pending/1/approve').status_code == 401
        assert client.post(f'{BASE}/{msca_id}/ca/pending/1/deny').status_code == 401

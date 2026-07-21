"""
Microsoft CA inventory sync tests (#185 phase B)

The sync lists issued certs on the CA via certutil -view (CSV over the WinRM
admin channel), imports the ones UCM doesn't know (dedup by serial), and keeps
an incremental high-water mark (last_synced_request_id). The reconciliation
view is read-only. Here the WinRM layer is monkeypatched: the fake inspects
the certutil script to serve either the CSV listing or a single RawCertificate.
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
    # certutil prints serials in lowercase hex; the service compares lowercased.
    return format(serial, 'x'), pem


class FakeADCS:
    """Serves certutil -view output for a set of issued certs.

    rows: list of dicts {request_id, serial (hex lower), template, cn, pem}.
    """

    def __init__(self):
        self.rows = []

    def add(self, request_id, cn, template='WebServer'):
        serial, pem = _make_cert(cn)
        self.rows.append({'request_id': request_id, 'serial': serial,
                          'template': template, 'cn': cn, 'pem': pem})
        return serial

    def run_ps(self, msca, script):
        if 'RawCertificate' in script:
            req_id = int(re.search(r'RequestId=(\d+)', script).group(1))
            for row in self.rows:
                if row['request_id'] == req_id:
                    return f'Row 1:\n  RawCertificate:\n{row["pem"]}\nCertUtil: -view command completed successfully.\n'
            return 'CertUtil: no rows\n'
        # CSV listing, filtered on the RequestId>=N restriction
        start = int(re.search(r'RequestId>=(\d+)', script).group(1))
        lines = ['"ID de la demande","Numéro de série","Expiration","Modèle","Nom commun"']
        for row in self.rows:
            if row['request_id'] >= start:
                lines.append(
                    f'"{row["request_id"]}","{row["serial"]}","01/01/2030 12:00",'
                    f'"{row["template"]}","{row["cn"]}"'
                )
        return '\n'.join(lines) + '\n'


@pytest.fixture
def fake_ca(monkeypatch):
    """A FakeADCS instance wired into the WinRM admin channel."""
    from services.msca.admin_channel import MicrosoftCAAdminChannelMixin

    fake = FakeADCS()
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
            refid=f'inv-{cn[:10]}-{serial_hex_lower[:6]}',
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
# Service-level tests
# ---------------------------------------------------------------------------

class TestInventorySyncService:

    def test_imports_unknown_certs(self, app, fake_ca):
        msca_id = _make_msca(app, 'Inv Import A')
        s1 = fake_ca.add(5, 'inv-a1.test.local', template='WebServer')
        s2 = fake_ca.add(6, 'inv-a2.test.local', template='Machine')

        with app.app_context():
            from services.msca_service import MicrosoftCAService
            summary = MicrosoftCAService.inventory_sync(msca_id)

            assert summary['status'] == 'success'
            assert summary['imported'] == 2
            assert summary['skipped'] == 0
            assert summary['failed'] == 0
            assert summary['last_request_id'] == 6
            assert {c['serial_number'] for c in summary['certs']} == {s1, s2}

            from models import Certificate, db
            from models.msca import MicrosoftCA, MSCARequest

            cert = Certificate.query.filter(
                Certificate.serial_number == s1.upper()).one()
            assert cert.source == 'msca'
            assert cert.imported_from == 'msca:Inv Import A'
            assert cert.subject_cn == 'inv-a1.test.local'
            assert cert.crt is not None

            req = MSCARequest.query.filter_by(
                msca_id=msca_id, request_id=5).one()
            assert req.status == 'issued'
            assert req.cert_id == cert.id
            assert req.submitted_by == 'inventory'
            assert req.template == 'WebServer'

            msca = db.session.get(MicrosoftCA, msca_id)
            assert msca.last_synced_request_id == 6
            assert msca.last_inventory_sync_at is not None
            assert msca.last_inventory_sync_result.startswith('success')

    def test_dedup_by_serial_counts_skipped(self, app, fake_ca):
        msca_id = _make_msca(app, 'Inv Dedup B')
        known = fake_ca.add(10, 'inv-b-known.test.local')
        fake_ca.add(11, 'inv-b-new.test.local')
        # UCM already knows the first cert (same serial, uppercase in DB)
        row = fake_ca.rows[0]
        pre_id = _add_ucm_cert(app, msca_id, 'Inv Dedup B',
                               row['cn'], row['serial'], row['pem'])

        with app.app_context():
            from services.msca_service import MicrosoftCAService
            summary = MicrosoftCAService.inventory_sync(msca_id)

            assert summary['imported'] == 1
            assert summary['skipped'] == 1
            assert summary['certs'][0]['request_id'] == 11

            from models import Certificate
            matches = [c for c in Certificate.query.all()
                       if (c.serial_number or '').lower() == known]
            assert len(matches) == 1  # not re-imported
            assert matches[0].id == pre_id

    def test_dedup_by_swapped_serial(self, app, fake_ca):
        """certutil -view may print the serial with its byte pairs reversed
        (AD CS quirk) — a cert UCM knows under the straight byte order must
        not be re-imported as a duplicate."""
        msca_id = _make_msca(app, 'Inv Swap S')
        fake_ca.add(15, 'inv-s-known.test.local')
        row = fake_ca.rows[0]
        # UCM knows the cert under the straight serial…
        pre_id = _add_ucm_cert(app, msca_id, 'Inv Swap S',
                               row['cn'], row['serial'], row['pem'])
        # …but the CA listing shows the byte pairs reversed.
        s = row['serial'] if len(row['serial']) % 2 == 0 else '0' + row['serial']
        pairs = [s[i:i + 2] for i in range(0, len(s), 2)]
        row['serial'] = ''.join(reversed(pairs))

        with app.app_context():
            from services.msca_service import MicrosoftCAService
            summary = MicrosoftCAService.inventory_sync(msca_id)
            assert summary['imported'] == 0
            assert summary['skipped'] == 1

            from models import Certificate
            assert Certificate.query.filter(
                Certificate.subject_cn == 'inv-s-known.test.local').count() == 1
            assert Certificate.query.filter(
                Certificate.subject_cn == 'inv-s-known.test.local').one().id == pre_id

    def test_dedup_by_request_id(self, app, fake_ca):
        """A row whose RequestId is already tracked by UCM is skipped even if
        the serial comparison would miss (exact-link dedup)."""
        msca_id = _make_msca(app, 'Inv ReqId R')
        fake_ca.add(25, 'inv-r-known.test.local')
        row = fake_ca.rows[0]
        with app.app_context():
            from models import Certificate, db
            from models.msca import MSCARequest
            cert = Certificate(
                refid='inv-r-known', descr=f'MSCA: {row["cn"]}',
                crt=base64.b64encode(row['pem'].encode()).decode(),
                cert_type='server', subject=f'CN={row["cn"]}',
                subject_cn=row['cn'],
                serial_number='not-a-matching-serial',
                source='msca', imported_from='msca:Inv ReqId R',
            )
            db.session.add(cert)
            db.session.flush()
            db.session.add(MSCARequest(msca_id=msca_id, cert_id=cert.id,
                                       request_id=25, template='WebServer',
                                       status='issued'))
            db.session.commit()

        with app.app_context():
            from services.msca_service import MicrosoftCAService
            summary = MicrosoftCAService.inventory_sync(msca_id)
            assert summary['imported'] == 0
            assert summary['skipped'] == 1

    def test_incremental_high_water_mark_and_full_rescan(self, app, fake_ca):
        msca_id = _make_msca(app, 'Inv Incr C')
        fake_ca.add(20, 'inv-c1.test.local')
        fake_ca.add(21, 'inv-c2.test.local')

        with app.app_context():
            from services.msca_service import MicrosoftCAService

            first = MicrosoftCAService.inventory_sync(msca_id)
            assert first['imported'] == 2
            assert first['last_request_id'] == 21

            # Incremental: only RequestId>=21 is re-listed, already known.
            second = MicrosoftCAService.inventory_sync(msca_id)
            assert second['imported'] == 0
            assert second['skipped'] == 1
            assert second['last_request_id'] == 21

            # Full rescan lists everything again, dedup keeps imported at 0.
            full = MicrosoftCAService.inventory_sync(msca_id, full=True)
            assert full['imported'] == 0
            assert full['skipped'] == 2
            assert full['last_request_id'] == 21

    def test_no_admin_channel_raises(self, app, fake_ca):
        msca_id = _make_msca(app, 'Inv NoChan D', winrm=False)
        with app.app_context():
            from services.msca_service import MicrosoftCAService, MSCAAdminChannelError
            with pytest.raises(MSCAAdminChannelError):
                MicrosoftCAService.inventory_sync(msca_id)
            with pytest.raises(MSCAAdminChannelError):
                MicrosoftCAService.reconcile_inventory(msca_id)


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------

class TestInventoryEndpoints:

    def test_post_inventory_sync(self, app, auth_client, fake_ca):
        msca_id = _make_msca(app, 'Inv EP E')
        serial = fake_ca.add(30, 'inv-e1.test.local')

        r = post_json(auth_client, f'{BASE}/{msca_id}/inventory-sync', {'full': False})
        assert r.status_code == 200, r.data
        data = get_json(r)['data']
        assert data['status'] == 'success'
        assert data['imported'] == 1
        assert data['last_request_id'] == 30
        assert data['certs'][0]['serial_number'] == serial

    def test_post_inventory_sync_without_channel_400(self, app, auth_client, fake_ca):
        msca_id = _make_msca(app, 'Inv EP F', winrm=False)
        r = post_json(auth_client, f'{BASE}/{msca_id}/inventory-sync', {})
        assert r.status_code == 400
        assert 'admin channel' in get_json(r)['message'].lower()

    def test_get_reconciliation(self, app, auth_client, fake_ca):
        msca_id = _make_msca(app, 'Inv EP G')
        ca_serial = fake_ca.add(40, 'inv-g-caonly.test.local')
        ucm_serial, ucm_pem = _make_cert('inv-g-ucmonly.test.local')
        ucm_id = _add_ucm_cert(app, msca_id, 'Inv EP G',
                               'inv-g-ucmonly.test.local', ucm_serial, ucm_pem)

        r = auth_client.get(f'{BASE}/{msca_id}/reconciliation')
        assert r.status_code == 200, r.data
        data = get_json(r)['data']
        assert data['ca_total'] == 1
        assert data['ucm_total'] == 1
        assert len(data['ca_only']) == 1
        assert data['ca_only'][0]['serial_number'] == ca_serial
        assert data['ca_only'][0]['request_id'] == 40
        assert data['ca_only'][0]['subject_cn'] == 'inv-g-caonly.test.local'
        assert len(data['ucm_only']) == 1
        assert data['ucm_only'][0]['id'] == ucm_id
        assert data['ucm_only'][0]['subject_cn'] == 'inv-g-ucmonly.test.local'


class TestReconcileService:

    def test_reconcile_matches_are_excluded(self, app, fake_ca):
        """A cert known on both sides appears in neither ca_only nor ucm_only."""
        msca_id = _make_msca(app, 'Inv Rec H')
        fake_ca.add(50, 'inv-h-both.test.local')
        row = fake_ca.rows[0]
        _add_ucm_cert(app, msca_id, 'Inv Rec H', row['cn'], row['serial'], row['pem'])
        fake_ca.add(51, 'inv-h-caonly.test.local')

        with app.app_context():
            from services.msca_service import MicrosoftCAService
            result = MicrosoftCAService.reconcile_inventory(msca_id)

            assert result['ca_total'] == 2
            assert result['ucm_total'] == 1
            assert [r['request_id'] for r in result['ca_only']] == [51]
            assert result['ucm_only'] == []

    def test_reconcile_matches_swapped_serials(self, app, fake_ca):
        """Reconciliation must match certs even when certutil reports the
        serial with reversed byte pairs."""
        msca_id = _make_msca(app, 'Inv Rec I')
        fake_ca.add(60, 'inv-i-both.test.local')
        row = fake_ca.rows[0]
        _add_ucm_cert(app, msca_id, 'Inv Rec I', row['cn'], row['serial'], row['pem'])
        s = row['serial'] if len(row['serial']) % 2 == 0 else '0' + row['serial']
        pairs = [s[i:i + 2] for i in range(0, len(s), 2)]
        row['serial'] = ''.join(reversed(pairs))

        with app.app_context():
            from services.msca_service import MicrosoftCAService
            result = MicrosoftCAService.reconcile_inventory(msca_id)
            assert result['ca_only'] == []
            assert result['ucm_only'] == []

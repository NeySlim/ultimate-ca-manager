"""
Dashboard & Stats API Tests — /api/v2/dashboard/* and /api/v2/stats/*

Tests all dashboard endpoints:
- GET /api/v2/stats/overview — public stats (no auth)
- GET /api/v2/dashboard/stats — dashboard statistics
- GET /api/v2/dashboard/recent-cas — recently created CAs
- GET /api/v2/dashboard/expiring-certs — expiring certificates
- GET /api/v2/dashboard/activity — recent activity/audit entries
- GET /api/v2/dashboard/certificate-trend — cert creation trend
- GET /api/v2/dashboard/system-status — system health (no auth)

Uses shared conftest fixtures: app, client, auth_client, create_ca, create_cert.
"""
import json
import pytest
from tests.conftest import get_json, assert_success, assert_error

CONTENT_JSON = 'application/json'
STATS_OVERVIEW = '/api/v2/stats/overview'
DASH = '/api/v2/dashboard'

# ============================================================
# Auth Required — authenticated endpoints must reject unauthed
# ============================================================

class TestAuthRequired:
    """Dashboard endpoints that require auth must return 401."""

    def test_dashboard_stats_requires_auth(self, client):
        response = client.get(f'{DASH}/stats')
        assert response.status_code == 401, response.data

    def test_recent_cas_requires_auth(self, client):
        response = client.get(f'{DASH}/recent-cas')
        assert response.status_code == 401, response.data

    def test_expiring_certs_requires_auth(self, client):
        response = client.get(f'{DASH}/expiring-certs')
        assert response.status_code == 401, response.data

    def test_activity_requires_auth(self, client):
        response = client.get(f'{DASH}/activity')
        assert response.status_code == 401, response.data

    def test_certificate_trend_requires_auth(self, client):
        response = client.get(f'{DASH}/certificate-trend')
        assert response.status_code == 401, response.data


# ============================================================
# Public Endpoints (no auth)
# ============================================================

class TestPublicEndpoints:
    """Endpoints now require authentication (security hardening)."""

    def test_stats_overview_requires_auth(self, client):
        r = client.get(STATS_OVERVIEW)
        assert r.status_code == 401, r.data

    def test_stats_overview_with_auth(self, auth_client):
        r = auth_client.get(STATS_OVERVIEW)
        data = assert_success(r)
        assert 'total_cas' in data
        assert 'total_certs' in data
        assert 'active_users' in data

    def test_stats_overview_returns_integers(self, auth_client):
        r = auth_client.get(STATS_OVERVIEW)
        data = assert_success(r)
        assert isinstance(data['total_cas'], int)
        assert isinstance(data['total_certs'], int)

    def test_system_status_requires_auth(self, client):
        r = client.get(f'{DASH}/system-status')
        assert r.status_code == 401, r.data

    def test_system_status_with_auth(self, auth_client):
        r = auth_client.get(f'{DASH}/system-status')
        data = assert_success(r)
        assert 'database' in data
        assert 'core' in data
        assert data['database']['status'] in ('online', 'offline')
        assert data['core']['status'] == 'online'

    def test_system_status_has_services(self, auth_client):
        r = auth_client.get(f'{DASH}/system-status')
        data = assert_success(r)
        for svc in ('database', 'acme', 'scep', 'core'):
            assert svc in data
            assert 'status' in data[svc]
            assert 'message' in data[svc]


# ============================================================
# Dashboard Stats
# ============================================================

class TestDashboardStats:
    """GET /api/v2/dashboard/stats"""

    def test_stats_returns_expected_keys(self, auth_client):
        r = auth_client.get(f'{DASH}/stats')
        data = assert_success(r)
        for key in ('total_cas', 'total_certificates', 'expiring_soon', 'revoked', 'pending_csrs'):
            assert key in data, f'Missing key: {key}'

    def test_stats_values_are_integers(self, auth_client):
        r = auth_client.get(f'{DASH}/stats')
        data = assert_success(r)
        assert isinstance(data['total_cas'], int)
        assert isinstance(data['total_certificates'], int)
        assert isinstance(data['expiring_soon'], int)
        assert isinstance(data['revoked'], int)

    def test_stats_reflect_created_ca(self, auth_client, create_ca):
        """After creating a CA, dashboard stats should count it."""
        r1 = auth_client.get(f'{DASH}/stats')
        before = assert_success(r1)['total_cas']

        create_ca(cn='Dashboard Stats Test CA')

        r2 = auth_client.get(f'{DASH}/stats')
        after = assert_success(r2)['total_cas']
        assert after > before

    def test_stats_reflect_created_cert(self, auth_client, create_cert):
        """After creating a cert, dashboard stats should count it."""
        r1 = auth_client.get(f'{DASH}/stats')
        before = assert_success(r1)['total_certificates']

        create_cert(cn='dashboard-stats-test.example.com')

        r2 = auth_client.get(f'{DASH}/stats')
        after = assert_success(r2)['total_certificates']
        assert after > before


# ============================================================
# Recent CAs
# ============================================================

class TestRecentCAs:
    """GET /api/v2/dashboard/recent-cas"""

    def test_recent_cas_returns_list(self, auth_client):
        r = auth_client.get(f'{DASH}/recent-cas')
        data = assert_success(r)
        assert isinstance(data, list)

    def test_recent_cas_limit(self, auth_client):
        r = auth_client.get(f'{DASH}/recent-cas?limit=2')
        data = assert_success(r)
        assert len(data) <= 2

    def test_recent_cas_entry_structure(self, auth_client, create_ca):
        create_ca(cn='Recent CA Structure Test')
        r = auth_client.get(f'{DASH}/recent-cas?limit=1')
        data = assert_success(r)
        assert len(data) >= 1
        entry = data[0]
        assert 'id' in entry
        assert 'common_name' in entry or 'descr' in entry


# ============================================================
# Expiring Certificates
# ============================================================

class TestExpiringCerts:
    """GET /api/v2/dashboard/expiring-certs"""

    def test_expiring_certs_returns_list(self, auth_client):
        r = auth_client.get(f'{DASH}/expiring-certs')
        data = assert_success(r)
        assert isinstance(data, list)

    def test_expiring_certs_limit(self, auth_client):
        r = auth_client.get(f'{DASH}/expiring-certs?limit=3')
        data = assert_success(r)
        assert len(data) <= 3

    def test_expiring_certs_after_create(self, auth_client, create_cert):
        """A newly created cert should appear in expiring list (sorted by soonest)."""
        create_cert(cn='expiring-test.example.com', validity_days=30)
        r = auth_client.get(f'{DASH}/expiring-certs?limit=50')
        data = assert_success(r)
        assert isinstance(data, list)
        # Should have at least the cert we just created
        assert len(data) >= 1
        # Each entry should have valid_to
        for cert in data:
            assert 'valid_to' in cert

    def test_expiring_certs_flags_the_configured_tsa_signer(
        self, app, auth_client, create_cert
    ):
        """#312: the row for the configured dedicated signer carries is_tsa_signer."""
        from models import SystemConfig, db

        signer = create_cert(cn='dash-tsa-signer', validity_days=25,
                             extra_ekus=['1.3.6.1.5.5.7.3.8'])
        plain = create_cert(cn='dash-plain-cert', validity_days=25)
        try:
            with app.app_context():
                row = (SystemConfig.query.filter_by(key='tsa_signer_cert_refid').first()
                       or SystemConfig(key='tsa_signer_cert_refid'))
                row.value = signer['refid']
                db.session.add(row)
                db.session.commit()

            data = assert_success(auth_client.get(f'{DASH}/expiring-certs?limit=100'))
            by_refid = {c['refid']: c for c in data}
            assert by_refid[signer['refid']]['is_tsa_signer'] is True
            assert by_refid[plain['refid']]['is_tsa_signer'] is False
        finally:
            with app.app_context():
                SystemConfig.query.filter_by(
                    key='tsa_signer_cert_refid'
                ).delete(synchronize_session=False)
                db.session.commit()


class TestWebhooksSystemStatus:
    """GET /api/v2/dashboard/system-status — the `webhooks` service entry.

    Regression: the probe queried a nonexistent `active` column, so the badge
    always fell back to "Not configured", and on PostgreSQL the failed
    statement aborted the transaction for every later probe in the request.
    """

    def _webhooks(self, auth_client):
        return assert_success(auth_client.get(f'{DASH}/system-status'))['webhooks']

    def _cleanup(self, app, ids):
        from services.webhook_service import WebhookEndpoint
        from models import db
        with app.app_context():
            WebhookEndpoint.query.filter(WebhookEndpoint.id.in_(ids)).delete(
                synchronize_session=False)
            db.session.commit()

    def test_enabled_endpoint_reports_online_and_next_probes_survive(
        self, app, auth_client
    ):
        from services.webhook_service import WebhookEndpoint
        from models import db
        with app.app_context():
            ep = WebhookEndpoint(name='dash-wh-on', url='https://wh.example/hook',
                                 enabled=True)
            db.session.add(ep)
            db.session.commit()
            ep_id = ep.id
        try:
            data = assert_success(auth_client.get(f'{DASH}/system-status'))
            assert data['webhooks']['status'] == 'online'
            assert 'active endpoint' in data['webhooks']['message']
            # the probes that run after webhooks in the same request must not
            # be poisoned by a failed statement (PostgreSQL aborts the tx)
            assert data['tsa']['message'] != 'Status unavailable'
            assert data['core']['status'] == 'online'
        finally:
            self._cleanup(app, [ep_id])

    def test_disabled_endpoint_reports_warning(self, app, auth_client):
        from services.webhook_service import WebhookEndpoint
        from models import db
        with app.app_context():
            ep = WebhookEndpoint(name='dash-wh-off', url='https://wh.example/hook',
                                 enabled=False)
            db.session.add(ep)
            db.session.commit()
            ep_id = ep.id
        try:
            wh = self._webhooks(auth_client)
            assert wh['status'] in ('warning', 'online')  # online if other tests left enabled rows
            assert wh['message'] != 'Not configured'
        finally:
            self._cleanup(app, [ep_id])


class TestTsaSystemStatus:
    """GET /api/v2/dashboard/system-status — the `tsa` service entry (#312)."""

    TS_OID = '1.3.6.1.5.5.7.3.8'

    @pytest.fixture(autouse=True)
    def _isolate_tsa_config(self, app):
        """The session DB is shared; make each case start from no TSA rows so a
        stray tsa_ca_refid / tsa_enabled from elsewhere cannot flip the result."""
        self._clear(app)
        yield
        self._clear(app)

    def _set(self, app, **cfg):
        from models import SystemConfig, db
        with app.app_context():
            for k, v in cfg.items():
                row = SystemConfig.query.filter_by(key=k).first() or SystemConfig(key=k)
                row.value = v
                db.session.add(row)
            db.session.commit()

    def _clear(self, app):
        from models import SystemConfig, db
        with app.app_context():
            SystemConfig.query.filter(
                SystemConfig.key.in_([
                    'tsa_enabled', 'tsa_signer_cert_refid', 'tsa_ca_refid',
                ])
            ).delete(synchronize_session=False)
            db.session.commit()

    def _ca_refid(self, app, create_ca, cn):
        from models import db, CA
        ca = create_ca(cn=cn)
        with app.app_context():
            return db.session.get(CA, ca['id']).refid

    def _tsa(self, auth_client):
        return assert_success(auth_client.get(f'{DASH}/system-status'))['tsa']

    def test_disabled_when_tsa_not_enabled(self, app, auth_client):
        self._set(app, tsa_enabled='false')
        try:
            assert self._tsa(auth_client)['status'] == 'offline'
        finally:
            self._clear(app)

    def test_online_ca_certificate_when_no_dedicated_signer(
        self, app, auth_client, create_ca
    ):
        refid = self._ca_refid(app, create_ca, 'status-tsa-ca')
        self._set(app, tsa_enabled='true', tsa_signer_cert_refid='',
                  tsa_ca_refid=refid)
        try:
            tsa = self._tsa(auth_client)
            assert tsa['status'] == 'online'
            assert 'CA certificate' in tsa['message']
        finally:
            self._clear(app)

    def test_offline_when_enabled_but_no_tsa_ca_configured(self, app, auth_client):
        """Enabled + no dedicated signer + no tsa_ca_refid: /tsa 503s, so must
        the widget. Previously it reported online (#315 review, case 1a)."""
        self._set(app, tsa_enabled='true', tsa_signer_cert_refid='')
        try:
            assert self._tsa(auth_client)['status'] == 'offline'
        finally:
            self._clear(app)

    def test_grandfathered_missing_enabled_row_mirrors_protocol(
        self, app, auth_client, create_ca
    ):
        """No tsa_enabled row (pre-2.200) + a configured TSA CA: tsa_protocol.py
        treats the missing row as enabled, so the widget must too, not offline
        (#315 review, case 1b)."""
        refid = self._ca_refid(app, create_ca, 'status-tsa-grandfathered-ca')
        self._set(app, tsa_ca_refid=refid)  # note: tsa_enabled deliberately unset
        try:
            assert self._tsa(auth_client)['status'] == 'online'
        finally:
            self._clear(app)

    def test_warning_when_signer_is_near_expiry(self, app, auth_client, create_cert):
        signer = create_cert(cn='status-tsa-near', validity_days=10,
                             extra_ekus=[self.TS_OID])
        self._set(app, tsa_enabled='true', tsa_signer_cert_refid=signer['refid'])
        try:
            tsa = self._tsa(auth_client)
            assert tsa['status'] == 'warning'
            assert 'expires' in tsa['message']
        finally:
            self._clear(app)

    def test_online_when_signer_is_healthy(self, app, auth_client, create_cert):
        signer = create_cert(cn='status-tsa-ok', validity_days=365,
                             extra_ekus=[self.TS_OID])
        self._set(app, tsa_enabled='true', tsa_signer_cert_refid=signer['refid'])
        try:
            assert self._tsa(auth_client)['status'] == 'online'
        finally:
            self._clear(app)

    def test_offline_when_signer_is_revoked(self, app, auth_client, create_cert):
        from models import Certificate, db

        signer = create_cert(cn='status-tsa-revoked', validity_days=200,
                             extra_ekus=[self.TS_OID])
        self._set(app, tsa_enabled='true', tsa_signer_cert_refid=signer['refid'])
        try:
            with app.app_context():
                row = Certificate.query.filter_by(refid=signer['refid']).first()
                row.revoked = True
                db.session.commit()
            tsa = self._tsa(auth_client)
            assert tsa['status'] == 'offline'
            # Coarse, client-safe class only — no refid, no exception text
            # (#315 review, case 3).
            assert 'revoked' in tsa['message'].lower()
            assert signer['refid'] not in tsa['message']
        finally:
            self._clear(app)

    def test_offline_message_does_not_leak_internal_detail(
        self, app, auth_client, create_cert
    ):
        """The key-loading / parse failure classes are the ones whose
        TSAConfigurationError embeds exception text; the widget must map them to
        a coarse reason and never forward refid or a traceback (#315 review,
        case 3)."""
        from models import Certificate, db

        signer = create_cert(cn='status-tsa-nokey', validity_days=200,
                             extra_ekus=[self.TS_OID])
        self._set(app, tsa_enabled='true', tsa_signer_cert_refid=signer['refid'])
        try:
            with app.app_context():
                row = Certificate.query.filter_by(refid=signer['refid']).first()
                row.prv = None  # key no longer held by UCM
                db.session.commit()
            tsa = self._tsa(auth_client)
            assert tsa['status'] == 'offline'
            assert 'key' in tsa['message'].lower()
            assert signer['refid'] not in tsa['message']
            assert 'Traceback' not in tsa['message']
        finally:
            self._clear(app)

    def test_resolution_error_is_not_reported_as_online(
        self, app, auth_client, create_ca, monkeypatch
    ):
        """A crash in the status check is exactly when the widget must not
        claim health (#315 review, case 2)."""
        import services.tsa_service as tsa_service

        refid = self._ca_refid(app, create_ca, 'status-tsa-boom-ca')
        self._set(app, tsa_enabled='true', tsa_ca_refid=refid)

        def _boom():
            raise RuntimeError('resolver blew up')

        monkeypatch.setattr(tsa_service, 'describe_configured_signer', _boom)
        tsa = self._tsa(auth_client)
        assert tsa['status'] != 'online'


# ============================================================
# Activity Log
# ============================================================

class TestActivityLog:
    """GET /api/v2/dashboard/activity"""

    def test_activity_returns_structure(self, auth_client):
        r = auth_client.get(f'{DASH}/activity')
        data = assert_success(r)
        assert 'activity' in data
        assert isinstance(data['activity'], list)

    def test_activity_limit(self, auth_client):
        r = auth_client.get(f'{DASH}/activity?limit=5')
        data = assert_success(r)
        assert len(data['activity']) <= 5

    def test_activity_entry_structure(self, auth_client):
        """Activity entries should have type, action, message, timestamp, user."""
        r = auth_client.get(f'{DASH}/activity?limit=5')
        data = assert_success(r)
        if data['activity']:
            entry = data['activity'][0]
            for key in ('type', 'action', 'message', 'timestamp', 'user'):
                assert key in entry, f'Missing key: {key}'


# ============================================================
# Certificate Trend
# ============================================================

class TestCertificateTrend:
    """GET /api/v2/dashboard/certificate-trend"""

    def test_trend_returns_structure(self, auth_client):
        r = auth_client.get(f'{DASH}/certificate-trend')
        data = assert_success(r)
        assert 'trend' in data
        assert isinstance(data['trend'], list)

    def test_trend_default_7_days(self, auth_client):
        r = auth_client.get(f'{DASH}/certificate-trend')
        data = assert_success(r)
        assert len(data['trend']) == 7

    def test_trend_custom_days(self, auth_client):
        r = auth_client.get(f'{DASH}/certificate-trend?days=14')
        data = assert_success(r)
        assert len(data['trend']) == 14

    def test_trend_entry_has_fields(self, auth_client):
        r = auth_client.get(f'{DASH}/certificate-trend?days=3')
        data = assert_success(r)
        assert len(data['trend']) == 3
        entry = data['trend'][0]
        for key in ('name', 'date', 'issued', 'revoked', 'expired'):
            assert key in entry, f'Missing key: {key}'

    def test_trend_clamped_max_90(self, auth_client):
        r = auth_client.get(f'{DASH}/certificate-trend?days=200')
        data = assert_success(r)
        assert len(data['trend']) <= 90


# ============================================================
# System status reflects the real SCEP / SMTP configuration (#328, #329)
# ============================================================

def _set_config(app, key, value):
    from models import db, SystemConfig
    with app.app_context():
        row = SystemConfig.query.filter_by(key=key).first()
        if value is None:
            if row:
                db.session.delete(row)
        elif row:
            row.value = value
        else:
            db.session.add(SystemConfig(key=key, value=value))
        db.session.commit()


@pytest.fixture
def scep_config(app):
    """Set SCEP config keys for a test, restore the previous values after."""
    from models import SystemConfig
    keys = ('scep_enabled', 'scep_ca_id')
    with app.app_context():
        saved = {k: (SystemConfig.query.filter_by(key=k).first() or SystemConfig()).value
                 for k in keys}
    def _set(**values):
        for k, v in values.items():
            _set_config(app, k, v)
    yield _set
    for k in keys:
        _set_config(app, k, saved[k])


@pytest.fixture
def smtp_config(app):
    """Replace the smtp_config row for a test, remove it after."""
    from models import db
    from models.email_notification import SMTPConfig
    def _set(**fields):
        with app.app_context():
            SMTPConfig.query.delete()
            if fields:
                db.session.add(SMTPConfig(**fields))
            db.session.commit()
    yield _set
    with app.app_context():
        SMTPConfig.query.delete()
        db.session.commit()


def _status(auth_client, service):
    data = assert_success(auth_client.get(f'{DASH}/system-status'))
    return data[service]['status'], data[service]['message']


class TestSystemStatusScep:
    """#328: the SCEP tile used to be hardcoded 'online'."""

    def test_disabled_reports_offline(self, auth_client, scep_config):
        scep_config(scep_enabled='false', scep_ca_id=None)
        assert _status(auth_client, 'scep') == ('offline', 'Disabled')

    def test_enabled_without_ca_is_a_warning(self, auth_client, scep_config):
        scep_config(scep_enabled='true', scep_ca_id=None)
        assert _status(auth_client, 'scep') == ('warning', 'Enabled, no CA assigned')

    def test_default_without_key_is_enabled(self, auth_client, scep_config):
        """No scep_enabled row = enabled, like the protocol endpoint."""
        scep_config(scep_enabled=None, scep_ca_id=None)
        assert _status(auth_client, 'scep')[0] == 'warning'

    def test_enabled_with_ca_is_online(self, auth_client, scep_config, create_ca):
        ca = create_ca(cn='SCEP status CA')
        scep_config(scep_enabled='true', scep_ca_id=str(ca['id']))
        assert _status(auth_client, 'scep') == ('online', 'Configured')

    def test_dangling_ca_id_is_a_warning(self, auth_client, scep_config):
        scep_config(scep_enabled='true', scep_ca_id='999999')
        assert _status(auth_client, 'scep') == ('warning', 'Enabled, no CA assigned')

    def test_any_value_but_true_disables(self, auth_client, scep_config):
        """The endpoint only honours the literal 'true'; so must the tile."""
        scep_config(scep_enabled='0', scep_ca_id=None)
        assert _status(auth_client, 'scep') == ('offline', 'Disabled')

    def test_ec_ca_is_not_usable(self, app, auth_client, scep_config, create_ca):
        """SCEP decrypts the request envelope with an RSA key only."""
        from api.scep_protocol import get_scep_service
        ca = create_ca(cn='SCEP status EC CA', keyType='EC', keySize='P-256')
        scep_config(scep_enabled='true', scep_ca_id=str(ca['id']))
        assert _status(auth_client, 'scep') == ('warning', 'Enabled, CA not usable')
        with app.app_context():
            service, error = get_scep_service()
        assert service is None and 'RSA key' in error

    def test_offline_ca_is_not_usable(self, app, auth_client, scep_config, create_ca):
        from models import db, CA
        ca = create_ca(cn='SCEP offline CA')
        scep_config(scep_enabled='true', scep_ca_id=str(ca['id']))
        with app.app_context():
            row = db.session.get(CA, ca['id'])
            row.offline = True
            db.session.commit()
        try:
            assert _status(auth_client, 'scep') == ('warning', 'Enabled, CA not usable')
        finally:
            with app.app_context():
                row = db.session.get(CA, ca['id'])
                row.offline = False
                db.session.commit()

    def test_profile_on_offline_ca_is_not_counted(self, app, auth_client, scep_config, create_ca):
        from models import db, CA
        from models.scep import ScepProfile
        ca = create_ca(cn='SCEP profile offline CA')
        scep_config(scep_enabled='true', scep_ca_id=None)
        with app.app_context():
            ca_row = db.session.get(CA, ca['id'])
            ca_row.offline = True
            profile = ScepProfile(name='offline-profile', url_slug='offline-profile',
                                  ca_refid=ca_row.refid, enabled=True)
            db.session.add(profile)
            db.session.commit()
            pid = profile.id
        try:
            assert _status(auth_client, 'scep') == ('warning', 'Enabled, CA not usable')
        finally:
            with app.app_context():
                db.session.delete(db.session.get(ScepProfile, pid))
                db.session.get(CA, ca['id']).offline = False
                db.session.commit()

    def test_enabled_profile_counts_as_configured(self, app, auth_client, scep_config, create_ca):
        from models import db, CA
        from models.scep import ScepProfile
        ca = create_ca(cn='SCEP profile status CA')
        scep_config(scep_enabled='true', scep_ca_id=None)
        with app.app_context():
            ca_row = db.session.get(CA, ca['id'])
            profile = ScepProfile(name='status-profile', url_slug='status-profile',
                                  ca_refid=ca_row.refid, enabled=True)
            db.session.add(profile)
            db.session.commit()
            pid = profile.id
        try:
            assert _status(auth_client, 'scep') == ('online', '1 profile(s)')
        finally:
            with app.app_context():
                db.session.delete(db.session.get(ScepProfile, pid))
                db.session.commit()


class TestSystemStatusSmtp:
    """#329: the SMTP tile read system_config keys nothing writes."""

    def test_no_row_is_not_configured(self, auth_client, smtp_config):
        smtp_config()
        assert _status(auth_client, 'smtp') == ('offline', 'Not configured')

    def test_working_setup_is_online(self, auth_client, smtp_config):
        smtp_config(smtp_host='mail.example.test', smtp_port=25, smtp_from='ucm@example.test',
                    smtp_auth=False, enabled=True)
        assert _status(auth_client, 'smtp') == ('online', 'Host: mail.example.test')

    def test_host_set_but_disabled_is_a_warning(self, auth_client, smtp_config):
        smtp_config(smtp_host='mail.example.test', smtp_port=25, smtp_from='ucm@example.test',
                    enabled=False)
        assert _status(auth_client, 'smtp') == ('warning', 'Configured but disabled')

    def test_missing_from_address_is_a_warning(self, auth_client, smtp_config):
        smtp_config(smtp_host='mail.example.test', smtp_port=25, smtp_from='', enabled=True)
        assert _status(auth_client, 'smtp')[0] == 'warning'


class TestForgotPasswordUsesSmtpConfig:
    """#329: the same stale key made every reset request answer 503."""

    def test_configured_smtp_lets_the_request_through(self, client, app, smtp_config):
        smtp_config(smtp_host='mail.example.test', smtp_port=25, smtp_from='ucm@example.test',
                    enabled=True)
        r = client.post('/api/v2/auth/forgot-password', json={'email': 'nobody@example.com'})
        assert r.status_code == 200

    def test_unconfigured_smtp_still_refuses(self, client, smtp_config):
        smtp_config()
        r = client.post('/api/v2/auth/forgot-password', json={'email': 'nobody@example.com'})
        assert r.status_code == 503

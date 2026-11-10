"""Discovered certificates store notBefore/notAfter as naive UTC like the rest of the schema,
whatever offset the probe reports and whatever TimeZone the PostgreSQL session runs in."""
import os
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from models import DiscoveredCertificate, ScanRun, db
from services.discovery import DiscoveryService
from utils.datetime_utils import utc_now

_PG_URL = os.environ.get('UCM_TEST_PG_URL')

# +02:00 on the wire: 2026-01-01T02:00+02:00 is 2026-01-01T00:00 UTC
NOT_BEFORE_WIRE = '2026-01-01T02:00:00+02:00'
NOT_BEFORE_UTC = datetime(2026, 1, 1, 0, 0, 0)


def _scan_one(monkeypatch, host, not_after_wire):
    def fake_probe(self, h, port, timeout=None, resolve_dns=False, sni_hostname=None):
        if sni_hostname or h != host:
            return {'target': h, 'port': port, 'error': 'refused', 'error_type': 'refused'}
        return {'target': h, 'port': port, 'subject': 'CN=ts.test', 'issuer': 'CN=Test CA',
                'serial_number': '1A', 'not_before': NOT_BEFORE_WIRE, 'not_after': not_after_wire,
                'fingerprint_sha256': uuid.uuid4().hex * 2,
                'pem_certificate': '-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----',
                'san_dns_names': [], 'san_ip_addresses': [], 'san_emails': [], 'san_uris': []}
    for name in ('on_discovery_scan_started', 'on_discovery_scan_progress',
                 'on_discovery_scan_complete', 'on_discovery_new_cert', 'on_discovery_cert_changed'):
        monkeypatch.setattr(f'websocket.emitters.{name}', lambda *a, **k: None)
    monkeypatch.setattr(DiscoveryService, 'probe_tls', fake_probe)
    monkeypatch.setattr(DiscoveryService, '_send_notifications', lambda self, *a, **k: None)
    run = ScanRun(total_targets=1, triggered_by='manual')
    db.session.add(run)
    db.session.commit()
    DiscoveryService()._do_scan(run.id, [(host, 443)], None, timeout=1, max_workers=1)
    db.session.expire_all()
    return DiscoveredCertificate.query.filter_by(target=host).one()


def _check(monkeypatch):
    host = f'192.0.2.{uuid.uuid4().int % 200 + 1}'
    soon = (utc_now() + timedelta(days=10)).replace(microsecond=0)
    before = DiscoveryService().get_stats()['expiring_soon']
    row = _scan_one(monkeypatch, host, soon.isoformat() + '+00:00')
    try:
        assert row.not_before == NOT_BEFORE_UTC and row.not_before.tzinfo is None
        assert row.not_after == soon
        # the "expires within 30 days" count sees it, with a session zone far from UTC
        assert DiscoveryService().get_stats()['expiring_soon'] == before + 1
    finally:
        db.session.delete(row)
        db.session.commit()


def test_dates_are_stored_as_naive_utc(app, monkeypatch):
    with app.app_context():
        _check(monkeypatch)


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_dates_are_stored_as_naive_utc_under_a_foreign_session_timezone(app, monkeypatch):
    from tests.test_scheduled_claims_pg import _pg
    with _pg(app), app.app_context():
        for zone in ('Pacific/Auckland', 'America/Los_Angeles'):
            db.session.execute(text(f"SET TIME ZONE '{zone}'"))
            _check(monkeypatch)


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_expiry_window_ignores_the_session_timezone(app):
    from models import ScanProfile
    from tests.test_scheduled_claims_pg import _pg
    with _pg(app), app.app_context():
        db.session.execute(text("SET TIME ZONE 'Pacific/Auckland'"))
        profile = ScanProfile(name=f'win-{uuid.uuid4().hex[:8]}', targets='["example.test"]')
        db.session.add(profile)
        db.session.commit()
        row = DiscoveredCertificate(
            target=f'192.0.2.{uuid.uuid4().int % 200 + 1}', port=443, scan_profile_id=profile.id,
            fingerprint_sha256=uuid.uuid4().hex * 2,
            not_after=(utc_now() + timedelta(days=30, hours=6)).replace(microsecond=0))
        db.session.add(row)
        db.session.commit()
        try:
            assert DiscoveryService._expiring_in_window(profile.id)[0] == 0
        finally:
            db.session.delete(row)
            db.session.delete(profile)
            db.session.commit()


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_stats_expiring_count_ignores_the_session_timezone(app):
    from models import ScanProfile
    from tests.test_scheduled_claims_pg import _pg
    with _pg(app), app.app_context():
        db.session.execute(text("SET TIME ZONE 'Pacific/Auckland'"))
        profile = ScanProfile(name=f'stat-{uuid.uuid4().hex[:8]}', targets='["example.test"]')
        db.session.add(profile)
        db.session.commit()
        before = DiscoveryService().get_stats()['expiring_soon']
        # 30 days 6 hours out is beyond the window in UTC, inside it if read in Auckland time
        row = DiscoveredCertificate(
            target=f'192.0.2.{uuid.uuid4().int % 200 + 1}', port=443, scan_profile_id=profile.id,
            fingerprint_sha256=uuid.uuid4().hex * 2,
            not_after=(utc_now() + timedelta(days=30, hours=6)).replace(microsecond=0))
        db.session.add(row)
        db.session.commit()
        try:
            assert DiscoveryService().get_stats()['expiring_soon'] - before == 0
        finally:
            db.session.delete(row)
            db.session.delete(profile)
            db.session.commit()

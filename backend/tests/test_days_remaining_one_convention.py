"""Every producer of "days left" answers the same number.

`utils/days_remaining` settled the rule: time left rounds up, time past rounds
down, and a row with no date answers None. Four places still computed their
own, three of them with `timedelta.days`, which floors. The visible cost was
at the boundary: a certificate expiring in twelve hours read 1 on the list and
0 in the expiry pass, where `d > 0` gates the webhook, so the last day before
expiry emitted nothing at all.
"""
from datetime import timedelta

import pytest

from utils.datetime_utils import utc_now
from utils.days_remaining import days_remaining


@pytest.fixture()
def twelve_hours_left():
    now = utc_now()
    return now, now + timedelta(hours=12)


class TestTheHelperIsTheRule:
    def test_time_left_rounds_up(self, twelve_hours_left):
        now, valid_to = twelve_hours_left
        assert days_remaining(valid_to, now) == 1

    def test_time_past_rounds_down(self):
        now = utc_now()
        assert days_remaining(now - timedelta(hours=12), now) == -1

    def test_no_date_has_no_answer(self):
        assert days_remaining(None) is None


class _Thresholds:
    """The scheduler reads a config object; only these fields are used."""

    thresholds = [1, 7, 30]
    include_revoked = False


class TestTheProducersAgree:
    def test_the_expiry_pass_sees_the_last_day(self, app, create_cert):
        """`d > 0` gates the expiring webhook; a floor made it 0."""
        from models import Certificate, db
        from services.expiry_alert_service import get_expiring_certificates

        cert = create_cert(cn='last-day-probe.example')
        with app.app_context():
            row = db.session.get(Certificate, cert['id'])
            row.valid_to = utc_now() + timedelta(hours=12)
            db.session.commit()

            listed = [c for c in get_expiring_certificates(days=30)
                      if c['id'] == cert['id']]
            assert listed, 'the certificate should be listed as expiring'
            assert listed[0]['days_until_expiry'] == 1

    def test_the_notification_scheduler_counts_the_last_day(self, app, create_cert):
        """The tightest threshold fires on the last day, not the day after."""
        import json
        from models import Certificate, db
        from models.email_notification import NotificationConfig
        from services.notification.scheduler import NotificationSchedulerMixin

        cert = create_cert(cn='scheduler-last-day-probe.example')
        with app.app_context():
            config = NotificationConfig.query.filter_by(type='cert_expiring').first()
            previous = None
            if not config:
                config = NotificationConfig(type='cert_expiring')
                db.session.add(config)
            else:
                previous = (config.enabled, config.get_alert_days(), config.recipients)
            config.enabled = True
            config.set_alert_days([1, 7, 30])
            config.include_revoked = False
            config.recipients = json.dumps(['ops@example.test'])

            row = db.session.get(Certificate, cert['id'])
            row.valid_to = utc_now() + timedelta(hours=12)
            db.session.commit()

            try:
                due = NotificationSchedulerMixin.check_expiring_certificates()
                mine = [entry for entry in due if entry['cert'].id == cert['id']]
                assert mine, 'half a day left is inside the 1-day threshold'
                assert mine[0]['days_remaining'] == 1
            finally:
                if previous is None:
                    db.session.delete(config)
                else:
                    config.enabled, days, config.recipients = previous
                    config.set_alert_days(days)
                db.session.commit()

    def test_a_discovered_certificate_uses_the_helper(self, app):
        from models.discovered_certificate import DiscoveredCertificate
        row = DiscoveredCertificate()
        row.not_after = utc_now() + timedelta(hours=12)
        assert row.days_until_expiry == 1
        row.not_after = None
        assert row.days_until_expiry is None

    def test_the_inspection_tool_counts_the_last_day(self):
        """`cert_to_dict` feeds the SSL checker, which warns under 30 days."""
        from api.v2.tools import cert_to_dict
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        from datetime import datetime, timezone

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048,
                                       backend=default_backend())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'half-a-day.example')])
        now = datetime.now(timezone.utc)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(name).issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(hours=12))
            .sign(key, hashes.SHA256(), default_backend())
        )
        assert cert_to_dict(certificate)['days_until_expiry'] == 1

    def test_the_pdf_report_lists_the_last_day(self, app, create_cert):
        """`0 < days_left <= 30` dropped anything a floor rounded to zero."""
        from models import Certificate, db
        from services.reporting.formatters import collect_report_data

        cert = create_cert(cn='pdf-last-day-probe.example')
        with app.app_context():
            row = db.session.get(Certificate, cert['id'])
            row.valid_to = utc_now() + timedelta(hours=12)
            db.session.commit()

            data = collect_report_data()
            listed = [c.id for c in data['expiring_30']]
            assert cert['id'] in listed, 'a certificate expiring today is expiring'

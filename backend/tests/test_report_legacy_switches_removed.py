"""The legacy report switches no longer pose as a schedule.

`report_expiry_*`, seeded on, made the Reports page show a daily expiry
report that nothing ever ran.
"""
from models import SystemConfig, db


def test_legacy_switch_does_not_show_as_scheduled(app, auth_client):
    with app.app_context():
        for key, value in (('report_expiry_enabled', 'true'),
                           ('report_expiry_recipients', '["ops@example.test"]')):
            db.session.add(SystemConfig(key=key, value=value))
        db.session.commit()
    try:
        r = auth_client.get('/api/v2/reports/schedule')
        assert r.status_code == 200
        assert r.get_json()['data']['expiring_certificates']['enabled'] is False
    finally:
        with app.app_context():
            SystemConfig.query.filter(SystemConfig.key.in_(
                ['report_expiry_enabled', 'report_expiry_recipients'])).delete(synchronize_session=False)
            db.session.commit()

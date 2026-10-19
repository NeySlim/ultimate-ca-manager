"""Revoked-certificates report, and scheduled reports mailed in their format.

A schedule saved as JSON used to go out as CSV, and no file was attached at
all; PDF schedules saved from the UI were dropped by the API.
"""
import email
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from models import Certificate, SystemConfig, db
from services import email_service as email_module
from services import report_service
from services.email_service import EmailService
from utils.datetime_utils import utc_now


def _post(c, url, body):
    return c.post(url, data=json.dumps(body), content_type='application/json')


def _revoke(auth_client, cert_id, reason):
    r = _post(auth_client, f'/api/v2/certificates/{cert_id}/revoke', {'reason': reason})
    assert r.status_code == 200, r.data


@pytest.fixture(scope='module')
def revoked(app, auth_client, create_cert):
    recent = create_cert(cn='revoked-report-recent.example.com')
    old = create_cert(cn='revoked-report-old.example.com')
    _revoke(auth_client, recent['id'], 'keyCompromise')
    _revoke(auth_client, old['id'], 'superseded')
    with app.app_context():
        db.session.get(Certificate, old['id']).revoked_at = utc_now() - timedelta(days=100)
        db.session.commit()
    return {'recent': recent['id'], 'old': old['id']}


def _revoked_report(auth_client, **params):
    r = _post(auth_client, '/api/v2/reports/generate',
              {'report_type': 'revoked_certificates', 'params': {'format': 'json', **params}})
    assert r.status_code == 200, r.data
    content = json.loads(r.get_json()['data']['content'])
    return {i['id']: i for i in content['items']}, content['summary']


def test_revoked_report_is_listed(auth_client):
    types = auth_client.get('/api/v2/reports/types').get_json()['data']
    assert 'revoked_certificates' in types


def test_revoked_report_covers_the_period(auth_client, revoked):
    items, summary = _revoked_report(auth_client, days=30)
    assert revoked['recent'] in items
    assert revoked['old'] not in items
    assert items[revoked['recent']]['revoke_reason'] == 'keyCompromise'
    assert summary['period_days'] == 30
    assert summary['by_reason'].get('keyCompromise', 0) >= 1

    items, _ = _revoked_report(auth_client, days=365)
    assert revoked['old'] in items


def test_revoked_report_filters_by_reason(auth_client, revoked):
    items, _ = _revoked_report(auth_client, days=365, reason='superseded')
    assert revoked['old'] in items
    assert revoked['recent'] not in items


def test_revoked_report_downloads_as_csv(auth_client, revoked):
    r = auth_client.get('/api/v2/reports/download/revoked_certificates?format=csv&days=30')
    assert r.status_code == 200
    header = r.data.decode().splitlines()[0]
    assert 'revoked_at' in header and 'revoke_reason' in header


@pytest.fixture
def outbox(monkeypatch):
    sent = []

    def fake_send(**kwargs):
        sent.append(kwargs)
        return True, 'sent'

    monkeypatch.setattr(EmailService, 'send_email', staticmethod(fake_send))
    return sent


@pytest.fixture
def schedules(app):
    keys = []

    def _save(key, value):
        with app.app_context():
            SystemConfig.query.filter_by(key=f'report_schedule_{key}').delete()
            db.session.add(SystemConfig(key=f'report_schedule_{key}', value=json.dumps(value)))
            db.session.commit()
        keys.append(key)

    yield _save
    with app.app_context():
        for key in keys:
            SystemConfig.query.filter_by(key=f'report_schedule_{key}').delete()
        db.session.commit()


@pytest.mark.parametrize('fmt, mimetype', [('json', 'application/json'), ('csv', 'text/csv')])
def test_test_send_attaches_the_saved_format(auth_client, revoked, outbox, schedules, fmt, mimetype):
    schedules('revoked_certificates', {'enabled': False, 'format': fmt, 'recipients': []})
    r = _post(auth_client, '/api/v2/reports/send-test',
              {'report_type': 'revoked_certificates', 'recipient': 'ops@example.test'})
    assert r.status_code == 200, r.data

    (filename, content, sent_type), = outbox[-1]['attachments']
    assert filename.endswith(f'.{fmt}')
    assert sent_type == mimetype
    if fmt == 'json':
        assert any(i['id'] == revoked['recent'] for i in json.loads(content)['items'])
    else:
        assert content.decode().startswith('id,common_name')


def test_scheduler_sends_the_saved_format(app, outbox, schedules, monkeypatch):
    now = datetime(2026, 10, 19, 8, 0)
    monkeypatch.setattr(report_service, 'utc_now', lambda: now)
    schedules('ca_hierarchy', {'enabled': True, 'frequency': 'daily', 'time': '08:00',
                               'recipients': ['ops@example.test'], 'format': 'json'})
    with app.app_context():
        report_service.run_scheduled_reports()
    mailed = [m for m in outbox if 'CA Hierarchy' in m['subject']]
    assert len(mailed) == 1
    filename, content, sent_type = mailed[0]['attachments'][0]
    assert filename.endswith('.json') and sent_type == 'application/json'
    json.loads(content)


def test_pdf_schedule_is_saved_and_mailed_with_its_template(auth_client, outbox, schedules, monkeypatch):
    from services.pdf_report_service import PDFReportService
    calls = []
    monkeypatch.setattr(PDFReportService, 'generate_executive_report',
                        classmethod(lambda cls, sections=None: calls.append(sections) or b'%PDF-1.7 test'))
    r = auth_client.put('/api/v2/reports/schedule', data=json.dumps({'pdf_compliance': {
        'enabled': True, 'frequency': 'monthly', 'time': '07:00', 'day_of_month': 1,
        'recipients': ['ops@example.test']}}), content_type='application/json')
    assert r.status_code == 200, r.data
    schedules('pdf_compliance', {})  # cleanup only
    saved = r.get_json()['data']['pdf_compliance']
    assert saved['enabled'] is True and saved['format'] == 'pdf'

    r = _post(auth_client, '/api/v2/reports/send-test',
              {'report_type': 'pdf_compliance', 'recipient': 'ops@example.test'})
    assert r.status_code == 200, r.data
    assert calls[-1] == PDFReportService.TEMPLATES['compliance']['sections']
    filename, content, sent_type = outbox[-1]['attachments'][0]
    assert filename.endswith('.pdf') and sent_type == 'application/pdf' and content.startswith(b'%PDF')


def test_test_send_reports_a_failed_delivery(auth_client, monkeypatch):
    monkeypatch.setattr(EmailService, 'send_email',
                        staticmethod(lambda **kw: (False, 'SMTP is not configured or disabled')))
    r = _post(auth_client, '/api/v2/reports/send-test',
              {'report_type': 'ca_hierarchy', 'recipient': 'ops@example.test'})
    assert r.status_code == 502


def test_email_carries_the_attachment(app, monkeypatch):
    config = SimpleNamespace(enabled=True, smtp_content_type='html', smtp_from='ucm@example.test',
                             smtp_from_name='UCM', smtp_host='mail.example.test', smtp_port=25)
    captured = {}

    class FakeServer:
        def sendmail(self, sender, recipients, message):
            captured['message'] = message

        def quit(self):
            pass

    monkeypatch.setattr(EmailService, 'get_smtp_config', staticmethod(lambda: config))
    monkeypatch.setattr(email_module, '_smtp_connect', lambda cfg, timeout: FakeServer())
    monkeypatch.setattr(email_module, '_smtp_authenticate', lambda server, cfg: None)
    with app.app_context():
        ok, _ = EmailService.send_email(
            recipients=['ops@example.test'], subject='Report', body_html='<p>hi</p>',
            body_text='hi', notification_type='report',
            attachments=[('report.json', b'{"items": []}', 'application/json')])
    assert ok
    msg = email.message_from_string(captured['message'])
    parts = [p for p in msg.walk() if p.get_filename()]
    assert [p.get_filename() for p in parts] == ['report.json']
    assert parts[0].get_content_type() == 'application/json'
    assert parts[0].get_payload(decode=True) == b'{"items": []}'
    assert any(p.get_content_type() == 'text/html' for p in msg.walk())

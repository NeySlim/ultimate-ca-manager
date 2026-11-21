"""A clock a caller passes to date the mail log never reads on the caller's session: one that
fails falls back to this host's and leaves the caller's pending work in place."""
import uuid
from types import SimpleNamespace

import pytest

from models import SystemConfig, db
from models.email_notification import NotificationLog
from services import email_service as email_module
from services.email_service import EmailService


class _FakeServer:
    def sendmail(self, *a):
        pass

    def quit(self):
        pass


@pytest.fixture
def smtp(monkeypatch):
    config = SimpleNamespace(enabled=True, smtp_content_type='html', smtp_from='ucm@example.test',
                             smtp_from_name='UCM', smtp_host='mail.example.test', smtp_port=25)
    monkeypatch.setattr(EmailService, 'get_smtp_config', staticmethod(lambda: config))
    monkeypatch.setattr(email_module, '_smtp_connect', lambda cfg, timeout: _FakeServer())
    monkeypatch.setattr(email_module, '_smtp_authenticate', lambda server, cfg: None)


def _broken_clock(executor=None):
    raise RuntimeError('clock unreadable')


@pytest.mark.parametrize('delivered', [True, False])
def test_a_failing_log_clock_keeps_the_callers_work(app, smtp, monkeypatch, delivered):
    if not delivered:
        def refuse(*a):
            raise OSError('connection refused')
        monkeypatch.setattr(email_module, '_smtp_connect', lambda cfg, timeout: refuse())
    key, resource_id = f'test.clock.{uuid.uuid4().hex[:8]}', uuid.uuid4().hex[:8]
    with app.app_context():
        db.session.add(SystemConfig(key=key, value='kept'))
        db.session.flush()
        ok, _ = EmailService.send_email(
            recipients=['ops@example.test'], subject='s', body_html='<p>x</p>',
            notification_type='clock_test', resource_type='clock', resource_id=resource_id,
            log_clock=_broken_clock)
        assert ok is delivered
        db.session.expire_all()
        try:
            assert SystemConfig.query.filter_by(key=key).one().value == 'kept'
            assert NotificationLog.query.filter_by(resource_id=resource_id).count() == 1
        finally:
            SystemConfig.query.filter_by(key=key).delete()
            NotificationLog.query.filter_by(resource_id=resource_id).delete()
            db.session.commit()


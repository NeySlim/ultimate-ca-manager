"""notify_on_violation: a policy that refuses an operation or holds one for
approval e-mails its addresses, else its approvers; a refusal repeated within
the window is reported once."""

import json
import uuid

import pytest

from models import db
from models.email_notification import NotificationLog
from models.group import Group, GroupMember
from models.policy import ApprovalRequest, CertificatePolicy
from services import policy_notifications


def _json(client, method, url, payload=None):
    return getattr(client, method)(url, data=json.dumps(payload or {}), content_type='application/json')


@pytest.fixture
def sent(monkeypatch):
    """Every e-mail the notifier hands to the e-mail service."""
    calls = []

    def fake_send(recipients, subject, body_html, **kw):
        calls.append({'to': list(recipients), 'subject': subject, 'body': body_html, **kw})
        return True, 'ok'
    monkeypatch.setattr('services.email_service.EmailService.send_email', staticmethod(fake_send))
    policy_notifications._recent.clear()
    yield calls
    policy_notifications._recent.clear()


@pytest.fixture
def policies(app):
    made = []

    def make(ca_id, *, rules=None, approval=False, notify=True, emails=None, group_id=None):
        with app.app_context():
            pol = CertificatePolicy(name=f'notify-{uuid.uuid4().hex[:8]}', ca_id=ca_id,
                                    requires_approval=approval, approval_group_id=group_id,
                                    min_approvers=1, is_active=True, priority=100,
                                    notify_on_violation=notify,
                                    notification_emails=json.dumps(emails) if emails else None)
            pol.set_rules(rules or {})
            pol.set_operations(['issuance'])
            db.session.add(pol)
            db.session.commit()
            made.append(pol.id)
            return pol.id, pol.name
    yield make
    with app.app_context():
        for pid in made:
            ApprovalRequest.query.filter_by(policy_id=pid).delete()
            db.session.delete(db.session.get(CertificatePolicy, pid))
        db.session.commit()


def _issue(client, ca_id, cn, **extra):
    payload = {'cn': cn, 'ca_id': ca_id, 'key_type': 'rsa', 'key_size': 2048,
               'validity_days': 90, 'cert_type': 'server'}
    payload.update(extra)
    return _json(client, 'post', '/api/v2/certificates', payload)


class TestViolation:

    def test_a_refusal_is_reported_once_to_the_policy_addresses(self, app, auth_client, create_ca, policies, sent):
        ca = create_ca(cn='notify violation CA')
        _pid, name = policies(ca['id'], rules={'allowed_key_types': ['EC-P256']},
                              emails=['pki@example.test'])
        for _ in range(3):  # a client retrying the same refused request
            assert _issue(auth_client, ca['id'], 'refused.notify.test').status_code == 400
        assert len(sent) == 1, sent
        mail = sent[0]
        assert mail['to'] == ['pki@example.test'] and name in mail['subject']
        for part in (name, 'refused.notify.test', 'Issuance', 'admin', 'RSA-2048', 'notify violation CA'):
            assert part in mail['body'], part
        assert 'PRIVATE KEY' not in mail['body']
        # Another request is another refusal
        assert _issue(auth_client, ca['id'], 'other.notify.test').status_code == 400
        assert len(sent) == 2

    def test_no_mail_when_the_policy_does_not_notify(self, app, auth_client, create_ca, policies, sent):
        ca = create_ca(cn='notify off CA')
        policies(ca['id'], rules={'allowed_key_types': ['EC-P256']}, notify=False,
                 emails=['pki@example.test'])
        assert _issue(auth_client, ca['id'], 'quiet.notify.test').status_code == 400
        assert sent == []

    def test_another_worker_already_told_them(self, app, auth_client, create_ca, policies, sent):
        ca = create_ca(cn='notify worker CA')
        policies(ca['id'], rules={'allowed_key_types': ['EC-P256']}, emails=['pki@example.test'])
        assert _issue(auth_client, ca['id'], 'worker.notify.test').status_code == 400
        assert len(sent) == 1
        with app.app_context():
            db.session.add(NotificationLog(type=policy_notifications.VIOLATION, recipient='pki@example.test',
                                           status='sent', resource_type='policy',
                                           resource_id=sent[0]['resource_id']))
            db.session.commit()
        policy_notifications._recent.clear()  # as seen from another process
        assert _issue(auth_client, ca['id'], 'worker.notify.test').status_code == 400
        assert len(sent) == 1
        with app.app_context():
            NotificationLog.query.filter_by(resource_id=sent[0]['resource_id']).delete()
            db.session.commit()


class TestApprovalQueued:

    def test_the_approvers_are_told_once_with_a_link(self, app, auth_client, create_ca, create_user, policies, sent):
        ca = create_ca(cn='notify approval CA')
        tag = uuid.uuid4().hex[:8]
        approver = create_user(username=f'appr-{tag}', email=f'appr-{tag}@example.test', role='operator')
        outsider = create_user(username=f'out-{tag}', email=f'out-{tag}@example.test', role='operator')
        with app.app_context():
            group = Group(name=f'notify-approvers-{tag}', permissions=[])
            db.session.add(group)
            db.session.flush()
            db.session.add(GroupMember(group_id=group.id, user_id=approver['id']))
            db.session.commit()
            group_id = group.id
        pid, name = policies(ca['id'], approval=True, group_id=group_id)
        try:
            client = app.test_client()
            r = _json(client, 'post', '/api/v2/auth/login', {'username': outsider['username'], 'password': 'TestPass123!'})
            assert r.status_code == 200
            r = _issue(client, ca['id'], 'held.notify.test')
            assert r.status_code in (200, 202), r.get_json()
            with app.app_context():
                approval_id = ApprovalRequest.query.filter_by(policy_id=pid).one().id
            assert len(sent) == 1, sent
            mail = sent[0]
            assert mail['to'] == [f'appr-{tag}@example.test']
            assert f'/approvals?id={approval_id}' in mail['body']
            for part in (name, 'held.notify.test', outsider['username']):
                assert part in mail['body'], part
        finally:
            with app.app_context():
                ApprovalRequest.query.filter_by(policy_id=pid).delete()
                GroupMember.query.filter_by(group_id=group_id).delete()
                db.session.delete(db.session.get(Group, group_id))
                db.session.commit()

    def test_markup_in_a_name_is_escaped(self, app, create_ca, policies, sent):
        from services.policy_service import PolicyEvaluationService
        ca = create_ca(cn='notify escape CA')
        pid, _name = policies(ca['id'], approval=True, emails=['pki@example.test'])
        with app.app_context():
            pol = db.session.get(CertificatePolicy, pid)
            PolicyEvaluationService.create_approval_request(
                pol, {'cn': '<script>x</script>', 'ca_id': ca['id']}, None)
        assert len(sent) == 1
        assert '<script>' not in sent[0]['body'] and '&lt;script&gt;' in sent[0]['body']


class TestPolicyEmailsField:

    def test_addresses_are_validated_and_stored(self, app, auth_client):
        name = f'notify-field-{uuid.uuid4().hex[:6]}'
        try:
            r = _json(auth_client, 'post', '/api/v2/policies', {'name': name, 'notification_emails': ['nope']})
            assert r.status_code == 400
            r = _json(auth_client, 'post', '/api/v2/policies',
                      {'name': name, 'notification_emails': [' a@example.test ', 'a@example.test', 'b@example.test']})
            assert r.status_code == 200, r.get_json()
            pid = r.get_json()['data']['id']
            assert r.get_json()['data']['notification_emails'] == ['a@example.test', 'b@example.test']
            for bad in ('a@example.test', ['x@y.test\r\nBcc: z@w.test'], ['a,b@example.test'], ['<a@example.test>'], [1]):
                r = _json(auth_client, 'put', f'/api/v2/policies/{pid}', {'notification_emails': bad})
                assert r.status_code == 400, bad
            r = _json(auth_client, 'put', f'/api/v2/policies/{pid}', {'notification_emails': []})
            assert r.get_json()['data']['notification_emails'] == []
        finally:
            with app.app_context():
                CertificatePolicy.query.filter_by(name=name).delete()
                db.session.commit()


@pytest.fixture
def smtp_on(app):
    """An enabled SMTP configuration, the previous one restored afterwards."""
    from models.email_notification import SMTPConfig
    fields = ('enabled', 'smtp_host', 'smtp_port', 'smtp_from', 'smtp_auth', 'smtp_user',
              'smtp_use_tls', 'smtp_use_ssl', 'smtp_auth_method')
    with app.app_context():
        row = SMTPConfig.query.first()
        created = row is None
        if created:
            row = SMTPConfig()
            db.session.add(row)
        saved = {f: getattr(row, f) for f in fields}
        row.enabled, row.smtp_host, row.smtp_port, row.smtp_from = True, 'smtp.example.test', 25, 'ucm@example.test'
        row.smtp_auth, row.smtp_user, row.smtp_use_tls, row.smtp_use_ssl = False, None, False, False
        row.smtp_auth_method = 'password'
        db.session.commit()
    yield
    with app.app_context():
        row = SMTPConfig.query.first()
        if created:
            db.session.delete(row)
        else:
            for f, v in saved.items():
                setattr(row, f, v)
        db.session.commit()


class TestOwnSession:
    """The production path: a thread with its own session."""

    @pytest.fixture
    def threaded(self, app, monkeypatch):
        class SyncThread:
            def __init__(self, target, **_kw):
                self.target = target

            def start(self):
                self.target()
        monkeypatch.setitem(app.config, 'TESTING', False)
        monkeypatch.setattr(policy_notifications.threading, 'Thread', SyncThread)
        policy_notifications._recent.clear()
        yield
        policy_notifications._recent.clear()

    def _violate(self, app, pid, subject):
        with app.app_context():
            pol = db.session.get(CertificatePolicy, pid)
            policy_notifications.violation([pol], {id(pol): ['Key type RSA-2048 is not allowed']},
                                           {'operation': 'issuance', 'subject': subject})

    def test_no_connection_is_held_during_smtp_and_one_log_remains(
            self, app, create_ca, policies, smtp_on, threaded, monkeypatch):
        exchanges = []

        class FakeSMTP:
            def sendmail(self, *_a):
                pass

            def quit(self):
                pass

        def connect(_config, timeout):
            exchanges.append(db.session.registry.has())
            return FakeSMTP()
        monkeypatch.setattr('services.email_service._smtp_connect', connect)
        ca = create_ca(cn='notify thread CA')
        pid, _name = policies(ca['id'], emails=['pki@example.test'])
        self._violate(app, pid, 'thread.notify.test')
        assert exchanges == [False]  # a mail went out, with no session open
        with app.app_context():
            logs = NotificationLog.query.filter(
                NotificationLog.type == policy_notifications.VIOLATION,
                NotificationLog.resource_id.like(f'{pid}:%')).all()
            assert [log.status for log in logs] == ['sent']
            assert NotificationLog.query.filter_by(status='pending', resource_type='policy').count() == 0
            resource_id = logs[0].resource_id
        # Another worker (empty memory) sees the record and stays silent
        policy_notifications._recent.clear()
        self._violate(app, pid, 'thread.notify.test')
        assert exchanges == [False]
        with app.app_context():
            NotificationLog.query.filter_by(resource_id=resource_id).delete()
            db.session.commit()

    def test_the_record_comes_first_and_only_one_claim_wins(self, app):
        with app.app_context():
            first = policy_notifications._claim_in_db(policy_notifications.VIOLATION, 'test:claim', 'a@example.test')
            second = policy_notifications._claim_in_db(policy_notifications.VIOLATION, 'test:claim', 'a@example.test')
            assert first is not None and second is None
            assert NotificationLog.query.filter_by(resource_id='test:claim').count() == 1
            NotificationLog.query.filter_by(resource_id='test:claim').delete()
            db.session.commit()

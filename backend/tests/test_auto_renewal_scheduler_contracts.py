"""Scheduled certificate renewal: outcomes, failure audit, CRL publication
and tolerance of malformed settings."""
import threading

import pytest
from sqlalchemy import text

from models import db, AuditLog, CA, Certificate, SystemConfig

FAILED = 'certificate.auto_renewal_failed'
SETTING_KEYS = ('auto_renewal_enabled', 'auto_renewal_days', 'auto_renewal_sources',
                'auto_renewal_notify_on_renewal', 'auto_renewal_notify_on_failure',
                'auto_renewal_notify_emails')


def _cert_row(app, ca_id, cn):
    from services.cert_service import CertificateService
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        row = CertificateService.create_certificate(
            descr=cn, caref=ca.refid, dn={'CN': cn}, cert_type='server_cert',
            key_type='2048', validity_days=30, username='admin')
        db.session.commit()
        return row.id


def _drop(app, *ids):
    with app.app_context():
        for rid in ids:
            row = db.session.get(Certificate, rid)
            if row is not None:
                db.session.delete(row)
        db.session.commit()


def _failures(cert_id):
    """Failure entries for ``cert_id``, newest first (SQLite reuses ids, so
    earlier tests may have left some)."""
    return AuditLog.query.filter_by(action=FAILED, resource_id=str(cert_id)).order_by(
        AuditLog.id.desc()).all()


def _set_raw(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if row is None:
        db.session.add(SystemConfig(key=key, value=value))
    else:
        row.value = value
    db.session.commit()


@pytest.fixture
def settings(app):
    """Restore the auto-renewal settings as they were before the test."""
    with app.app_context():
        saved = {k: (r.value if r else None) for k in SETTING_KEYS
                 for r in [SystemConfig.query.filter_by(key=k).first()]}
    yield
    with app.app_context():
        db.session.rollback()
        for key, value in saved.items():
            row = SystemConfig.query.filter_by(key=key).first()
            if value is None and row is not None:
                db.session.delete(row)
            elif value is not None:
                _set_raw(key, value)
        db.session.commit()


@pytest.fixture
def cert_id(app, create_ca):
    ca = create_ca(cn='b5 contracts CA')
    rid = _cert_row(app, ca['id'], 'b5-contracts.example.test')
    yield rid
    _drop(app, rid)


@pytest.fixture
def svc():
    from services import auto_renewal_service
    return auto_renewal_service


class TestActor:

    def test_actor_value(self, svc):
        assert svc.AUTO_RENEWAL_ACTOR == 'auto-renewal'

    def test_scheduler_queues_approval_under_the_actor(self, app, svc, cert_id, monkeypatch):
        seen = []
        monkeypatch.setattr('services.approval_gate.queue_renewal',
                            lambda user, cert, scheduled_by=None: seen.append(scheduled_by) or (None, None))
        with app.app_context():
            cert = db.session.get(Certificate, cert_id)
            assert svc.AutoRenewalService._held_for_approval(cert, already_queued=False) is None
        assert seen == ['auto-renewal']

    def test_no_scheduler_thread_under_tests(self, app):
        assert not [t for t in threading.enumerate() if t.name == 'SchedulerService' and t.is_alive()]


class TestRenewCertificate:

    def test_success_calls_the_routine_with_the_scheduler_contract(self, app, svc, cert_id, monkeypatch):
        calls = []
        monkeypatch.setattr(svc, 'renew_certificate_in_place',
                            lambda cert, **kw: calls.append((cert.id, kw)) or {'cert_id': cert.id})
        marker = object()
        with app.app_context():
            cert = db.session.get(Certificate, cert_id)
            before = len(_failures(cert_id))
            assert svc.AutoRenewalService.renew_certificate(
                cert, regenerate_crl=False, known_serial=marker) == (True, cert_id)
            assert len(_failures(cert_id)) == before
        (called_id, kw), = calls
        assert called_id == cert_id
        assert kw['username'] == 'auto-renewal'
        assert kw['rekey'] is False and kw['trigger'] == 'auto'
        assert kw.get('actor_user_id') is None
        assert kw['regenerate_crl'] is False and kw['known_serial'] is marker

    def test_renewal_error_is_a_failure_with_its_audit_entry(self, app, svc, cert_id, monkeypatch):
        def refused(cert, **kw):
            raise svc.RenewalError('Issuing CA not found', 404)
        monkeypatch.setattr(svc, 'renew_certificate_in_place', refused)
        with app.app_context():
            cert = db.session.get(Certificate, cert_id)
            cn = cert.common_name
            before = len(_failures(cert_id))
            assert svc.AutoRenewalService.renew_certificate(cert) == (False, 'Issuing CA not found')
            db.session.rollback()  # committed, not merely staged
            assert len(_failures(cert_id)) == before + 1
            entry = _failures(cert_id)[0]
            assert entry.resource_type == 'certificate'
            assert entry.resource_name == cn
            assert entry.details == 'Auto-renewal failed: Issuing CA not found'
            assert entry.success is False
            assert entry.username == 'auto-renewal'

    def test_row_deleted_meanwhile_is_skipped_without_audit(self, app, svc, cert_id, monkeypatch):
        def gone(cert, **kw):
            # Deleted by someone else after the batch listed it
            db.session.execute(text('DELETE FROM certificates WHERE id = :id'), {'id': cert.id})
            db.session.commit()
            raise svc.RenewalError('Certificate no longer exists', 404)
        monkeypatch.setattr(svc, 'renew_certificate_in_place', gone)
        with app.app_context():
            cert = db.session.get(Certificate, cert_id)
            before = len(_failures(cert_id))
            assert svc.AutoRenewalService.renew_certificate(cert) == (None, 'Certificate no longer exists')
            assert len(_failures(cert_id)) == before

    def test_any_other_exception_is_a_generic_failure_and_the_session_survives(
            self, app, svc, cert_id, monkeypatch):
        def broken(cert, **kw):
            # Leave the session needing a rollback, then fail
            db.session.add(AuditLog(action=None))
            db.session.flush()
        monkeypatch.setattr(svc, 'renew_certificate_in_place', broken)
        with app.app_context():
            cert = db.session.get(Certificate, cert_id)
            before = len(_failures(cert_id))
            assert svc.AutoRenewalService.renew_certificate(cert) == (False, 'Renewal failed')
            db.session.rollback()
            assert len(_failures(cert_id)) == before + 1
            entry = _failures(cert_id)[0]
            assert entry.details == 'Auto-renewal failed: Renewal failed'
            assert db.session.get(Certificate, cert_id) is not None
            _set_raw('b5_probe', '1')
            db.session.delete(SystemConfig.query.filter_by(key='b5_probe').first())
            db.session.commit()


class TestLogFailure:

    def test_commit_error_is_swallowed(self, app, svc, cert_id, monkeypatch):
        with app.app_context():
            before = len(_failures(cert_id))

            def failing_commit():
                raise RuntimeError('database is locked')
            monkeypatch.setattr(db.session, 'commit', failing_commit)
            svc.AutoRenewalService._log_failure(cert_id, 'cn', 'boom')
            monkeypatch.undo()
            # Rolled back: nothing staged survives, the session still works
            assert len(_failures(cert_id)) == before

    def test_staging_error_is_swallowed(self, app, svc, cert_id, monkeypatch):
        def broken(**fields):
            raise RuntimeError('no ledger')
        monkeypatch.setattr('services.audit.staging.stage_audit_entry', broken)
        with app.app_context():
            before = len(_failures(cert_id))
            svc.AutoRenewalService._log_failure(cert_id, 'cn', 'boom')
            assert len(_failures(cert_id)) == before


class TestConfig:

    @pytest.mark.parametrize('raw', ['not json', '{"manual": 1}', '"manual"', '[1, {"a": 2}]'])
    def test_malformed_sources_keep_the_default(self, app, svc, settings, raw):
        with app.app_context():
            _set_raw('auto_renewal_sources', raw)
            assert svc.AutoRenewalService.get_renewal_config()['renewal_sources'] == \
                ['manual', 'scep', 'acme', 'est']

    def test_valid_sources_are_read(self, app, svc, settings):
        with app.app_context():
            _set_raw('auto_renewal_sources', '["acme"]')
            assert svc.AutoRenewalService.get_renewal_config()['renewal_sources'] == ['acme']

    def test_malformed_days_keep_the_default(self, app, svc, settings):
        with app.app_context():
            _set_raw('auto_renewal_days', 'soon')
            assert svc.AutoRenewalService.get_renewal_config()['days_before_expiry'] == 30

    def test_run_survives_malformed_settings(self, app, svc, settings, monkeypatch):
        monkeypatch.setattr(svc.AutoRenewalService, '_held_for_approval',
                            staticmethod(lambda cert, already_queued: None))
        monkeypatch.setattr(svc.AutoRenewalService, 'renew_certificate',
                            staticmethod(lambda cert, regenerate_crl=True, known_serial=None: (True, cert.id)))
        monkeypatch.setattr(svc.AutoRenewalService, '_publish_crls', staticmethod(lambda carefs: None))
        sent = []
        monkeypatch.setattr('services.email_service.EmailService.send_email',
                            lambda **kw: sent.append(kw['to']))
        with app.app_context():
            _set_raw('auto_renewal_enabled', 'true')
            _set_raw('auto_renewal_sources', '{broken')
            _set_raw('auto_renewal_days', 'x')
            _set_raw('auto_renewal_notify_emails', '{broken')
            stats = svc.AutoRenewalService.run_auto_renewal()
        assert set(stats) >= {'renewed', 'failed', 'skipped', 'queued', 'errors'}
        assert sent == []

    def test_flags_absent_default_to_true(self, app, svc, settings):
        with app.app_context():
            for key in ('auto_renewal_notify_on_renewal', 'auto_renewal_notify_on_failure'):
                row = SystemConfig.query.filter_by(key=key).first()
                if row is not None:
                    db.session.delete(row)
            db.session.commit()
            config = svc.AutoRenewalService.get_renewal_config()
        assert config['notify_on_renewal'] is True and config['notify_on_failure'] is True

    def test_flags_saved_false_are_read_false_and_true_only_for_true(self, app, svc, settings):
        with app.app_context():
            svc.AutoRenewalService.set_renewal_config({'notify_on_renewal': False, 'notify_on_failure': False})
            stored = {k: SystemConfig.query.filter_by(key=k).first().value
                      for k in ('auto_renewal_notify_on_renewal', 'auto_renewal_notify_on_failure')}
            assert set(stored.values()) == {'false'}
            config = svc.AutoRenewalService.get_renewal_config()
            assert config['notify_on_renewal'] is False and config['notify_on_failure'] is False
            svc.AutoRenewalService.set_renewal_config({'notify_on_renewal': True, 'notify_on_failure': 1})
            config = svc.AutoRenewalService.get_renewal_config()
            assert config['notify_on_renewal'] is True and config['notify_on_failure'] is True
            _set_raw('auto_renewal_notify_on_renewal', 'True')
            assert svc.AutoRenewalService.get_renewal_config()['notify_on_renewal'] is False


class TestNotifications:

    def _run(self, app, svc, monkeypatch, cert_id, *, flags):
        """One renewed and one failed certificate; returns the notifications sent."""
        sent = []
        monkeypatch.setattr(svc.AutoRenewalService, '_send_renewal_notification',
                            staticmethod(lambda stats: sent.append('renewal')))
        monkeypatch.setattr(svc.AutoRenewalService, '_send_failure_notification',
                            staticmethod(lambda stats: sent.append('failure')))
        monkeypatch.setattr(svc.AutoRenewalService, '_held_for_approval',
                            staticmethod(lambda cert, already_queued: None))
        monkeypatch.setattr(svc.AutoRenewalService, '_publish_crls', staticmethod(lambda carefs: None))
        outcomes = iter([(True, cert_id), (False, 'nope')])
        monkeypatch.setattr(svc.AutoRenewalService, 'renew_certificate',
                            staticmethod(lambda cert, regenerate_crl=True, known_serial=None: next(outcomes)))
        with app.app_context():
            cert = db.session.get(Certificate, cert_id)
            monkeypatch.setattr(svc.AutoRenewalService, 'get_certificates_for_renewal',
                                staticmethod(lambda: [cert, cert]))
            svc.AutoRenewalService.set_renewal_config(
                {'enabled': True, 'notify_on_renewal': flags, 'notify_on_failure': flags})
            stats = svc.AutoRenewalService.run_auto_renewal()
        assert stats['renewed'] == 1 and stats['failed'] == 1, stats
        return sent

    def test_flags_false_send_nothing(self, app, svc, settings, cert_id, monkeypatch):
        assert self._run(app, svc, monkeypatch, cert_id, flags=False) == []

    def test_flags_true_send_both(self, app, svc, settings, cert_id, monkeypatch):
        assert self._run(app, svc, monkeypatch, cert_id, flags=True) == ['renewal', 'failure']

    @pytest.mark.parametrize('raw', ['not json', '"admin@example.test"', '{"to": "a@example.test"}'])
    def test_malformed_recipients_send_nothing(self, app, svc, settings, monkeypatch, raw):
        sent = []
        monkeypatch.setattr('services.email_service.EmailService.send_email',
                            lambda **kw: sent.append(kw['to']))
        stats = {'renewed': 1, 'failed': 1, 'errors': [{'cert_id': 1, 'common_name': 'x', 'error': 'e'}]}
        with app.app_context():
            _set_raw('auto_renewal_notify_emails', raw)
            svc.AutoRenewalService._send_renewal_notification(stats)
            svc.AutoRenewalService._send_failure_notification(stats)
        assert sent == []

    def test_one_failing_recipient_does_not_stop_the_others(self, app, svc, settings, monkeypatch):
        sent = []

        def send(**kw):
            if kw['to'] == 'bad@example.test':
                raise RuntimeError('smtp down')
            sent.append(kw['to'])
        monkeypatch.setattr('services.email_service.EmailService.send_email', send)
        with app.app_context():
            _set_raw('auto_renewal_notify_emails', '["bad@example.test", "ok@example.test"]')
            svc.AutoRenewalService._send_renewal_notification({'renewed': 1})
        assert sent == ['ok@example.test']


class TestPublishCrls:

    @pytest.fixture
    def spy(self, monkeypatch):
        from services.crl import CRLService
        real = CRLService.generate_crl
        calls = []

        def generate(ca_id, validity_days=None, username='system'):
            calls.append((ca_id, username))
            return real(ca_id, validity_days=validity_days, username=username)
        monkeypatch.setattr(CRLService, 'generate_crl', staticmethod(generate))
        return calls

    def _ca(self, app, create_ca, cn, cdp):
        ca = create_ca(cn=cn)
        with app.app_context():
            row = db.session.get(CA, ca['id'])
            row.cdp_enabled = cdp
            db.session.commit()
            return row.id, row.refid

    def _batch(self, app, svc, monkeypatch, ids):
        """Real renewals of ``ids`` through the scheduler's batch."""
        monkeypatch.setattr(svc.AutoRenewalService, '_held_for_approval',
                            staticmethod(lambda cert, already_queued: None))
        with app.app_context():
            certs = [db.session.get(Certificate, i) for i in ids]
            monkeypatch.setattr(svc.AutoRenewalService, 'get_certificates_for_renewal',
                                staticmethod(lambda: certs))
            svc.AutoRenewalService.set_renewal_config(
                {'enabled': True, 'notify_on_renewal': False, 'notify_on_failure': False})
            return svc.AutoRenewalService.run_auto_renewal()

    def test_one_crl_after_a_batch_of_two(self, app, svc, settings, create_ca, monkeypatch, spy):
        from models.crl import CRLMetadata
        ca_id, _ = self._ca(app, create_ca, 'b5 cdp CA', True)
        ids = [_cert_row(app, ca_id, f'b5-cdp-{i}.example.test') for i in (1, 2)]
        try:
            with app.app_context():
                before = CRLMetadata.query.filter_by(ca_id=ca_id).count()
            stats = self._batch(app, svc, monkeypatch, ids)
            assert stats['renewed'] == 2, stats
            assert spy == [(ca_id, 'auto-renewal')]
            with app.app_context():
                assert CRLMetadata.query.filter_by(ca_id=ca_id).count() == before + 1
        finally:
            _drop(app, *ids)

    def test_no_crl_for_a_ca_without_cdp(self, app, svc, settings, create_ca, monkeypatch, spy):
        ca_id, _ = self._ca(app, create_ca, 'b5 nocdp CA', False)
        ids = [_cert_row(app, ca_id, 'b5-nocdp.example.test')]
        try:
            stats = self._batch(app, svc, monkeypatch, ids)
            assert stats['renewed'] == 1, stats
            assert spy == []
        finally:
            _drop(app, *ids)

    def test_a_failure_does_not_stop_the_others(self, app, svc, create_ca, monkeypatch):
        from services.crl import CRLService
        first, ref1 = self._ca(app, create_ca, 'b5 crl-fail CA', True)
        second, ref2 = self._ca(app, create_ca, 'b5 crl-ok CA', True)
        calls = []

        def generate(ca_id, validity_days=None, username='system'):
            calls.append(ca_id)
            if len(calls) == 1:
                raise RuntimeError('HSM unavailable')
        monkeypatch.setattr(CRLService, 'generate_crl', staticmethod(generate))
        with app.app_context():
            svc.AutoRenewalService._publish_crls({ref1, ref2, 'no-such-ca'})
        assert sorted(calls) == sorted([first, second])

    def test_empty_set_publishes_nothing(self, app, svc, monkeypatch):
        from services.crl import CRLService
        calls = []
        monkeypatch.setattr(CRLService, 'generate_crl', staticmethod(lambda *a, **k: calls.append(a)))
        with app.app_context():
            svc.AutoRenewalService._publish_crls(set())
        assert calls == []

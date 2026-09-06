"""
HTTPS certificate binding (#303 M1): the certificate applied to HTTPS is
remembered by refid; its renewal re-materializes the files and restarts the
service; regenerating a self-signed certificate clears the binding.
"""
import base64
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import has_app_context

import services.https_binding as https_binding
from services.https_binding import (
    backfill_legacy_https_binding, get_bound_refid, on_certificate_renewed,
    set_bound_refid,
)


@pytest.fixture
def clean_binding(app):
    with app.app_context():
        set_bound_refid('')
    yield
    with app.app_context():
        set_bound_refid('')


class TestBindingStore:
    def test_roundtrip(self, app, clean_binding):
        with app.app_context():
            assert get_bound_refid() == ''
            set_bound_refid('cert-ref-1')
            assert get_bound_refid() == 'cert-ref-1'
            set_bound_refid('')
            assert get_bound_refid() == ''


class TestLegacyBindingBackfill:
    def test_matches_installed_leaf_to_managed_certificate(
        self, app, clean_binding, monkeypatch, tmp_path, create_cert,
    ):
        cert_data = create_cert(cn='legacy-https.example.com')
        cert_path = tmp_path / 'https_cert.pem'
        key_path = tmp_path / 'https_key.pem'
        with app.app_context():
            from models import Certificate, db
            row = db.session.get(Certificate, cert_data['id'])
            cert_path.write_bytes(base64.b64decode(row.crt))

        monkeypatch.setattr(https_binding, '_paths', lambda: (cert_path, key_path))
        with app.app_context():
            assert backfill_legacy_https_binding() == cert_data['refid']
            assert get_bound_refid() == cert_data['refid']

    def test_never_overrides_an_explicit_binding(
        self, app, clean_binding, monkeypatch, tmp_path,
    ):
        cert_path = tmp_path / 'https_cert.pem'
        cert_path.write_text('not inspected when already bound')
        monkeypatch.setattr(https_binding, '_paths', lambda: (cert_path, tmp_path / 'key.pem'))
        with app.app_context():
            set_bound_refid('already-bound')
            assert backfill_legacy_https_binding() == 'already-bound'
            assert get_bound_refid() == 'already-bound'


class TestBackfillResilience:
    def test_unreadable_binding_does_not_break_startup(self, app, monkeypatch):
        """A database error while reading the binding (first boot after an
        update, base not ready yet) must not propagate into create_app."""
        def _boom():
            raise RuntimeError('database unavailable')
        monkeypatch.setattr(https_binding, 'get_bound_refid', _boom)
        with app.app_context():
            assert https_binding.backfill_legacy_https_binding() == ''


class TestSubscriberRegistration:
    def test_backfill_runs_with_app_context(self, app, monkeypatch):
        import services.events as events

        observed_contexts = []
        monkeypatch.setattr(events.event_bus, 'subscribe', MagicMock())
        monkeypatch.setattr(
            https_binding,
            'backfill_legacy_https_binding',
            lambda: observed_contexts.append(has_app_context()),
        )
        monkeypatch.setattr(
            https_binding.register_https_binding_subscriber,
            '_done',
            False,
            raising=False,
        )

        https_binding.register_https_binding_subscriber(app)

        assert observed_contexts == [True]


class TestMaterialization:
    def test_private_key_is_loaded_through_key_codec(self, monkeypatch, tmp_path):
        cert_path = tmp_path / 'https_cert.pem'
        key_path = tmp_path / 'https_key.pem'
        monkeypatch.setattr(https_binding, '_paths', lambda: (cert_path, key_path))

        key_pem = b'-----BEGIN PRIVATE KEY-----\ntest-key\n-----END PRIVATE KEY-----\n'
        load_key = MagicMock(return_value=key_pem)
        monkeypatch.setattr(https_binding, 'load_pem_bytes', load_key, raising=False)
        stored_key = base64.b64encode(b'ENC:encrypted-at-rest').decode()
        cert = SimpleNamespace(
            id=7,
            crt=base64.b64encode(
                b'-----BEGIN CERTIFICATE-----\ntest-cert\n-----END CERTIFICATE-----\n'
            ).decode(),
            prv=stored_key,
            caref=None,
        )

        https_binding.materialize_https_cert(cert)

        load_key.assert_called_once_with(stored_key, context='certificate 7')
        assert key_path.read_bytes() == key_pem


class TestRenewalSubscriber:
    def _payload(self, refid):
        return {'certificate': {'refid': refid, 'id': 1}}

    def test_other_certificate_is_ignored(self, app, clean_binding, monkeypatch):
        materialize = MagicMock()
        monkeypatch.setattr(https_binding, 'materialize_https_cert', materialize)
        with app.app_context():
            set_bound_refid('bound-ref')
            on_certificate_renewed('certificate.renewed',
                                   self._payload('other-ref'), None, {})
        assert materialize.call_count == 0

    def test_no_binding_is_a_noop(self, app, clean_binding, monkeypatch):
        materialize = MagicMock()
        monkeypatch.setattr(https_binding, 'materialize_https_cert', materialize)
        with app.app_context():
            on_certificate_renewed('certificate.renewed',
                                   self._payload('any'), None, {})
        assert materialize.call_count == 0

    def test_bound_certificate_rematerializes_and_restarts(
        self, app, clean_binding, monkeypatch, create_cert,
    ):
        restart = MagicMock(return_value=(True, 'ok'))
        materialize = MagicMock()
        monkeypatch.setattr(https_binding, 'materialize_https_cert', materialize)
        import utils.service_manager as sm
        monkeypatch.setattr(sm, 'restart_service', restart)
        monkeypatch.delenv('UCM_DOCKER', raising=False)

        cert = create_cert()
        refid = cert.get('refid')
        assert refid, cert
        with app.app_context():
            set_bound_refid(refid)
            on_certificate_renewed(
                'certificate.renewed',
                {'certificate': {'refid': refid, 'id': cert.get('id')}}, None, {},
            )
        assert materialize.call_count == 1
        assert restart.call_count == 1

    def test_subscriber_never_raises(self, app, clean_binding, monkeypatch):
        def boom(_cert):
            raise RuntimeError('disk full')
        monkeypatch.setattr(https_binding, 'materialize_https_cert', boom)
        with app.app_context():
            set_bound_refid('x')
            # missing cert row → warning path, no exception
            on_certificate_renewed('certificate.renewed',
                                   self._payload('x'), None, {})


class TestUnbindEndpoint:
    def test_unbind_without_binding_is_400(self, app, auth_client, clean_binding):
        assert auth_client.post('/api/v2/system/https/unbind').status_code == 400

    def test_unbind_clears_the_binding(self, app, auth_client, clean_binding):
        with app.app_context():
            set_bound_refid('bound-for-unbind')
        r = auth_client.post('/api/v2/system/https/unbind')
        assert r.status_code == 200
        with app.app_context():
            assert get_bound_refid() == ''

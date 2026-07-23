"""Tests for delegated OCSP responder auto-renewal (issue #226 follow-up).

The scheduled task renews responder certificates nearing expiry with the same
key pair and extensions, rebinds ocsp_responder_cert_<ca_id> to the new row,
and archives the old certificate.
"""
import base64
import json
from datetime import timedelta

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import ExtensionOID

from tests.conftest import get_json
from utils.datetime_utils import utc_now

CONTENT_JSON = 'application/json'
OCSP_SIGNING_OID = '1.3.6.1.5.5.7.3.9'


def _issue_responder_cert(auth_client, ca_id, cn):
    payload = {
        'cn': cn, 'ca_id': ca_id, 'key_type': 'rsa', 'key_size': 2048,
        'validity_days': 90, 'cert_type': 'custom',
        'extra_ekus': ['OCSPSigning'],
    }
    r = auth_client.post('/api/v2/certificates',
                         data=json.dumps(payload), content_type=CONTENT_JSON)
    assert r.status_code in (200, 201), r.data
    return get_json(r)['data']['id']


def _bind_responder(app, ca_id, cert_id):
    with app.app_context():
        from models import SystemConfig, db
        row = SystemConfig.query.filter_by(key=f'ocsp_responder_cert_{ca_id}').first()
        if row:
            row.value = str(cert_id)
        else:
            db.session.add(SystemConfig(key=f'ocsp_responder_cert_{ca_id}',
                                        value=str(cert_id)))
        db.session.commit()


def _set_cert_window(app, cert_id, valid_from, valid_to):
    with app.app_context():
        from models import Certificate, db
        cert = db.session.get(Certificate, cert_id)
        cert.valid_from = valid_from
        cert.valid_to = valid_to
        db.session.commit()


def _run(app):
    with app.app_context():
        from services.ocsp_responder_renewal import run_ocsp_responder_renewal
        return run_ocsp_responder_renewal()


def _binding_value(app, ca_id):
    with app.app_context():
        from models import SystemConfig
        row = SystemConfig.query.filter_by(key=f'ocsp_responder_cert_{ca_id}').first()
        return row.value if row else None


class TestOcspResponderRenewal:

    def test_renews_expiring_responder_and_rebinds(self, app, auth_client, create_ca):
        ca = create_ca(cn='OCSP Renewal CA')
        cert_id = _issue_responder_cert(auth_client, ca['id'], 'ocsp-renew.test')
        _bind_responder(app, ca['id'], cert_id)
        # 90-day cert, 5 days left: due (threshold 30 days)
        _set_cert_window(app, cert_id,
                         utc_now() - timedelta(days=85),
                         utc_now() + timedelta(days=5))

        stats = _run(app)
        assert stats['renewed'] == 1, stats
        assert stats['failed'] == 0

        new_id = int(_binding_value(app, ca['id']))
        assert new_id != cert_id

        with app.app_context():
            from models import Certificate, db
            old = db.session.get(Certificate, cert_id)
            new = db.session.get(Certificate, new_id)
            assert old.archived is True
            assert new.caref == old.caref
            assert new.prv == old.prv  # same key pair
            old_x509 = x509.load_pem_x509_certificate(
                base64.b64decode(old.crt), default_backend())
            new_x509 = x509.load_pem_x509_certificate(
                base64.b64decode(new.crt), default_backend())

        assert new_x509.subject == old_x509.subject
        assert new_x509.public_key().public_numbers() == \
            old_x509.public_key().public_numbers()
        eku = new_x509.extensions.get_extension_for_oid(
            ExtensionOID.EXTENDED_KEY_USAGE)
        assert OCSP_SIGNING_OID in {o.dotted_string for o in eku.value}
        # renewed at par: ~90 days again
        days = (new_x509.not_valid_after_utc - new_x509.not_valid_before_utc).days
        assert 88 <= days <= 92

    def test_not_due_responder_is_skipped(self, app, auth_client, create_ca):
        ca = create_ca(cn='OCSP NotDue CA')
        cert_id = _issue_responder_cert(auth_client, ca['id'], 'ocsp-notdue.test')
        _bind_responder(app, ca['id'], cert_id)

        stats = _run(app)
        assert stats['renewed'] == 0
        assert int(_binding_value(app, ca['id'])) == cert_id

        with app.app_context():
            from models import Certificate, db
            assert db.session.get(Certificate, cert_id).archived in (False, None)

    def test_disabled_config_skips_everything(self, app, auth_client, create_ca):
        ca = create_ca(cn='OCSP Disabled CA')
        cert_id = _issue_responder_cert(auth_client, ca['id'], 'ocsp-disabled.test')
        _bind_responder(app, ca['id'], cert_id)
        _set_cert_window(app, cert_id,
                         utc_now() - timedelta(days=85),
                         utc_now() + timedelta(days=5))

        with app.app_context():
            from models import SystemConfig, db
            db.session.add(SystemConfig(key='ocsp_responder_auto_renew',
                                        value='false'))
            db.session.commit()
        try:
            stats = _run(app)
            assert stats == {'renewed': 0, 'failed': 0, 'skipped': 0}
            assert int(_binding_value(app, ca['id'])) == cert_id
        finally:
            with app.app_context():
                from models import SystemConfig, db
                row = SystemConfig.query.filter_by(
                    key='ocsp_responder_auto_renew').first()
                if row:
                    db.session.delete(row)
                    db.session.commit()
            # shared session-scoped DB: leave this binding not-due so later
            # tests' global runs don't pick it up
            _set_cert_window(app, cert_id, utc_now(),
                             utc_now() + timedelta(days=90))

    def test_revoked_responder_is_skipped(self, app, auth_client, create_ca):
        ca = create_ca(cn='OCSP Revoked CA')
        cert_id = _issue_responder_cert(auth_client, ca['id'], 'ocsp-revoked.test')
        _bind_responder(app, ca['id'], cert_id)
        _set_cert_window(app, cert_id,
                         utc_now() - timedelta(days=85),
                         utc_now() + timedelta(days=5))
        with app.app_context():
            from models import Certificate, db
            cert = db.session.get(Certificate, cert_id)
            cert.revoked = True
            db.session.commit()

        stats = _run(app)
        assert stats['renewed'] == 0
        assert int(_binding_value(app, ca['id'])) == cert_id

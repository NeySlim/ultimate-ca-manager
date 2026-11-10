"""Work-queue rules: one kind per certificate, precedence, and the auto-renewal window."""
import json
from datetime import timedelta

import pytest

from models import CA, Certificate, SystemConfig, db
from models.policy import ApprovalRequest
from tests.test_dashboard_queue import SETTINGS, _ca, _cert, _find, _queue, _set
from utils.datetime_utils import utc_now


@pytest.fixture
def rules(app):
    """Auto-renewal on for 'manual' certificates, 30 days; rows removed afterwards."""
    keys = SETTINGS + ('auto_renewal_days',)
    created = {'cas': [], 'certs': [], 'requests': []}
    with app.app_context():
        saved = {k: getattr(SystemConfig.query.filter_by(key=k).first(), 'value', None) for k in keys}
        _set('auto_renewal_enabled', 'true')
        _set('auto_renewal_sources', '["manual"]')
        _set('auto_renewal_days', '30')
        db.session.commit()

        def ca(name, **kw):
            row = _ca(name, **kw)
            created['cas'].append(row.id)
            return row

        def cert(name, days, **kw):
            row = _cert(name, utc_now() + timedelta(days=days), **kw)
            created['certs'].append(row.id)
            return row

        def reject(certificate, **data):
            row = ApprovalRequest(request_type='renewal', status='rejected', created_at=utc_now(),
                                  request_data=json.dumps({'certificate_id': certificate.id, **data}))
            db.session.add(row)
            db.session.flush()
            created['requests'].append(row.id)

        def days(value):
            _set('auto_renewal_days', str(value))
            db.session.commit()

        yield type('Rules', (), {'ca': staticmethod(ca), 'cert': staticmethod(cert),
                                 'reject': staticmethod(reject), 'days': staticmethod(days)})
        db.session.rollback()
        ApprovalRequest.query.filter(ApprovalRequest.id.in_(created['requests'])).delete(synchronize_session=False)
        Certificate.query.filter(Certificate.id.in_(created['certs'])).delete(synchronize_session=False)
        CA.query.filter(CA.id.in_(created['cas'])).delete(synchronize_session=False)
        for key, value in saved.items():
            _set(key, value)
        db.session.commit()


def _kinds(client, cert_id):
    return [i['kind'] for i in _queue(client)['items'] if i['id'] == cert_id and i['kind'] != 'ca_expiring'
            and i['kind'] not in ('approval_pending', 'acme_order_failed')]


def test_manual_refusal_does_not_hide_a_blocked_renewal(app, auth_client, rules):
    with app.app_context():
        ca = rules.ca('rules-offline-a', offline=True, prv='k')
        cert = rules.cert('rules-manual-refusal', 10, prv='k', caref=ca.refid)
        rules.reject(cert, trigger='manual')
        db.session.commit()
        assert _find(_queue(auth_client), 'auto_renewal_blocked', cert.id) is not None


def test_automatic_refusal_parks_a_blocked_renewal_as_declined(app, auth_client, rules):
    with app.app_context():
        ca = rules.ca('rules-offline-b', offline=True, prv='k')
        cert = rules.cert('rules-auto-refusal', 10, prv='k', caref=ca.refid)
        rules.reject(cert, trigger='auto')
        db.session.commit()
        queue = _queue(auth_client)
        assert _find(queue, 'renewal_declined', cert.id) is not None
        assert _find(queue, 'auto_renewal_blocked', cert.id) is None


def test_blocked_is_bounded_by_the_auto_renewal_days(app, auth_client, rules):
    with app.app_context():
        rules.days(7)
        ca = rules.ca('rules-offline-c', offline=True, prv='k')
        far = rules.cert('rules-not-yet-due', 25, prv='k', caref=ca.refid)
        near = rules.cert('rules-due', 5, prv='k', caref=ca.refid)
        db.session.commit()
        assert _kinds(auth_client, far.id) == []
        item = _find(_queue(auth_client), 'auto_renewal_blocked', near.id)
        assert item is not None and item['tier'] == 'critical'


def test_declined_then_reissued_identically_is_superseded(app, auth_client, rules):
    with app.app_context():
        ca = rules.ca('rules-ca-d', prv='k')
        old = rules.cert('rules-reissued', 10, prv='k', caref=ca.refid)
        rules.cert('rules-reissued', 300, prv='k', caref=ca.refid)
        rules.reject(old, trigger='manual')
        db.session.commit()
        assert _kinds(auth_client, old.id) == []


def test_a_certificate_in_two_kinds_appears_once_with_the_higher_precedence(app, auth_client, rules):
    with app.app_context():
        cert = rules.cert('rules-two-kinds', 5, source='scep')
        rules.reject(cert, trigger='manual')
        db.session.commit()
        assert _kinds(auth_client, cert.id) == ['renewal_declined']


def test_a_blocked_renewal_with_a_manual_refusal_appears_once(app, auth_client, rules):
    with app.app_context():
        ca = rules.ca('rules-offline-e', offline=True, prv='k')
        cert = rules.cert('rules-blocked-and-refused', 10, prv='k', caref=ca.refid)
        rules.reject(cert, trigger='manual')
        db.session.commit()
        assert _kinds(auth_client, cert.id) == ['auto_renewal_blocked']



def test_a_keyless_msca_certificate_is_a_manual_renewal(app, auth_client, rules):
    with app.app_context():
        cert = rules.cert('rules-msca', 10, source='msca')
        db.session.commit()
        assert _kinds(auth_client, cert.id) == ['manual_renewal_due']

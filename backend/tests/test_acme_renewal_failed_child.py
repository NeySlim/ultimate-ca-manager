"""A failed renewal leaves no order behind and names the CA's reason."""
from unittest.mock import MagicMock, patch

import pytest

from models import SystemConfig, db
from models.acme_models import AcmeClientOrder, DnsProvider
from services import acme_renewal_service as renew_mod

EMAIL = 'acme.client.email'


@pytest.fixture
def orders(app):
    """An issued order and the pending one its renewal opens at the CA."""
    with app.app_context():
        provider = DnsProvider(name='failed-child', provider_type='gandi', credentials='{}')
        db.session.add(provider)
        db.session.flush()
        parent = AcmeClientOrder(domains='["example.com"]', environment='production', challenge_type='dns-01',
                                 status='issued', renewal_enabled=True, dns_provider_id=provider.id,
                                 order_url='https://ca.example/order/p')
        child = AcmeClientOrder(domains='["example.com"]', environment='production', challenge_type='dns-01',
                                status='pending', order_url='https://ca.example/order/c',
                                finalize_url='https://ca.example/order/c/finalize')
        child.set_challenges_dict({'example.com': {'dns_txt_value': 'token', 'authz_url': 'https://ca.example/authz/c'}})
        db.session.add_all([parent, child])
        email = SystemConfig.query.filter_by(key=EMAIL).first()
        previous = email.value if email else None
        if email:
            email.value = 'renewal-test@example.com'
        else:
            db.session.add(SystemConfig(key=EMAIL, value='renewal-test@example.com', description='test'))
        db.session.commit()
        ids = parent.id, child.id, provider.id
        yield ids
        db.session.rollback()
        AcmeClientOrder.query.filter(AcmeClientOrder.id.in_(ids[:2])).delete()
        db.session.delete(db.session.get(DnsProvider, ids[2]))
        email = SystemConfig.query.filter_by(key=EMAIL).first()
        if previous is None:
            db.session.delete(email)
        else:
            email.value = previous
        db.session.commit()


def _client(child_id, waited=('ready', {}), finalize=None):
    client = MagicMock()
    child = db.session.get(AcmeClientOrder, child_id)
    client.create_order.return_value = (True, 'ok', child)
    client.verify_challenge.return_value = (True, 'ok')

    def _wait(order):
        status, data = waited
        order.status = status  # what check_order_status writes on the way
        return status, data

    client.wait_for_order.side_effect = _wait
    client.finalize_order.side_effect = finalize or RuntimeError('finalize failed')
    client.check_authorization_status.return_value = ('invalid', {'error': {'detail': 'DNS problem: NXDOMAIN'}})
    return client


def _renew(parent_id, client):
    dns = MagicMock()
    dns.create_txt_record.return_value = (True, 'ok')
    dns.delete_txt_record.return_value = (True, 'ok')
    with patch('services.acme.dns_providers.create_provider', return_value=dns), \
            patch('services.acme.acme_client_service.AcmeClientService.for_order', return_value=client), \
            patch('time.sleep', return_value=None), \
            patch.object(renew_mod, 'wait_for_challenges', return_value={'ok': True, 'missing': [], 'waited': 0}):
        return renew_mod.renew_certificate(db.session.get(AcmeClientOrder, parent_id))


def test_an_invalid_order_fails_with_the_ca_detail_and_is_removed(app, orders):
    parent_id, child_id, _ = orders
    with app.app_context():
        client = _client(child_id, waited=('invalid', {'error': {'detail': 'Correct value not found for DNS challenge'}}))
        with pytest.raises(Exception, match='Order became invalid: Correct value not found for DNS challenge'):
            _renew(parent_id, client)
        client.finalize_order.assert_not_called()
        assert db.session.get(AcmeClientOrder, child_id) is None
        assert db.session.get(AcmeClientOrder, parent_id).status == 'issued'


def test_an_invalid_order_without_detail_names_the_failed_authorization(app, orders):
    parent_id, child_id, _ = orders
    with app.app_context():
        client = _client(child_id, waited=('invalid', {}))
        with pytest.raises(Exception, match='Order became invalid: example.com: DNS problem: NXDOMAIN'):
            _renew(parent_id, client)


def test_a_renewal_that_fails_before_issuance_removes_its_order(app, orders):
    parent_id, child_id, _ = orders
    with app.app_context():
        with pytest.raises(RuntimeError, match='finalize failed'):
            _renew(parent_id, _client(child_id))
        assert db.session.get(AcmeClientOrder, child_id) is None


def test_an_order_still_pending_at_the_deadline_fails_with_its_status_and_is_removed(app, orders):
    parent_id, child_id, _ = orders
    with app.app_context():
        client = _client(child_id, waited=('pending', {}))
        with pytest.raises(Exception, match=r'Order not ready after polling \(status: pending\)'):
            _renew(parent_id, client)
        client.finalize_order.assert_not_called()
        assert db.session.get(AcmeClientOrder, child_id) is None


# 'error' is what a finalize that failed after its request was sent leaves behind
@pytest.mark.parametrize('status', ['processing', 'valid', 'error'])
def test_an_order_the_ca_may_still_complete_is_kept(app, orders, status):
    parent_id, child_id, _ = orders

    def _finalize(order):
        order.status = status
        db.session.commit()
        return False, 'Certificate not ready after polling', None

    with app.app_context():
        with pytest.raises(Exception, match='Certificate not ready'):
            _renew(parent_id, _client(child_id, finalize=_finalize))
        kept = db.session.get(AcmeClientOrder, child_id)
        assert kept is not None and kept.status == status


def test_the_scheduler_records_the_ca_detail_on_the_renewed_order(app, orders):
    parent_id, child_id, _ = orders
    with app.app_context():
        client = _client(child_id, waited=('invalid', {'error': {'detail': 'CAA record forbids issuance'}}))
        dns = MagicMock()
        dns.create_txt_record.return_value = (True, 'ok')
        dns.delete_txt_record.return_value = (True, 'ok')
        with patch('services.acme.dns_providers.create_provider', return_value=dns), \
                patch('services.acme.acme_client_service.AcmeClientService.for_order', return_value=client), \
                patch('time.sleep', return_value=None), \
                patch.object(renew_mod, 'wait_for_challenges', return_value={'ok': True, 'missing': [], 'waited': 0}), \
                patch.object(renew_mod, '_order_is_due', return_value=True):
            renew_mod.scheduled_acme_renewal()
        parent = db.session.get(AcmeClientOrder, parent_id)
        assert parent.renewal_failures == 1
        assert parent.error_message == 'Order became invalid: CAA record forbids issuance'
        assert db.session.get(AcmeClientOrder, child_id) is None

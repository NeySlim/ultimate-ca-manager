"""A renewal leaves one order for its names, whatever status it started from."""
from unittest.mock import MagicMock, patch

import pytest

from models import Certificate, SystemConfig, db
from models.acme_models import AcmeClientOrder, DnsProvider
from services import acme_renewal_service as renew_mod
from tests.acme_fake_ca import FakeCA

URLS = ('https://ca.example/order/parent', 'https://ca.example/order/child')
EMAIL = 'acme.client.email'


@pytest.fixture
def orders(app):
    """An order to renew and the one its renewal opens; the configured email is put back."""
    with app.app_context():
        provider = DnsProvider(name='no-doubling', provider_type='gandi', credentials='{}')
        db.session.add(provider)
        db.session.flush()
        parent = AcmeClientOrder(domains='["example.com"]', environment='production', challenge_type='dns-01',
                                 status='issued', renewal_enabled=True, dns_provider_id=provider.id,
                                 order_url=URLS[0], key_type='EC-P256')
        child = AcmeClientOrder(domains='["example.com"]', environment='production', challenge_type='dns-01',
                                status='pending', order_url=URLS[1], finalize_url=f'{URLS[1]}/finalize',
                                key_type='EC-P256')
        child.set_challenges_dict({'example.com': {'dns_txt_value': 'token'}})
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
        cert_id = db.session.get(AcmeClientOrder, ids[0]).certificate_id
        AcmeClientOrder.query.filter(AcmeClientOrder.id.in_(ids[:2])).delete()
        if cert_id:
            Certificate.query.filter_by(id=cert_id).delete()
        db.session.delete(db.session.get(DnsProvider, ids[2]))
        email = SystemConfig.query.filter_by(key=EMAIL).first()
        if previous is None:
            db.session.delete(email)
        else:
            email.value = previous
        db.session.commit()


def _client(child_id):
    """A client on a CA that holds the child order, ready; finalize is the real one."""
    ca = FakeCA()
    ca.order(URLS[1], ['example.com'])
    client = ca.client()
    client._fetch_directory = lambda: {}
    client._get_account_url = lambda: 'https://ca.example/acct/1'
    client.create_order = MagicMock(return_value=(True, 'ok', db.session.get(AcmeClientOrder, child_id)))
    client.verify_challenge = lambda _order, _domain: (True, 'ok')
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


def _next_cycle():
    renewed = []
    with patch.object(renew_mod, 'renew_certificate', side_effect=lambda o, **_kw: renewed.append(o.id)), \
            patch.object(renew_mod, '_order_is_due', return_value=True):
        renew_mod.scheduled_acme_renewal()
    return renewed


@pytest.mark.parametrize('status', ['issued', 'valid'])
def test_a_renewal_leaves_one_order_and_it_comes_up_again(orders, status):
    # Renew is also offered on a valid order, whose import was refused
    parent_id, child_id, _provider = orders
    parent = db.session.get(AcmeClientOrder, parent_id)
    parent.status = status
    db.session.commit()
    ok, message = _renew(parent_id, _client(child_id))
    assert ok, message
    assert db.session.get(AcmeClientOrder, child_id) is None
    parent = db.session.get(AcmeClientOrder, parent_id)
    assert parent.status == 'issued' and db.session.get(Certificate, parent.certificate_id) is not None
    assert (parent.order_url, parent.certificate_url) == (URLS[1], f'{URLS[1]}/cert')
    assert parent_id in _next_cycle()


def test_a_failed_renewal_removes_its_order_and_leaves_the_original_alone(orders):
    # The order this renewal opened has nothing to keep; a reused HTTP-01 one is another test's case
    parent_id, child_id, _provider = orders
    client = _client(child_id)
    client.finalize_order = lambda _order, **_kwargs: (False, 'refused', None)
    with pytest.raises(Exception, match='refused'):
        _renew(parent_id, client)
    assert db.session.get(AcmeClientOrder, child_id) is None
    parent = db.session.get(AcmeClientOrder, parent_id)
    assert parent.order_url == URLS[0] and parent.status == 'issued'


def test_a_failed_save_keeps_both_orders_and_the_original_retries(orders):
    parent_id, child_id, _provider = orders
    real = renew_mod.AcmeClientService._complete_renewal

    def save_fails(self, order, renews, *args):
        db.session.add(Certificate())  # refid is required: the commit fails
        return real(self, order, renews, *args)

    with patch.object(renew_mod.AcmeClientService, '_complete_renewal', save_fails), \
            pytest.raises(Exception, match='Database error'):
        _renew(parent_id, _client(child_id))
    db.session.expire_all()
    assert db.session.get(AcmeClientOrder, child_id) is not None
    parent = db.session.get(AcmeClientOrder, parent_id)
    assert parent.status == 'issued' and parent.order_url == URLS[0]
    assert parent_id in _next_cycle()

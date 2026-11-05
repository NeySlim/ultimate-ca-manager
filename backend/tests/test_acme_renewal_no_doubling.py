"""A renewal leaves one order for its names, whatever status it started from."""
from unittest.mock import MagicMock, patch

import pytest

from models import SystemConfig, db
from models.acme_models import AcmeClientOrder, DnsProvider
from services import acme_renewal_service as renew_mod

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
                                 order_url=URLS[0])
        child = AcmeClientOrder(domains='["example.com"]', environment='production', challenge_type='dns-01',
                                status='pending', order_url=URLS[1], finalize_url=f'{URLS[1]}/finalize')
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
        AcmeClientOrder.query.filter(AcmeClientOrder.id.in_(ids[:2])).delete()
        db.session.delete(db.session.get(DnsProvider, ids[2]))
        email = SystemConfig.query.filter_by(key=EMAIL).first()
        if previous is None:
            db.session.delete(email)
        else:
            email.value = previous
        db.session.commit()


def _issued(order):
    order.status = 'issued'
    order.certificate_id = 4242
    db.session.commit()
    return True, 'issued', 4242


def _renew(parent_id, child_id, finalize=_issued):
    client = MagicMock()
    client.create_order.return_value = (True, 'ok', db.session.get(AcmeClientOrder, child_id))
    client.verify_challenge.return_value = (True, 'ok')
    client.wait_for_order.return_value = ('ready', {})
    client.finalize_order.side_effect = finalize
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
    with patch.object(renew_mod, 'renew_certificate', side_effect=lambda o: renewed.append(o.id)), \
            patch.object(renew_mod, '_order_is_due', return_value=True):
        renew_mod.scheduled_acme_renewal()
    return renewed


@pytest.mark.parametrize('status', ['issued', 'valid'])
def test_a_renewal_leaves_one_order_and_it_comes_up_again(orders, status):
    # Renew is also offered on a valid order, whose import was refused
    parent_id, child_id, _provider = orders
    parent = db.session.get(AcmeClientOrder, parent_id)
    parent.status = status
    db.session.get(AcmeClientOrder, child_id).certificate_url = 'https://ca.example/cert/new'
    db.session.commit()
    ok, message = _renew(parent_id, child_id)
    assert ok, message
    assert db.session.get(AcmeClientOrder, child_id) is None
    parent = db.session.get(AcmeClientOrder, parent_id)
    assert (parent.certificate_id, parent.order_url, parent.certificate_url) == \
        (4242, URLS[1], 'https://ca.example/cert/new')
    assert parent_id in _next_cycle()


def test_a_failed_renewal_removes_its_order_and_leaves_the_original_alone(orders):
    # The order this renewal opened has nothing to keep; a reused HTTP-01 one is another test's case
    parent_id, child_id, _provider = orders
    with pytest.raises(Exception, match='refused'):
        _renew(parent_id, child_id, finalize=lambda _order: (False, 'refused', None))
    assert db.session.get(AcmeClientOrder, child_id) is None
    parent = db.session.get(AcmeClientOrder, parent_id)
    assert parent.order_url == URLS[0] and parent.status == 'issued'


def test_a_failed_save_keeps_both_orders_and_the_original_retries(orders):
    parent_id, child_id, _provider = orders
    real = renew_mod.commit_or_rollback

    def _only_the_final_save_fails(log, message):
        if 'persist renewed' in message:
            db.session.rollback()
            return False
        return real(log, message)

    with patch.object(renew_mod, 'commit_or_rollback', side_effect=_only_the_final_save_fails), \
            pytest.raises(RuntimeError, match='persist renewed'):
        _renew(parent_id, child_id)
    db.session.expire_all()
    assert db.session.get(AcmeClientOrder, child_id) is not None
    assert db.session.get(AcmeClientOrder, parent_id).status == 'issued'
    assert parent_id in _next_cycle()

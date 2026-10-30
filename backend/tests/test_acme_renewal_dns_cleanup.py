"""Renewal DNS TXT cleanup on failure paths (LOT A review fix)."""
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def renewal_order(app):
    from models import db, SystemConfig
    from models.acme_models import AcmeClientOrder, DnsProvider

    with app.app_context():
        provider = DnsProvider(
            name='test-gandi',
            provider_type='gandi',
            credentials='{}',
        )
        db.session.add(provider)
        db.session.flush()

        email_cfg = SystemConfig.query.filter_by(key='acme.client.email').first()
        if email_cfg:
            email_cfg.value = 'renewal-test@example.com'
        else:
            db.session.add(SystemConfig(
                key='acme.client.email',
                value='renewal-test@example.com',
                description='test',
            ))

        order = AcmeClientOrder(
            domains='["example.com"]',
            environment='production',
            challenge_type='dns-01',
            status='issued',
            renewal_enabled=True,
            dns_provider_id=provider.id,
        )
        db.session.add(order)
        db.session.commit()
        yield order.id, provider.id


def test_renewal_submits_upstream_when_propagation_not_ready(app, renewal_order):
    """Soft-fail: a local DNS pre-check miss must NOT abort the renewal — the challenge
    is still submitted to the CA (which has its own DNS view). See acme_renewal_service."""
    from models import db, SystemConfig
    from models.acme_models import AcmeClientOrder
    from services import acme_renewal_service as renew_mod

    order_id, _provider_id = renewal_order
    deleted = []

    mock_provider = MagicMock()
    mock_provider.create_txt_record.return_value = (True, 'ok')
    mock_provider.delete_txt_record.side_effect = (
        lambda **kwargs: deleted.append(kwargs) or (True, 'ok')
    )

    with app.app_context():
        new_order = AcmeClientOrder(
            domains='["example.com"]',
            environment='production',
            challenge_type='dns-01',
            status='pending',
            order_url='https://ca.example/order/1',
            finalize_url='https://ca.example/order/1/finalize',
        )
        new_order.set_challenges_dict({
            'example.com': {'dns_txt_value': 'token-value'},
        })
        db.session.add(new_order)
        db.session.commit()

        mock_client = MagicMock()
        mock_client.create_order.return_value = (True, 'ok', new_order)
        mock_client.verify_challenge.return_value = (True, 'ok')
        # Stop the flow right after challenge submission so we don't need to mock
        # the full finalize/cert-import path; the pre-check must be behind us by then.
        mock_client.finalize_order.side_effect = RuntimeError('STOP_AFTER_SUBMIT')

        cfg = SystemConfig.query.filter_by(
            key='acme.client.dns_propagation_timeout',
        ).first()
        if cfg:
            cfg.value = '60'
        else:
            db.session.add(SystemConfig(
                key='acme.client.dns_propagation_timeout',
                value='60',
                description='test',
            ))
        db.session.commit()

        order = db.session.get(AcmeClientOrder, order_id)

        with patch('services.acme.dns_providers.create_provider', return_value=mock_provider), \
             patch(
                 'services.acme.acme_client_service.AcmeClientService.for_order',
                 return_value=mock_client,
             ), \
             patch('time.sleep', return_value=None), \
             patch.object(
                 renew_mod,
                 'wait_for_challenges',
                 return_value={'ok': False, 'missing': ['example.com'], 'waited': 5},
             ):
            # Renewal proceeds past the DNS pre-check (soft-fail) and reaches finalize,
            # where our sentinel stops it — it does NOT raise 'DNS propagation not ready'.
            with pytest.raises(RuntimeError, match='STOP_AFTER_SUBMIT'):
                renew_mod.renew_certificate(order)

    assert mock_provider.create_txt_record.called
    # The upstream challenge WAS submitted despite the local DNS miss.
    mock_client.verify_challenge.assert_called_once()
    assert mock_client.verify_challenge.call_args[0][1] == 'example.com'
    # TXT is still cleaned up on the way out (finally block).
    assert len(deleted) == 1
    assert deleted[0]['record_name'] == '_acme-challenge.example.com'


def test_renewal_deletes_txt_when_create_fails_on_second_domain(app, renewal_order):
    """Multi-domain renewal must clean up TXT records created before a later failure."""
    from models import db
    from models.acme_models import AcmeClientOrder
    from services import acme_renewal_service as renew_mod

    order_id, _provider_id = renewal_order
    deleted = []
    create_calls = []

    def create_side_effect(**kwargs):
        create_calls.append(kwargs['domain'])
        if kwargs['domain'] == 'www.example.com':
            return False, 'provider error'
        return True, 'ok'

    mock_provider = MagicMock()
    mock_provider.create_txt_record.side_effect = create_side_effect
    mock_provider.delete_txt_record.side_effect = (
        lambda **kwargs: deleted.append(kwargs) or (True, 'ok')
    )

    with app.app_context():
        new_order = AcmeClientOrder(
            domains='["example.com", "www.example.com"]',
            environment='production',
            challenge_type='dns-01',
            status='pending',
            order_url='https://ca.example/order/1',
            finalize_url='https://ca.example/order/1/finalize',
        )
        new_order.set_challenges_dict({
            'example.com': {'dns_txt_value': 'token-a'},
            'www.example.com': {'dns_txt_value': 'token-b'},
        })
        db.session.add(new_order)
        db.session.commit()

        mock_client = MagicMock()
        mock_client.create_order.return_value = (True, 'ok', new_order)

        order = db.session.get(AcmeClientOrder, order_id)

        with patch('services.acme.dns_providers.create_provider', return_value=mock_provider), \
             patch(
                 'services.acme.acme_client_service.AcmeClientService.for_order',
                 return_value=mock_client,
             ):
            with pytest.raises(Exception, match='Failed to create DNS record for www.example.com'):
                renew_mod.renew_certificate(order)

    assert create_calls == ['example.com', 'www.example.com']
    assert len(deleted) == 2
    assert {d['domain'] for d in deleted} == {'example.com', 'www.example.com'}


def test_renewal_writes_and_cleans_up_txt_under_the_name_lock(app, renewal_order, monkeypatch):
    from contextlib import contextmanager
    from models import db
    from models.acme_models import AcmeClientOrder
    from services import acme_renewal_service as renew_mod

    order_id, _provider_id = renewal_order
    held = []

    @contextmanager
    def _recording(name):
        held.append(name)
        yield
        held.remove(name)

    calls = []
    mock_provider = MagicMock()
    mock_provider.create_txt_record.side_effect = lambda **kw: calls.append(('create', list(held))) or (True, 'ok')
    mock_provider.delete_txt_record.side_effect = lambda **kw: calls.append(('delete', list(held))) or (True, 'ok')
    monkeypatch.setattr(renew_mod, 'txt_record_lock', _recording)

    with app.app_context():
        new_order = AcmeClientOrder(
            domains='["example.com"]', environment='production', challenge_type='dns-01',
            status='pending', order_url='https://ca.example/order/lk',
            finalize_url='https://ca.example/order/lk/finalize',
        )
        new_order.set_challenges_dict({'example.com': {'dns_txt_value': 'token-value'}})
        db.session.add(new_order)
        db.session.commit()
        mock_client = MagicMock()
        mock_client.create_order.return_value = (True, 'ok', new_order)
        mock_client.verify_challenge.side_effect = RuntimeError('STOP')
        order = db.session.get(AcmeClientOrder, order_id)
        with patch('services.acme.dns_providers.create_provider', return_value=mock_provider), \
             patch('services.acme.acme_client_service.AcmeClientService.for_order', return_value=mock_client), \
             patch('time.sleep', return_value=None), \
             patch.object(renew_mod, 'wait_for_challenges', return_value={'ok': True, 'missing': [], 'waited': 0}):
            with pytest.raises(RuntimeError, match='STOP'):
                renew_mod.renew_certificate(order)

    name = '_acme-challenge.example.com'
    assert calls == [('create', [name]), ('delete', [name])]

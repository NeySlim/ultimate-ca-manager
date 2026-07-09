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


def test_renewal_deletes_txt_when_propagation_not_ready(app, renewal_order):
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
             patch.object(
                 renew_mod,
                 'wait_for_challenges',
                 return_value={'ok': False, 'missing': ['example.com'], 'waited': 5},
             ):
            with pytest.raises(Exception, match='DNS propagation not ready'):
                renew_mod.renew_certificate(order)

    assert mock_provider.create_txt_record.called
    assert len(deleted) == 1
    assert deleted[0]['record_name'] == '_acme-challenge.example.com'
    assert deleted[0]['domain'] == 'example.com'

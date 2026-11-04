"""A renewal leaves one order on the schedule, not two that each renew at the next cycle."""
from unittest.mock import MagicMock, patch

from models import SystemConfig, db
from models.acme_models import AcmeClientOrder, DnsProvider
from services import acme_renewal_service as renew_mod

URLS = ('https://ca.example/order/parent', 'https://ca.example/order/child')


def test_only_the_original_order_comes_up_again(app):
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
        email = SystemConfig.query.filter_by(key='acme.client.email').first()
        if email:
            email.value = 'renewal-test@example.com'
        else:
            db.session.add(SystemConfig(key='acme.client.email', value='renewal-test@example.com', description='test'))
        db.session.commit()
        parent_id, child_id, provider_id = parent.id, child.id, provider.id

        def finalize(order):
            order.status = 'issued'
            order.certificate_id = 4242
            db.session.commit()
            return True, 'issued', 4242

        client = MagicMock()
        client.create_order.return_value = (True, 'ok', child)
        client.verify_challenge.return_value = (True, 'ok')
        client.finalize_order.side_effect = finalize
        dns = MagicMock()
        dns.create_txt_record.return_value = (True, 'ok')
        dns.delete_txt_record.return_value = (True, 'ok')
        try:
            with patch('services.acme.dns_providers.create_provider', return_value=dns), \
                    patch('services.acme.acme_client_service.AcmeClientService.for_order', return_value=client), \
                    patch('time.sleep', return_value=None), \
                    patch.object(renew_mod, 'wait_for_challenges',
                                 return_value={'ok': True, 'missing': [], 'waited': 0}):
                ok, message = renew_mod.renew_certificate(db.session.get(AcmeClientOrder, parent_id))
            assert ok, message

            renewed = []
            with patch.object(renew_mod, 'renew_certificate', side_effect=lambda o: renewed.append(o.id)), \
                    patch.object(renew_mod, '_order_is_due', return_value=True):
                renew_mod.scheduled_acme_renewal()
            assert parent_id in renewed and child_id not in renewed
            assert db.session.get(AcmeClientOrder, parent_id).certificate_id == 4242
        finally:
            db.session.rollback()
            AcmeClientOrder.query.filter(AcmeClientOrder.id.in_([parent_id, child_id])).delete()
            db.session.delete(db.session.get(DnsProvider, provider_id))
            db.session.commit()

"""An apex and its wildcard get one authorization each, both named by the base domain (RFC 8555 §7.1.4)."""
from models import db
from services.acme import acme_client_service as svc_module
from services.acme.acme_client_service import AcmeClientService
from tests.test_acme_client_alpn_ip_identifiers import _Response, _registered_account


class _RecordingProvider:
    def __init__(self):
        self.created = []

    def create_txt_record(self, domain, record_name, record_value, ttl=300):
        self.created.append((domain, record_name, record_value))
        return True, 'ok'


def test_apex_and_wildcard_keep_both_challenges(app, monkeypatch):
    with app.app_context():
        account = _registered_account()
        service = AcmeClientService(account=account)
        monkeypatch.setattr(service, 'ensure_account', lambda _email: (True, 'ok'))
        monkeypatch.setattr(service, '_fetch_directory', lambda: {'newOrder': 'https://ca.example/new-order'})
        authorizations = {'https://ca.example/authz/apex': False, 'https://ca.example/authz/wild': True}

        def fake_post(url, payload, use_jwk=False):
            if url == 'https://ca.example/new-order':
                return _Response(201, {
                    'expires': '2027-01-01T00:00:00Z',
                    'finalize': 'https://ca.example/order/1/finalize',
                    'authorizations': list(authorizations),
                }, 'https://ca.example/order/1')
            body = {
                'identifier': {'type': 'dns', 'value': 'example.com'},
                'status': 'pending',
                'challenges': [{'type': 'dns-01', 'token': url.rsplit('/', 1)[1],
                                'url': f'{url}/dns', 'status': 'pending'}],
            }
            if authorizations[url]:
                body['wildcard'] = True
            return _Response(200, body)

        monkeypatch.setattr(service, '_post', fake_post)
        ok, message, order = service.create_order(['example.com', '*.example.com'], 'admin@example.com',
                                                  challenge_type='dns-01')
        assert ok, message
        challenges = order.challenges_dict
        assert set(challenges) == {'example.com', '*.example.com'}
        assert challenges['*.example.com']['authz_url'] == 'https://ca.example/authz/wild'
        assert challenges['example.com']['dns_txt_value'] != challenges['*.example.com']['dns_txt_value']

        provider = _RecordingProvider()
        monkeypatch.setattr(svc_module, 'create_provider', lambda *_a: provider)
        ok, message, _ = service.setup_dns_challenge(order)
        assert ok, message
        assert sorted(provider.created) == sorted(
            ('example.com', '_acme-challenge.example.com', c['dns_txt_value']) for c in challenges.values())

        db.session.delete(order)
        db.session.delete(account)
        db.session.commit()

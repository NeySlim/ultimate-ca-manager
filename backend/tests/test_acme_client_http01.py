"""HTTP-01 for UCM's ACME client: UCM serves its tokens, checks them before
submitting, and renews HTTP-01 orders without a DNS provider (#392)."""
import json
import secrets
from unittest.mock import MagicMock, patch

import pytest
import requests
from werkzeug.test import Client

from api.v2.acme_client import orders as orders_mod
from models import db, AuditLog, SystemConfig
from models.acme_models import AcmeClientOrder
from protocol_http_server import ProtocolOnlyMiddleware
from services import acme_renewal_service as renew_mod
from services.acme import http01


def post_json(client, url, data=None):
    return client.post(url, data=json.dumps(data or {}), content_type='application/json')


def _token():
    return secrets.token_urlsafe(32)


class _Resp:
    def __init__(self, status_code, text='', headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}


@pytest.fixture
def make_order(app):
    created = []

    def _make(challenge_type='http-01', status='pending', domain='www.example.com',
              is_proxy_order=False, dns_provider_id=None):
        token = _token()
        with app.app_context():
            order = AcmeClientOrder(
                domains=json.dumps([domain]),
                environment='staging',
                challenge_type=challenge_type,
                status=status,
                order_url=f'https://ca.example/order/{token[:8]}',
                is_proxy_order=is_proxy_order,
                renewal_enabled=True,
                dns_provider_id=dns_provider_id,
            )
            order.set_challenges_dict({domain: {
                'url': 'https://ca.example/chall/1',
                'token': token,
                'key_authorization': f'{token}.thumbprint',
                'status': 'pending',
            }})
            db.session.add(order)
            db.session.commit()
            created.append(order.id)
            return order.id, token
    yield _make
    with app.app_context():
        AcmeClientOrder.query.filter(AcmeClientOrder.id.in_(created)).delete(synchronize_session=False)
        db.session.commit()


@pytest.fixture
def acme_email(app):
    with app.app_context():
        cfg = SystemConfig.query.filter_by(key='acme.client.email').first()
        if cfg:
            cfg.value = 'http01-test@example.com'
        else:
            db.session.add(SystemConfig(key='acme.client.email', value='http01-test@example.com'))
        db.session.commit()


# ---- serving the token -------------------------------------------------------

def test_pending_order_token_is_served(client, make_order):
    _, token = make_order()
    r = client.get(f'/.well-known/acme-challenge/{token}')
    assert r.status_code == 200
    assert r.get_data(as_text=True) == f'{token}.thumbprint'
    assert r.mimetype == 'application/octet-stream'


@pytest.mark.parametrize('kwargs', [
    {'status': 'issued'},
    {'status': 'invalid'},
    {'challenge_type': 'dns-01'},
    {'is_proxy_order': True},
])
def test_token_not_served_outside_a_pending_http01_client_order(client, make_order, kwargs):
    _, token = make_order(**kwargs)
    assert client.get(f'/.well-known/acme-challenge/{token}').status_code == 404


def test_unknown_or_malformed_token_is_404(client, make_order):
    _, token = make_order()
    # '_' is a LIKE wildcard: a near-miss must not match the stored token.
    near_miss = token[:5] + ('_' if token[5] != '_' else 'A') + token[6:]
    assert client.get(f'/.well-known/acme-challenge/{near_miss}').status_code == 404
    assert client.get('/.well-known/acme-challenge/short').status_code == 404
    # A prefix passes the SQL substring filter; only the exact token may be served.
    assert client.get(f'/.well-known/acme-challenge/{token[:30]}').status_code == 404


def test_http_protocol_port_lets_the_challenge_path_through(app, make_order):
    _, token = make_order()
    c = Client(ProtocolOnlyMiddleware(app))
    assert c.get(f'/.well-known/acme-challenge/{token}').status_code == 200
    assert c.get('/api/v2/health').status_code == 404


# ---- self-check ----------------------------------------------------------------

def test_challenge_url_brackets_ipv6():
    assert http01.challenge_url('2001:db8::1', 'tok') == 'http://[2001:db8::1]/.well-known/acme-challenge/tok'
    assert http01.challenge_url('www.example.com', 'tok') == 'http://www.example.com/.well-known/acme-challenge/tok'


@pytest.mark.parametrize('responses, ok', [
    ([_Resp(200, 'tok.thumb\n')], True),
    ([_Resp(301, headers={'Location': 'https://www.example.com/x'}), _Resp(200, 'tok.thumb')], True),
    ([_Resp(404)], False),
    ([_Resp(200, 'something else')], False),
])
def test_challenge_reachable(responses, ok):
    queue = list(responses)
    with patch.object(http01, '_get', side_effect=lambda url, pin: queue.pop(0)), \
         patch('utils.ssrf_protection.validate_url_not_cloud_metadata'):
        result, _reason = http01.challenge_reachable(
            'www.example.com', {'token': 'tok', 'key_authorization': 'tok.thumb'})
    assert result is ok


@pytest.mark.parametrize('exc, reason', [
    (ValueError('Cannot resolve host'), 'not resolvable'),
    (requests.ConnectionError('refused'), 'connection failed'),
    (requests.Timeout('slow'), 'timed out'),
])
def test_unreachable_reason_names_the_failure(exc, reason):
    with patch.object(http01, 'fetch_following_redirects', side_effect=exc), \
         patch('utils.ssrf_protection.validate_url_not_cloud_metadata'):
        ok, why = http01.challenge_reachable('www.example.com', {'token': 'tok', 'key_authorization': 'k'})
    assert not ok and reason in why and why.startswith('http://www.example.com/')


def _fake_client(verify_calls):
    client = MagicMock()
    client.verify_challenge.side_effect = lambda order, d: verify_calls.append(d) or (True, 'ok')
    client.check_order_status.return_value = ('pending', {})
    return client


def test_verify_refuses_to_submit_an_unreachable_http01_file(app, auth_client, make_order, monkeypatch):
    order_id, _ = make_order()
    calls = []
    monkeypatch.setattr(orders_mod.AcmeClientService, 'for_order', lambda o: _fake_client(calls))
    with patch.object(http01, '_get', return_value=_Resp(404)):
        r = post_json(auth_client, f'/api/v2/acme/client/orders/{order_id}/verify')
    assert r.status_code == 200, r.get_data(as_text=True)
    data = r.get_json()['data']
    assert data['http_not_ready'] is True
    assert data['missing'] == ['www.example.com']
    assert calls == []


def test_verify_submits_a_reachable_http01_file(app, auth_client, make_order, monkeypatch):
    order_id, token = make_order()
    calls = []
    monkeypatch.setattr(orders_mod.AcmeClientService, 'for_order', lambda o: _fake_client(calls))
    with patch.object(http01, '_get', return_value=_Resp(200, f'{token}.thumbprint')):
        r = post_json(auth_client, f'/api/v2/acme/client/orders/{order_id}/verify')
    assert 'http_not_ready' not in r.get_json()['data']
    assert calls == ['www.example.com']


def test_verify_force_skips_the_http01_check(app, auth_client, make_order, monkeypatch):
    order_id, _ = make_order()
    calls = []
    monkeypatch.setattr(orders_mod.AcmeClientService, 'for_order', lambda o: _fake_client(calls))
    with patch.object(http01, '_get', return_value=_Resp(404)):
        post_json(auth_client, f'/api/v2/acme/client/orders/{order_id}/verify', {'force': True})
    assert calls == ['www.example.com']


# ---- renewal -------------------------------------------------------------------

def _renew(app, order_id, new_order_id, probe_response):
    """Run renew_certificate with a mocked CA; return the client mock."""
    with app.app_context():
        order = db.session.get(AcmeClientOrder, order_id)
        new_order = db.session.get(AcmeClientOrder, new_order_id)
        client = MagicMock()
        client.create_order.return_value = (True, 'ok', new_order)
        client.verify_challenge.return_value = (True, 'ok')
        client.finalize_order.side_effect = RuntimeError('STOP_AFTER_SUBMIT')
        client._fetch_directory.return_value = {}
        with patch.object(renew_mod.AcmeClientService, 'for_order', return_value=client), \
             patch.object(http01, '_get', return_value=probe_response), \
             patch.object(http01, 'SELFCHECK_INTERVAL', 0), \
             patch.object(renew_mod, 'HTTP01_RENEWAL_WAIT', 0), \
             patch('time.sleep', return_value=None):
            try:
                renew_mod.renew_certificate(order)
            except RuntimeError as exc:
                assert 'STOP_AFTER_SUBMIT' in str(exc)
        return client


def test_http01_renewal_needs_no_dns_provider(app, make_order, acme_email):
    order_id, _ = make_order(status='issued')
    new_id, new_token = make_order()
    client = _renew(app, order_id, new_id, _Resp(200, f'{new_token}.thumbprint'))
    client.verify_challenge.assert_called_once()


def test_http01_renewal_stops_before_the_ca_when_the_file_is_unreachable(app, make_order, acme_email):
    order_id, _ = make_order(status='issued')
    new_id, _ = make_order()
    with pytest.raises(renew_mod.RenewalBlocked, match='not reachable'):
        _renew(app, order_id, new_id, _Resp(404))
    with app.app_context():
        new_order = db.session.get(AcmeClientOrder, new_id)
        assert new_order.status == 'pending'
        assert 'not reachable' in new_order.error_message


def test_tls_alpn_renewal_needs_no_dns_provider(app, make_order, acme_email):
    order_id, _ = make_order(challenge_type='tls-alpn-01', status='issued')
    new_id, _ = make_order(challenge_type='tls-alpn-01')
    client = _renew(app, order_id, new_id, _Resp(404))
    client.verify_challenge.assert_called_once()


def test_manual_dns01_renewal_says_why(app, make_order, acme_email):
    order_id, _ = make_order(challenge_type='dns-01', status='issued')
    with app.app_context():
        order = db.session.get(AcmeClientOrder, order_id)
        with pytest.raises(renew_mod.RenewalBlocked, match='manual DNS order'):
            renew_mod.renew_certificate(order)


def test_renew_endpoint_returns_the_blocking_reason(app, auth_client, make_order, acme_email):
    order_id, _ = make_order(challenge_type='dns-01', status='issued')
    r = post_json(auth_client, f'/api/v2/acme/client/orders/{order_id}/renew')
    assert r.status_code == 409
    assert 'manual DNS order' in r.get_json()['message']


def test_scheduled_renewal_failure_is_audited(app, make_order, acme_email):
    order_id, _ = make_order(challenge_type='dns-01', status='issued')
    with app.app_context():
        with patch.object(renew_mod, '_order_is_due', side_effect=lambda o, *a: o.id == order_id):
            renew_mod.scheduled_acme_renewal()
        order = db.session.get(AcmeClientOrder, order_id)
        assert order.renewal_failures == 1
        entry = AuditLog.query.filter_by(
            action='acme_order.auto_renewal_failed', resource_id=str(order_id)).first()
        assert entry is not None and entry.success is False

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
from models.acme_models import AcmeClientOrder, DnsProvider
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


@pytest.fixture(autouse=True)
def no_dns(monkeypatch):
    """The SSRF guard resolves the host; keep these tests off the network."""
    monkeypatch.setattr(http01, 'validate_url_not_cloud_metadata', lambda *a, **k: None)


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
    with patch.object(http01, '_get', side_effect=lambda *a, **k: queue.pop(0)):
        result, _reason = http01.challenge_reachable(
            'www.example.com', {'token': 'tok', 'key_authorization': 'tok.thumb'})
    assert result is ok


@pytest.mark.parametrize('exc, reason', [
    (ValueError('Cannot resolve host'), 'not resolvable'),
    (requests.ConnectionError('refused'), 'connection failed'),
    (requests.Timeout('slow'), 'timed out'),
])
def test_unreachable_reason_names_the_failure(exc, reason):
    with patch.object(http01, 'fetch_following_redirects', side_effect=exc):
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

def _renew(app, order_id, new_order_id, probe_response, client=None):
    """Run renew_certificate with a mocked CA; return the client mock."""
    with app.app_context():
        order = db.session.get(AcmeClientOrder, order_id)
        new_order = db.session.get(AcmeClientOrder, new_order_id)
        if client is None:
            client = MagicMock()
            client.account = None
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


def test_blocked_http01_renewal_reuses_the_pending_order(app, make_order, acme_email):
    order_id, _ = make_order(status='issued')
    pending_id, _ = make_order()
    client = MagicMock()
    client.account = None
    for _attempt in range(2):
        with pytest.raises(renew_mod.RenewalBlocked):
            _renew(app, order_id, pending_id, _Resp(404), client=client)
    client.create_order.assert_not_called()
    with app.app_context():
        assert AcmeClientOrder.query.filter_by(status='pending', challenge_type='http-01').count() == 1


def test_http01_renewal_opens_an_order_when_none_is_pending(app, make_order, acme_email):
    order_id, _ = make_order(status='issued')
    make_order(domain='other.example.com')  # pending, but for other names
    without_challenges, _ = make_order()  # pending, authorizations never fetched
    without_token, _ = make_order()  # pending, name present but no token
    with app.app_context():
        db.session.get(AcmeClientOrder, without_challenges).set_challenges_dict({})
        db.session.get(AcmeClientOrder, without_token).set_challenges_dict(
            {'www.example.com': {'url': 'https://ca.example/chall/2', 'status': 'pending'}})
        db.session.commit()
    new_id, new_token = make_order(status='ready')
    client = _renew(app, order_id, new_id, _Resp(200, f'{new_token}.thumbprint'))
    client.create_order.assert_called_once()


def test_tls_alpn_renewal_needs_no_dns_provider(app, make_order, acme_email):
    order_id, _ = make_order(challenge_type='tls-alpn-01', status='issued')
    new_id, _ = make_order(challenge_type='tls-alpn-01')
    client = _renew(app, order_id, new_id, _Resp(404))
    client.verify_challenge.assert_called_once()


def test_manual_provider_dns01_renewal_is_blocked(app, make_order, acme_email):
    with app.app_context():
        provider = DnsProvider(name='manual-renewal-test', provider_type='manual', credentials='{}')
        db.session.add(provider)
        db.session.commit()
        provider_id = provider.id
    order_id, _ = make_order(challenge_type='dns-01', status='issued', dns_provider_id=provider_id)
    with app.app_context():
        order = db.session.get(AcmeClientOrder, order_id)
        with pytest.raises(renew_mod.RenewalBlocked, match='manual DNS order'):
            renew_mod.renew_certificate(order)
        AcmeClientOrder.query.filter_by(id=order_id).delete()
        DnsProvider.query.filter_by(id=provider_id).delete()
        db.session.commit()


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


def test_challenge_path_has_its_own_rate_limit_bucket():
    from security.rate_limiter import RateLimitConfig
    assert RateLimitConfig.pattern_for(f'/.well-known/acme-challenge/{_token()}') == '/.well-known/acme-challenge/'


def test_selfcheck_probes_identifiers_in_parallel_with_a_short_timeout():
    import time as _time
    timeouts = []

    def slow_get(url, pin, timeout=10):
        timeouts.append(timeout)
        _time.sleep(0.3)
        return _Resp(404)

    challenges = {f'host{i}.example.com': {'token': f'tok{i}', 'key_authorization': 'k'} for i in range(4)}
    started = _time.monotonic()
    with patch.object(http01, '_get', side_effect=slow_get):
        result = http01.wait_for_http01(challenges, 0)
    assert _time.monotonic() - started < 0.9
    assert sorted(result['missing']) == sorted(challenges)
    assert timeouts == [http01.SELFCHECK_TIMEOUT] * 4


def test_legacy_order_reuses_the_order_pinned_to_the_resolved_account(app, make_order, acme_email):
    from models import AcmeClientAccount
    with app.app_context():
        account = AcmeClientAccount(directory_url='https://ca.example/directory', label='Reuse test', email='reuse@example.com')
        db.session.add(account)
        db.session.commit()
        account_id = account.id
    order_id, _ = make_order(status='issued')  # legacy row: no account
    pending_id, _ = make_order()
    with app.app_context():
        db.session.get(AcmeClientOrder, pending_id).acme_client_account_id = account_id
        db.session.commit()
    client = MagicMock()
    client.account.id = account_id
    try:
        with pytest.raises(renew_mod.RenewalBlocked):
            _renew(app, order_id, pending_id, _Resp(404), client=client)
        client.create_order.assert_not_called()
    finally:
        with app.app_context():
            db.session.get(AcmeClientOrder, pending_id).acme_client_account_id = None
            db.session.delete(db.session.get(AcmeClientAccount, account_id))
            db.session.commit()


def test_reused_order_drops_the_earlier_block_message(app, make_order, acme_email):
    order_id, _ = make_order(status='issued')
    pending_id, token = make_order()
    with app.app_context():
        db.session.get(AcmeClientOrder, pending_id).error_message = 'HTTP-01 file not reachable, order left pending: x'
        db.session.commit()
        order = db.session.get(AcmeClientOrder, order_id)
        client = MagicMock()
        client.account = None
        client.verify_challenge.return_value = (True, 'ok')
        client.finalize_order.side_effect = RuntimeError('STOP_AFTER_SUBMIT')
        with patch.object(renew_mod.AcmeClientService, 'for_order', return_value=client), \
             patch.object(http01, '_get', return_value=_Resp(200, f'{token}.thumbprint')), \
             patch('time.sleep', return_value=None):
            with pytest.raises(RuntimeError):
                renew_mod.renew_certificate(order)
        assert db.session.get(AcmeClientOrder, pending_id).error_message is None

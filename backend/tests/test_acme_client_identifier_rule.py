"""The preflight and the order apply the same rule (DUP-PKI-017).

``POST /api/v2/acme/client/preflight`` exists to tell an operator, before
anything is ordered upstream, whether the request will be accepted. It carried
its own copy of the order route's FQDN regex and not its length cap, so a name
of 254 characters or more got "Domain validation: OK" from the preflight and a
400 from the order a second later.
"""
import pytest

from services.acme.identifiers import normalize_client_identifier

TOO_LONG = ('a' * 60 + '.') * 4 + 'example.com'          # 255 chars, labels <= 63


@pytest.mark.parametrize('value,expected', [
    ('example.com', (None, False, None)),
    ('*.example.com', (None, False, None)),
    ('192.0.2.1', ('192.0.2.1', True, None)),
    ('localhost', (None, False, 'Invalid domain syntax: localhost')),
    ('a_b.example.com', (None, False, 'Invalid domain syntax: a_b.example.com')),
    ('example.com.', (None, False, 'Invalid domain syntax: example.com.')),
    ('host.example.com\n', (None, False, 'Invalid domain syntax: host.example.com\n')),
    ('host.123', (None, False, 'Invalid domain syntax: host.123')),
    ('xn--zz.example', (None, False, 'Invalid domain syntax: xn--zz.example')),
    ('', (None, False, 'Invalid domain (empty or not a string)')),
    (5, (None, False, 'Invalid domain (empty or not a string)')),
])
def test_the_client_rule_keeps_the_order_routes_wording(value, expected):
    normalized, is_ip, problem = normalize_client_identifier(value)
    _, expected_ip, expected_problem = expected
    assert (is_ip, problem) == (expected_ip, expected_problem)
    if problem is None and not is_ip:
        assert normalized == value


def test_the_length_cap_is_part_of_the_rule():
    normalized, is_ip, problem = normalize_client_identifier(TOO_LONG)
    assert normalized is None and is_ip is False
    assert problem == f'Invalid domain (>253 chars): {TOO_LONG[:60]}...'


def _domains_step(report):
    return next(s for s in report['steps'] if s['name'] == 'domains')


@pytest.mark.parametrize('domain,acceptable', [
    ('good.example.com', True),
    ('*.good.example.com', True),
    (TOO_LONG, False),
    ('localhost', False),
    ('under_score.example.com', False),
])
def test_preflight_and_order_agree(auth_client, monkeypatch, domain, acceptable):
    # The rule is all this compares: no ACME directory is reached
    calls = []

    def offline(url, *args, **kwargs):
        calls.append(url)
        raise ConnectionError('no network in tests')
    monkeypatch.setattr('utils.ssrf_protection.safe_request_get', offline)
    preflight = auth_client.post(
        '/api/v2/acme/client/preflight',
        json={'domains': [domain], 'mode': 'validate_only'},
    )
    assert preflight.status_code == 200
    step = _domains_step(preflight.get_json()['data'])

    order = auth_client.post('/api/v2/acme/client/request', json={'domains': [domain]})
    order_body = order.get_json() or {}
    order_refused_the_domain = (
        order.status_code == 400
        and str(order_body.get('message', '')).startswith('Invalid domain')
    )

    assert (step['status'] == 'pass') is acceptable
    assert order_refused_the_domain is not acceptable
    assert calls, 'the preflight no longer asks the directory: drop the stub'

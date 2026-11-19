"""Both ACME clients get the same outbound guard, timeout and nonce handling.

``acme_client_service`` and ``acme_proxy_service`` each wrote their own copy of
the outbound URL guard, fetched their nonce on a hard-coded timeout (30 on one
side, 15 on the other, while the configured HTTP timeout sat unused), and owned
one nonce mechanism each: the reserve and the RFC 8555 §6.5 badNonce retry were
the proxy's, the newNonce backoff was the client's.
"""

import pytest

from services.acme import outbound
from services.acme.acme_client_service import AcmeClientService
from services.acme.acme_proxy_service import AcmeProxyService

NONCE_URL = 'https://ca.example/new-nonce'
DIRECTORY_URL = 'https://ca.example/directory'
CONFIGURED_TIMEOUT = 7


class _Account:
    def get_http_timeout_sec(self):
        return CONFIGURED_TIMEOUT


class _HeadResponse:
    status_code = 200

    def __init__(self, nonce='fresh-nonce'):
        self.headers = {'Replay-Nonce': nonce}

    def raise_for_status(self):
        return None


class _BadNonceResponse:
    status_code = 400

    def __init__(self):
        self.headers = {'Replay-Nonce': 'nonce-after-bad'}

    def json(self):
        return {'type': outbound.BAD_NONCE, 'detail': 'stale'}


@pytest.fixture(autouse=True)
def _empty_pool():
    outbound.reset_nonce_pool()
    yield
    outbound.reset_nonce_pool()


@pytest.fixture
def client_service():
    service = AcmeClientService.__new__(AcmeClientService)
    service.directory = {'newNonce': NONCE_URL}
    service.directory_url = DIRECTORY_URL
    service.verify_ssl = True
    service.account = _Account()
    service.session = type('_S', (), {'headers': {}})()
    return service


@pytest.fixture
def proxy_service():
    service = AcmeProxyService.__new__(AcmeProxyService)
    service.directory = {'newNonce': NONCE_URL}
    service.upstream_directory_url = DIRECTORY_URL
    service.verify_ssl = True
    service.account = _Account()
    return service


def _record_head(monkeypatch, seen):
    def fake_head(url, **kwargs):
        seen.append(kwargs.get('timeout'))
        return _HeadResponse()

    from utils import ssrf_protection
    monkeypatch.setattr(ssrf_protection, 'safe_request_head', fake_head)


def test_client_nonce_uses_the_configured_timeout(app, monkeypatch, client_service):
    seen = []
    _record_head(monkeypatch, seen)

    with app.app_context():
        client_service._get_nonce()

    assert seen == [CONFIGURED_TIMEOUT]


def test_proxy_nonce_uses_the_configured_timeout(app, monkeypatch, proxy_service):
    seen = []
    _record_head(monkeypatch, seen)

    with app.app_context():
        proxy_service._get_nonce()

    assert seen == [CONFIGURED_TIMEOUT]


def test_both_sides_validate_the_outbound_url_the_same_way():
    """One implementation, so the message cannot drift."""
    with pytest.raises(ValueError) as client_err:
        AcmeClientService._validate_outbound_acme_url('http://169.254.169.254/')
    with pytest.raises(ValueError) as proxy_err:
        AcmeProxyService._validate_outbound_acme_url('http://169.254.169.254/')

    assert str(client_err.value) == str(proxy_err.value)
    assert str(client_err.value).startswith('ACME outbound URL blocked: ')


def test_the_client_takes_a_pooled_nonce_too(app, monkeypatch, client_service):
    """The reserve was the proxy's alone."""
    calls = []
    _record_head(monkeypatch, calls)
    outbound.nonce_pool_push(DIRECTORY_URL, 'pooled-nonce')

    with app.app_context():
        assert client_service._get_nonce() == 'pooled-nonce'

    assert calls == []


def test_the_proxy_retries_a_slow_new_nonce(app, monkeypatch, proxy_service):
    """The backoff was the client's alone."""
    attempts = []

    def flaky_head(url, **kwargs):
        attempts.append(1)
        if len(attempts) < 2:
            raise OSError('upstream timed out')
        return _HeadResponse()

    from utils import ssrf_protection
    monkeypatch.setattr(ssrf_protection, 'safe_request_head', flaky_head)
    monkeypatch.setattr(outbound.time, 'sleep', lambda _s: None)

    with app.app_context():
        assert proxy_service._get_nonce() == 'fresh-nonce'

    assert len(attempts) == 2


def test_the_client_retries_once_on_bad_nonce(app, monkeypatch, client_service):
    """RFC 8555 §6.5: a badNonce was terminal on the client side."""
    posts = []

    def fake_post(url, **kwargs):
        posts.append(kwargs.get('json'))
        if len(posts) == 1:
            return _BadNonceResponse()
        return _HeadResponse('after-retry')

    from utils import ssrf_protection
    monkeypatch.setattr(ssrf_protection, 'safe_request_post', fake_post)
    monkeypatch.setattr(ssrf_protection, 'safe_request_head',
                        lambda url, **kw: _HeadResponse('first-nonce'))
    monkeypatch.setattr(
        AcmeClientService, '_sign_jws',
        lambda self, url, payload, use_jwk=False, nonce=None: {
            'nonce': nonce or self._get_nonce()})

    with app.app_context():
        resp = client_service._post(NONCE_URL, {'x': 1})

    assert len(posts) == 2
    assert resp.status_code == 200


def test_the_client_retries_bad_nonces_in_a_row_a_bounded_number_of_times(
        app, monkeypatch, client_service):
    """RFC 8555 §6.5: each badNonce carries the nonce of the next attempt."""
    posts = []

    def fake_post(url, **kwargs):
        posts.append(kwargs.get('json'))
        return _BadNonceResponse() if len(posts) < 3 else _HeadResponse('done')

    from utils import ssrf_protection
    monkeypatch.setattr(ssrf_protection, 'safe_request_post', fake_post)
    monkeypatch.setattr(ssrf_protection, 'safe_request_head',
                        lambda url, **kw: _HeadResponse('first-nonce'))
    monkeypatch.setattr(
        AcmeClientService, '_sign_jws',
        lambda self, url, payload, use_jwk=False, nonce=None: {
            'nonce': nonce or self._get_nonce()})

    with app.app_context():
        assert client_service._post(NONCE_URL, {'x': 1}).status_code == 200
        assert len(posts) == 3
        posts.clear()
        monkeypatch.setattr(ssrf_protection, 'safe_request_post',
                            lambda url, **kw: posts.append(1) or _BadNonceResponse())
        assert client_service._post(NONCE_URL, {'x': 1}).status_code == 400
    assert len(posts) == 1 + outbound.BAD_NONCE_RETRIES


def test_bad_nonce_detection_ignores_other_problems():
    class _Other:
        status_code = 400
        headers = {'Replay-Nonce': 'n'}

        def json(self):
            return {'type': 'urn:ietf:params:acme:error:malformed'}

    class _NotJson:
        status_code = 400
        headers = {'Replay-Nonce': 'n'}

        def json(self):
            raise ValueError('no json here')

    assert outbound.bad_nonce_retry_value(_Other()) is None
    assert outbound.bad_nonce_retry_value(_NotJson()) is None
    assert outbound.bad_nonce_retry_value(_BadNonceResponse()) == 'nonce-after-bad'


def test_the_pool_keeps_its_contract():
    """Single use, newest first, capped, and no duplicate."""
    outbound.nonce_pool_push(DIRECTORY_URL, 'a')
    outbound.nonce_pool_push(DIRECTORY_URL, 'a')
    outbound.nonce_pool_push(DIRECTORY_URL, 'b')

    assert outbound.nonce_pool_pop(DIRECTORY_URL) == 'b'
    assert outbound.nonce_pool_pop(DIRECTORY_URL) == 'a'
    assert outbound.nonce_pool_pop(DIRECTORY_URL) is None


def test_reset_proxy_caches_still_empties_the_pool():
    from services.acme.acme_proxy_service import reset_proxy_caches

    outbound.nonce_pool_push(DIRECTORY_URL, 'to-be-dropped')
    reset_proxy_caches()

    assert outbound.nonce_pool_pop(DIRECTORY_URL) is None

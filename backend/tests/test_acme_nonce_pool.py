"""Behaviour of the shared ACME nonce reserve and the client's deposits into it."""

import threading

import pytest

from services.acme import outbound
from services.acme.acme_client_service import AcmeClientService

URL_X = 'https://ca-x.example/directory'
URL_Y = 'https://ca-y.example/directory'
POST_URL = 'https://ca-x.example/acme/new-order'


@pytest.fixture(autouse=True)
def _empty_pool():
    outbound.reset_nonce_pool()
    yield
    outbound.reset_nonce_pool()


@pytest.fixture
def clock(monkeypatch):
    state = {'now': 1000.0}
    monkeypatch.setattr(outbound, '_now', lambda: state['now'])
    return state


def _drain(url):
    out = []
    while True:
        nonce = outbound.nonce_pool_pop(url)
        if nonce is None:
            return out
        out.append(nonce)


def test_a_nonce_is_never_served_for_another_directory():
    outbound.nonce_pool_push(URL_X, 'only-x')

    assert outbound.nonce_pool_pop(URL_Y) is None
    assert outbound.nonce_pool_pop(URL_X) == 'only-x'


def test_the_pool_keeps_the_eight_newest():
    for i in range(9):
        outbound.nonce_pool_push(URL_X, f'n{i}')

    assert _drain(URL_X) == [f'n{i}' for i in range(8, 0, -1)]


def test_a_stale_nonce_is_discarded_and_a_newer_one_still_served(clock):
    outbound.nonce_pool_push(URL_X, 'old')
    clock['now'] += outbound.NONCE_POOL_TTL_SEC + 1
    assert outbound.nonce_pool_pop(URL_X) is None

    outbound.nonce_pool_push(URL_X, 'old-2')
    clock['now'] += outbound.NONCE_POOL_TTL_SEC + 1
    outbound.nonce_pool_push(URL_X, 'new')
    assert outbound.nonce_pool_pop(URL_X) == 'new'
    assert outbound.nonce_pool_pop(URL_X) is None


def test_a_nonce_at_exactly_the_ttl_is_still_served(clock):
    outbound.nonce_pool_push(URL_X, 'edge')
    clock['now'] += outbound.NONCE_POOL_TTL_SEC

    assert outbound.nonce_pool_pop(URL_X) == 'edge'


@pytest.mark.parametrize('url,nonce', [(URL_X, None), (URL_X, ''), ('', 'n'), (None, 'n')])
def test_empty_deposits_leave_the_pool_unchanged(url, nonce):
    outbound.nonce_pool_push(URL_X, 'kept')
    outbound.nonce_pool_push(url, nonce)

    assert _drain(URL_X) == ['kept']
    assert outbound.nonce_pool_pop(url) is None


def test_concurrent_pops_never_serve_a_nonce_twice():
    total = outbound.NONCE_POOL_MAX
    for i in range(total):
        outbound.nonce_pool_push(URL_X, f'n{i}')

    served = []
    served_lock = threading.Lock()
    barrier = threading.Barrier(16)

    def worker():
        barrier.wait()
        for _ in range(4):
            nonce = outbound.nonce_pool_pop(URL_X)
            if nonce is not None:
                with served_lock:
                    served.append(nonce)

    threads = [threading.Thread(target=worker) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(served) == sorted(f'n{i}' for i in range(total))


def test_reset_twice_on_a_full_pool():
    for i in range(outbound.NONCE_POOL_MAX):
        outbound.nonce_pool_push(URL_X, f'x{i}')
        outbound.nonce_pool_push(URL_Y, f'y{i}')

    outbound.reset_nonce_pool()
    outbound.reset_nonce_pool()

    assert outbound.nonce_pool_pop(URL_X) is None
    assert outbound.nonce_pool_pop(URL_Y) is None


# --- client side -------------------------------------------------------------

class _Account:
    def get_http_timeout_sec(self):
        return 5


class _Response:
    def __init__(self, status_code, nonce=None, body=None):
        self.status_code = status_code
        self.headers = {'Replay-Nonce': nonce} if nonce else {}
        self._body = body or {}

    def json(self):
        return self._body


@pytest.fixture
def client_service(monkeypatch):
    service = AcmeClientService.__new__(AcmeClientService)
    service.directory = {'newNonce': 'https://ca-x.example/new-nonce'}
    service.directory_url = URL_X
    service.verify_ssl = True
    service.account = _Account()
    service.session = type('_S', (), {'headers': {}})()
    monkeypatch.setattr(
        AcmeClientService, '_sign_jws',
        lambda self, url, payload, use_jwk=False, nonce=None: {'nonce': nonce or 'n0'})
    return service


def _answer_with(monkeypatch, *responses):
    queue = list(responses)
    from utils import ssrf_protection
    monkeypatch.setattr(ssrf_protection, 'safe_request_post',
                        lambda url, **kw: queue.pop(0))


def test_the_client_pools_the_nonce_of_a_success(app, monkeypatch, client_service):
    _answer_with(monkeypatch, _Response(200, 'n1'))

    with app.app_context():
        client_service._post(POST_URL, {'x': 1})

    assert outbound.nonce_pool_pop(URL_X) == 'n1'


def test_the_client_never_pools_the_nonce_of_a_400(app, monkeypatch, client_service):
    _answer_with(monkeypatch, _Response(400, 'n2', {'type': 'urn:ietf:params:acme:error:malformed'}))

    with app.app_context():
        resp = client_service._post(POST_URL, {'x': 1})

    assert resp.status_code == 400
    assert outbound.nonce_pool_pop(URL_X) is None


def test_a_bad_nonce_retry_spends_its_nonce_once(app, monkeypatch, client_service):
    """The badNonce answer's nonce goes to the retry, the retry's answer to the pool."""
    _answer_with(monkeypatch,
                 _Response(400, 'n2', {'type': outbound.BAD_NONCE}),
                 _Response(201, 'n3'))

    with app.app_context():
        resp = client_service._post(POST_URL, {'x': 1})

    assert resp.status_code == 201
    assert _drain(URL_X) == ['n3']


def test_a_response_without_usable_headers_does_not_fail(app, monkeypatch, client_service):
    class _Bare:
        status_code = 200
        headers = None

    _answer_with(monkeypatch, _Bare(), _Response(200))

    with app.app_context():
        assert client_service._post(POST_URL, {}).status_code == 200
        assert client_service._post(POST_URL, {}).status_code == 200

    assert outbound.nonce_pool_pop(URL_X) is None

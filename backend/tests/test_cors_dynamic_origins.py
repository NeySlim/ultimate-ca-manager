"""The CORS allowlist is read on each request: a Base URL set after the start is allowed, one
replaced is refused, an unknown origin never is, and the answer keeps what Flask-CORS sent
(the origin echoed, credentials, Vary: Origin, the preflight's methods and headers)."""
import pytest

from models import SystemConfig, db

URL = '/api/v2/auth/methods'
LATE = 'https://late-admin.cors.example.test'
OTHER = 'https://other-admin.cors.example.test'


def _set_base_url(app, value):
    with app.app_context():
        row = SystemConfig.query.filter_by(key='base_url').first()
        if value is None:
            if row is not None:
                db.session.delete(row)
        elif row is None:
            db.session.add(SystemConfig(key='base_url', value=value))
        else:
            row.value = value
        db.session.commit()
        from utils.public_endpoints import get_admin_canonical_origin
        return get_admin_canonical_origin()


@pytest.fixture
def base_url(app):
    with app.app_context():
        row = SystemConfig.query.filter_by(key='base_url').first()
        previous = row.value if row is not None else None
    yield lambda value: _set_base_url(app, value)
    _set_base_url(app, previous)


def _allowed(client, origin, method='get'):
    if method == 'options':
        r = client.options(URL, headers={'Origin': origin, 'Access-Control-Request-Method': 'POST',
                                         'Access-Control-Request-Headers': 'Content-Type'})
    else:
        r = client.get(URL, headers={'Origin': origin})
    return r


@pytest.mark.parametrize('method', ['get', 'options'])
def test_a_base_url_set_after_the_start_is_allowed(app, client, base_url, method):
    origin = base_url(LATE)
    assert origin and origin.startswith(LATE)
    r = _allowed(client, origin, method)
    assert r.headers.get('Access-Control-Allow-Origin') == origin
    assert r.headers.get('Access-Control-Allow-Credentials') == 'true'
    assert 'Origin' in r.headers.get('Vary', '')
    if method == 'options':
        assert 'POST' in r.headers.get('Access-Control-Allow-Methods', '')
        assert r.headers.get('Access-Control-Allow-Headers', '').lower() == 'content-type'


def test_a_base_url_replaced_is_refused(app, client, base_url):
    first = base_url(LATE)
    assert _allowed(client, first).headers.get('Access-Control-Allow-Origin') == first
    second = base_url(OTHER)
    assert _allowed(client, first).headers.get('Access-Control-Allow-Origin') is None
    assert _allowed(client, second).headers.get('Access-Control-Allow-Origin') == second


@pytest.mark.parametrize('origin', ['https://evil.example.test', 'null', '*'])
def test_an_unknown_origin_is_never_echoed(app, client, base_url, origin):
    base_url(LATE)
    r = _allowed(client, origin)
    assert r.headers.get('Access-Control-Allow-Origin') is None
    assert r.headers.get('Access-Control-Allow-Credentials') is None


def test_localhost_stays_allowed_without_a_base_url(app, client, base_url):
    base_url(None)
    with app.app_context():
        from utils.public_endpoints import get_cors_origins
        local = get_cors_origins()[0]
    assert _allowed(client, local).headers.get('Access-Control-Allow-Origin') == local


def test_an_origin_that_only_starts_like_a_listed_one_is_refused(app, client, base_url):
    origin = base_url(LATE)
    for near in (origin + '.evil.example.test', origin + '0', origin[:-1]):
        assert _allowed(client, near).headers.get('Access-Control-Allow-Origin') is None, near


@pytest.mark.parametrize('extra', ['*', '.*', 'https://.*\\.example\\.test'])
def test_an_extra_origin_is_never_a_wildcard_or_a_pattern(app, client, base_url, monkeypatch, extra):
    monkeypatch.setenv('CORS_EXTRA_ORIGINS', f'{extra}, https://extra.cors.example.test')
    base_url(LATE)
    assert _allowed(client, 'https://evil.example.test').headers.get('Access-Control-Allow-Origin') is None
    assert _allowed(client, 'https://x.example.test').headers.get('Access-Control-Allow-Origin') is None
    listed = _allowed(client, 'https://extra.cors.example.test')
    assert listed.headers.get('Access-Control-Allow-Origin') == 'https://extra.cors.example.test'


def test_an_error_answer_carries_the_headers(app, client, base_url):
    origin = base_url(LATE)
    r = client.get('/api/v2/no-such-route-cors', headers={'Origin': origin})
    assert r.status_code == 404
    assert r.headers.get('Access-Control-Allow-Origin') == origin


def test_a_path_outside_the_resources_has_no_headers(app, client, base_url):
    origin = base_url(LATE)
    assert client.get('/health', headers={'Origin': origin}).headers.get(
        'Access-Control-Allow-Origin') is None


def test_a_request_without_origin_reads_no_allowlist(app, client, base_url, monkeypatch):
    import utils.public_endpoints as public_endpoints
    base_url(LATE)

    def refused():
        raise AssertionError('the allowlist was read for a request without Origin')
    monkeypatch.setattr(public_endpoints, 'get_cors_origins', refused)
    r = client.get(URL)
    assert r.headers.get('Access-Control-Allow-Origin') is None
    assert 'Origin' in r.headers.get('Vary', '')

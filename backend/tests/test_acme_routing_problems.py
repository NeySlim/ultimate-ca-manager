"""Requests Flask routing refuses under /acme get an ACME problem document that
links the directory (RFC 8555 §6.7, §7.1), for the server and the proxy."""
import pytest

from models import db, AcmeClientAccount

MALFORMED = 'urn:ietf:params:acme:error:malformed'


def _index_links(resp):
    return [v for v in resp.headers.getlist('Link') if 'rel="index"' in v]


def _assert_problem(resp, status, directory_suffix):
    assert resp.status_code == status
    assert resp.headers['Content-Type'] == 'application/problem+json'
    body = resp.get_json()
    assert body['type'] == MALFORMED and body['status'] == status
    links = _index_links(resp)
    assert len(links) == 1 and links[0].endswith(f'{directory_suffix}>;rel="index"'), links


@pytest.fixture
def slug_endpoint(app):
    with app.app_context():
        acct = AcmeClientAccount(directory_url='https://acme-route.example/directory',
                                 label='routing problems', email='route@example.com',
                                 proxy_enabled=True, proxy_slug='route-test')
        db.session.add(acct)
        db.session.commit()
        acct_id = acct.id
    yield 'route-test'
    with app.app_context():
        db.session.rollback()
        AcmeClientAccount.query.filter_by(id=acct_id).delete()
        db.session.commit()


class TestServer:
    def test_unknown_resource(self, client):
        _assert_problem(client.get('/acme/no-such-resource'), 404, '/acme/directory')

    def test_wrong_method_keeps_allow(self, client):
        resp = client.get('/acme/new-order')
        _assert_problem(resp, 405, '/acme/directory')
        assert 'POST' in resp.headers['Allow']

    def test_a_post_gets_a_nonce(self, client):
        resp = client.post('/acme/no-such-resource', data=b'{}',
                           content_type='application/jose+json')
        _assert_problem(resp, 404, '/acme/directory')
        assert resp.headers.get('Replay-Nonce')

    def test_a_get_gets_no_nonce(self, client):
        assert 'Replay-Nonce' not in client.get('/acme/no-such-resource').headers


class TestProxy:
    def test_unknown_resource_links_the_proxy_directory(self, client):
        _assert_problem(client.get('/acme/proxy/no-such/resource'), 404, '/acme/proxy/directory')

    def test_wrong_method(self, client):
        resp = client.put('/acme/proxy/new-order')
        _assert_problem(resp, 405, '/acme/proxy/directory')
        assert 'POST' in resp.headers['Allow']

    def test_slug_endpoint_links_its_own_directory(self, client, slug_endpoint):
        _assert_problem(client.get(f'/acme/proxy/{slug_endpoint}/new-order'), 405,
                        f'/acme/proxy/{slug_endpoint}/directory')
        _assert_problem(client.get(f'/acme/proxy/{slug_endpoint}/a/b/c'), 404,
                        f'/acme/proxy/{slug_endpoint}/directory')


@pytest.mark.parametrize('path', ['/acmefoo/bar', '/acme'])
def test_paths_outside_acme_are_left_alone(client, path):
    """/acme is the ACME page of the web UI, served by the SPA."""
    resp = client.get(path)
    assert resp.status_code == 200
    assert resp.mimetype == 'text/html'
    assert not _index_links(resp)


def test_post_on_a_get_only_resource(client):
    resp = client.post('/acme/directory', data=b'{}', content_type='application/jose+json')
    _assert_problem(resp, 405, '/acme/directory')
    assert 'GET' in resp.headers['Allow'] and 'POST' not in resp.headers['Allow']

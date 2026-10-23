"""CT log submission goes through the pinned SSRF guard (redirects, DNS rebinding)."""
import http.server
import socket
import threading

import pytest

from utils import ct_client, ssrf_protection

_CHAIN = ['-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n']


@pytest.fixture
def loopback_server():
    """A server on loopback counting every request it receives."""
    hits = []

    class _Handler(http.server.BaseHTTPRequestHandler):
        def _answer(self):
            hits.append((self.command, self.path))
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"sct_version": 0}')

        do_GET = do_POST = _answer

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(('127.0.0.1', 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1], hits
    server.shutdown()


def test_a_rebound_name_cannot_reach_loopback(monkeypatch, loopback_server):
    """The guard sees a public address, the system resolver then answers loopback."""
    port, hits = loopback_server
    real = socket.getaddrinfo

    def system_resolver(host, *args, **kwargs):
        if host == 'ct-rebind.test':
            return real('127.0.0.1', *args, **kwargs)
        return real(host, *args, **kwargs)

    monkeypatch.setattr(socket, 'getaddrinfo', system_resolver)
    monkeypatch.setattr(ssrf_protection.socket, 'getaddrinfo',
                        lambda host, *a, **k: real('192.0.2.1', *a, **k))
    result = ct_client._submit_chain(f'http://ct-rebind.test:{port}/', _CHAIN, '/ct/v1/add-chain', 1)
    assert result is None
    assert hits == []


def test_a_redirect_is_never_followed(monkeypatch):
    import requests

    calls = []

    class _Redirect:
        status_code = 302
        headers = {'Location': 'http://169.254.169.254/latest/meta-data/'}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def close(self):
            pass

    def _post(url, **kwargs):
        calls.append((url, kwargs.get('allow_redirects')))
        return _Redirect()

    monkeypatch.setattr(requests, 'post', _post)
    monkeypatch.setattr(requests, 'get', _post)
    assert ct_client._submit_chain('https://ct.example.com/', _CHAIN, '/ct/v1/add-chain', 1) is None
    assert calls == [('https://ct.example.com/ct/v1/add-chain', False)]

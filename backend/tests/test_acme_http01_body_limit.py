"""HTTP-01 responses are read bounded (RFC 8555 §8.3: the body is the key authorization).

A challenge server under the ACME account's control can stream an endless body
or drip it one byte at a time; neither may hold memory or a worker past a bound.
"""
import http.server
import threading
import time

import pytest
import requests

from services.acme import http01


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    mode = 'flood'

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(404 if self.mode == 'big404' else 200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Transfer-Encoding', 'chunked')
        self.end_headers()
        try:
            if self.mode in ('flood', 'big404'):
                chunk = b'A' * 65536
                for _ in range(512):  # 32 MiB
                    self.wfile.write(b'%x\r\n%s\r\n' % (len(chunk), chunk))
            elif self.mode == 'drip':
                for _ in range(60):
                    self.wfile.write(b'1\r\nA\r\n')
                    self.wfile.flush()
                    time.sleep(0.25)
            else:
                body = self.mode.encode()
                self.wfile.write(b'%x\r\n%s\r\n' % (len(body), body))
            self.wfile.write(b'0\r\n\r\n')
        except (BrokenPipeError, ConnectionResetError):
            pass


@pytest.fixture
def challenge_server():
    servers = []

    def start(mode):
        handler = type('H', (_Handler,), {'mode': mode})
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f'http://127.0.0.1:{server.server_address[1]}/.well-known/acme-challenge/tok'

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def test_http01_endless_body_is_refused(challenge_server):
    url = challenge_server('flood')
    with pytest.raises(http01.ResponseTooLarge):
        http01.fetch_following_redirects(url, None, allow_private=True, timeout=5)


def test_http01_dripped_body_hits_the_total_deadline(challenge_server):
    url = challenge_server('drip')
    started = time.monotonic()
    with pytest.raises(requests.Timeout):
        http01.fetch_following_redirects(url, None, allow_private=True, timeout=1)
    assert time.monotonic() - started < 6


def test_http01_key_authorization_is_still_read(challenge_server):
    url = challenge_server('tok.thumbprint\n')
    response = http01.fetch_following_redirects(url, None, allow_private=True, timeout=5)
    assert response.status_code == 200
    assert response.text.strip() == 'tok.thumbprint'


def test_http01_selfcheck_names_an_oversized_body(challenge_server, monkeypatch):
    url = challenge_server('flood')
    monkeypatch.setattr(http01, 'challenge_url', lambda identifier, token: url)
    ok, reason = http01.challenge_reachable('127.0.0.1', {'token': 'tok', 'key_authorization': 'x'})
    assert not ok
    assert reason.endswith('response too large')


def test_http01_error_body_is_not_read_so_its_status_is_reported(challenge_server, monkeypatch):
    url = challenge_server('big404')
    monkeypatch.setattr(http01, 'challenge_url', lambda identifier, token: url)
    ok, reason = http01.challenge_reachable('127.0.0.1', {'token': 'tok', 'key_authorization': 'x'})
    assert (ok, reason) == (False, f'{url}: HTTP 404')

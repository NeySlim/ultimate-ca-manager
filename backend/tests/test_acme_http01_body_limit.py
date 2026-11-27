"""HTTP-01 responses are read bounded (RFC 8555 §8.3: the body is the key authorization).

A challenge server under the ACME account's control can stream an endless body
or drip it one byte at a time; neither may hold memory or a worker past a bound.
"""
import gzip
import http.server
import os
import socket
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
        if self.mode in ('drip_length', 'drip_close'):
            # Not chunked: a read of N bytes would wait for all N, or for EOF.
            if self.mode == 'drip_length':
                self.send_header('Content-Length', '40')
            else:
                self.send_header('Connection', 'close')
            self.end_headers()
            try:
                for _ in range(40):
                    self.wfile.write(b'A')
                    self.wfile.flush()
                    time.sleep(0.5)
            except (BrokenPipeError, ConnectionResetError):
                pass
            self.close_connection = True
            return
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


@pytest.mark.parametrize('mode', ['drip_length', 'drip_close'])
def test_http01_unchunked_dripped_body_hits_the_total_deadline(challenge_server, mode):
    # Each byte arrives within the per-read timeout; only the total deadline stops it.
    url = challenge_server(mode)
    started = time.monotonic()
    with pytest.raises(requests.Timeout):
        http01.fetch_following_redirects(url, None, allow_private=True, timeout=1)
    assert time.monotonic() - started < 5


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


# Raw servers: a prefix sent at once, then one byte every 0.5 s for 12 s. Each byte
# lands inside the per-read timeout, in a read that never hands control back.
_GZIP_FCOMMENT = b'\x1f\x8b\x08\x10\x00\x00\x00\x00\x00\xff'
_RAW_DRIPS = {
    'headers': (b'HTTP/1.1 200 OK\r\nX-Pad: ', b'a' * 24),
    'chunk_extension': (b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n1;', b'a' * 24),
    'gzip_comment': (b'HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nConnection: close\r\n\r\n'
                     + _GZIP_FCOMMENT, b'a' * 24),
}


@pytest.fixture
def raw_server():
    listeners = []

    def start(prefix, drip):
        listener = socket.create_server(('127.0.0.1', 0))
        listeners.append(listener)

        def serve():
            try:
                conn, _ = listener.accept()
            except OSError:
                return
            with conn:
                try:
                    request = b''
                    while b'\r\n\r\n' not in request:
                        data = conn.recv(4096)
                        if not data:
                            return
                        request += data
                    conn.sendall(prefix)
                    for i in range(len(drip)):
                        conn.sendall(drip[i:i + 1])
                        time.sleep(0.5)
                except OSError:
                    pass

        threading.Thread(target=serve, daemon=True).start()
        return f'http://127.0.0.1:{listener.getsockname()[1]}/.well-known/acme-challenge/tok'

    yield start
    for listener in listeners:
        listener.close()


@pytest.mark.parametrize('case', sorted(_RAW_DRIPS))
def test_http01_deadline_holds_in_reads_that_never_return(raw_server, case):
    url = raw_server(*_RAW_DRIPS[case])
    started = time.monotonic()
    # A gzip body is refused on its headers; without that refusal the deadline stops it.
    with pytest.raises((requests.Timeout, http01.IncorrectResponse) if case == 'gzip_comment'
                       else requests.Timeout):
        http01.fetch_following_redirects(url, None, allow_private=True, timeout=1)
    assert time.monotonic() - started < 5


def test_http01_asks_for_and_requires_an_identity_body(raw_server):
    body = gzip.compress(b'tok.thumbprint')
    url = raw_server(b'HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nContent-Length: %d\r\n\r\n%s'
                     % (len(body), body), b'')
    with pytest.raises(http01.IncorrectResponse, match='Content-Encoding'):
        http01.fetch_following_redirects(url, None, allow_private=True, timeout=5)


def test_http01_sends_accept_encoding_identity(raw_server):
    seen = []
    url = raw_server(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok', b'')
    real_get = requests.get

    def spy(*args, **kwargs):
        seen.append(kwargs.get('headers'))
        return real_get(*args, **kwargs)

    import unittest.mock
    with unittest.mock.patch.object(requests, 'get', spy):
        assert http01.fetch_following_redirects(url, None, allow_private=True, timeout=5).text == 'ok'
    assert seen == [{'Accept-Encoding': 'identity'}]


def _open_fds():
    return len(os.listdir('/proc/self/fd'))


def test_http01_deadline_timer_leaks_no_thread_or_socket(challenge_server):
    url = challenge_server('tok.thumbprint\n')
    http01.fetch_following_redirects(url, None, allow_private=True, timeout=5)
    fds = _open_fds()
    for _ in range(50):
        assert http01.fetch_following_redirects(url, None, allow_private=True, timeout=5).status_code == 200
    # Only this module's deadline timers: other tests run short Timers of their own
    assert not [t for t in threading.enumerate() if isinstance(t, threading.Timer)
                and getattr(getattr(t, 'function', None), '__func__', None) is http01._HopDeadline._fire]
    for _ in range(20):
        if _open_fds() - fds < 5:
            break
        time.sleep(0.1)
    assert _open_fds() - fds < 5

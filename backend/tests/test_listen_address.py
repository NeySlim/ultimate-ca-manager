"""Listen address (HOST) handling: bind string, dual-stack peers, middleware.

Uses shared conftest fixtures: app.
"""
import socket

import pytest

from listen_address import (
    PeerAddressNormalizer,
    format_bind,
    get_bind_host,
    normalize_peer_address,
)


class TestGetBindHost:
    def test_default_is_ipv4_any(self, monkeypatch):
        monkeypatch.delenv('HOST', raising=False)
        assert get_bind_host() == '0.0.0.0'

    def test_dual_stack(self, monkeypatch):
        monkeypatch.setenv('HOST', '::')
        assert get_bind_host() == '::'

    def test_specific_address_and_whitespace(self, monkeypatch):
        monkeypatch.setenv('HOST', ' 192.0.2.10 ')
        assert get_bind_host() == '192.0.2.10'

    def test_invalid_value_falls_back(self, monkeypatch, capsys):
        monkeypatch.setenv('HOST', 'ucm.example.com')
        assert get_bind_host() == '0.0.0.0'
        assert 'HOST=' in capsys.readouterr().err


class TestFormatBind:
    def test_ipv4(self):
        assert format_bind('0.0.0.0', '8443') == '0.0.0.0:8443'

    def test_ipv6_gets_brackets(self):
        assert format_bind('::', 8443) == '[::]:8443'
        assert format_bind('2001:db8::1', 8443) == '[2001:db8::1]:8443'


class TestNormalizePeerAddress:
    @pytest.mark.parametrize('raw, expected', [
        ('::ffff:192.0.2.1', '192.0.2.1'),
        ('::ffff:127.0.0.1', '127.0.0.1'),
        ('192.0.2.1', '192.0.2.1'),
        ('2001:db8::1', '2001:db8::1'),
        ('::1', '::1'),
        ('', ''),
        (None, None),
        ('not-an-ip', 'not-an-ip'),
    ])
    def test_cases(self, raw, expected):
        assert normalize_peer_address(raw) == expected


class TestPeerAddressNormalizer:
    def _run(self, remote_addr):
        seen = {}

        def inner(environ, start_response):
            seen['REMOTE_ADDR'] = environ.get('REMOTE_ADDR')
            start_response('200 OK', [])
            return [b'']

        environ = {'REMOTE_ADDR': remote_addr} if remote_addr is not None else {}
        list(PeerAddressNormalizer(inner)(environ, lambda *a: None))
        return seen.get('REMOTE_ADDR')

    def test_mapped_ipv4_is_rewritten(self):
        assert self._run('::ffff:10.0.0.5') == '10.0.0.5'

    def test_plain_addresses_untouched(self):
        assert self._run('10.0.0.5') == '10.0.0.5'
        assert self._run('2001:db8::5') == '2001:db8::5'
        assert self._run(None) is None

    def test_installed_outermost_on_the_app(self, app):
        # First WSGI layer must be the normalizer so ProxyFix (when enabled)
        # records an already-normalized original peer.
        assert isinstance(app.wsgi_app, PeerAddressNormalizer)


class TestDualStackTrustedProxy:
    """A local reverse proxy on 127.0.0.1 reaching a dual-stack listener is
    seen as ::ffff:127.0.0.1 on the socket; it must still count as the
    default trusted (loopback) proxy once the request goes through the
    middleware. Uses a throwaway Flask app: the shared session app has
    already served requests, so no route/hook can be added to it."""

    def test_mapped_loopback_is_trusted(self, monkeypatch):
        from flask import Flask
        from utils.trusted_proxy import immediate_peer_addr, is_request_from_trusted_proxy

        monkeypatch.delenv('UCM_TRUSTED_PROXIES', raising=False)
        probe = Flask('listen-address-probe')

        @probe.route('/')
        def _probe():
            return f"{immediate_peer_addr()} {is_request_from_trusted_proxy()}"

        probe.wsgi_app = PeerAddressNormalizer(probe.wsgi_app)
        body = probe.test_client().get(
            '/', environ_overrides={'REMOTE_ADDR': '::ffff:127.0.0.1'}).get_data(as_text=True)
        assert body == '127.0.0.1 True'


def _has_ipv6_loopback():
    """Whether ``::1`` is actually usable on this host.

    ``socket.has_ipv6`` only says the interpreter was built with IPv6, and
    stays True on a kernel that has it switched off -- the shape several
    WSL2 images ship with. There, creating and binding an ``AF_INET6``
    socket still succeeds, so neither that flag nor the bind of ``[::]``
    below tells the test anything: the failure arrives later, as
    ``EADDRNOTAVAIL`` on the client's connect to ``::1``, which reads as a
    broken dual-stack listener rather than a host without IPv6. Binding the
    exact address the client will dial is the question worth asking.
    """
    if not socket.has_ipv6:
        return False
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as probe:
            probe.bind(('::1', 0))
    except OSError:
        return False
    return True


@pytest.mark.skipif(not _has_ipv6_loopback(),
                    reason='no usable IPv6 loopback (::1) on this host')
def test_dual_stack_listener_accepts_ipv4_and_ipv6():
    """HOST=:: must serve both address families on one socket (Linux default
    bindv6only=0), which is what makes the option useful. The gevent server
    runs in its own thread (own hub) because this test process is not
    monkey-patched: blocking client calls in the main thread would starve
    the hub otherwise."""
    import threading
    import urllib.request
    from gevent.pywsgi import WSGIServer

    def hello(environ, start_response):
        start_response('200 OK', [('Content-Type', 'text/plain')])
        return [environ['REMOTE_ADDR'].encode()]

    holder, ready = {}, threading.Event()

    def serve():
        try:
            srv = WSGIServer(('::', 0), hello, log=None)
            srv.start()
        except OSError as exc:
            holder['error'] = exc
            ready.set()
            return
        holder['srv'] = srv
        ready.set()
        srv.serve_forever()

    threading.Thread(target=serve, daemon=True).start()
    assert ready.wait(10), 'server thread did not start'
    if 'error' in holder:
        pytest.skip(f"cannot bind [::]: {holder['error']}")
    srv = holder['srv']
    port = srv.address[1]
    try:
        v4 = urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=5).read().decode()
        v6 = urllib.request.urlopen(f'http://[::1]:{port}/', timeout=5).read().decode()
    finally:
        srv.loop.run_callback(srv.stop)
    # gevent reports the raw socket peer: mapped form for the IPv4 client
    assert v4 in ('::ffff:127.0.0.1', '127.0.0.1')
    assert v6 == '::1'

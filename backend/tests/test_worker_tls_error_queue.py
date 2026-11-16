"""One worker thread serves every TLS connection, and OpenSSL keeps one error queue per
thread. CPython leaves a system error there when it raises it as OSError, so another
connection's next ``SSL_write`` that only has to wait was reported as that error: the
server dropped a healthy download (a truncated bundle, a blank page in the browser)."""
import ctypes
import datetime
import errno
import threading

import _ssl
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

import gevent
import gevent.socket
import gevent.ssl

import workers  # noqa: F401  # the worker module guards gevent's TLS sockets on import

CHUNK = b'x' * 8192
ERR_LIB_SYS = 2


@pytest.fixture(scope='module')
def contexts(tmp_path_factory):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(1)
            .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1))
            .sign(key, hashes.SHA256()))
    d = tmp_path_factory.mktemp('tls')
    (d / 'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (d / 'key.pem').write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    server = gevent.ssl.SSLContext(gevent.ssl.PROTOCOL_TLS_SERVER)
    server.load_cert_chain(str(d / 'cert.pem'), str(d / 'key.pem'))
    client = gevent.ssl.SSLContext(gevent.ssl.PROTOCOL_TLS_CLIENT)
    client.check_hostname = False
    client.verify_mode = gevent.ssl.CERT_NONE
    return server, client


def _in_own_hub(fn):
    # gevent keeps one hub per thread: the scenario runs in its own, unpatched
    out = {}

    def run():
        try:
            out['value'] = fn()
        except BaseException as exc:  # noqa: BLE001  # re-raised in the test thread
            out['error'] = exc

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(30)
    assert not t.is_alive(), 'scenario did not finish'
    if 'error' in out:
        raise out['error']
    return out['value']


def _pair(listener, contexts):
    server_ctx, client_ctx = contexts
    raw = gevent.socket.create_connection(listener.getsockname())
    accepted, _ = listener.accept()
    client = gevent.spawn(client_ctx.wrap_socket, raw, server_hostname='localhost')
    server = server_ctx.wrap_socket(accepted, server_side=True)
    return server, client.get(timeout=10)


def _fill_until_error(server, timeout):
    """Writes to a peer that reads nothing until the send buffer is full."""
    server.settimeout(timeout)
    try:
        for _ in range(100000):
            server.sendall(CHUNK)
    except OSError as exc:
        return exc
    pytest.fail('the send buffer never filled')


def _push_system_error(code):
    """What CPython leaves on the queue after raising a system error as OSError."""
    crypto = ctypes.CDLL(_ssl.__file__)
    try:
        crypto.ERR_new()
    except AttributeError:
        pytest.skip('OpenSSL before 3.0: no ERR_new')
    crypto.ERR_set_error.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p]
    crypto.ERR_set_error(ERR_LIB_SYS, code, None)


def test_a_waiting_write_is_not_reported_as_another_connections_system_error(contexts):
    def scenario():
        listener = gevent.socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(8)
        server, client = _pair(listener, contexts)
        _push_system_error(errno.EPIPE)
        return _fill_until_error(server, 0.5), client

    err, _client = _in_own_hub(scenario)
    assert isinstance(err, TimeoutError), f'a healthy connection was reported as {err!r}'


def test_a_tls_call_resumed_after_a_wait_finds_the_queue_empty(contexts):
    # Other greenlets run while a connection waits: what they leave is gone before its retry
    def scenario():
        listener = gevent.socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(8)
        server, client = _pair(listener, contexts)
        crypto = ctypes.CDLL(_ssl.__file__)
        crypto.ERR_peek_error.restype = ctypes.c_ulong
        waiter = gevent.spawn(server._wait, server._write_event)
        gevent.spawn(_push_system_error, errno.ECONNRESET).join()
        waiter.get(timeout=5)
        return crypto.ERR_peek_error(), client

    left, _client = _in_own_hub(scenario)
    assert left == 0


def test_a_connection_the_browser_dropped_does_not_break_the_next_download(contexts):
    def scenario():
        listener = gevent.socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(8)
        dropped, gone = _pair(listener, contexts)
        server, client = _pair(listener, contexts)
        gone.close()  # a navigation cancels a request in flight
        lost = _fill_until_error(dropped, 5)
        return lost, _fill_until_error(server, 0.5), client

    lost, err, _client = _in_own_hub(scenario)
    assert isinstance(lost, (BrokenPipeError, ConnectionResetError)), lost
    assert isinstance(err, TimeoutError), f'the download was cut by {err!r}'

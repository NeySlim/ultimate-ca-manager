"""The worker hands the TLS 1.2 tls-unique channel binding to the request
(RFC 5929 §3, checked by EST under RFC 7030 §3.5); TLS 1.3 has none (RFC 9266)."""
import base64
import datetime
import ssl
import socket
import threading

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from flask import Flask, request
from gevent import pywsgi

from workers import MTLSWebSocketHandler


def _app():
    app = Flask(__name__)

    @app.route('/binding')
    def binding():
        value = request.environ.get('ucm.tls_unique')
        return base64.b64encode(value).decode() if value else 'none'

    return app


@pytest.fixture(scope='module')
def tls_server(tmp_path_factory):
    folder = tmp_path_factory.mktemp('tls-unique')
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=1)).sign(key, hashes.SHA256()))
    (folder / 'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (folder / 'key.pem').write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    ready, holder = threading.Event(), {}

    def run():
        srv = pywsgi.WSGIServer(('127.0.0.1', 0), _app(), handler_class=MTLSWebSocketHandler,
                                log=None, error_log=None,
                                certfile=str(folder / 'cert.pem'),
                                keyfile=str(folder / 'key.pem'))
        srv.init_socket()
        holder['address'] = srv.address
        ready.set()
        srv.serve_forever()

    threading.Thread(target=run, daemon=True).start()
    assert ready.wait(5)
    yield holder['address']


def _get(address, maximum):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.maximum_version = maximum
    with socket.create_connection(address, timeout=5) as raw:
        with ctx.wrap_socket(raw, server_hostname='localhost') as tls:
            tls.sendall(b'GET /binding HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
            data = b''
            while True:
                chunk = tls.recv(4096)
                if not chunk:
                    break
                data += chunk
            return tls.get_channel_binding('tls-unique'), data.partition(b'\r\n\r\n')[2]


def test_tls12_request_carries_the_connection_binding(tls_server):
    binding, body = _get(tls_server, ssl.TLSVersion.TLSv1_2)
    assert binding
    assert body == base64.b64encode(binding)


def test_tls13_request_carries_no_binding(tls_server):
    _binding, body = _get(tls_server, ssl.TLSVersion.TLSv1_3)
    assert body == b'none'

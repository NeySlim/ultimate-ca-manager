"""TLS-ALPN-01 validation (RFC 8737) is bounded in real time, as HTTP-01 is.

A challenge server under the ACME account's control can drip its handshake one byte
at a time, each within the per-read timeout: only a total deadline frees the worker.
"""
import json
import socket
import threading
import time

import pytest

from models import db
from models.acme_models import AcmeAccount
from services.acme.acme_service import AcmeService
from services.acme.mixins import challenge as challenge_mixin
from tests.test_acme_security_paths import _gen_key_and_jwk, _thumbprint

BASE = 'http://localhost'


@pytest.fixture
def dripping_server():
    """A listener that answers a ClientHello with a TLS record header, then one byte every 0.3 s."""
    listener = socket.create_server(('127.0.0.1', 0))
    stop = threading.Event()

    def serve():
        listener.settimeout(0.2)
        while not stop.is_set():
            try:
                conn, _ = listener.accept()
            except OSError:
                continue
            with conn:
                try:
                    conn.recv(4096)
                    conn.sendall(b'\x16\x03\x03\x40\x00')  # a handshake record of 16 KiB
                    for _ in range(40):
                        if stop.wait(0.3):
                            break
                        conn.sendall(b'\x02')
                except OSError:
                    pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield listener.getsockname()[1]
    stop.set()
    thread.join(5)
    listener.close()


def _validate(app, monkeypatch, port, unreachable):
    """Validate against *unreachable* addresses that each take the whole connect timeout, then the server."""
    import utils.ssrf_protection as ssrf
    real_connect = socket.create_connection
    addresses = [f'192.0.2.{n}' for n in range(1, unreachable + 1)] + ['127.0.0.1']

    def connect(address, timeout=None, *a, **k):
        if address[0] != '127.0.0.1':
            time.sleep(timeout)
            raise TimeoutError('timed out')
        return real_connect(('127.0.0.1', port), timeout, *a, **k)
    monkeypatch.setattr(ssrf, 'validate_url_not_cloud_metadata', lambda *a, **k: None)
    monkeypatch.setattr(ssrf, 'validated_addresses', lambda *a, **k: ('h', addresses))
    monkeypatch.setattr(socket, 'create_connection', connect)
    # Per-operation timeout 1 s, so a total of 3 s
    monkeypatch.setattr(challenge_mixin, 'TLS_ALPN_TIMEOUT', 1, raising=False)
    _key, jwk = _gen_key_and_jwk()
    with app.app_context():
        account = AcmeAccount(jwk=json.dumps(jwk), jwk_thumbprint=_thumbprint(jwk), status='valid')
        db.session.add(account)
        db.session.commit()
        service = AcmeService(base_url=BASE)
        order = service.create_order(account_id=account.account_id,
                                     identifiers=[{'type': 'dns', 'value': 'alpn-drip.example'}])
        challenge = next(c for c in order.authorizations[0].challenges if c.type == 'tls-alpn-01')
        started = time.monotonic()
        assert service.validate_tls_alpn01_challenge(challenge, account) is False
        elapsed = time.monotonic() - started
        assert challenge.status == 'invalid'
        return elapsed, json.loads(challenge.error)['detail']


def test_addresses_that_never_answer_share_one_deadline(app, monkeypatch, dripping_server):
    # A name can resolve to many addresses: each connect attempt is bounded, their sum was not
    elapsed, detail = _validate(app, monkeypatch, dripping_server, unreachable=8)
    assert elapsed < 5, elapsed
    assert 'in time' in detail


def test_a_dripped_handshake_ends_by_the_deadline(app, monkeypatch, dripping_server):
    elapsed, detail = _validate(app, monkeypatch, dripping_server, unreachable=0)
    assert elapsed < 5, elapsed
    assert 'in time' in detail

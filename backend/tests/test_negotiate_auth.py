"""Tests for services/kerberos/negotiate_auth.py's negotiated_protocol
enforcement.

Both 'authenticated' return points in authenticate_negotiate justify
accepting on nothing more than "this acceptor was only ever configured
with a Kerberos keytab, so there's no weaker mechanism to downgrade to" --
_is_kerberos_negotiated turns that assumption into an enforced check
instead. No Flask app/DB needed: get_spn() and _new_acceptor() are
monkeypatched, and everything else here is pure.
"""
import base64
import builtins

import pytest

from services.kerberos import negotiate_auth


class _FakeServer:
    def __init__(self, *, complete, client_principal, negotiated_protocol, out_token=b'out-token'):
        self.complete = complete
        self.client_principal = client_principal
        self.negotiated_protocol = negotiated_protocol
        self._out_token = out_token

    def step(self, token):
        return self._out_token


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.setattr(negotiate_auth, 'get_spn', lambda: 'HTTP/ucm.example.test@EXAMPLE.TEST')
    negotiate_auth._pending_contexts.clear()
    yield
    negotiate_auth._pending_contexts.clear()


def _authenticate(monkeypatch, fake_server):
    monkeypatch.setattr(negotiate_auth, '_new_acceptor', lambda hostname, service: fake_server)
    token_b64 = base64.b64encode(b'token-bytes').decode()
    return negotiate_auth.authenticate_negotiate(f'Negotiate {token_b64}', '10.0.0.1')


def test_mic_bypass_accepts_kerberos(monkeypatch):
    server = _FakeServer(complete=False, client_principal='alice@EXAMPLE.TEST', negotiated_protocol='kerberos')
    result = _authenticate(monkeypatch, server)
    assert result.status == 'authenticated'
    assert result.client_principal == 'alice@EXAMPLE.TEST'


def test_mic_bypass_rejects_non_kerberos(monkeypatch):
    """The whole point of the early-accept branch is 'no weaker mechanism
    to downgrade to' -- if pyspnego ever reports anything but kerberos here,
    that premise is false and acceptance must not happen."""
    server = _FakeServer(complete=False, client_principal='alice', negotiated_protocol='ntlm')
    result = _authenticate(monkeypatch, server)
    assert result.status == 'failed'


def test_full_completion_accepts_kerberos(monkeypatch):
    server = _FakeServer(complete=True, client_principal='WIN11$@EXAMPLE.TEST', negotiated_protocol='kerberos')
    result = _authenticate(monkeypatch, server)
    assert result.status == 'authenticated'
    assert result.client_principal == 'WIN11$@EXAMPLE.TEST'


def test_full_completion_rejects_non_kerberos(monkeypatch):
    server = _FakeServer(complete=True, client_principal='WIN11$@EXAMPLE.TEST', negotiated_protocol='ntlm')
    result = _authenticate(monkeypatch, server)
    assert result.status == 'failed'


def test_full_completion_rejects_unresolved_protocol(monkeypatch):
    """negotiated_protocol is None until pyspnego resolves a mechanism --
    an 'authenticated' context should never actually reach this state, but
    if it somehow did, treat it the same as any other non-kerberos result."""
    server = _FakeServer(complete=True, client_principal='alice@EXAMPLE.TEST', negotiated_protocol=None)
    result = _authenticate(monkeypatch, server)
    assert result.status == 'failed'


def test_is_library_available_requires_gssapi_not_just_spnego(monkeypatch):
    """Regression for GH #229: the base ``spnego`` package is importable
    even without GSSAPI (it's pulled in transitively by requests-ntlm, so
    ``import spnego`` alone proves nothing about Kerberos actually working).
    If ``gssapi`` isn't importable, this must report unavailable rather than
    let a caller advertise/attempt Kerberos that's guaranteed to fail."""
    negotiate_auth.is_library_available.cache_clear()
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == 'gssapi':
            raise ImportError("No module named 'gssapi'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', fake_import)
    try:
        assert negotiate_auth.is_library_available() is False
    finally:
        negotiate_auth.is_library_available.cache_clear()

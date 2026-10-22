"""
Regression tests for est_protocol._trusted_client_cert().

PR #248 made the reverse-proxy client-cert path fail closed (a missing
SSL_CLIENT_VERIFY no longer counts as success) but shipped no test, and the
new warning fired on EVERY ordinary Basic-auth request arriving through a
trusted proxy that forwards no SSL_CLIENT_* variables at all — the exact
setup of the sample nginx config in docs/installation/docker.md.

These tests call the function directly under a bare Flask request context
(no UCM create_app, no database), so they also run on hosts where the shared
`app` fixture cannot start.
"""
import logging

import pytest
from flask import Flask

from api import est_protocol



def _self_signed_pem():
    import datetime
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'est-client')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(1)
            .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1))
            .sign(key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM).decode()


# Header values cannot carry newlines: sent folded to spaces, as Apache does.
CLIENT_PEM = _self_signed_pem()
CLIENT_CERT = CLIENT_PEM.replace('\n', ' ').strip()
LOGGER_NAME = est_protocol.logger.name


@pytest.fixture()
def bare_app(monkeypatch):
    # Default trusted-proxy set is loopback; make sure the environment does
    # not widen or narrow it.
    monkeypatch.delenv('UCM_TRUSTED_PROXIES', raising=False)
    return Flask(__name__)


def _warnings(caplog):
    return [
        r for r in caplog.records
        if r.name == LOGGER_NAME and r.levelno >= logging.WARNING
    ]


def test_missing_verify_with_presented_cert_is_refused_and_warned(bare_app, caplog):
    """Fail-closed regression (the #248 behavior change itself, untested there):
    a trusted proxy forwarding a certificate WITHOUT a verify result must have
    the certificate refused — and that genuine anomaly must be logged."""
    with bare_app.test_request_context(
        '/.well-known/est/simpleenroll',
        environ_base={'REMOTE_ADDR': '127.0.0.1'},
        headers={'X-SSL-Client-Cert': CLIENT_CERT},
    ):
        with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
            result = est_protocol._trusted_client_cert()

    assert result is None
    warnings = _warnings(caplog)
    assert len(warnings) == 1
    assert 'refusing client cert' in warnings[0].getMessage()


def test_basic_auth_request_without_cert_logs_no_warning(bare_app, caplog):
    """An ordinary Basic-auth request through a same-host proxy carries no
    SSL_CLIENT_* variables at all. It must still be refused a client cert
    (fail closed) but must NOT warn 'refusing client cert' — no certificate
    was ever presented, and this is the normal success path."""
    with bare_app.test_request_context(
        '/.well-known/est/simpleenroll',
        environ_base={'REMOTE_ADDR': '127.0.0.1'},
    ):
        with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
            result = est_protocol._trusted_client_cert()

    assert result is None
    assert _warnings(caplog) == []


def test_verified_cert_is_returned_without_warning(bare_app, caplog):
    with bare_app.test_request_context(
        '/.well-known/est/simpleenroll',
        environ_base={'REMOTE_ADDR': '127.0.0.1'},
        headers={
            'X-SSL-Client-Verify': 'SUCCESS',
            'X-SSL-Client-Cert': CLIENT_CERT,
        },
    ):
        with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
            result = est_protocol._trusted_client_cert()

    assert result == CLIENT_PEM
    assert _warnings(caplog) == []


def test_failed_verify_with_cert_still_warns(bare_app, caplog):
    """nginx with `ssl_verify_client optional` forwards e.g. 'FAILED' — a
    presented-but-unverified certificate keeps its warning (pre-existing
    behavior, must not be silenced by the noise fix)."""
    with bare_app.test_request_context(
        '/.well-known/est/simpleenroll',
        environ_base={'REMOTE_ADDR': '127.0.0.1'},
        headers={
            'X-SSL-Client-Verify': 'FAILED',
            'X-SSL-Client-Cert': CLIENT_CERT,
        },
    ):
        with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
            result = est_protocol._trusted_client_cert()

    assert result is None
    warnings = _warnings(caplog)
    assert len(warnings) == 1
    assert 'refusing client cert' in warnings[0].getMessage()


def test_untrusted_peer_cert_headers_are_ignored_and_warned(bare_app, caplog):
    """A peer outside the trusted-proxy set sending cert headers is a spoof
    attempt: refuse and log, regardless of what the headers claim."""
    with bare_app.test_request_context(
        '/.well-known/est/simpleenroll',
        environ_base={'REMOTE_ADDR': '203.0.113.7'},
        headers={
            'X-SSL-Client-Verify': 'SUCCESS',
            'X-SSL-Client-Cert': CLIENT_CERT,
        },
    ):
        with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
            result = est_protocol._trusted_client_cert()

    assert result is None
    warnings = _warnings(caplog)
    assert len(warnings) == 1
    assert 'untrusted peer' in warnings[0].getMessage()


def _der_of(pem):
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    return x509.load_pem_x509_certificate(pem.encode()).public_bytes(
        serialization.Encoding.DER)


def test_native_tls_der_peercert_is_returned_as_pem(bare_app):
    """workers.MTLSWebSocketHandler stores the peer certificate as DER
    (getpeercert(binary_form=True)); every EST caller parses the value with
    load_pem_x509_certificate, so it must come back as PEM."""
    from cryptography import x509
    with bare_app.test_request_context(
        '/.well-known/est/simplereenroll',
        environ_overrides={'peercert': _der_of(CLIENT_PEM)},
    ):
        result = est_protocol._trusted_client_cert()

    assert result is not None
    cert = x509.load_pem_x509_certificate(
        result.encode() if isinstance(result, str) else result)
    assert cert == x509.load_pem_x509_certificate(CLIENT_PEM.encode())


def test_native_tls_pem_peercert_is_returned_unchanged(bare_app):
    with bare_app.test_request_context(
        '/.well-known/est/simplereenroll',
        environ_overrides={'peercert': CLIENT_PEM},
    ):
        assert est_protocol._trusted_client_cert() == CLIENT_PEM

"""A proxied client certificate is read whether it arrives as raw PEM or URL-encoded
(nginx ``$ssl_client_escaped_cert``); the trusted-proxy gate is unchanged."""
import datetime
from urllib.parse import quote

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from flask import Flask

from api import est_protocol
from services.certificate_parser import CertificateParser


@pytest.fixture(scope='module')
def pem():
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'proxied-client')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=1))
            .not_valid_after(now + datetime.timedelta(days=1))
            .sign(key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def nginx_escaped(pem):
    escaped = quote(pem, safe='')
    assert '%20' in escaped and '%0A' in escaped
    return escaped


@pytest.mark.parametrize('form', ['raw', 'escaped'])
def test_nginx_headers_parse_both_forms(pem, form):
    value = pem if form == 'raw' else nginx_escaped(pem)
    info = CertificateParser.extract_from_nginx_headers(
        {'X-SSL-Client-Verify': 'SUCCESS', 'X-SSL-Client-Cert': value})
    assert info is not None
    assert info['common_name'] == 'proxied-client'


def test_escaped_with_plus_slash_and_padding(pem):
    body = ''.join(pem.splitlines()[1:-1])
    escaped = nginx_escaped(pem)
    for ch, code in (('+', '%2B'), ('/', '%2F'), ('=', '%3D')):
        if ch in body:
            assert code in escaped
    info = CertificateParser.extract_from_apache_headers(
        {'X-SSL-Client-Verify': 'SUCCESS', 'X-SSL-Client-Cert': escaped})
    assert info['common_name'] == 'proxied-client'


@pytest.fixture()
def bare_app(monkeypatch):
    monkeypatch.delenv('UCM_TRUSTED_PROXIES', raising=False)
    return Flask(__name__)


def test_est_trusted_proxy_escaped_cert_is_decoded(bare_app, pem):
    with bare_app.test_request_context(
        '/.well-known/est/simpleenroll', environ_base={'REMOTE_ADDR': '127.0.0.1'},
        headers={'X-SSL-Client-Verify': 'SUCCESS', 'X-SSL-Client-Cert': nginx_escaped(pem)},
    ):
        presented = est_protocol._trusted_client_cert()
    cert = x509.load_pem_x509_certificate(presented.encode())
    assert cert.subject.rfc4514_string() == 'CN=proxied-client'


def test_est_untrusted_peer_escaped_cert_still_ignored(bare_app, pem):
    with bare_app.test_request_context(
        '/.well-known/est/simpleenroll', environ_base={'REMOTE_ADDR': '203.0.113.7'},
        headers={'X-SSL-Client-Verify': 'SUCCESS', 'X-SSL-Client-Cert': nginx_escaped(pem)},
    ):
        assert est_protocol._trusted_client_cert() is None


def apache_folded(pem):
    return pem.replace('\n', ' ').strip()


def bare_der_base64(pem):
    return ''.join(pem.splitlines()[1:-1])


@pytest.mark.parametrize('form', [apache_folded, bare_der_base64])
def test_parser_reads_apache_and_bare_forms(pem, form):
    info = CertificateParser.extract_from_apache_headers(
        {'X-SSL-Client-Verify': 'SUCCESS', 'X-SSL-Client-Cert': form(pem)})
    assert info['common_name'] == 'proxied-client'


@pytest.mark.parametrize('form', [apache_folded, bare_der_base64])
def test_est_reads_apache_and_bare_forms(bare_app, pem, form):
    with bare_app.test_request_context(
        '/.well-known/est/simpleenroll', environ_base={'REMOTE_ADDR': '127.0.0.1'},
        headers={'X-SSL-Client-Verify': 'SUCCESS', 'X-SSL-Client-Cert': form(pem)},
    ):
        presented = est_protocol._trusted_client_cert()
    assert x509.load_pem_x509_certificate(presented.encode()).subject.rfc4514_string() == 'CN=proxied-client'


@pytest.mark.parametrize('form', [apache_folded, bare_der_base64])
def test_est_untrusted_peer_other_forms_still_ignored(bare_app, pem, form):
    with bare_app.test_request_context(
        '/.well-known/est/simpleenroll', environ_base={'REMOTE_ADDR': '203.0.113.7'},
        headers={'X-SSL-Client-Verify': 'SUCCESS', 'X-SSL-Client-Cert': form(pem)},
    ):
        assert est_protocol._trusted_client_cert() is None

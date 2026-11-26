"""SMTP over TLS checks the relay: a relay presenting a self-signed certificate, or
one issued to another name, is refused before any credential is sent."""
import datetime
import socket
import ssl
import threading

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from services.email_service import _smtp_connect


@pytest.fixture(scope='module')
def impostor_cert(tmp_path_factory):
    """A self-signed certificate for a name that is not the relay's."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'not-the-relay.invalid')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName('not-the-relay.invalid')]),
                           critical=False)
            .sign(key, hashes.SHA256()))
    d = tmp_path_factory.mktemp('impostor')
    (d / 'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (d / 'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                                  serialization.PrivateFormat.PKCS8,
                                                  serialization.NoEncryption()))
    return str(d / 'cert.pem'), str(d / 'key.pem')


def _impostor(cert, starttls):
    """One-connection SMTP relay on 127.0.0.1; returns (port, seen) where seen
    records whether the TLS handshake completed."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(*cert)
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(1)
    listener.settimeout(10)
    seen = {'handshake': False}

    def serve():
        try:
            conn, _ = listener.accept()
            conn.settimeout(10)
            if starttls:
                conn.sendall(b'220 relay ESMTP\r\n')
                conn.recv(1024)  # EHLO
                conn.sendall(b'250-relay\r\n250 STARTTLS\r\n')
                conn.recv(1024)  # STARTTLS
                conn.sendall(b'220 go ahead\r\n')
            tls = ctx.wrap_socket(conn, server_side=True)
            seen['handshake'] = True
            if not starttls:
                tls.sendall(b'220 relay ESMTP\r\n')
            tls.recv(1024)
            tls.close()
        except (OSError, ssl.SSLError):
            pass
        finally:
            listener.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return listener.getsockname()[1], seen, thread


class _Config:
    smtp_host = '127.0.0.1'


@pytest.mark.parametrize('starttls', [False, True], ids=['implicit-tls', 'starttls'])
def test_a_relay_with_an_untrusted_certificate_is_refused(impostor_cert, starttls):
    port, seen, thread = _impostor(impostor_cert, starttls)
    cfg = _Config()
    cfg.smtp_port, cfg.smtp_use_ssl, cfg.smtp_use_tls = port, not starttls, starttls
    with pytest.raises(ssl.SSLCertVerificationError):
        server = _smtp_connect(cfg, timeout=5)
        server.close()
    thread.join(10)
    assert not seen['handshake']

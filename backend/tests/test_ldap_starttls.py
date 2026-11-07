"""LDAP StartTLS: no bind leaves before TLS is up (RFC 4513 §3, §5.1.3).

A fake directory on a local socket records what reaches the wire: the bytes as
sent, and the messages it reads once TLS is established.
"""
import datetime
import socket
import ssl
import threading
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

STARTTLS_OID = b'1.3.6.1.4.1.1466.20037'
SERVICE_SECRET = 'S3rvice-Secret!'
USER_SECRET = 'Us3r-Secret!'


def _self_signed(tmp_path):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'ldap.test')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName('ldap.test')]), critical=False)
            .sign(key, hashes.SHA256()))
    cert_path, key_path = tmp_path / 'c.pem', tmp_path / 'k.pem'
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                           serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    return str(cert_path), str(key_path)


class _Recorder:
    """Wraps a socket and keeps every byte read from it."""

    def __init__(self, sock):
        self.sock, self.raw = sock, bytearray()

    def recv(self, n):
        data = self.sock.recv(n)
        self.raw += data
        return data


def _read_message(sock):
    """One BER element: (tag, whole message bytes), or (None, b'') at EOF."""
    def exact(n):
        buf = b''
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise EOFError
            buf += chunk
        return buf
    try:
        head = exact(2)
        length = head[1]
        extra = b''
        if length & 0x80:
            extra = exact(length & 0x7F)
            length = int.from_bytes(extra, 'big')
        body = exact(length)
    except EOFError:
        return None, b''
    msg = head + extra + body
    # LDAPMessage: SEQUENCE { messageID INTEGER, protocolOp ... }
    id_len = body[1]
    return body[2 + id_len], msg, body[2:2 + id_len]


def _ldap_result(msg_id, app_tag, extra=b''):
    op = b'\x0a\x01\x00\x04\x00\x04\x00' + extra
    inner = b'\x02' + bytes([len(msg_id)]) + msg_id + bytes([app_tag, len(op)]) + op
    return b'\x30' + bytes([len(inner)]) + inner


def _entry(msg_id, dn):
    op = b'\x04' + bytes([len(dn)]) + dn + b'\x30\x00'
    inner = b'\x02' + bytes([len(msg_id)]) + msg_id + bytes([0x64, len(op)]) + op
    return b'\x30' + bytes([len(inner)]) + inner


class FakeDirectory:
    """Answers StartTLS, binds and searches with success and no entries."""

    def __init__(self, tmp_path):
        self.cert, self.key = _self_signed(tmp_path)
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(5)
        self.listener.settimeout(0.2)
        self.port = self.listener.getsockname()[1]
        self.plain = bytearray()       # every byte as it crossed the wire
        self.first_ops = []            # first protocolOp tag of each connection
        self.tls_ops = []              # protocolOp tags read inside TLS
        self.tls_bytes = bytearray()   # decrypted messages read inside TLS
        self._stop = False
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        while not self._stop:
            try:
                conn, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            conn.settimeout(5)
            try:
                self._session(conn)
            except Exception:
                pass
            finally:
                conn.close()

    def _session(self, conn):
        rec = _Recorder(conn)
        stream, in_tls, first = rec, False, True
        while True:
            parsed = _read_message(stream)
            if parsed[0] is None:
                break
            tag, msg, msg_id = parsed
            if not in_tls:
                self.plain += rec.raw
                rec.raw.clear()
            if first:
                self.first_ops.append(tag)
                first = False
            if in_tls:
                self.tls_ops.append(tag)
                self.tls_bytes += msg
            if tag == 0x77 and STARTTLS_OID in msg:            # ExtendedRequest
                conn.sendall(_ldap_result(msg_id, 0x78))
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ctx.load_cert_chain(self.cert, self.key)
                stream = ctx.wrap_socket(conn, server_side=True)
                in_tls = True
            elif tag == 0x60:                                    # BindRequest
                stream_send = stream.sendall if in_tls else conn.sendall
                stream_send(_ldap_result(msg_id, 0x61))
            elif tag == 0x63:                                    # SearchRequest
                send = stream.sendall if in_tls else conn.sendall
                if b'alice' in msg:
                    send(_entry(msg_id, b'uid=alice,dc=example'))
                send(_ldap_result(msg_id, 0x65))
            elif tag == 0x42:                                    # UnbindRequest
                break
            else:
                break

    def close(self):
        self._stop = True
        self.thread.join(timeout=5)
        self.listener.close()


@pytest.fixture
def directory(tmp_path):
    d = FakeDirectory(tmp_path)
    yield d
    d.close()


def _provider(directory, **kw):
    values = dict(
        id=1, name='wire', provider_type='ldap', ldap_server='127.0.0.1', ldap_port=directory.port,
        ldap_use_ssl=False, ldap_start_tls=True, ldap_verify_ssl=False, ldap_ca_bundle=None,
        ldap_bind_dn='cn=svc,dc=example', ldap_bind_password=SERVICE_SECRET,
        ldap_base_dn='dc=example', ldap_user_filter='(uid={username})', ldap_group_filter=None,
        ldap_group_member_attr='member', ldap_username_attr='uid', ldap_email_attr='mail',
        ldap_fullname_attr='cn', ldap_uid_attr=None, ldap_required_groups=None,
        account_status_attr=None,
    )
    values.update(kw)
    return SimpleNamespace(**values)


@pytest.fixture
def clear_password(monkeypatch):
    from api.v2.sso import connection_tests
    monkeypatch.setattr(connection_tests, '_decrypt_ldap_password', lambda p: p.ldap_bind_password)


def test_service_bind_goes_after_starttls(app, directory, clear_password):
    from api.v2.sso.connection_tests import _ldap_authenticate_user
    with app.app_context():
        _ldap_authenticate_user(_provider(directory), 'alice', USER_SECRET)
    # Two connections (service, then the user's own bind), each opened by StartTLS.
    assert len(directory.first_ops) >= 2 and set(directory.first_ops) == {0x77}
    for secret in (SERVICE_SECRET, USER_SECRET):
        assert secret.encode() not in directory.plain
        assert secret.encode() in directory.tls_bytes


def test_connection_test_binds_after_starttls(app, directory, clear_password):
    from api.v2.sso.connection_tests import _test_ldap_connection
    with app.app_context():
        _test_ldap_connection(_provider(directory))
    assert directory.first_ops[0] == 0x77
    assert SERVICE_SECRET.encode() not in directory.plain
    assert 0x60 in directory.tls_ops


def test_a_certificate_that_fails_verification_stops_before_any_bind(app, directory, clear_password):
    """Verification on, certificate not trusted: no bind at all, in clear or not."""
    from api.v2.sso.connection_tests import _ldap_authenticate_user
    with app.app_context():
        info, error = _ldap_authenticate_user(_provider(directory, ldap_verify_ssl=True),
                                              'alice', USER_SECRET)
    assert info is None and error
    assert 0x60 not in directory.tls_ops
    assert SERVICE_SECRET.encode() not in directory.plain


def test_plain_ldap_without_starttls_is_unchanged(app, directory, clear_password):
    from api.v2.sso.connection_tests import _ldap_authenticate_user
    with app.app_context():
        _ldap_authenticate_user(_provider(directory, ldap_start_tls=False), 'alice', USER_SECRET)
    assert directory.first_ops[0] == 0x60

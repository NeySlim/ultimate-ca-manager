"""In FIPS mode the SSH deploy transport negotiates only what runs in the
module: no Ed25519 host key (libsodium), no Diffie-Hellman group exchange
(Python arithmetic), and a pinned Ed25519 host key asks for a reset."""
import io
import logging
import socket
import threading

import paramiko
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

import fips_mode
from services.deploy import ssh as deploy_ssh

DH_KEX = ['diffie-hellman-group16-sha512', 'diffie-hellman-group-exchange-sha256',
          'diffie-hellman-group14-sha256']


class _AcceptAll(paramiko.ServerInterface):
    def get_allowed_auths(self, username):
        return 'publickey'

    def check_auth_publickey(self, username, key):
        return paramiko.AUTH_SUCCESSFUL


def _ed25519_host_key():
    pem = ed25519.Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
        serialization.NoEncryption()).decode()
    return paramiko.Ed25519Key.from_private_key(io.StringIO(pem))


@pytest.fixture
def sshd():
    """sshd(host_keys, kex=None) -> port of a one-connection paramiko server."""
    transports, sockets = [], []

    def start(host_keys, kex=None):
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        sockets.append(listener)
        disabled = None
        if kex is not None:
            disabled = {'kex': [k for k in paramiko.Transport._preferred_kex if k not in kex]}

        def serve():
            try:
                conn, _ = listener.accept()
            except OSError:
                return
            transport = paramiko.Transport(conn, disabled_algorithms=disabled)
            transports.append(transport)
            for key in host_keys:
                transport.add_server_key(key)
            try:
                transport.start_server(server=_AcceptAll())
            except (paramiko.SSHException, EOFError, OSError):
                pass
        threading.Thread(target=serve, daemon=True).start()
        return listener.getsockname()[1]
    yield start
    for transport in transports:
        transport.close()
    for listener in sockets:
        listener.close()


@pytest.fixture
def fips(monkeypatch):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)


@pytest.fixture
def client_key_ecdsa(monkeypatch):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    private, _public = deploy_ssh.generate_keypair()  # ECDSA P-256 in FIPS mode
    return private


def _connect(port, key, pin=None):
    client, learned = deploy_ssh.open_client('127.0.0.1', port, 'deploy', key, pin)
    transport = client.get_transport()
    negotiated = (transport.host_key_type, transport.local_cipher, transport.local_mac)
    client.close()
    return negotiated, learned


def test_disabled_algorithms_leave_only_the_module_s(fips):
    disabled = deploy_ssh.disabled_algorithms(paramiko)
    left, right = socket.socketpair()
    try:
        transport = paramiko.Transport(left, disabled_algorithms=disabled)
        offered = {'kex': transport.preferred_kex, 'keys': transport.preferred_keys,
                   'pubkeys': transport.preferred_pubkeys,
                   'ciphers': transport.preferred_ciphers, 'macs': transport.preferred_macs}
    finally:
        left.close()
        right.close()
    for kind, names in offered.items():
        # paramiko adds the certificate variant of each host key type it keeps
        bare = {name.replace('-cert-v01@openssh.com', '') for name in names}
        assert names and bare <= set(deploy_ssh.FIPS_SSH_ALGORITHMS[kind]), kind
    assert 'ssh-ed25519' not in offered['keys'] + offered['pubkeys']
    assert not set(DH_KEX) & set(offered['kex'])
    assert '3des-cbc' not in offered['ciphers'] and 'hmac-md5' not in offered['macs']


def test_nothing_is_disabled_outside_fips(monkeypatch):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: False)
    assert deploy_ssh.disabled_algorithms(paramiko) is None


def test_fips_picks_the_ecdsa_host_key_over_ed25519(sshd, client_key_ecdsa, caplog):
    port = sshd([_ed25519_host_key(), paramiko.ECDSAKey.generate()])
    with caplog.at_level(logging.DEBUG, logger='paramiko.transport'):
        (host_key, cipher, mac), learned = _connect(port, client_key_ecdsa)
    assert host_key == 'ecdsa-sha2-nistp256' and learned.startswith('ecdsa-sha2-nistp256 ')
    assert cipher in deploy_ssh.FIPS_SSH_ALGORITHMS['ciphers']
    assert mac in deploy_ssh.FIPS_SSH_ALGORITHMS['macs']
    assert 'Kex: ecdh-sha2-nistp256' in caplog.text


def test_standard_mode_still_prefers_ed25519(sshd, client_key_ecdsa, monkeypatch):
    port = sshd([_ed25519_host_key(), paramiko.ECDSAKey.generate()])
    monkeypatch.setattr(fips_mode, 'enabled', lambda: False)
    (host_key, _, _), _ = _connect(port, client_key_ecdsa)
    assert host_key == 'ssh-ed25519'


def test_an_ed25519_only_host_is_refused_with_a_reason(sshd, client_key_ecdsa):
    port = sshd([_ed25519_host_key()])
    with pytest.raises(deploy_ssh.DeploySSHError) as exc:
        _connect(port, client_key_ecdsa)
    assert deploy_ssh.FIPS_SSH_REFUSED in str(exc.value)


def test_a_dh_only_host_is_refused_with_a_reason(sshd, client_key_ecdsa):
    port = sshd([paramiko.ECDSAKey.generate()], kex=DH_KEX)
    with pytest.raises(deploy_ssh.DeploySSHError) as exc:
        _connect(port, client_key_ecdsa)
    assert deploy_ssh.FIPS_SSH_REFUSED in str(exc.value)


@pytest.mark.parametrize('host_keys, kex', [
    (lambda: [_ed25519_host_key()], None),
    (lambda: [paramiko.ECDSAKey.generate()], DH_KEX),
])
def test_the_same_hosts_work_outside_fips(sshd, client_key_ecdsa, monkeypatch, host_keys, kex):
    port = sshd(host_keys(), kex=kex)
    monkeypatch.setattr(fips_mode, 'enabled', lambda: False)
    (_, _, _), learned = _connect(port, client_key_ecdsa)
    assert learned


def test_a_pinned_ed25519_host_key_asks_for_a_reset_without_connecting(client_key_ecdsa):
    with socket.socket() as unused:
        unused.bind(('127.0.0.1', 0))
        port = unused.getsockname()[1]  # nothing listens: a connection attempt would fail
    with pytest.raises(deploy_ssh.HostKeyMismatch, match='pinned host key is Ed25519'):
        deploy_ssh.open_client('127.0.0.1', port, 'deploy', client_key_ecdsa,
                               'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPinned')


def test_a_pinned_ecdsa_host_key_still_matches(sshd, client_key_ecdsa):
    host_key = paramiko.ECDSAKey.generate()
    port = sshd([host_key])
    pin = f'{host_key.get_name()} {host_key.get_base64()}'
    (host_key_type, _, _), learned = _connect(port, client_key_ecdsa, pin=pin)
    assert host_key_type == 'ecdsa-sha2-nistp256' and learned is None

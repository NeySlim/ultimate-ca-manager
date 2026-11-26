"""SSH signatures (PROTOCOL.sshsig) as `ssh-keygen -Y sign` writes them, checked without running
anything on the server: every host key type verifies, and a signature of another message, of
another purpose, by another key or altered in any byte does not."""
import base64
import shutil
import subprocess

import pytest

from utils import sshsig

pytestmark = pytest.mark.skipif(not shutil.which('ssh-keygen'), reason='ssh-keygen not available')

KEYS = {'ed25519': ['-t', 'ed25519'], 'ecdsa256': ['-t', 'ecdsa', '-b', '256'],
        'ecdsa384': ['-t', 'ecdsa', '-b', '384'], 'ecdsa521': ['-t', 'ecdsa', '-b', '521'],
        'rsa': ['-t', 'rsa', '-b', '2048']}


def _key(tmp_path, kind, name='key'):
    path = tmp_path / f'{name}-{kind}'
    subprocess.run(['ssh-keygen', '-q', '-N', '', '-f', str(path), *KEYS[kind]], check=True)
    return path, (tmp_path / f'{name}-{kind}.pub').read_text()


def _sign(tmp_path, key, message, namespace='ucm-ssh-host-renewal', hashalg=None):
    data = tmp_path / 'message'
    data.write_bytes(message)
    extra = ['-O', f'hashalg={hashalg}'] if hashalg else []
    subprocess.run(['ssh-keygen', '-q', '-Y', 'sign', '-n', namespace, '-f', str(key), *extra, str(data)], check=True)
    signature = (tmp_path / 'message.sig').read_text()
    (tmp_path / 'message.sig').unlink()
    return signature


@pytest.mark.parametrize('kind', sorted(KEYS))
def test_every_host_key_type_verifies(tmp_path, kind):
    key, public = _key(tmp_path, kind)
    sshsig.verify(_sign(tmp_path, key, b'challenge-1'), b'challenge-1', 'ucm-ssh-host-renewal', public)


def test_sha256_hashed_messages_verify(tmp_path):
    key, public = _key(tmp_path, 'ed25519')
    sshsig.verify(_sign(tmp_path, key, b'c', hashalg='sha256'), b'c', 'ucm-ssh-host-renewal', public)


@pytest.mark.parametrize('kind', ['ed25519', 'ecdsa256', 'rsa'])
def test_what_was_not_signed_does_not_verify(tmp_path, kind):
    key, public = _key(tmp_path, kind)
    _, other = _key(tmp_path, kind, 'other')
    signature = _sign(tmp_path, key, b'challenge-1')
    with pytest.raises(sshsig.SignatureError, match='does not verify'):
        sshsig.verify(signature, b'challenge-2', 'ucm-ssh-host-renewal', public)
    with pytest.raises(sshsig.SignatureError, match='another purpose'):
        sshsig.verify(signature, b'challenge-1', 'file', public)
    with pytest.raises(sshsig.SignatureError, match='another key'):
        sshsig.verify(signature, b'challenge-1', 'ucm-ssh-host-renewal', other)


def test_a_signature_altered_in_any_byte_is_refused(tmp_path):
    key, public = _key(tmp_path, 'ed25519')
    armored = _sign(tmp_path, key, b'challenge')
    lines = armored.strip().splitlines()
    blob = base64.b64decode(''.join(lines[1:-1]))
    for at in range(len(blob)):
        tampered = bytearray(blob)
        tampered[at] ^= 0x01
        text = '\n'.join([lines[0], base64.b64encode(bytes(tampered)).decode(), lines[-1]])
        with pytest.raises(sshsig.SignatureError):
            sshsig.verify(text, b'challenge', 'ucm-ssh-host-renewal', public)


@pytest.mark.parametrize('armored', [None, '', 'x' * 20000, 'not a signature',
                                     '-----BEGIN SSH SIGNATURE-----\n!!!\n-----END SSH SIGNATURE-----'])
def test_garbage_is_refused(armored):
    with pytest.raises(sshsig.SignatureError):
        sshsig.verify(armored, b'c', 'n', 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl')

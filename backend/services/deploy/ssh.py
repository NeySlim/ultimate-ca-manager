"""SSH/SFTP transport for deploy hooks (#299).

paramiko is a required dependency (requirements.txt) but is imported lazily so
an environment missing it degrades to clear per-request errors instead of
breaking startup (same policy as certsrv/pkilint).

Host keys are pinned trust-on-first-use: the first successful connection
records '<type> <base64>' on the target; every later connection requires an
exact match and fails closed on any change.
"""
import io
import logging
import socket
from typing import Optional, Tuple

import fips_mode
from utils.key_codec import refuse_eddsa_key

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT_SECONDS = 10
COMMAND_TIMEOUT_SECONDS = 60


# What paramiko runs through the FIPS module: ECDH on NIST curves, ECDSA and RSA,
# AES, HMAC-SHA-1/SHA-2. Ed25519 (libsodium) and DH groups (Python pow) are outside.
FIPS_SSH_ALGORITHMS = {
    'kex': ('ecdh-sha2-nistp256', 'ecdh-sha2-nistp384', 'ecdh-sha2-nistp521'),
    'keys': ('ecdsa-sha2-nistp256', 'ecdsa-sha2-nistp384', 'ecdsa-sha2-nistp521',
             'rsa-sha2-512', 'rsa-sha2-256'),
    'pubkeys': ('ecdsa-sha2-nistp256', 'ecdsa-sha2-nistp384', 'ecdsa-sha2-nistp521',
                'rsa-sha2-512', 'rsa-sha2-256'),
    'ciphers': ('aes128-ctr', 'aes192-ctr', 'aes256-ctr', 'aes128-cbc', 'aes192-cbc',
                'aes256-cbc', 'aes128-gcm@openssh.com', 'aes256-gcm@openssh.com'),
    'macs': ('hmac-sha2-256', 'hmac-sha2-512', 'hmac-sha2-256-etm@openssh.com',
             'hmac-sha2-512-etm@openssh.com', 'hmac-sha1'),
}
FIPS_SSH_REFUSED = ('the target offers no SSH algorithm FIPS mode accepts: it needs an ECDSA '
                    'or RSA host key, ECDH key exchange on P-256, P-384 or P-521, AES and '
                    'HMAC-SHA-1/SHA-2 (an Ed25519 host key or a Diffie-Hellman key exchange '
                    'alone is refused)')


class DeploySSHError(Exception):
    """Transport-level deploy failure with an operator-readable message."""


class HostKeyMismatch(DeploySSHError):
    """Presented host key differs from the pinned one — fails closed."""


def paramiko_available() -> bool:
    try:
        import paramiko  # noqa: F401
        return True
    except ImportError:
        return False


def _require_paramiko():
    try:
        import paramiko
        return paramiko
    except ImportError:
        raise DeploySSHError(
            "paramiko is not installed: reinstall UCM dependencies (pip install -r requirements.txt)"
        )


def generate_keypair() -> Tuple[str, str]:
    """Generate an Ed25519 keypair, ECDSA P-256 in FIPS mode where Ed25519 is
    not approved. Returns (private_openssh, public_openssh)."""
    from cryptography.hazmat.primitives import serialization
    from utils import key_algorithms

    key = key_algorithms.generate('EC-P256' if fips_mode.enabled() else 'ED25519')
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.OpenSSH,
        serialization.NoEncryption(),
    ).decode()
    public_openssh = key.public_key().public_bytes(
        serialization.Encoding.OpenSSH,
        serialization.PublicFormat.OpenSSH,
    ).decode() + ' ucm-deploy'
    return private_pem, public_openssh


def load_private_key(text: str):
    """Parse an SSH private key (OpenSSH or PEM; ed25519/ECDSA/RSA)."""
    refuse_eddsa_key(text, 'the deploy target')
    paramiko = _require_paramiko()
    last_error = None
    for key_cls in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey):
        try:
            return key_cls.from_private_key(io.StringIO(text))
        except Exception as e:
            last_error = e
    raise DeploySSHError(f"Unsupported or invalid SSH private key: {last_error}")


def public_key_from_private(text: str) -> Optional[str]:
    """Derive the OpenSSH public line from a private key, for display."""
    try:
        pkey = load_private_key(text)
        return f"{pkey.get_name()} {pkey.get_base64()} ucm-deploy"
    except Exception:
        return None


def disabled_algorithms(paramiko):
    """Every algorithm paramiko offers outside FIPS_SSH_ALGORITHMS in FIPS mode, None otherwise."""
    if not fips_mode.enabled():
        return None
    transport = paramiko.Transport
    return {kind: [name for name in getattr(transport, f'_preferred_{kind}') if name not in allowed]
            for kind, allowed in FIPS_SSH_ALGORITHMS.items()}


class _PinningPolicy:
    """MissingHostKeyPolicy implementing TOFU pinning against a stored pin."""

    def __init__(self, expected: Optional[str]):
        self.expected = (expected or '').strip() or None
        self.learned: Optional[str] = None

    def missing_host_key(self, client, hostname, key):
        presented = f"{key.get_name()} {key.get_base64()}"
        if self.expected is None:
            # First connect: accept and record.
            self.learned = presented
            return
        if presented != self.expected:
            raise HostKeyMismatch(
                "Host key verification failed: the key presented by the target "
                "does not match the pinned one. If the host was legitimately "
                "reinstalled, reset the pinned host key on the deploy target."
            )


def open_client(host: str, port: int, username: str, private_key_text: str,
                expected_host_key: Optional[str]):
    """Open an authenticated SSHClient with host-key pinning.

    Returns (client, learned_host_key) — learned_host_key is set only on a
    first (TOFU) connection. Caller must close the client.
    """
    pkey = load_private_key(private_key_text)
    paramiko = _require_paramiko()
    disabled = disabled_algorithms(paramiko)
    if disabled and str(expected_host_key or '').startswith('ssh-ed25519 '):
        raise HostKeyMismatch(
            "The pinned host key is Ed25519, which FIPS mode cannot verify: reset the pinned "
            "host key on the deploy target so that the next connection pins its ECDSA or RSA key.")
    policy = _PinningPolicy(expected_host_key)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(policy)
    try:
        client.connect(
            hostname=host,
            port=int(port or 22),
            username=username,
            pkey=pkey,
            timeout=CONNECT_TIMEOUT_SECONDS,
            banner_timeout=CONNECT_TIMEOUT_SECONDS,
            auth_timeout=CONNECT_TIMEOUT_SECONDS,
            allow_agent=False,
            look_for_keys=False,
            disabled_algorithms=disabled,
        )
    except HostKeyMismatch:
        client.close()
        raise
    except paramiko.ssh_exception.IncompatiblePeer as e:
        client.close()
        if disabled:
            raise DeploySSHError(f"SSH connection failed: {FIPS_SSH_REFUSED} ({e})")
        raise DeploySSHError(f"SSH connection failed: {e}")
    except paramiko.AuthenticationException as e:
        client.close()
        raise DeploySSHError(f"SSH authentication failed: {e}")
    except (paramiko.SSHException, socket.error, OSError) as e:
        client.close()
        raise DeploySSHError(f"SSH connection failed: {e}")
    return client, policy.learned


def push_files(client, files):
    """SFTP-write files atomically. files: [(path, content_bytes, mode)].

    Writes to '<path>.ucm-tmp' then renames over the destination, so a reader
    never sees a half-written certificate.
    """
    paramiko = _require_paramiko()
    try:
        sftp = client.open_sftp()
    except paramiko.SSHException as e:
        raise DeploySSHError(f"SFTP unavailable on target: {e}")
    try:
        for path, content, mode in files:
            tmp_path = path + '.ucm-tmp'
            try:
                with sftp.file(tmp_path, 'wb') as f:
                    f.write(content)
                sftp.chmod(tmp_path, mode)
                try:
                    sftp.posix_rename(tmp_path, path)
                except (IOError, OSError):
                    # Server without posix-rename@openssh.com: replace non-atomically
                    try:
                        sftp.remove(path)
                    except (IOError, OSError):
                        pass
                    sftp.rename(tmp_path, path)
            except (IOError, OSError) as e:
                try:
                    sftp.remove(tmp_path)
                except (IOError, OSError):
                    pass
                raise DeploySSHError(f"SFTP write to {path} failed: {e}")
    finally:
        sftp.close()


def run_command(client, command: str) -> Tuple[int, str]:
    """Run the reload command. Returns (exit_status, stderr_tail)."""
    paramiko = _require_paramiko()
    try:
        _, stdout, stderr = client.exec_command(command, timeout=COMMAND_TIMEOUT_SECONDS)
        exit_status = stdout.channel.recv_exit_status()
        err = stderr.read(4096).decode('utf-8', 'replace').strip()
        return exit_status, err
    except (paramiko.SSHException, socket.timeout, OSError) as e:
        raise DeploySSHError(f"Reload command failed to run: {e}")

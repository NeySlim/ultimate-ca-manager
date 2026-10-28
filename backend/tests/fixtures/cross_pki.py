"""A cross-signed PKI for tests: Root A, Root B, B cross-certified by A, Int B, a leaf.

The cross certificate carries Root B's subject and key under Root A's signature,
so the leaf validates against either root alone given the matching intermediates.
"""
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def pem(cert):
    """PEM text of a certificate."""
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def key_pem(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


def new_key(kind='ec'):
    return rsa.generate_private_key(65537, 2048) if kind == 'rsa' else ec.generate_private_key(ec.SECP256R1())


def make_cert(subject_cn, subject_key, issuer_cn=None, issuer_key=None, *, ca=True, days=365,
              path_length=None, san=None, not_before=None):
    """A certificate for *subject_key*; self-signed unless an issuer is given."""
    now = datetime.now(timezone.utc)
    signer = issuer_key or subject_key
    builder = (x509.CertificateBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject_cn)]))
               .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_cn or subject_cn)]))
               .public_key(subject_key.public_key())
               .serial_number(x509.random_serial_number())
               .not_valid_before(not_before or now - timedelta(days=1))
               .not_valid_after(now + timedelta(days=days))
               .add_extension(x509.BasicConstraints(ca=ca, path_length=path_length if ca else None), critical=True)
               .add_extension(x509.SubjectKeyIdentifier.from_public_key(subject_key.public_key()), critical=False)
               .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(signer.public_key()),
                              critical=False))
    if ca:
        builder = builder.add_extension(
            x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
    else:
        builder = builder.add_extension(
            x509.KeyUsage(True, False, False, False, False, False, False, False, False), critical=True)
        builder = builder.add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
    if san:
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(san)]), critical=False)
    return builder.sign(signer, hashes.SHA256())


@dataclass
class CrossPKI:
    tag: str
    key_a: object
    key_b: object
    key_int: object
    key_leaf: object
    root_a: x509.Certificate
    root_b: x509.Certificate
    cross_b: x509.Certificate
    int_b: x509.Certificate
    leaf: x509.Certificate

    @property
    def name_a(self):
        return f'Cross Root A {self.tag}'

    @property
    def name_b(self):
        return f'Cross Root B {self.tag}'


def build_cross_pki(kind='ec', tag=None, cross_days=365):
    """Root A, Root B, the cross certificate of B by A, Int B (under B) and a leaf (under Int B)."""
    tag = tag or uuid.uuid4().hex[:8]
    key_a, key_b, key_int, key_leaf = (new_key(kind) for _ in range(4))
    name_a, name_b, name_int = f'Cross Root A {tag}', f'Cross Root B {tag}', f'Cross Int B {tag}'
    return CrossPKI(
        tag=tag, key_a=key_a, key_b=key_b, key_int=key_int, key_leaf=key_leaf,
        root_a=make_cert(name_a, key_a),
        root_b=make_cert(name_b, key_b),
        cross_b=make_cert(name_b, key_b, name_a, key_a, days=cross_days),
        int_b=make_cert(name_int, key_int, name_b, key_b, days=300, path_length=0),
        leaf=make_cert(f'leaf-{tag}.example', key_leaf, name_int, key_int, ca=False, days=90,
                       san=f'leaf-{tag}.example'),
    )


def openssl_verify(leaf, trusted, untrusted=()):
    """Run `openssl verify`: (ok, output). Only *trusted* are anchors, the system store is ignored."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / 'leaf.pem').write_text(leaf if isinstance(leaf, str) else pem(leaf))
        (tmp / 'trusted.pem').write_text(''.join(c if isinstance(c, str) else pem(c) for c in trusted))
        cmd = ['openssl', 'verify', '-no-CApath', '-no-CAstore', '-CAfile', str(tmp / 'trusted.pem')]
        if untrusted:
            (tmp / 'untrusted.pem').write_text(''.join(c if isinstance(c, str) else pem(c) for c in untrusted))
            cmd += ['-untrusted', str(tmp / 'untrusted.pem')]
        done = subprocess.run(cmd + [str(tmp / 'leaf.pem')], capture_output=True, text=True, timeout=30)
        return done.returncode == 0, (done.stdout + done.stderr).strip()

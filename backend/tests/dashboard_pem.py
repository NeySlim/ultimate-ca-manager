"""Real certificates for the dashboard tests, as base64 PEM the way rows store them."""
import base64
import datetime
import subprocess
import tempfile
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.x509.oid import NameOID


def self_signed(key, algorithm=hashes.SHA256(), cn='dashboard.test', days=30):
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.datetime.now(datetime.timezone.utc)
    if isinstance(key, ed25519.Ed25519PrivateKey):
        algorithm = None
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=days))
            .sign(key, algorithm))
    return base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode()


def sha1_rsa(cn='sha1.dashboard.test'):
    """cryptography refuses to sign with SHA-1, so openssl makes it."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / 'c.pem'
        result = subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                                 '-keyout', str(Path(tmp) / 'k.pem'), '-out', str(out), '-sha1',
                                 '-subj', f'/CN={cn}', '-days', '30'], capture_output=True)
        if result.returncode != 0:
            pytest.skip('openssl cannot produce a SHA-1 certificate here')
        return base64.b64encode(out.read_bytes()).decode()

"""SSH wire verification independent of SSHCertificateBuilder and its verifier."""
import base64
import struct
import uuid
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa, utils

from models import db
from models.hsm import HsmKey, HsmProvider
from models.ssh import SSHCertificate, SSHCertificateAuthority
from services.hsm import HsmService
from services.hsm.base_provider import HsmConnectionError
from services.ssh_ca_service import SSHCAService
from services.ssh_cert import SSHCertificateService
from tests.test_hsm_sync_and_listing import needs_softhsm, softhsm_token  # noqa: F401


def spki(key):
    return key.public_key().public_bytes(serialization.Encoding.PEM,
                                        serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def ssh_public(key):
    return key.public_key().public_bytes(serialization.Encoding.OpenSSH,
                                        serialization.PublicFormat.OpenSSH).decode()


class SoftwareToken:
    ECDSA_SIGNATURE_FORMAT = 'raw'

    def __init__(self, key):
        self.key = key
        self.fixed_hash = None
        self.offline = False
        self.calls = []

    def __enter__(self):
        if self.offline:
            raise HsmConnectionError('Test token unavailable')
        return self

    def __exit__(self, *exc):
        return False

    def hash_for_key(self, identifier, algorithm, requested):
        return self.fixed_hash or requested

    def sign(self, identifier, data, algorithm=None, hash_algorithm=None):
        digest = {'sha256': hashes.SHA256, 'sha384': hashes.SHA384,
                  'sha512': hashes.SHA512}[self.fixed_hash or hash_algorithm]()
        self.calls.append((data, hash_algorithm))
        if isinstance(self.key, rsa.RSAPrivateKey):
            return self.key.sign(data, padding.PKCS1v15(), digest)
        signature = self.key.sign(data, ec.ECDSA(digest))
        r, s = utils.decode_dss_signature(signature)
        size = (self.key.curve.key_size + 7) // 8
        return r.to_bytes(size, 'big') + s.to_bytes(size, 'big')


@pytest.fixture
def token(app, monkeypatch):
    ids = []
    with app.app_context():
        def make(key, algorithm):
            provider = HsmProvider(name=f'ssh-binding-{uuid.uuid4().hex}', type='pkcs11', config='{}')
            db.session.add(provider)
            db.session.flush()
            row = HsmKey(provider_id=provider.id, key_identifier='01', label='SSH signer',
                         algorithm=algorithm, key_type='asymmetric', purpose='signing',
                         public_key_pem=spki(key))
            db.session.add(row)
            db.session.commit()
            ids.append((provider.id, row.id))
            fake = SoftwareToken(key)
            monkeypatch.setattr(HsmService, '_get_provider_instance', lambda *a: fake)
            return row, fake
        yield make
        db.session.rollback()
        for pid, kid in ids:
            ca_ids = db.select(SSHCertificateAuthority.id).where(SSHCertificateAuthority.hsm_key_id == kid)
            SSHCertificate.query.filter(SSHCertificate.ssh_ca_id.in_(ca_ids)).delete(synchronize_session=False)
            SSHCertificateAuthority.query.filter_by(hsm_key_id=kid).delete(synchronize_session=False)
            HsmKey.query.filter_by(id=kid).delete(synchronize_session=False)
            HsmProvider.query.filter_by(id=pid).delete(synchronize_session=False)
            HsmService.forget_signing_hash(kid)
        db.session.commit()


def create(row, role='user'):
    return SSHCAService.import_hsm_ca(descr='Bound token CA', ca_type=role,
                                     hsm_key_id=row.id, allow_any_principal=True)


def issue(ca, subject=None):
    return SSHCertificateService.sign_certificate(
        ca.id, ssh_public(subject or ec.generate_private_key(ec.SECP256R1())), ca.ca_type,
        ['alice'] if ca.ca_type == 'user' else ['server.example.test'])


class Wire:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def fixed(self, size):
        value = self.data[self.pos:self.pos + size]
        assert len(value) == size
        self.pos += size
        return value

    def string(self):
        size, = struct.unpack('>I', self.fixed(4))
        return self.fixed(size)

    def mpint(self):
        value = self.string()
        assert value and not value[0] & 128
        if len(value) > 1 and value[0] == 0:
            assert value[1] & 128
        return int.from_bytes(value, 'big')

    def end(self):
        assert self.pos == len(self.data)


def verify_wire(certificate, published_key, public):
    wire = Wire(base64.b64decode(certificate.split()[1], validate=True))
    cert_type = wire.string()
    wire.string()  # nonce
    if cert_type.startswith(b'ssh-rsa-'):
        wire.mpint()
        wire.mpint()
    elif cert_type.startswith(b'ecdsa-sha2-'):
        wire.string()
        wire.string()
    else:
        assert cert_type == b'ssh-ed25519-cert-v01@openssh.com'
        assert len(wire.string()) == 32
    wire.fixed(12)  # serial and certificate type
    wire.string()  # key id
    wire.string()  # principals
    wire.fixed(16)  # validity
    for _ in range(3):
        wire.string()  # critical options, extensions, reserved
    anchor = wire.string()
    assert anchor == base64.b64decode(published_key.split()[1])
    signed = wire.data[:wire.pos]
    signature = Wire(wire.string())
    wire.end()
    label, blob = signature.string(), signature.string()
    signature.end()
    if isinstance(public, rsa.RSAPublicKey):
        assert label == b'rsa-sha2-512'
        public.verify(blob, signed, padding.PKCS1v15(), hashes.SHA512())
    else:
        name, digest = {256: (b'nistp256', hashes.SHA256()),
                        384: (b'nistp384', hashes.SHA384()),
                        521: (b'nistp521', hashes.SHA512())}[public.curve.key_size]
        assert label == b'ecdsa-sha2-' + name
        pair = Wire(blob)
        r, s = pair.mpint(), pair.mpint()
        pair.end()
        public.verify(utils.encode_dss_signature(r, s), signed, ec.ECDSA(digest))


KEYS = [('RSA-2048', lambda: rsa.generate_private_key(65537, 2048)),
        ('EC-P256', lambda: ec.generate_private_key(ec.SECP256R1())),
        ('EC-P384', lambda: ec.generate_private_key(ec.SECP384R1())),
        ('EC-P521', lambda: ec.generate_private_key(ec.SECP521R1()))]


@pytest.mark.parametrize('algorithm,generate', KEYS)
@pytest.mark.parametrize('role', ['user', 'host'])
@pytest.mark.parametrize('subject', ['rsa', 'ec', 'ed25519'])
def test_issued_certificate_wire_verifies_independently(token, algorithm, generate, role, subject):
    row, fake = token(generate(), algorithm)
    ca = create(row, role)
    key = {'rsa': lambda: rsa.generate_private_key(65537, 2048),
           'ec': lambda: ec.generate_private_key(ec.SECP256R1()),
           'ed25519': ed25519.Ed25519PrivateKey.generate}[subject]()
    certificate = issue(ca, key)
    verify_wire(certificate.certificate, ca.public_key, fake.key.public_key())


@pytest.mark.parametrize('algorithm,generate', KEYS)
def test_creation_proves_possession_with_ssh_digest(token, algorithm, generate):
    row, fake = token(generate(), algorithm)
    create(row)
    expected = {'RSA-2048': 'sha512', 'EC-P256': 'sha256',
                'EC-P384': 'sha384', 'EC-P521': 'sha512'}[algorithm]
    assert len(fake.calls) == 1
    assert fake.calls[0][1] == expected


@pytest.mark.parametrize('algorithm,generate', KEYS)
@pytest.mark.parametrize('failure', ['offline', 'different-key', 'wrong-digest', 'lying-digest'])
def test_creation_cannot_trust_cached_pem_without_a_working_signer(
        token, failure, monkeypatch, algorithm, generate):
    row, fake = token(generate(), algorithm)
    if failure == 'offline':
        fake.offline = True
    elif failure == 'different-key':
        fake.key = generate()
    else:
        fake.fixed_hash = 'sha384' if algorithm == 'EC-P256' else 'sha256'
        if failure == 'lying-digest':
            monkeypatch.setattr(fake, 'hash_for_key', lambda i, a, r: r)
    with pytest.raises((ValueError, HsmConnectionError)):
        create(row)
    assert SSHCertificateAuthority.query.filter_by(hsm_key_id=row.id).count() == 0
    if failure == 'wrong-digest':
        assert fake.calls == [], 'A declared incompatible digest is refused before signing'


@pytest.mark.parametrize('algorithm,generate', KEYS)
def test_issuance_rejects_rotated_token_with_stale_cache(token, algorithm, generate):
    row, fake = token(generate(), algorithm)
    ca = create(row)
    anchor = ca.public_key
    fake.key = generate()
    with pytest.raises(ValueError, match='signature.*verif'):
        issue(ca)
    assert SSHCertificate.query.filter_by(ssh_ca_id=ca.id).count() == 0
    assert ca.public_key == anchor


def test_loading_refuses_rotation_after_sync_without_changing_anchor(token):
    row, fake = token(ec.generate_private_key(ec.SECP256R1()), 'EC-P256')
    ca = create(row)
    anchor = ca.public_key
    fake.key = ec.generate_private_key(ec.SECP256R1())
    row.public_key_pem = spki(fake.key)
    db.session.commit()
    with pytest.raises(ValueError, match='token key.*published key'):
        SSHCAService.get_private_key_object(ca.id)
    with pytest.raises(ValueError, match='token key.*published key'):
        issue(ca)
    assert ca.public_key == anchor
    assert ca.serial_counter == 0
    assert SSHCertificate.query.filter_by(ssh_ca_id=ca.id).count() == 0


def test_loading_checks_fingerprint_as_well_as_public_key(token):
    row, _ = token(ec.generate_private_key(ec.SECP256R1()), 'EC-P256')
    ca = create(row)
    ca.fingerprint = 'SHA256:wrong'
    db.session.commit()
    with pytest.raises(ValueError, match='published key'):
        SSHCAService.get_private_key_object(ca.id)


def test_postsign_check_uses_published_anchor_not_envelope(token, monkeypatch):
    row, _ = token(ec.generate_private_key(ec.SECP256R1()), 'EC-P256')
    ca = create(row)
    other = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setattr(SSHCAService, 'get_private_key_object', lambda i: other)
    with pytest.raises(ValueError, match='published key'):
        issue(ca)
    assert SSHCertificate.query.filter_by(ssh_ca_id=ca.id).count() == 0


def test_rsa_fixed_sha256_signature_is_never_recorded_as_sha512(token):
    row, fake = token(rsa.generate_private_key(65537, 2048), 'RSA-2048')
    ca = create(row)
    fake.fixed_hash = 'sha256'
    with pytest.raises(ValueError, match='signature.*verif'):
        issue(ca)
    assert SSHCertificate.query.filter_by(ssh_ca_id=ca.id).count() == 0
    # The existing allocator commits before signing; this serial cannot be reclaimed safely.
    assert ca.serial_counter == 1


def test_gcp_sign_ignores_requested_hash_and_is_rejected_at_issuance(token, monkeypatch):
    pytest.importorskip('google.cloud.kms_v1')
    from services.hsm.gcp_provider import GcpKmsProvider
    key = rsa.generate_private_key(65537, 2048)
    row, _ = token(key, 'RSA-2048')
    ca = create(row)
    provider = GcpKmsProvider.__new__(GcpKmsProvider)
    provider._client = SimpleNamespace(
        get_crypto_key=lambda **kw: SimpleNamespace(primary=SimpleNamespace(name='version/1')),
        get_crypto_key_version=lambda **kw: SimpleNamespace(algorithm='RSA_SIGN_PKCS1_2048_SHA256'),
        asymmetric_sign=lambda **kw: SimpleNamespace(signature=key.sign(
            kw['digest']['sha256'], padding.PKCS1v15(), utils.Prehashed(hashes.SHA256()))))
    monkeypatch.setattr(provider, 'connect', lambda: True)
    monkeypatch.setattr(provider, 'disconnect', lambda: None)
    monkeypatch.setattr(HsmService, '_get_provider_instance', lambda *a: provider)
    with pytest.raises(ValueError, match='signature.*verif'):
        issue(ca)
    assert SSHCertificate.query.filter_by(ssh_ca_id=ca.id).count() == 0


@needs_softhsm
@pytest.mark.parametrize('algorithm,generate', KEYS)
def test_real_token_ssh_certificate_verifies_independently(token, monkeypatch, softhsm_token, algorithm, generate):
    from services.hsm.pkcs11_provider import Pkcs11Provider
    with Pkcs11Provider(softhsm_token) as provider:
        info = provider.generate_key(f'ssh-wire-{algorithm}', algorithm)
    try:
        row, _ = token(generate(), algorithm)
        row.key_identifier, row.public_key_pem = info.key_identifier, info.public_key_pem
        db.session.commit()
        monkeypatch.setattr(HsmService, '_get_provider_instance', lambda *a: Pkcs11Provider(softhsm_token))
        ca = create(row)
        certificate = issue(ca)
        verify_wire(certificate.certificate, ca.public_key,
                    serialization.load_pem_public_key(info.public_key_pem.encode()))
    finally:
        with Pkcs11Provider(softhsm_token) as provider:
            provider.delete_key(info.key_identifier)


def test_ed25519_refusal_identifies_wrapper_limitation(token):
    row, _ = token(ed25519.Ed25519PrivateKey.generate(), 'ED25519')
    with pytest.raises(ValueError, match='HSM.*wrapper'):
        create(row)

"""The English help on SSH CA algorithms states what the backend does with each HSM key type.

Each key type goes through the HSM wrapper loader and SSHCAService.import_hsm_ca: accepted,
refused by the wrappers (no HSM signing), or wrapped but refused by the OpenSSH format.
"""
import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, mldsa, padding, rsa

from models import db
from models.hsm import HsmKey, HsmProvider
from models.ssh import SSHCertificateAuthority

FRONTEND = Path(__file__).resolve().parents[2] / 'frontend' / 'src' / 'data'

# Name used by the help -> a key of that type
KEY_TYPES = {
    'RSA': lambda: rsa.generate_private_key(public_exponent=65537, key_size=2048),
    'P-256': lambda: ec.generate_private_key(ec.SECP256R1()),
    'P-384': lambda: ec.generate_private_key(ec.SECP384R1()),
    'P-521': lambda: ec.generate_private_key(ec.SECP521R1()),
    'Brainpool': lambda: ec.generate_private_key(ec.BrainpoolP256R1()),
    'ML-DSA': lambda: mldsa.MLDSA65PrivateKey.generate(),
    'Ed25519': lambda: ed25519.Ed25519PrivateKey.generate(),
}


def _signer(real):
    def sign(key_id, data, algo=None, hash_algorithm=None):
        digest = {'sha384': hashes.SHA384, 'sha512': hashes.SHA512}.get(hash_algorithm, hashes.SHA256)()
        if isinstance(real, rsa.RSAPrivateKey):
            return real.sign(data, padding.PKCS1v15(), digest)
        return real.sign(data, ec.ECDSA(digest))
    return sign


def _outcome(app, name, make):
    """'accepted', 'no_hsm_signing' (the wrapper loader refuses it) or 'no_openssh_type'."""
    from services.hsm.hsm_private_key import load_hsm_private_key
    from services.ssh_ca_service import SSHCAService

    real = make()
    pem = real.public_key().public_bytes(serialization.Encoding.PEM,
                                         serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    with app.app_context(), patch('services.hsm.HsmService.get_public_key', return_value=pem), \
            patch('services.hsm.HsmService.sign', side_effect=_signer(real)):
        provider = HsmProvider(name=f'ssh-algo-{name}', type='pkcs11', config=json.dumps({}))
        db.session.add(provider)
        db.session.commit()
        key = HsmKey(provider_id=provider.id, key_identifier=f'ssh-algo-{name}', label=f'ssh-algo-{name}',
                     algorithm='RSA-2048', key_type='asymmetric', purpose='signing', public_key_pem=pem)
        db.session.add(key)
        db.session.commit()
        try:
            try:
                load_hsm_private_key(key.id)
            except ValueError:
                return 'no_hsm_signing'
            try:
                SSHCAService.import_hsm_ca(descr=f'ssh-algo-{name}', ca_type='user', hsm_key_id=key.id)
                return 'accepted'
            except ValueError as e:
                db.session.rollback()
                assert 'OpenSSH' in str(e), e
                return 'no_openssh_type'
        finally:
            SSHCertificateAuthority.query.filter_by(hsm_key_id=key.id).delete()
            db.session.delete(db.session.get(HsmKey, key.id))
            db.session.delete(db.session.get(HsmProvider, provider.id))
            db.session.commit()


def _named(clause):
    return {n for n in KEY_TYPES if n in clause}


def _check(text, backend):
    """The first sentence names the accepted types, the 'not cover' clause the types without HSM
    signing, the 'no key type' clause those OpenSSH certificates cannot carry."""
    by = {kind: {n for n, k in backend.items() if k == kind}
          for kind in ('accepted', 'no_hsm_signing', 'no_openssh_type')}
    first, rest = text.split('. ', 1)
    sentences = rest.split('. ')
    no_signing = [s for s in sentences if 'does not cover' in s]
    no_type = [s for s in sentences if 'no key type' in s]
    assert len(no_signing) == 1 and len(no_type) == 1, text
    assert _named(first) == by['accepted'], (first, by)
    assert _named(no_signing[0]) == by['no_hsm_signing'], (no_signing, by)
    assert _named(no_type[0]) == by['no_openssh_type'], (no_type, by)


@pytest.fixture(scope='module')
def backend(app):
    return {name: _outcome(app, name, make) for name, make in KEY_TYPES.items()}


def test_the_backend_splits_the_key_types_as_the_help_says(backend):
    assert set(backend.values()) == {'accepted', 'no_hsm_signing', 'no_openssh_type'}, backend


def test_the_help_panel_names_both_reasons(backend):
    source = (FRONTEND / 'helpContent.js').read_text(encoding='utf-8')
    section = source[source.index("title: 'HSM-backed SSH CAs'"):]
    text = re.search(r"label: 'Algorithms', text: '((?:[^'\\]|\\.)*)'", section).group(1).replace("\\'", "'")
    _check(text, backend)


def test_the_guide_names_both_reasons(backend):
    source = (FRONTEND / 'helpGuides.js').read_text(encoding='utf-8')
    section = source[source.index('### On an HSM key'):]
    bullet = re.search(r'Good to know:\n- (.*)\n', section).group(1)
    _check(bullet, backend)

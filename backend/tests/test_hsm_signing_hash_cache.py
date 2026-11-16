"""Provider round trips of HsmService.signing_hash: cached per SPKI, asked each time without one."""
import uuid

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from models import db
from models.hsm import HsmKey, HsmProvider
from services.hsm import HsmService
from services.hsm.hsm_private_key import load_hsm_private_key

SIGNATURES = 20


class _CountingProvider:
    def __init__(self, pem):
        self.pem = pem
        self.hash_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_public_key(self, key_identifier):
        return self.pem

    def hash_for_key(self, key_identifier, algorithm, requested):
        self.hash_calls += 1
        return 'sha384'


@pytest.fixture
def counted_key(app, monkeypatch):
    created = []
    with app.app_context():
        def make(stored_pem, published_pem):
            provider = HsmProvider(name=f'count-{uuid.uuid4().hex}', type='pkcs11', config='{}')
            db.session.add(provider)
            db.session.flush()
            row = HsmKey(provider_id=provider.id, key_identifier='01', label='counted',
                         algorithm='EC-P384', key_type='asymmetric', purpose='signing',
                         public_key_pem=stored_pem)
            db.session.add(row)
            db.session.commit()
            created.append((provider.id, row.id))
            fake = _CountingProvider(published_pem)
            monkeypatch.setattr(HsmService, '_get_provider_instance', lambda *a: fake)
            return row, fake
        yield make
        db.session.rollback()
        for pid, kid in created:
            HsmService.forget_signing_hash(kid)
            HsmKey.query.filter_by(id=kid).delete(synchronize_session=False)
            HsmProvider.query.filter_by(id=pid).delete(synchronize_session=False)
        db.session.commit()


def _pem():
    return ec.generate_private_key(ec.SECP384R1()).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def test_a_readable_spki_asks_the_provider_once(counted_key):
    row, fake = counted_key(_pem(), None)
    for _ in range(SIGNATURES):
        assert HsmService.signing_hash(row.id, None, 'sha256') == 'sha384'
    assert fake.hash_calls == 1


def test_a_key_without_spki_asks_the_provider_each_time(counted_key):
    # Nothing identifies its key material, so no answer may outlive a rotation
    row, fake = counted_key(None, None)
    for _ in range(SIGNATURES):
        assert HsmService.signing_hash(row.id, None, 'sha256') == 'sha384'
    assert fake.hash_calls == SIGNATURES


def test_a_wrapper_caches_the_spki_it_loads_so_one_round_trip_suffices(counted_key):
    row, fake = counted_key(None, _pem())
    wrapper = load_hsm_private_key(row.id)
    for _ in range(SIGNATURES):
        assert wrapper.signing_hash(hashes.SHA256()).name == 'sha384'
    assert fake.hash_calls == 1

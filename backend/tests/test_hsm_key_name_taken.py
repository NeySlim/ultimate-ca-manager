"""A new HSM key never takes over a name the HSM holds, and a CA that fails takes its new key with it."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from models import CA, db
from models.hsm import HsmKey, HsmProvider
from services.hsm import azure_provider
from services.hsm.base_provider import HsmKeyExistsError, HsmKeyInfo, HsmOperationError


def _azure(found):
    missing = pytest.importorskip('azure.core.exceptions').ResourceNotFoundError
    provider = azure_provider.AzureKeyVaultProvider({'vault_url': 'https://v.vault.azure.net/'})
    provider._key_client = MagicMock()
    if not found:
        provider._key_client.get_key.side_effect = missing('no such key')
    return provider


@pytest.mark.parametrize('algorithm', ['RSA-2048', 'EC-P256'])
def test_azure_refuses_a_name_it_holds_and_adds_no_version(algorithm):
    provider = _azure(found=True)
    with pytest.raises(HsmKeyExistsError):
        provider.generate_key('taken', algorithm)
    provider._key_client.create_rsa_key.assert_not_called()
    provider._key_client.create_ec_key.assert_not_called()


def test_azure_names_a_soft_deleted_key():
    exceptions = pytest.importorskip('azure.core.exceptions')
    provider = _azure(found=False)
    provider._key_client.create_ec_key.side_effect = exceptions.ResourceExistsError('soft deleted')
    with pytest.raises(HsmKeyExistsError, match='deleted'):
        provider.generate_key('held', 'EC-P256')


def test_azure_creates_a_free_name():
    provider = _azure(found=False)
    with patch.object(provider, '_export_public_key', return_value='pem'):
        info = provider.generate_key('free', 'EC-P256')
    provider._key_client.create_ec_key.assert_called_once()
    assert info.label == 'free'


class _Fake:
    """Generates a real key; refuses to sign when told to, as a token without sign rights does."""

    def __init__(self, exists=False, public_key=True):
        self.exists, self.public_key, self.deleted = exists, public_key, []
        self.key = ec.generate_private_key(ec.SECP256R1())

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def generate_key(self, label, algorithm, purpose='signing', extractable=False):
        if self.exists:
            raise HsmKeyExistsError(f'Key already exists: {label}')
        pem = self.key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        return HsmKeyInfo(key_identifier=label, label=label, algorithm=algorithm,
                          key_type='asymmetric', purpose=purpose,
                          public_key_pem=pem if self.public_key else None)

    def hash_for_key(self, key_identifier, key_algorithm, requested='sha256'):
        return requested

    def sign(self, *args, **kwargs):
        raise HsmOperationError('permission denied')

    def delete_key(self, key_identifier):
        self.deleted.append(key_identifier)
        return True


@pytest.fixture
def hsm_provider(app):
    with app.app_context():
        provider = HsmProvider(name=f'Fake {id(object())}', type='openbao', config='{}')
        db.session.add(provider)
        db.session.commit()
        provider_id = provider.id
    yield provider_id
    with app.app_context():
        db.session.rollback()
        HsmKey.query.filter_by(provider_id=provider_id).delete()
        HsmProvider.query.filter_by(id=provider_id).delete()
        db.session.commit()


def _ca_body(provider_id, label, kind='root'):
    return {'type': kind, 'commonName': label, 'organization': 'T', 'country': 'US',
            'keyAlgo': 'EC', 'curve': 'P-256', 'validityYears': 1, 'hashAlgorithm': 'sha256',
            'hsm_provider_id': provider_id, 'hsm_key_label': label, 'hsm_key_algorithm': 'EC-P256'}


def test_a_taken_name_answers_409_with_the_reason(app, auth_client, hsm_provider):
    fake = _Fake(exists=True)
    with patch('services.hsm.HsmService._get_provider_instance', return_value=fake):
        key = auth_client.post(f'/api/v2/hsm/providers/{hsm_provider}/keys',
                               json={'label': 'taken', 'algorithm': 'EC-P256', 'purpose': 'signing'})
        ca = auth_client.post('/api/v2/cas', json=_ca_body(hsm_provider, 'taken'))
    assert key.status_code == 409 and 'already exists' in key.get_json()['message']
    assert ca.status_code == 409 and 'already exists' in ca.get_json()['message']
    with app.app_context():
        assert not HsmKey.query.filter_by(provider_id=hsm_provider).count()


@pytest.mark.parametrize('kind', ['root', 'external'])
def test_a_ca_whose_signature_fails_removes_its_new_key(app, auth_client, hsm_provider, kind):
    fake = _Fake()
    with patch('services.hsm.HsmService._get_provider_instance', return_value=fake):
        r = auth_client.post('/api/v2/cas', json=_ca_body(hsm_provider, 'unsigned-ca', kind))
    assert r.status_code == 500, r.data
    assert fake.deleted == ['unsigned-ca']
    with app.app_context():
        assert not HsmKey.query.filter_by(provider_id=hsm_provider).count()


@pytest.mark.parametrize('kind', ['root', 'external'])
def test_a_ca_that_cannot_be_stored_removes_its_new_key(app, auth_client, hsm_provider, kind):
    fake = _Fake()
    fake.sign = lambda key_identifier, data, *a, **k: fake.key.sign(data, ec.ECDSA(hashes.SHA256()))
    real_commit = db.session.commit

    def refuse_the_ca():
        if any(isinstance(row, CA) for row in db.session.new):
            raise RuntimeError('database gone')
        real_commit()

    with patch('services.hsm.HsmService._get_provider_instance', return_value=fake), \
            patch.object(db.session, 'commit', side_effect=refuse_the_ca):
        r = auth_client.post('/api/v2/cas', json=_ca_body(hsm_provider, 'unstored-ca', kind))
    assert r.status_code == 500, r.data
    assert fake.deleted == ['unstored-ca']
    with app.app_context():
        assert not HsmKey.query.filter_by(provider_id=hsm_provider).count()
        assert not CA.query.filter_by(descr='unstored-ca').count()


@pytest.mark.parametrize('kind', ['root', 'external'])
def test_a_new_key_that_cannot_be_loaded_is_removed(app, auth_client, hsm_provider, kind):
    fake = _Fake(public_key=False)
    with patch('services.hsm.HsmService._get_provider_instance', return_value=fake):
        r = auth_client.post('/api/v2/cas', json=_ca_body(hsm_provider, 'unloaded-ca', kind))
    assert r.status_code >= 400, r.data
    assert fake.deleted == ['unloaded-ca']
    with app.app_context():
        assert not HsmKey.query.filter_by(provider_id=hsm_provider).count()


def test_an_existing_key_survives_a_failed_ca(app, auth_client, hsm_provider):
    fake = _Fake()
    with patch('services.hsm.HsmService._get_provider_instance', return_value=fake):
        made = auth_client.post(f'/api/v2/hsm/providers/{hsm_provider}/keys',
                                json={'label': 'kept', 'algorithm': 'EC-P256', 'purpose': 'signing'})
        assert made.status_code == 201, made.data
        body = _ca_body(hsm_provider, 'kept-ca')
        for field in ('hsm_provider_id', 'hsm_key_label', 'hsm_key_algorithm'):
            body.pop(field)
        r = auth_client.post('/api/v2/cas', json={**body, 'hsm_key_id': made.get_json()['data']['id']})
    assert r.status_code == 500, r.data
    assert fake.deleted == []
    with app.app_context():
        assert HsmKey.query.filter_by(provider_id=hsm_provider).count() == 1


@pytest.mark.parametrize('value', ['false', 0, None, []])
def test_extractable_must_be_a_boolean(app, auth_client, hsm_provider, value):
    fake = _Fake()
    with patch('services.hsm.HsmService._get_provider_instance', return_value=fake):
        r = auth_client.post(f'/api/v2/hsm/providers/{hsm_provider}/keys', json={
            'label': 'text-switch', 'algorithm': 'EC-P256', 'purpose': 'signing', 'extractable': value})
    assert r.status_code == 400 and 'extractable' in r.get_json()['message']
    with app.app_context():
        assert not HsmKey.query.filter_by(provider_id=hsm_provider).count()


def test_a_key_whose_ca_was_stored_after_all_is_kept(app, auth_client, hsm_provider):
    # The commit went through and only its answer was lost: the CA holds the key
    fake = _Fake()
    fake.sign = lambda key_identifier, data, *a, **k: fake.key.sign(data, ec.ECDSA(hashes.SHA256()))
    real_commit = db.session.commit

    def commit_then_lose_the_answer():
        lost = any(isinstance(row, CA) for row in db.session.new)
        real_commit()
        if lost:
            raise RuntimeError('connection lost')

    with patch('services.hsm.HsmService._get_provider_instance', return_value=fake), \
            patch.object(db.session, 'commit', side_effect=commit_then_lose_the_answer):
        r = auth_client.post('/api/v2/cas', json=_ca_body(hsm_provider, 'stored-ca'))
    assert r.status_code == 500, r.data
    assert fake.deleted == []
    with app.app_context():
        ca = CA.query.filter_by(descr='stored-ca').one()
        try:
            assert ca.hsm_key_id == HsmKey.query.filter_by(provider_id=hsm_provider).one().id
        finally:
            db.session.delete(ca)
            db.session.commit()


def test_a_failed_rollback_does_not_hide_the_original_error(app):
    from services.ca.ca_creation import _discarding_new_hsm_key
    with app.app_context():
        with patch.object(db.session, 'rollback', side_effect=RuntimeError('database gone')), \
                pytest.raises(ValueError, match='the real reason'):
            with _discarding_new_hsm_key(1, SimpleNamespace(id=999999)):
                raise ValueError('the real reason')

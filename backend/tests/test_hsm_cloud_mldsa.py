"""ML-DSA on the cloud providers. Google Cloud KMS signs PQ_SIGN_ML_DSA_* versions over
the data itself and serves their public key in NIST_PQC form (mapped, not tested
against the real service). Azure Key Vault has no ML-DSA: every path says so."""
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import mldsa

from services.hsm.base_provider import HsmOperationError
from utils import key_algorithms

pytestmark = pytest.mark.skipif(not key_algorithms.mldsa_supported(), reason='this build has no ML-DSA')

LEVELS = {'ML-DSA-44': mldsa.MLDSA44PrivateKey, 'ML-DSA-65': mldsa.MLDSA65PrivateKey,
          'ML-DSA-87': mldsa.MLDSA87PrivateKey}


def _gcp():
    try:
        from google.cloud.kms_v1 import types
        from services.hsm import gcp_provider
    except ImportError:
        pytest.skip('google-cloud-kms not installed')
    if not gcp_provider.GCP_AVAILABLE:
        pytest.skip('google-cloud-kms not installed')
    return gcp_provider, types


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _KmsClient:
    """The KMS calls the provider makes, answered for one ML-DSA key version."""

    def __init__(self, types, label):
        self.key = LEVELS[label].generate()
        self.algorithm = getattr(types.CryptoKeyVersion.CryptoKeyVersionAlgorithm,
                                 f"PQ_SIGN_{label.replace('-', '_')}")
        self.version = _Obj(name='k/cryptoKeyVersions/1', algorithm=self.algorithm)
        self.calls = []

    def get_crypto_key(self, name):
        return _Obj(name=name, primary=self.version)

    def get_crypto_key_version(self, name):
        return self.version

    def get_public_key(self, request=None, name=None):
        self.calls.append(('get_public_key', request or {'name': name}))
        from google.cloud.kms_v1 import types
        if (request or {}).get('public_key_format') != types.PublicKey.PublicKeyFormat.NIST_PQC:
            raise ValueError('PEM is not served for a post-quantum key version')
        return _Obj(pem='', public_key=_Obj(data=self.key.public_key().public_bytes_raw()))

    def asymmetric_sign(self, name, digest=None, data=None):
        self.calls.append(('asymmetric_sign', digest, data))
        if digest is not None:
            raise ValueError('ML-DSA versions sign data, not a digest')
        return _Obj(signature=self.key.sign(data))


def _gcp_provider(label):
    gcp_provider, types = _gcp()
    provider = object.__new__(gcp_provider.GcpKmsProvider)
    provider._client = _KmsClient(types, label)
    return provider


@pytest.mark.parametrize('label', sorted(LEVELS))
def test_gcp_maps_ml_dsa_both_ways(label):
    gcp_provider, types = _gcp()
    algorithm = getattr(types.CryptoKeyVersion.CryptoKeyVersionAlgorithm, f"PQ_SIGN_{label.replace('-', '_')}")
    assert gcp_provider.ALGORITHM_TO_GCP[label] == algorithm
    assert gcp_provider.GCP_ALGORITHM_NAMES[algorithm] == label


@pytest.mark.parametrize('label', sorted(LEVELS))
def test_gcp_signs_the_data_itself(label):
    provider = _gcp_provider(label)
    signature = provider.sign('k', b'tbs certificate', label)
    provider._client.key.public_key().verify(signature, b'tbs certificate')
    assert provider._client.calls == [('asymmetric_sign', None, b'tbs certificate')]


def test_gcp_names_no_digest_for_an_ml_dsa_version():
    provider = _gcp_provider('ML-DSA-65')
    assert provider._digest_of_version(provider._client.version) is None


def test_gcp_refuses_a_version_that_names_no_digest_it_knows():
    gcp_provider, types = _gcp()
    raw = _Obj(algorithm=types.CryptoKeyVersion.CryptoKeyVersionAlgorithm.RSA_SIGN_RAW_PKCS1_2048)
    with pytest.raises(HsmOperationError, match='RSA_SIGN_RAW_PKCS1_2048'):
        gcp_provider.GcpKmsProvider._digest_of_version(raw)


@pytest.mark.parametrize('label', sorted(LEVELS))
def test_gcp_public_key_is_asked_in_nist_form_and_returned_as_spki(label):
    provider = _gcp_provider(label)
    pem = provider.get_public_key('k')
    public = serialization.load_pem_public_key(pem.encode())
    assert key_algorithms.label_for_public_key(public) == label
    assert public == provider._client.key.public_key()


def test_gcp_ml_dsa_refuses_a_digest():
    provider = _gcp_provider('ML-DSA-65')
    with pytest.raises(HsmOperationError, match='ML-DSA'):
        provider.sign('k', b'tbs', 'ML-DSA-65', hash_algorithm='sha256')
    assert provider._client.calls == []


def test_gcp_ml_dsa_signs_data_up_to_the_kms_cap():
    gcp_provider, _types = _gcp()
    provider = _gcp_provider('ML-DSA-65')
    data = b'\x30' * gcp_provider.KMS_SIGN_DATA_MAX
    provider._client.key.public_key().verify(provider.sign('k', data, 'ML-DSA-65'), data)


def test_gcp_ml_dsa_refuses_data_over_the_kms_cap_before_the_call():
    gcp_provider, _types = _gcp()
    assert gcp_provider.KMS_SIGN_DATA_MAX == 64 * 1024
    provider = _gcp_provider('ML-DSA-65')
    with pytest.raises(HsmOperationError, match='64 KiB'):
        provider.sign('k', b'\x30' * (gcp_provider.KMS_SIGN_DATA_MAX + 1), 'ML-DSA-65')
    assert [call for call in provider._client.calls if call[0] == 'asymmetric_sign'] == []


# ---- Azure Key Vault --------------------------------------------------------------

def test_the_service_says_which_providers_hold_ml_dsa():
    import services.hsm  # noqa: F401  registers the providers
    from services.hsm import HsmService
    message = HsmService.mldsa_refusal('azure-keyvault', 'ML-DSA-65')
    assert 'ML-DSA' in message and 'azure-keyvault' in message and 'not available' in message
    assert HsmService.mldsa_refusal('azure-keyvault', 'EC-P256') is None
    assert HsmService.mldsa_refusal('pkcs11', 'ML-DSA-65') is None
    assert HsmService.mldsa_refusal('openbao', 'ML-DSA-87') is None


@pytest.mark.parametrize('provider_type, library', [
    ('google-kms', 'google-cloud-kms 3.11.0'), ('pkcs11', 'python-pkcs11 0.9.5')])
def test_a_client_library_too_old_is_named_not_the_type(monkeypatch, provider_type, library):
    import services.hsm  # noqa: F401
    from services.hsm import HsmService
    provider_class = HsmService._provider_registry.get(provider_type)
    if provider_class is None:
        pytest.skip(f'{provider_type} not registered')
    monkeypatch.setattr(provider_class, 'SIGNS_ML_DSA', False)
    for message in (HsmService.mldsa_refusal(provider_type, 'ML-DSA-65'),
                    _refusal_of(object.__new__(provider_class), 'ML-DSA-65')):
        assert 'ML-DSA keys are not available' in message and library in message
        assert 'needs a PKCS#11 3.2 token' not in message


@pytest.mark.parametrize('provider_type', ['google-kms', 'pkcs11'])
def test_the_library_named_is_the_floor_requirements_install(provider_type):
    import pathlib
    import services.hsm  # noqa: F401
    from services.hsm import HsmService
    provider_class = HsmService._provider_registry.get(provider_type)
    if provider_class is None:
        pytest.skip(f'{provider_type} not registered')
    package, version = provider_class.ML_DSA_LIBRARY.split()
    requirements = (pathlib.Path(__file__).parents[1] / 'requirements.txt').read_text().split()
    assert f'{package}>={version}' in requirements


def _refusal_of(provider, algorithm):
    with pytest.raises(HsmOperationError) as raised:
        provider.refuse_unsupported_algorithm(algorithm)
    return str(raised.value)


def test_the_azure_provider_itself_refuses_with_the_same_words():
    try:
        from services.hsm.azure_provider import AzureKeyVaultProvider
    except ImportError:
        pytest.skip('Azure SDK not installed')
    import services.hsm  # noqa: F401
    provider = object.__new__(AzureKeyVaultProvider)
    with pytest.raises(HsmOperationError, match="ML-DSA keys are not available with provider type 'azure-keyvault'"):
        provider.generate_key('pq', 'ML-DSA-65')


def _provider_row(app, type_name):
    from models import db
    from models.hsm import HsmProvider
    with app.app_context():
        row = HsmProvider(name=f'pq-refuse-{type_name}', type=type_name, config='{}')
        db.session.add(row)
        db.session.commit()
        return row.id


def _drop(app, provider_id):
    from models import db
    from models.hsm import HsmKey, HsmProvider
    with app.app_context():
        db.session.query(HsmKey).filter_by(provider_id=provider_id).delete()
        db.session.query(HsmProvider).filter_by(id=provider_id).delete()
        db.session.commit()


def test_key_generation_api_refuses_ml_dsa_on_azure(app, auth_client):
    pid = _provider_row(app, 'azure-keyvault')
    try:
        resp = auth_client.post(f'/api/v2/hsm/providers/{pid}/keys', json={
            'label': 'pq', 'algorithm': 'ML-DSA-65', 'purpose': 'signing'})
        assert resp.status_code == 400, resp.get_json()
        assert 'ML-DSA keys are not available' in resp.get_data(as_text=True)
    finally:
        _drop(app, pid)


def test_key_generation_api_says_the_build_lacks_ml_dsa(app, auth_client, monkeypatch):
    import services.hsm  # noqa: F401
    from services.hsm import HsmService
    if 'pkcs11' not in HsmService._provider_registry:
        pytest.skip('python-pkcs11 not installed')
    pid = _provider_row(app, 'pkcs11')
    monkeypatch.setattr(key_algorithms, 'mldsa_supported', lambda: False)
    key_algorithms._load()
    try:
        resp = auth_client.post(f'/api/v2/hsm/providers/{pid}/keys', json={
            'label': 'pq', 'algorithm': 'ML-DSA-65', 'purpose': 'signing'})
        assert resp.status_code == 400, resp.get_json()
        assert 'not available on this build' in resp.get_data(as_text=True)
    finally:
        monkeypatch.undo()
        key_algorithms._load()
        _drop(app, pid)


def test_ca_creation_refuses_a_new_ml_dsa_key_on_azure(app, auth_client):
    pid = _provider_row(app, 'azure-keyvault')
    try:
        resp = auth_client.post('/api/v2/cas', json={
            'type': 'root', 'commonName': 'pq-azure.test', 'organization': 'T',
            'hsm_provider_id': pid, 'hsm_key_label': 'pq', 'hsm_key_algorithm': 'ML-DSA-65'})
        assert resp.status_code == 400, resp.get_json()
        assert 'ML-DSA keys are not available' in resp.get_data(as_text=True)
    finally:
        _drop(app, pid)

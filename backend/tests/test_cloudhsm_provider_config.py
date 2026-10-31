"""AWS CloudHSM: the crypto user logs in through PKCS#11 with the PIN "<user>:<password>"."""
import json

import pytest

pytest.importorskip('pkcs11')

from models.hsm import HsmProvider
from services.hsm.pkcs11_provider import Pkcs11Provider


@pytest.fixture
def module(tmp_path):
    lib = tmp_path / 'libcloudhsm_pkcs11.so'
    lib.write_bytes(b'')
    return str(lib)


def test_crypto_user_and_password_become_the_pin(module):
    provider = Pkcs11Provider({'module_path': module, 'token_label': 'hsm1',
                               'hsm_user': 'cu', 'hsm_password': 'Secret:1'})
    assert provider.user_pin == 'cu:Secret:1'


def test_an_explicit_pin_is_kept(module):
    provider = Pkcs11Provider({'module_path': module, 'token_label': 't',
                               'user_pin': '1234', 'hsm_user': 'cu', 'hsm_password': 'x'})
    assert provider.user_pin == '1234'


def test_the_form_reads_back_the_token_label_and_module():
    row = HsmProvider(name='c', type='aws-cloudhsm', config=json.dumps({
        'module_path': '/opt/cloudhsm/lib/libcloudhsm_pkcs11.so', 'token_label': 'hsm1',
        'hsm_user': 'cu', 'cluster_id': 'cluster-1'}))
    data = row.to_dict(include_config=True)
    assert data['pkcs11_token_label'] == 'hsm1'
    assert data['pkcs11_library_path'] == '/opt/cloudhsm/lib/libcloudhsm_pkcs11.so'
    assert data['aws_crypto_user'] == 'cu'


# ---- algorithms: AWS CloudHSM holds neither Brainpool nor ML-DSA ------------------

def _registry():
    import services.hsm  # noqa: F401  registers the providers
    from services.hsm import HsmService
    if 'aws-cloudhsm' not in HsmService._provider_registry:
        pytest.skip('python-pkcs11 not installed')
    return HsmService


@pytest.mark.parametrize('algorithm, family', [('EC-BP256', 'Brainpool'), ('ML-DSA-65', 'ML-DSA')])
def test_the_service_refuses_brainpool_and_ml_dsa_on_cloudhsm(algorithm, family):
    service = _registry()
    message = service.algorithm_refusal('aws-cloudhsm', algorithm)
    assert message and family in message and "'aws-cloudhsm'" in message
    assert service.algorithm_refusal('aws-cloudhsm', 'EC-P256') is None
    assert service.algorithm_refusal('pkcs11', 'EC-BP256') is None


def test_the_generic_pkcs11_type_keeps_its_own_name():
    service = _registry()
    assert service._provider_registry['pkcs11'].PROVIDER_TYPE == 'pkcs11'
    assert service._provider_registry['aws-cloudhsm'].PROVIDER_TYPE == 'aws-cloudhsm'


def test_the_cloudhsm_provider_refuses_brainpool_before_touching_the_token():
    from services.hsm.base_provider import HsmOperationError
    provider = object.__new__(_registry()._provider_registry['aws-cloudhsm'])
    provider._session = None
    with pytest.raises(HsmOperationError,
                       match="Brainpool key EC-BP384 is not supported by provider type 'aws-cloudhsm'"):
        provider.generate_key('bp', 'EC-BP384')


@pytest.fixture
def cloudhsm_row(app):
    from models import db
    from models.hsm import HsmKey
    with app.app_context():
        row = HsmProvider(name='cloudhsm-algorithms', type='aws-cloudhsm', config='{}')
        db.session.add(row)
        db.session.commit()
        provider_id = row.id
    yield provider_id
    with app.app_context():
        db.session.rollback()
        db.session.query(HsmKey).filter_by(provider_id=provider_id).delete()
        db.session.query(HsmProvider).filter_by(id=provider_id).delete()
        db.session.commit()


@pytest.mark.parametrize('algorithm, family', [('EC-BP512', 'Brainpool'), ('ML-DSA-87', 'ML-DSA')])
def test_key_generation_api_refuses_them_on_cloudhsm(auth_client, cloudhsm_row, algorithm, family):
    _registry()
    from utils import key_algorithms
    if family == 'ML-DSA' and not key_algorithms.mldsa_supported():
        pytest.skip('this build has no ML-DSA')
    resp = auth_client.post(f'/api/v2/hsm/providers/{cloudhsm_row}/keys', json={
        'label': 'cloudhsm-refused', 'algorithm': algorithm, 'purpose': 'signing'})
    body = resp.get_data(as_text=True)
    assert resp.status_code == 400, body
    assert family in body and 'aws-cloudhsm' in body

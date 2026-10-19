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

"""The ACME client's certificate key types are the ones its forms offer.

`contracts/acme_client_key_types.json` is the list;
`frontend/src/lib/__tests__/acmeClientKeyTypes.test.js` holds the forms to it.
"""
import json
import os

import pytest

import fips_mode
from services.acme.acme_client_service import CERT_KEY_TYPES, fips_key_type_refusal
from utils import key_algorithms

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
with open(os.path.join(_REPO, 'contracts', 'acme_client_key_types.json')) as _fh:
    _ROWS = json.load(_fh)['cert_key_types']


def test_the_server_accepts_the_contract_types_in_its_order():
    expected = [r['label'] for r in _ROWS if key_algorithms.mldsa_supported() or not r['ml_dsa']]
    assert list(CERT_KEY_TYPES) == expected


@pytest.mark.parametrize('row', _ROWS, ids=lambda r: r['label'])
def test_fips_mode_keeps_what_the_contract_says(row, monkeypatch):
    if row['ml_dsa'] and not key_algorithms.mldsa_supported():
        pytest.skip('this build has no ML-DSA')
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    if row['fips'] is not None:
        assert (fips_key_type_refusal(row['label']) is None) is row['fips']
        return
    # Decided by the loaded module: kept where it approves the algorithm, refused elsewhere
    for approves in (True, False):
        monkeypatch.setattr(fips_mode, 'module_approves', lambda alg, a=approves: a)
        assert (fips_key_type_refusal(row['label']) is None) is approves

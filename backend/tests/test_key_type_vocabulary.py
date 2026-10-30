"""The key types a policy may allow are the ones a template may ask for.

`services/template_service.TEMPLATE_KEY_TYPES` accepts RSA-2048/3072/4096 and
EC-P256/384/521; `utils/key_type.RSA_SIZES` generates all three RSA sizes.
`frontend/src/pages/PoliciesPage.jsx` once offered five of the six, with
**RSA-3072 missing**, so an RSA-3072 template could be created and then refused
at issuance by a policy, with no option on the policy screen to permit it.

The screens now read one registry, `frontend/src/lib/keyAlgorithms.js`, which
is checked here against the backend registry and its parsers: the screen that
chooses a key type and the screen that permits one cannot drift apart.

The vocabularies for a CA (`prime256v1`) and for SSH (`ed25519`) are
deliberately different and are not in scope here; see the class at the end.
"""
import json
import os
import shutil
import subprocess

import pytest

from services.template_service import TEMPLATE_KEY_TYPES
from utils import key_algorithms
from utils.ca_profile import default_digest_for_key_type
from utils.key_type import parse_csr_key_type, parse_issue_key_type

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REGISTRY = os.path.join(_REPO, 'frontend', 'src', 'lib', 'keyAlgorithms.js')

# The labels a template stores; legacy spellings (`rsa:2048`, `ec:p256`) are
# accepted on input and stored as these.
CANONICAL = set(TEMPLATE_KEY_TYPES)
SCREEN_SET = CANONICAL


@pytest.fixture(scope='module')
def js_registry():
    """The frontend registry, evaluated by node (it has no imports)."""
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    out = subprocess.run(
        [node, '--input-type=module', '-e',
         f"import {{ KEY_ALGORITHMS }} from {json.dumps('file://' + REGISTRY)};"
         'console.log(JSON.stringify(KEY_ALGORITHMS))'],
        capture_output=True, text=True, timeout=60, check=True)
    return json.loads(out.stdout)


def _generated(rows):
    return [r for r in rows if r['generate']]


class TestTheScreensOfferWhatTheApiAccepts:
    def test_the_canonical_set_is_the_six_plus_brainpool(self):
        assert CANONICAL == {'RSA-2048', 'RSA-3072', 'RSA-4096',
                             'EC-P256', 'EC-P384', 'EC-P521',
                             'EC-BP256', 'EC-BP384', 'EC-BP512'}

    def test_the_registry_the_screens_read_offers_all_of_them(self, js_registry):
        offered = {r['label'] for r in _generated(js_registry)}
        assert offered == SCREEN_SET, (
            f'the screens offer {sorted(offered)} where the API '
            f'accepts {sorted(SCREEN_SET)}; a key type a template can ask for '
            'and a policy cannot permit is refused with no way to allow it')

    def test_each_row_matches_the_backend_registry(self, js_registry):
        for row in js_registry:
            backend = key_algorithms.get(row['label'])
            assert backend is not None, row['label']
            if backend.needs_digest:
                # the digest 'auto' resolves to when a CA is created
                assert row['digest'] == default_digest_for_key_type(backend.trust_store_id), row['label']
            else:
                assert row['digest'] is None, row['label']
            assert row['fips'] == backend.fips_approved, row['label']
            assert row['securityLevel'] == backend.security_level, row['label']

    def test_both_registries_list_the_same_keys_in_the_same_order(self, js_registry):
        assert [r['label'] for r in js_registry] == list(key_algorithms.labels())

    def test_mldsa_is_read_and_policed_but_not_yet_generated(self, js_registry):
        pq = [r for r in js_registry if r['family'] == 'ML-DSA']
        assert [r['label'] for r in pq] == ['ML-DSA-44', 'ML-DSA-65', 'ML-DSA-87']
        for row in pq:
            assert (row['group'], row['bits'], row['digest'], row['generate']) == ('pq', None, None, False)
            assert row['issue'] is row['ca'] is row['csr'] is row['providers'] is None

    def test_each_form_value_parses_to_the_same_key(self, js_registry):
        for row in _generated(js_registry):
            expected = key_algorithms.get(row['label']).trust_store_id
            assert parse_issue_key_type(*row['issue']) == expected, row['label']
            assert parse_csr_key_type(row['csr']) == expected, row['label']
            if row['ca'][0] == 'ECDSA':
                assert parse_issue_key_type('ecdsa', row['ca'][1]) == expected, row['label']
            else:
                assert row['ca'][1] == expected, row['label']


class TestTheOtherVocabulariesAreLeftAlone:
    """Not every difference is drift.

    A CA is created with the OpenSSL curve names (`prime256v1`) because that
    is what the key generator takes, and SSH has `ed25519`, which X.509
    issuance cannot generate at all. Those are different questions with
    different answers, and collapsing them would be the mistake.
    """

    def test_ssh_has_a_vocabulary_of_its_own(self):
        from models.ssh import SSHCertificateAuthority  # noqa: F401
        from api.v2.ssh_certificates import _VALID_KEY_TYPES as ssh_types
        assert 'ed25519' in ssh_types
        assert 'ed25519' not in CANONICAL

    def test_x509_issuance_still_cannot_generate_an_edwards_key(self):
        from utils.key_type import parse_issue_key_type
        with pytest.raises(ValueError):
            parse_issue_key_type('ed25519')

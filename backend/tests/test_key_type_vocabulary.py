"""The key types a policy may allow are the ones a template may ask for.

`api/v2/templates._VALID_KEY_TYPES` accepts RSA-2048/3072/4096 and
EC-P256/384/521; `utils/key_type.RSA_SIZES` generates all three RSA sizes.
`frontend/src/pages/PoliciesPage.jsx` offered five of the six, with
**RSA-3072 missing**, and seeded a new policy's `allowed_key_types` with four
of them. So an RSA-3072 template could be created and then refused at
issuance by a policy, with no option on the policy screen to permit it.

`TemplatesPage.jsx` offers the six and is checked here too, so the screen
that chooses a key type and the screen that permits one cannot drift apart.

The vocabularies for a CA (`prime256v1`) and for SSH (`ed25519`) are
deliberately different and are not in scope here; see the class at the end.
"""
import os
import re

import pytest

from api.v2.templates import _VALID_KEY_TYPES

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
POLICIES = os.path.join(_REPO, 'frontend', 'src', 'pages', 'PoliciesPage.jsx')
TEMPLATES = os.path.join(_REPO, 'frontend', 'src', 'pages', 'TemplatesPage.jsx')

# The canonical spelling the template API documents; the same file also
# accepts the legacy `rsa:2048` / `ec:p256` forms for older clients.
CANONICAL = {name for name in _VALID_KEY_TYPES if '-' in name}


def _js_array(path, name):
    source = open(path, encoding='utf-8').read()
    match = re.search(rf'const {name}\s*=\s*\[(.*?)\n\]', source, re.S)
    assert match, f'no {name} array in {os.path.basename(path)}'
    return match.group(1)


class TestTheScreensOfferWhatTheApiAccepts:
    def test_the_canonical_set_is_the_six(self):
        assert CANONICAL == {'RSA-2048', 'RSA-3072', 'RSA-4096',
                             'EC-P256', 'EC-P384', 'EC-P521'}

    def test_the_template_screen_offers_all_of_them(self):
        body = _js_array(TEMPLATES, 'KEY_TYPE_OPTIONS')
        offered = set(re.findall(r"'([A-Z][^']*)'", body))
        assert offered == CANONICAL, (
            f'the template editor offers {sorted(offered)} where the API '
            f'accepts {sorted(CANONICAL)}')

    def test_the_policy_screen_offers_all_of_them(self):
        body = _js_array(POLICIES, 'KEY_TYPE_OPTIONS')
        offered = set(re.findall(r"value: '([^']+)'", body))
        assert offered == CANONICAL, (
            f'the policy editor offers {sorted(offered)} where the API '
            f'accepts {sorted(CANONICAL)}; a key type a template can ask for '
            'and a policy cannot permit is refused with no way to allow it')

    def test_a_new_policy_permits_everything_the_api_accepts(self):
        source = open(POLICIES, encoding='utf-8').read()
        match = re.search(r'allowed_key_types:\s*(.+)', source)
        assert match, 'no allowed_key_types default in the policy screen'
        line = match.group(1)
        if 'KEY_TYPE_OPTIONS' in line or line.strip().rstrip(',') == '[]':
            return      # seeded from the list itself, or empty: no restriction
        seeded = set(re.findall(r"'([^']+)'", line))
        assert seeded == CANONICAL, (
            f'a new policy is seeded permitting {sorted(seeded)}, so an '
            f'{sorted(CANONICAL - seeded)} certificate is refused by the '
            'default policy')


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

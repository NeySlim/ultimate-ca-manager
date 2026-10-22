"""Key generators folded into the key registry behave as the copies they replace.

Each ``_old_*`` helper below is the removed implementation, kept verbatim as
the reference: same valid input, same key type/size/curve; same refusal.
"""
import base64
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed448, ed25519, rsa

from utils import key_algorithms
from utils.key_type import (RSA_SIZES, _EC_COLLAPSED_ALIASES, parse_csr_key_type,
                            parse_issue_key_type)


def _shape(key):
    """What a refactor must preserve: algorithm class plus size or curve."""
    if isinstance(key, rsa.RSAPrivateKey):
        return ('rsa', key.key_size, key.public_key().public_numbers().e)
    if isinstance(key, ec.EllipticCurvePrivateKey):
        return ('ec', key.curve.name)
    return (type(key).__name__,)


# Every id parse_issue_key_type / parse_csr_key_type can return.
ISSUE_KEY_IDS = sorted(RSA_SIZES | set(_EC_COLLAPSED_ALIASES.values()))


# ---------------------------------------------------------------------------
# cert_create.py / policies.py: EC_CURVES cascade
# ---------------------------------------------------------------------------

def _old_issue_cascade(normalized_key):
    EC_CURVES = {
        'prime256v1': ec.SECP256R1(),
        'secp384r1': ec.SECP384R1(),
        'secp521r1': ec.SECP521R1(),
        'brainpoolP256r1': ec.BrainpoolP256R1(),
        'brainpoolP384r1': ec.BrainpoolP384R1(),
        'brainpoolP512r1': ec.BrainpoolP512R1(),
    }
    if normalized_key in EC_CURVES:
        return ec.generate_private_key(EC_CURVES[normalized_key])
    return rsa.generate_private_key(65537, int(normalized_key))


@pytest.mark.parametrize('normalized', ISSUE_KEY_IDS)
def test_issue_cascade_and_registry_generate_the_same_key(normalized):
    assert _shape(key_algorithms.generate(normalized)) == _shape(_old_issue_cascade(normalized))


@pytest.mark.parametrize('args,kwargs', [
    (('rsa', '2048'), {}), (('RSA', 'rsa 3072'), {}), (('rsa', 4096), {}),
    (('ec', '256'), {}), (('ecdsa', 'P-384'), {}), (('ec', '2048'), {'curve': 'secp521r1'}),
    (('EC P-256', None), {}), (('RSA 4096', None), {}),
])
def test_issue_inputs_reach_the_registry(args, kwargs):
    normalized = parse_issue_key_type(*args, **kwargs)
    assert _shape(key_algorithms.generate(normalized)) == _shape(_old_issue_cascade(normalized))


@pytest.mark.parametrize('args', [('rsa', '1024'), ('rsa', '8192'), ('ec', '3072'),
                                  ('ec', 'secp256k1'), ('dsa', '2048')])
def test_issue_refusals_happen_before_generation(args):
    with pytest.raises(ValueError):
        parse_issue_key_type(*args)


# ---------------------------------------------------------------------------
# services/tsa_signer_cert.py: _generate_key
# ---------------------------------------------------------------------------

def _old_tsa_generate_key(key_type, key_size, curve):
    from services.tsa_signer_cert import (DEFAULT_KEY_SIZE, DEFAULT_KEY_TYPE,
                                          TsaSignerIssueError)
    try:
        normalized = parse_issue_key_type(key_type or DEFAULT_KEY_TYPE,
                                          key_size or DEFAULT_KEY_SIZE, curve=curve)
    except ValueError as exc:
        raise TsaSignerIssueError(str(exc), 400)
    return _old_issue_cascade(normalized)


TSA_VALID = [
    (None, None, None), ('rsa', None, None), ('rsa', '2048', None), ('RSA', 4096, None),
    ('ec', None, 'P-256'), ('ec', '384', None), ('ecdsa', 'secp521r1', None),
    ('ec', '', 'prime256v1'), ('EC P-384', None, None), (None, '3072', None),
]
TSA_INVALID = [
    ('rsa', '1024', None), ('rsa', 'big', None), ('dsa', None, None),
    ('ec', 'P-192', None), ('ec', None, 'secp256k1'), ('', '512', None),
]
TSA_EC_WITHOUT_CURVE = [('ec', None, None), ('EC', '', None), ('ecdsa', 0, ''),
                        (' Ec ', None, None)]


@pytest.mark.parametrize('key_type,key_size,curve', TSA_VALID)
def test_tsa_valid_inputs_give_the_same_key(key_type, key_size, curve):
    from services.tsa_signer_cert import _generate_key
    assert _shape(_generate_key(key_type, key_size, curve)) == \
        _shape(_old_tsa_generate_key(key_type, key_size, curve))


@pytest.mark.parametrize('key_type,key_size,curve', TSA_INVALID)
def test_tsa_invalid_inputs_give_the_same_refusal(key_type, key_size, curve):
    from services.tsa_signer_cert import TsaSignerIssueError, _generate_key
    with pytest.raises(TsaSignerIssueError) as old:
        _old_tsa_generate_key(key_type, key_size, curve)
    with pytest.raises(TsaSignerIssueError) as new:
        _generate_key(key_type, key_size, curve)
    assert (new.value.message, new.value.status) == (old.value.message, old.value.status)


@pytest.mark.parametrize('key_type,key_size,curve', TSA_EC_WITHOUT_CURVE)
def test_tsa_ec_without_curve_is_still_refused_with_a_clear_message(key_type, key_size, curve):
    from services.tsa_signer_cert import TsaSignerIssueError, _generate_key
    with pytest.raises(TsaSignerIssueError):
        _old_tsa_generate_key(key_type, key_size, curve)
    with pytest.raises(TsaSignerIssueError) as new:
        _generate_key(key_type, key_size, curve)
    assert new.value.status == 400
    assert 'needs a curve' in new.value.message


# ---------------------------------------------------------------------------
# api/v2/acme/accounts.py: account key and JWK
# ---------------------------------------------------------------------------

def _old_account_key_and_jwk(key_type):
    def _b64url(data):
        return base64.urlsafe_b64encode(data).rstrip(b'=').decode()
    if key_type.startswith('EC'):
        curve_map = {'EC-P256': ec.SECP256R1(), 'EC-P384': ec.SECP384R1()}
        curve = curve_map.get(key_type, ec.SECP256R1())
        private_key = ec.generate_private_key(curve)
        numbers = private_key.public_key().public_numbers()
        crv = 'P-256' if isinstance(curve, ec.SECP256R1) else 'P-384'
        byte_len = 32 if crv == 'P-256' else 48
        return private_key, {'kty': 'EC', 'crv': crv,
                             'x': _b64url(numbers.x.to_bytes(byte_len, 'big')),
                             'y': _b64url(numbers.y.to_bytes(byte_len, 'big'))}
    key_size = int(key_type.replace('RSA-', '')) if 'RSA-' in key_type else 2048
    private_key = rsa.generate_private_key(65537, key_size)
    numbers = private_key.public_key().public_numbers()
    return private_key, {'kty': 'RSA',
                         'e': _b64url(numbers.e.to_bytes(3, 'big')),
                         'n': _b64url(numbers.n.to_bytes(key_size // 8, 'big'))}


def _old_jwk_of(key_type, private_key):
    """The old JWK formula, applied to a given key instead of a fresh one."""
    numbers = private_key.public_key().public_numbers()
    b = lambda v, n: base64.urlsafe_b64encode(v.to_bytes(n, 'big')).rstrip(b'=').decode()
    if key_type.startswith('EC'):
        crv = 'P-384' if key_type == 'EC-P384' else 'P-256'
        n = 48 if crv == 'P-384' else 32
        return {'kty': 'EC', 'crv': crv, 'x': b(numbers.x, n), 'y': b(numbers.y, n)}
    size = int(key_type.replace('RSA-', ''))
    return {'kty': 'RSA', 'e': b(numbers.e, 3), 'n': b(numbers.n, size // 8)}


def _cert_key_types():
    from services.acme.acme_client_service import CERT_KEY_TYPES
    return sorted(CERT_KEY_TYPES)


@pytest.mark.parametrize('key_type', _cert_key_types())
def test_account_key_and_jwk_match_the_old_route(key_type):
    from api.v2.acme.accounts import _public_jwk
    new_key = key_algorithms.generate(key_type)
    old_key, _ = _old_account_key_and_jwk(key_type)
    assert _shape(new_key) == _shape(old_key)
    assert _public_jwk(new_key) == _old_jwk_of(key_type, new_key)


@pytest.mark.parametrize('make', [ed25519.Ed25519PrivateKey.generate,
                                  lambda: ec.generate_private_key(ec.SECP256K1())])
def test_account_jwk_refuses_a_key_it_cannot_describe(make):
    from api.v2.acme.accounts import _public_jwk
    with pytest.raises(ValueError):
        _public_jwk(make())


@pytest.mark.parametrize('key_type', _cert_key_types())
def test_account_route_stores_a_jwk_of_the_stored_key(auth_client, app, key_type):
    from api.v2.acme.accounts import _public_jwk
    from models import SystemConfig
    from models.acme_models import AcmeAccount
    from security.encryption import decrypt_text

    email = f'dedup-{key_type}@example.test'
    r = auth_client.post('/api/v2/acme/accounts', data=json.dumps({
        'email': email, 'key_type': key_type, 'agree_tos': True,
    }), content_type='application/json')
    assert r.status_code in (200, 201)
    with app.app_context():
        account = AcmeAccount.query.filter(AcmeAccount.contact.like(f'%{email}%')).first()
        row = SystemConfig.query.filter_by(
            key=f'acme.account.{account.account_id}.private_key').first()
        key = serialization.load_pem_private_key(decrypt_text(row.value).encode(), None)
        jwk = json.loads(account.jwk)
    assert key_algorithms.label_for_private_key(key) == key_type
    assert jwk == _public_jwk(key) == _old_jwk_of(key_type, key)


# ---------------------------------------------------------------------------
# services/cert/mixins/csr.py: _csr_key_type_label
# ---------------------------------------------------------------------------

def _old_csr_key_type_label(public_key):
    if isinstance(public_key, rsa.RSAPublicKey):
        return str(public_key.key_size)
    if isinstance(public_key, ec.EllipticCurvePublicKey):
        return public_key.curve.name
    if isinstance(public_key, ed25519.Ed25519PublicKey):
        return 'ed25519'
    if isinstance(public_key, ed448.Ed448PublicKey):
        return 'ed448'
    return None


# Every key sign_csr lets through to the override computation (2560: an
# unregistered RSA size inside the accepted 2048..8192 range).
CSR_KEYS = [
    lambda: rsa.generate_private_key(65537, 2048),
    lambda: rsa.generate_private_key(65537, 2560),
    lambda: rsa.generate_private_key(65537, 3072),
    lambda: rsa.generate_private_key(65537, 4096),
    lambda: ec.generate_private_key(ec.SECP256R1()),
    lambda: ec.generate_private_key(ec.SECP384R1()),
    lambda: ec.generate_private_key(ec.SECP521R1()),
    ed25519.Ed25519PrivateKey.generate,
    ed448.Ed448PrivateKey.generate,
]


@pytest.mark.parametrize('make', CSR_KEYS)
def test_csr_label_compares_the_same_against_any_template(make):
    from services.policy_service import key_label_for_public_key
    from services.template_service import _normalize_key_type_label, compute_template_overrides
    from utils.key_type import validate_enrollment_public_key

    public_key = make().public_key()
    assert validate_enrollment_public_key(public_key) is None
    assert _normalize_key_type_label(key_label_for_public_key(public_key)) == \
        _normalize_key_type_label(_old_csr_key_type_label(public_key))

    class _Template:
        validity_days = None
        digest = None

    for tpl_key in (*key_algorithms.labels(), 'RSA-2560', 'rsa:2048', None):
        _Template.key_type = tpl_key
        assert compute_template_overrides(_Template, key_type=key_label_for_public_key(public_key)) \
            == compute_template_overrides(_Template, key_type=_old_csr_key_type_label(public_key))


def test_curves_where_the_labels_differ_never_reach_the_override():
    """Off-registry curves would label differently, but sign_csr refuses them first."""
    from utils.key_type import validate_enrollment_public_key
    key = ec.generate_private_key(ec.SECP256K1()).public_key()
    assert validate_enrollment_public_key(key) is not None


# ---------------------------------------------------------------------------
# services/trust_store/constants.py: KEY_TYPES
# ---------------------------------------------------------------------------

def test_key_types_no_longer_offer_weak_rsa():
    from services.trust_store.constants import KEY_TYPES
    from services.trust_store.key_operations_mixin import KeyOperationsMixin
    for size in ('512', '1024'):
        assert size not in KEY_TYPES
        with pytest.raises(ValueError, match='Unsupported key type'):
            KeyOperationsMixin.generate_private_key(size)


def test_every_id_a_caller_sends_is_still_served():
    """Issue/CSR parsers, the CA allowlist and the MSCA rekey sizes all resolve."""
    from services.trust_store.constants import KEY_TYPES
    sent = set(ISSUE_KEY_IDS) | {parse_csr_key_type(v) for v in ('RSA 2048', 'EC P-521')}
    sent |= {'2048', '3072', '4096', 'prime256v1', 'secp384r1', 'secp521r1', '8192'}
    assert sent <= set(KEY_TYPES)
    assert KEY_TYPES['8192'] == ('rsa', 8192)
    assert key_algorithms.get('RSA-8192') is None  # why KEY_TYPES keeps its own row

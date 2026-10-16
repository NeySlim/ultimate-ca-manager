"""The key algorithm registry, and the three facades that now delegate to it.

`fixtures/key_algorithms_facades_truth.json` was produced from the code BEFORE the
registry existed: every facade must still give the same answer (value, or
exception type and message) for every input recorded there. Do not regenerate
it to make a test pass; edit the lines a deliberate behaviour change touches.
"""
import dataclasses
import json
import os
from functools import lru_cache

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import dsa, ec, ed448, ed25519, mldsa, rsa, x448, x25519
from cryptography.x509.oid import NameOID

import utils.key_type as kt
from services.policy_service import key_label_for_public_key
from services.template_service import _normalize_key_type_label
from services.trust_store.constants import KEY_TYPES
from utils import key_algorithms as ka
from utils.signing_hash import signing_hash_for

_TRUTH_PATH = os.path.join(os.path.dirname(__file__), 'fixtures','key_algorithms_facades_truth.json')
with open(_TRUTH_PATH, encoding='utf-8') as _fh:
    TRUTH = json.load(_fh)

LABELS = ['RSA-2048', 'RSA-3072', 'RSA-4096', 'EC-P256', 'EC-P384', 'EC-P521', 'ED25519', 'ED448']


@lru_cache(maxsize=None)
def build_key(spec):
    """Key object for a corpus spec; same construction as when the table was frozen."""
    if spec == 'none':
        return None
    private = spec.startswith('priv:')
    spec = spec.removeprefix('priv:')
    kind, _, param = spec.partition(':')
    if kind == 'rsa':
        sk = rsa.generate_private_key(public_exponent=65537, key_size=int(param))
    elif kind == 'ec':
        sk = ec.generate_private_key(ec._CURVE_TYPES[param])
    elif kind == 'dsa':
        sk = dsa.generate_private_key(key_size=int(param))
    else:
        sk = {'ed25519': ed25519.Ed25519PrivateKey, 'ed448': ed448.Ed448PrivateKey,
              'x25519': x25519.X25519PrivateKey, 'x448': x448.X448PrivateKey,
              'mldsa44': mldsa.MLDSA44PrivateKey, 'mldsa65': mldsa.MLDSA65PrivateKey,
              'mldsa87': mldsa.MLDSA87PrivateKey}[kind].generate()
    return sk if private else sk.public_key()


def _outcome(fn, *args, **kwargs):
    try:
        res = fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - the frozen table records any exception
        return {'raises': type(exc).__name__, 'msg': TRUTH['messages'].index(str(exc))
                if str(exc) in TRUTH['messages'] else str(exc)}
    return {'value': list(res) if isinstance(res, tuple) else res}


_FACADES = {
    'template_normalize': lambda v: _outcome(_normalize_key_type_label, v),
    'normalize_ec_curve': lambda v: _outcome(kt.normalize_ec_curve, v),
    'parse_csr_key_type': lambda v: _outcome(kt.parse_csr_key_type, v),
    'issue_key_type_from_template': lambda v: _outcome(kt.issue_key_type_from_template, v),
    'parse_issue_key_type': lambda a: _outcome(kt.parse_issue_key_type, a[0], a[1], curve=a[2]),
    'fill_key_params_from_template': lambda a: _outcome(kt.fill_key_params_from_template, *a),
    'policy_key_label': lambda s: _outcome(key_label_for_public_key, build_key(s)),
    'validate_enrollment_public_key': lambda s: _outcome(kt.validate_enrollment_public_key, build_key(s)),
}


class TestFacadesUnchanged:
    """Same outputs as before the registry, on the frozen corpus."""

    @pytest.mark.parametrize('section', sorted(_FACADES))
    def test_section_matches_frozen_outputs(self, section):
        rows = TRUTH[section]
        assert rows, section
        diverging = [(inp, want, got) for inp, want in rows
                     if (got := _FACADES[section](inp)) != want]
        assert diverging == [], f'{len(diverging)}/{len(rows)} diverge, first: {diverging[:5]}'

    def test_key_type_constants_unchanged(self):
        frozen = TRUTH['constants']
        assert sorted(kt.RSA_SIZES) == frozen['RSA_SIZES']
        assert isinstance(kt.RSA_SIZES, frozenset)
        assert sorted(kt._ALLOWED_EC_CURVES) == frozen['_ALLOWED_EC_CURVES']
        assert kt._EC_COLLAPSED_ALIASES == frozen['_EC_COLLAPSED_ALIASES']

    def test_corpus_covers_every_registered_label(self):
        inputs = {v for v, _ in TRUTH['template_normalize'] if isinstance(v, str)}
        assert set(LABELS) <= inputs


class TestRegistry:
    def test_table_is_the_classical_set(self):
        assert list(ka.labels()) == LABELS

    @pytest.mark.parametrize('label', LABELS)
    def test_generate_round_trips_through_both_key_lookups(self, label):
        sk = ka.generate(label)
        assert ka.label_for_private_key(sk) == label
        assert ka.label_for_public_key(sk.public_key()) == label

    @pytest.mark.parametrize('label', LABELS)
    def test_spellings_normalize_to_the_label(self, label):
        alg = ka.get(label)
        for spelling in (label, label.lower(), f' {label} ', alg.display, alg.legacy_key_algo,
                         alg.trust_store_id, *alg.curve_names, *alg.aliases):
            if spelling:
                assert ka.normalize_label(spelling) == label, spelling

    @pytest.mark.parametrize('label', LABELS)
    def test_parse_label_gives_family_and_param(self, label):
        alg = ka.get(label)
        assert ka.parse_label(label) == (alg.family, alg.param)
        expected = label if alg.param is None else f'{alg.family}-{alg.param}'
        assert expected == label

    @pytest.mark.parametrize('label', LABELS)
    def test_trust_store_id_generates_the_same_algorithm(self, label):
        alg = ka.get(label)
        if alg.trust_store_id is None:
            assert alg.family in ('ED25519', 'ED448')
            return
        algo, param = KEY_TYPES[alg.trust_store_id]
        if algo == 'rsa':
            assert alg.family == 'RSA' and param == alg.key_size
        else:
            assert alg.family == 'EC' and param.name in alg.curve_names

    @pytest.mark.parametrize('label', LABELS)
    def test_legacy_key_algo_is_what_renewal_writes(self, label):
        from services.cert.renewal import _key_algo_label
        assert _key_algo_label(ka.generate(label).public_key()) == ka.get(label).legacy_key_algo

    @pytest.mark.parametrize('label', LABELS)
    def test_needs_digest_matches_signing_hash_for(self, label):
        alg = ka.get(label)
        sk = ka.generate(label)
        assert (signing_hash_for(sk) is not None) == alg.needs_digest
        assert (alg.default_digest is None) == (not alg.needs_digest)
        # The default digest really signs with this key.
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'k')])
        digest = getattr(hashes, alg.default_digest.upper())() if alg.default_digest else None
        x509.CertificateSigningRequestBuilder().subject_name(name).sign(sk, digest)

    def test_fips_approved(self):
        assert ka.fips_approved_labels() == (
            'RSA-2048', 'RSA-3072', 'RSA-4096', 'EC-P256', 'EC-P384', 'EC-P521')
        assert ka.fips_approved('rsa:2048') and ka.fips_approved('prime256v1')
        assert not ka.fips_approved('ED25519')
        assert not ka.fips_approved('Ed448')
        assert not ka.fips_approved('RSA-1024')
        assert not ka.fips_approved(None)

    @pytest.mark.parametrize('value', [None, '', '  ', 'RSA-1024', 'secp256k1', 'EdDSA', 'ML-DSA-65', True, 1024])
    def test_unknown_is_none(self, value):
        assert ka.get(value) is None
        assert ka.normalize_label(value) is None
        assert ka.parse_label(value) is None
        assert ka.fips_approved(value) is False

    def test_generate_unknown_raises(self):
        with pytest.raises(ValueError):
            ka.generate('RSA-1024')

    @pytest.mark.parametrize('spec', ['rsa:1024', 'ec:secp256k1', 'x25519', 'dsa:1024', 'mldsa65', 'none'])
    def test_unregistered_keys_have_no_label(self, spec):
        assert ka.label_for_public_key(build_key(spec)) is None

    def test_private_key_is_not_a_public_key(self):
        assert ka.label_for_public_key(build_key('priv:rsa:2048')) is None
        assert ka.label_for_private_key(build_key('rsa:2048')) is None

    def test_family_for_public_key_ignores_size(self):
        assert ka.family_for_public_key(build_key('rsa:1024')) == 'RSA'
        assert ka.family_for_public_key(build_key('ec:secp256k1')) == 'EC'
        assert ka.family_for_public_key(build_key('x25519')) is None

    def test_label_for_curve_name_is_exact(self):
        assert ka.label_for_curve_name('PRIME256V1 ') == 'EC-P256'
        assert ka.label_for_curve_name('p256') is None
        assert ka.label_for_curve_name(None) is None

    def test_ambiguous_spelling_is_refused(self):
        twin = dataclasses.replace(ka.get('EC-P384'), label='EC-X', aliases=('P-256',))
        with pytest.raises(ValueError, match='names both'):
            ka._Registry(ka.ALGORITHMS + (twin,))


class TestRoomForNewFamilies:
    """A hyphenated family slots in as one more row, with no lookup cut at '-'."""

    @pytest.fixture
    def with_mldsa65(self, monkeypatch):
        entry = ka.KeyAlgorithm(
            label='ML-DSA-65', family='ML-DSA', param='65',
            private_class=mldsa.MLDSA65PrivateKey, public_class=mldsa.MLDSA65PublicKey,
            generator=mldsa.MLDSA65PrivateKey.generate, needs_digest=False, default_digest=None,
            display='ML-DSA-65', legacy_key_algo='ML-DSA-65', trust_store_id=None,
            fips_approved=False)
        monkeypatch.setattr(ka, '_REGISTRY', ka._Registry(ka.ALGORITHMS + (entry,)))

    def test_lookups(self, with_mldsa65):
        for spelling in ('ML-DSA-65', 'mldsa65', 'ml-dsa-65', 'ML_DSA 65'):
            assert ka.normalize_label(spelling) == 'ML-DSA-65'
        assert ka.parse_label('ML-DSA-65') == ('ML-DSA', '65')
        sk = ka.generate('ML-DSA-65')
        assert ka.label_for_private_key(sk) == 'ML-DSA-65'
        assert ka.label_for_public_key(sk.public_key()) == 'ML-DSA-65'
        assert ka.label_for_public_key(build_key('mldsa44')) is None
        assert ka.normalize_label('RSA-2048') == 'RSA-2048'

    def test_facades_pick_it_up(self, with_mldsa65):
        assert key_label_for_public_key(build_key('mldsa65')) == 'ML-DSA-65'
        assert _normalize_key_type_label('ml-dsa-65') == 'ML-DSA-65'


@pytest.mark.parametrize('make_key,expected', [
    (lambda: rsa.generate_private_key(public_exponent=65537, key_size=2048), 'RSA 2048'),
    (lambda: rsa.generate_private_key(public_exponent=65537, key_size=1024), 'RSA 1024'),
    (lambda: ec.generate_private_key(ec.SECP384R1()), 'EC secp384r1'),
    (lambda: ec.generate_private_key(ec.SECP256K1()), 'EC secp256k1'),
    (lambda: ed25519.Ed25519PrivateKey.generate(), 'Ed25519'),
    (lambda: ed448.Ed448PrivateKey.generate(), 'Ed448'),
])
def test_imported_and_renewed_certificates_store_one_spelling(make_key, expected):
    # Import wrote "EdDSA" where renewal wrote "Ed25519"/"Ed448"
    from services.cert.renewal import _key_algo_label
    public_key = make_key().public_key()
    assert ka.key_algo_for_public_key(public_key) == expected
    assert _key_algo_label(public_key) == expected


def test_an_imported_ed25519_certificate_stores_ed25519(app):
    import datetime
    from cryptography.hazmat.primitives import serialization
    from models import Certificate, db
    from services.cert_service import CertificateService
    key = ed25519.Ed25519PrivateKey.generate()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'ed-import.registry.test')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=30))
            .sign(key, None))
    pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    with app.app_context():
        row = CertificateService.import_certificate(descr='ed-import', cert_pem=pem)
        try:
            assert row.key_algo == 'Ed25519'
        finally:
            db.session.delete(db.session.get(Certificate, row.id))
            db.session.commit()

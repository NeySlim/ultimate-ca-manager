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
BRAINPOOL = {'EC-BP256': ('brainpoolP256r1', 'sha256'), 'EC-BP384': ('brainpoolP384r1', 'sha384'),
             'EC-BP512': ('brainpoolP512r1', 'sha512')}
# label: (param, NIST security category, OID of the key and of its signatures)
MLDSA = {'ML-DSA-44': ('44', 2, '2.16.840.1.101.3.4.3.17'),
         'ML-DSA-65': ('65', 3, '2.16.840.1.101.3.4.3.18'),
         'ML-DSA-87': ('87', 5, '2.16.840.1.101.3.4.3.19')}
REGISTERED = LABELS[:6] + list(BRAINPOOL) + LABELS[6:] + list(MLDSA)


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
    def test_table_is_classical_brainpool_and_mldsa(self):
        assert list(ka.labels()) == REGISTERED

    @pytest.mark.parametrize('label', REGISTERED)
    def test_generate_round_trips_through_both_key_lookups(self, label):
        sk = ka.generate(label)
        assert ka.label_for_private_key(sk) == label
        assert ka.label_for_public_key(sk.public_key()) == label

    @pytest.mark.parametrize('label', REGISTERED)
    def test_spellings_normalize_to_the_label(self, label):
        alg = ka.get(label)
        for spelling in (label, label.lower(), f' {label} ', alg.display, alg.legacy_key_algo,
                         alg.trust_store_id, *alg.curve_names, *alg.aliases):
            if spelling:
                assert ka.normalize_label(spelling) == label, spelling

    @pytest.mark.parametrize('label', REGISTERED)
    def test_parse_label_gives_family_and_param(self, label):
        alg = ka.get(label)
        assert ka.parse_label(label) == (alg.family, alg.param)
        expected = label if alg.param is None else f'{alg.family}-{alg.param}'
        assert expected == label

    @pytest.mark.parametrize('label', REGISTERED)
    def test_trust_store_id_generates_the_same_algorithm(self, label):
        alg = ka.get(label)
        if alg.trust_store_id is None:
            assert alg.family in ('ED25519', 'ED448')
            return
        if alg.family == 'ML-DSA':
            # reserved for TrustStore generation, which does not take it yet
            assert alg.trust_store_id == label.lower() and alg.trust_store_id not in KEY_TYPES
            return
        algo, param = KEY_TYPES[alg.trust_store_id]
        if algo == 'rsa':
            assert alg.family == 'RSA' and param == alg.key_size
        else:
            assert alg.family == 'EC' and param.name.lower() in alg.curve_names

    @pytest.mark.parametrize('label', REGISTERED)
    def test_legacy_key_algo_is_the_spelling_of_the_public_key(self, label):
        assert ka.key_algo_for_public_key(ka.generate(label).public_key()) == ka.get(label).legacy_key_algo

    @pytest.mark.parametrize('label', REGISTERED)
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
        assert not ka.fips_approved('ML-DSA-65')
        assert not ka.fips_approved('RSA-1024')
        assert not ka.fips_approved(None)

    @pytest.mark.parametrize('value', [None, '', '  ', 'RSA-1024', 'secp256k1', 'EdDSA', 'ML-DSA-66', 'SLH-DSA-SHA2-128s', True, 1024])
    def test_unknown_is_none(self, value):
        assert ka.get(value) is None
        assert ka.normalize_label(value) is None
        assert ka.parse_label(value) is None
        assert ka.fips_approved(value) is False

    def test_generate_unknown_raises(self):
        with pytest.raises(ValueError):
            ka.generate('RSA-1024')

    @pytest.mark.parametrize('spec', ['rsa:1024', 'ec:secp256k1', 'x25519', 'dsa:1024', 'none'])
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


class TestMLDSA:
    """ML-DSA-44/65/87 (FIPS 204): a hyphenated family, never cut at '-'."""

    @pytest.fixture
    def fips(self, monkeypatch):
        import fips_mode
        monkeypatch.setattr(fips_mode, 'enabled', lambda: True)

    @pytest.fixture
    def without_mldsa(self, monkeypatch):
        """The tables a build whose libcrypto has no ML-DSA (OpenSSL < 3.5) loads."""
        monkeypatch.setattr(ka, 'mldsa_supported', lambda: False)
        ka._load()
        yield
        monkeypatch.undo()
        ka._load()

    @pytest.mark.parametrize('label', MLDSA)
    def test_row_shape(self, label):
        alg = ka.get(label)
        param, level, oid = MLDSA[label]
        assert (alg.family, alg.param, alg.security_level, alg.oid) == ('ML-DSA', param, level, oid)
        assert (alg.needs_digest, alg.default_digest, alg.key_size, alg.fips_approved) == (False, None, None, False)
        assert (alg.display, alg.legacy_key_algo, alg.trust_store_id) == (label, label, label.lower())

    @pytest.mark.parametrize('label', MLDSA)
    def test_spellings(self, label):
        param = MLDSA[label][0]
        for spelling in (label, f'mldsa{param}', f'ml_dsa_{param}', f'ML_DSA {param}', f'ml-dsa-{param}'):
            assert ka.normalize_label(spelling) == label, spelling
        assert ka.parse_label(label) == ('ML-DSA', param)

    @pytest.mark.parametrize('label', MLDSA)
    def test_keys_of_each_size_are_told_apart(self, label):
        sk = build_key(f"priv:mldsa{MLDSA[label][0]}")
        assert ka.label_for_private_key(sk) == label
        assert ka.label_for_public_key(sk.public_key()) == label
        assert ka.key_algo_for_public_key(sk.public_key()) == label
        assert ka.family_for_public_key(sk.public_key()) == 'ML-DSA'

    @pytest.mark.parametrize('label', MLDSA)
    def test_signature_oid_names_the_label(self, label):
        oid = MLDSA[label][2]
        assert ka.label_for_signature_oid(oid) == label
        assert ka.label_for_signature_oid(x509.ObjectIdentifier(oid)) == label
        sk = ka.generate(label)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'k')])
        csr = x509.CertificateSigningRequestBuilder().subject_name(name).sign(sk, None)
        assert ka.label_for_signature_oid(csr.signature_algorithm_oid) == label

    def test_other_signature_oids_name_nothing(self):
        for oid in ('1.2.840.113549.1.1.11', '1.3.101.112', '2.16.840.1.101.3.4.3.20', '', None, 'x'):
            assert ka.label_for_signature_oid(oid) is None, oid

    def test_is_post_quantum(self):
        assert all(ka.is_post_quantum(label) for label in MLDSA)
        assert ka.is_post_quantum('mldsa65')
        for label in (*LABELS, *BRAINPOOL, 'ML-DSA-66', None, ''):
            assert not ka.is_post_quantum(label), label

    def test_facades_pick_it_up(self):
        assert key_label_for_public_key(build_key('mldsa65')) == 'ML-DSA-65'
        assert key_label_for_public_key(build_key('mldsa87')) == 'ML-DSA-87'
        assert _normalize_key_type_label('ml-dsa-65') == 'ML-DSA-65'

    @pytest.mark.parametrize('label', MLDSA)
    def test_refused_in_fips_mode(self, label, fips):
        import fips_mode
        with pytest.raises(fips_mode.FipsRestricted):
            ka.generate(label)

    def test_absent_when_the_libcrypto_lacks_it(self, without_mldsa):
        assert list(ka.labels()) == REGISTERED[:-3]
        assert ka.get('ML-DSA-65') is None
        assert ka.label_for_public_key(build_key('mldsa65')) is None
        with pytest.raises(ValueError, match='not available on this build'):
            ka.generate('ML-DSA-65')
        with pytest.raises(ValueError, match='Unsupported key algorithm'):
            ka.generate('RSA-1024')
        # still named, for what reads certificates without using the key
        assert ka.is_post_quantum('ML-DSA-65')
        assert ka.label_for_signature_oid(MLDSA['ML-DSA-65'][2]) == 'ML-DSA-65'

    def test_present_when_the_libcrypto_has_it(self):
        from cryptography.hazmat.backends.openssl.backend import backend
        assert ka.mldsa_supported() is backend.mldsa_supported() is True
        assert set(MLDSA) <= set(ka.labels())


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
    assert ka.key_algo_for_public_key(make_key().public_key()) == expected


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


class TestBrainpool:
    """Brainpool P256r1/P384r1/P512r1 (RFC 5639): accepted outside FIPS mode, refused inside it."""

    @pytest.fixture
    def fips(self, monkeypatch):
        import fips_mode
        monkeypatch.setattr(fips_mode, 'enabled', lambda: True)

    @pytest.mark.parametrize('label', BRAINPOOL)
    def test_row_shape(self, label):
        alg = ka.get(label)
        curve, digest = BRAINPOOL[label]
        assert (alg.family, alg.curve_names, alg.trust_store_id) == ('EC', (curve.lower(),), curve)
        assert (alg.default_digest, alg.fips_approved) == (digest, False)
        assert len(label) <= 20 and ka.label_for_curve_name(curve) == label

    @pytest.mark.parametrize('label', BRAINPOOL)
    def test_every_documented_alias_names_the_label(self, label):
        curve = BRAINPOOL[label][0]
        bits = label[-3:]
        for spelling in (curve, f'EC-{curve}', f'BP-{bits}', f'bp{bits}', curve.upper()):
            assert ka.normalize_label(spelling) == label, spelling

    @pytest.mark.parametrize('label', BRAINPOOL)
    def test_generate_and_recognise(self, label):
        key = ka.generate(label)
        assert key.curve.name == BRAINPOOL[label][0]
        assert ka.label_for_public_key(key.public_key()) == label
        assert key_label_for_public_key(key.public_key()) == label
        assert ka.key_algo_for_public_key(key.public_key()) == f'EC {BRAINPOOL[label][0]}'

    @pytest.mark.parametrize('label', BRAINPOOL)
    def test_refused_in_fips_mode(self, label, fips):
        import fips_mode
        with pytest.raises(fips_mode.FipsRestricted):
            ka.generate(label)
        with pytest.raises(fips_mode.FipsRestricted):
            kt.normalize_ec_curve(label)
        pub = ec.generate_private_key(ka_curve(label)).public_key()
        assert 'FIPS' in kt.validate_enrollment_public_key(pub)

    @pytest.mark.parametrize('label', BRAINPOOL)
    def test_key_type_entry_points(self, label):
        curve = BRAINPOOL[label][0]
        short = label.removeprefix('EC-')
        assert kt.normalize_ec_curve(label) == curve
        assert kt.normalize_ec_curve(f'BP-{label[-3:]}') == curve
        assert kt.parse_csr_key_type(f'EC {curve}') == curve
        assert kt.parse_csr_key_type(curve) == curve
        assert kt.parse_issue_key_type('EC', short) == curve
        assert kt.parse_issue_key_type('ec', None, curve=label) == curve
        assert kt.issue_key_type_from_template(label) == curve

    @pytest.mark.parametrize('label', BRAINPOOL)
    def test_enrollment_accepts_outside_fips(self, label):
        pub = ec.generate_private_key(ka_curve(label)).public_key()
        assert kt.validate_enrollment_public_key(pub) is None

    @pytest.mark.parametrize('label', BRAINPOOL)
    def test_vocabularies_know_it(self, label):
        from services.template_service import TEMPLATE_KEY_TYPES
        curve = BRAINPOOL[label][0]
        assert label in TEMPLATE_KEY_TYPES
        assert KEY_TYPES[curve][1].name == curve
        assert _normalize_key_type_label(curve) == label
        assert _normalize_key_type_label(f'EC-{curve}') == label

    @pytest.mark.parametrize('label', BRAINPOOL)
    def test_ca_creation_resolves_the_curve(self, label):
        from api.v2.cas.crud import _resolve_local_key_type
        curve = BRAINPOOL[label][0]
        assert _resolve_local_key_type({'keyAlgo': label}) == (curve, None)
        assert _resolve_local_key_type({'keyAlgo': 'ECDSA', 'keySize': curve}) == (curve, None)

    def test_other_curves_stay_refused(self):
        for bad in ('brainpoolP320r1', 'EC-BP224', 'secp256k1'):
            with pytest.raises(ValueError):
                kt.normalize_ec_curve(bad)
        pub = ec.generate_private_key(ec.SECP256K1()).public_key()
        assert 'Unsupported EC curve' in kt.validate_enrollment_public_key(pub)


def ka_curve(label):
    return {'EC-BP256': ec.BrainpoolP256R1, 'EC-BP384': ec.BrainpoolP384R1,
            'EC-BP512': ec.BrainpoolP512R1}[label]()


@pytest.mark.parametrize('spec,expected', [
    ('mldsa44', ('ML-DSA-44', None)), ('mldsa87', ('ML-DSA-87', None)),
    ('ed448', ('Ed448', 448)), ('rsa:3072', ('RSA', 3072)), ('x25519', ('Unknown', None)),
])
def test_ca_detail_names_the_exact_algorithm(spec, expected):
    from api.v2.cas.crud import _public_key_summary
    assert _public_key_summary(build_key(spec)) == expected


@pytest.mark.parametrize('spec', ['priv:mldsa87', 'priv:mldsa44', 'priv:ed448', 'priv:ec:secp384r1', 'priv:rsa:3072'])
def test_renewal_rekey_keeps_the_exact_algorithm(spec):
    from services.cert.renewal import _generate_like
    public_key = build_key(spec).public_key()
    new = _generate_like(public_key)
    assert ka.key_algo_for_public_key(new.public_key()) == ka.key_algo_for_public_key(public_key)


def test_renewal_rekey_refuses_an_unregistered_family():
    from services.cert.renewal import _generate_like
    with pytest.raises(ValueError):
        _generate_like(build_key('x25519'))

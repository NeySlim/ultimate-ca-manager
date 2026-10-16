"""HSM key listing and synchronisation.

The PKCS#11 listing read attributes with ``obj.get``, which python-pkcs11
objects do not have, so every key was dropped and the listing came back empty;
a sync then deleted every key row and the CA bound to one lost its key.
"""
import os
import shutil
import subprocess
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from services.hsm.base_provider import HsmKeyInfo

pkcs11 = pytest.importorskip('pkcs11')
from pkcs11 import Attribute, KeyType, ObjectClass  # noqa: E402
from pkcs11.exceptions import AttributeTypeInvalid  # noqa: E402
from pkcs11.util.ec import encode_named_curve_parameters  # noqa: E402

SOFTHSM_MODULES = ('/usr/lib/softhsm/libsofthsm2.so',
                   '/usr/lib/x86_64-linux-gnu/softhsm/libsofthsm2.so',
                   '/usr/lib64/pkcs11/libsofthsm2.so',
                   '/usr/local/lib/softhsm/libsofthsm2.so')
SOFTHSM_MODULE = next((m for m in SOFTHSM_MODULES if os.path.exists(m)), None)
needs_softhsm = pytest.mark.skipif(
    not (SOFTHSM_MODULE and shutil.which('softhsm2-util')), reason='SoftHSM not installed')


# ---------------------------------------------------------------------------
# PKCS#11 listing on fake objects (always runs)
# ---------------------------------------------------------------------------

class _FakeObject:
    """Indexable like python-pkcs11 objects, no ``get``; absent attributes raise."""

    def __init__(self, attrs):
        self._attrs = attrs

    def __getitem__(self, attribute):
        if attribute not in self._attrs:
            raise AttributeTypeInvalid()
        return self._attrs[attribute]


class _FakeSession:
    def __init__(self, objects):
        self.objects = objects

    def get_objects(self, template):
        return [o for o in self.objects
                if all(o._attrs.get(k) == v for k, v in template.items())]


def _ec_private(key_id, curve, with_params=True):
    attrs = {Attribute.CLASS: ObjectClass.PRIVATE_KEY, Attribute.KEY_TYPE: KeyType.EC,
             Attribute.ID: key_id, Attribute.LABEL: f'ec-{curve}', Attribute.SIGN: True}
    if with_params:
        attrs[Attribute.EC_PARAMS] = encode_named_curve_parameters(curve)
    return _FakeObject(attrs)


def _ec_public(key_id, curve):
    return _FakeObject({Attribute.CLASS: ObjectClass.PUBLIC_KEY, Attribute.KEY_TYPE: KeyType.EC,
                        Attribute.ID: key_id, Attribute.EC_PARAMS: encode_named_curve_parameters(curve)})


@pytest.fixture
def fake_pkcs11(tmp_path):
    from services.hsm.pkcs11_provider import Pkcs11Provider
    module = tmp_path / 'fake.so'
    module.write_bytes(b'\x00')
    provider = Pkcs11Provider({'module_path': str(module), 'token_label': 't', 'user_pin': '1'})

    def listing(objects):
        provider._session = _FakeSession(objects)
        return {k.label: k for k in provider.list_keys()}
    return provider, listing


class TestPkcs11ListingOnFakeObjects:
    def test_keys_are_listed_with_their_real_algorithm(self, fake_pkcs11):
        provider, listing = fake_pkcs11
        rsa = _FakeObject({Attribute.CLASS: ObjectClass.PRIVATE_KEY, Attribute.KEY_TYPE: KeyType.RSA,
                           Attribute.ID: b'\x03', Attribute.LABEL: 'rsa', Attribute.SIGN: True,
                           Attribute.MODULUS: (1 << 3071).to_bytes(384, 'big')})
        aes = _FakeObject({Attribute.CLASS: ObjectClass.SECRET_KEY, Attribute.KEY_TYPE: KeyType.AES,
                           Attribute.ID: b'\x04', Attribute.LABEL: 'aes', Attribute.ENCRYPT: True,
                           Attribute.VALUE_LEN: 32})
        keys = listing([_ec_private(b'\x01', 'secp384r1'), _ec_private(b'\x02', 'secp521r1'), rsa, aes])
        assert {label: k.algorithm for label, k in keys.items()} == {
            'ec-secp384r1': 'EC-P384', 'ec-secp521r1': 'EC-P521', 'rsa': 'RSA-3072', 'aes': 'AES-256'}
        assert keys['ec-secp384r1'].key_identifier == '01'
        assert keys['ec-secp384r1'].purpose == 'signing'
        assert keys['aes'].purpose == 'encryption'
        assert provider.list_errors == []

    def test_unknown_curve_is_unknown_never_p256(self, fake_pkcs11):
        _provider, listing = fake_pkcs11
        keys = listing([_ec_private(b'\x05', 'secp256k1')])
        assert keys['ec-secp256k1'].algorithm == 'UNKNOWN'

    def test_curve_falls_back_to_the_public_half(self, fake_pkcs11):
        _provider, listing = fake_pkcs11
        keys = listing([_ec_private(b'\x06', 'secp384r1', with_params=False),
                        _ec_public(b'\x06', 'secp384r1')])
        assert keys['ec-secp384r1'].algorithm == 'EC-P384'

    def test_an_unreadable_key_is_reported(self, fake_pkcs11):
        provider, listing = fake_pkcs11
        broken = _FakeObject({Attribute.CLASS: ObjectClass.PRIVATE_KEY, Attribute.KEY_TYPE: KeyType.EC})
        keys = listing([broken, _ec_private(b'\x07', 'secp256r1')])
        assert list(keys) == ['ec-secp256r1']
        assert keys['ec-secp256r1'].algorithm == 'EC-P256'
        assert len(provider.list_errors) == 1


# ---------------------------------------------------------------------------
# Azure Key Vault curve labels
# ---------------------------------------------------------------------------

try:
    import azure.keyvault.keys as azure_keys
except ImportError:  # optional dependency
    azure_keys = None


def _azure_provider():
    from services.hsm.azure_provider import AzureKeyVaultProvider
    return AzureKeyVaultProvider({'vault_url': 'https://vault.example.invalid/'})


def _azure_ec_key(crv, curve=ec.SECP384R1()):
    numbers = ec.generate_private_key(curve).public_key().public_numbers()
    size = (curve.key_size + 7) // 8
    jwk = SimpleNamespace(crv=crv, x=numbers.x.to_bytes(size, 'big'), y=numbers.y.to_bytes(size, 'big'))
    return SimpleNamespace(key_type=azure_keys.KeyType.ec_hsm, key=jwk, key_operations=['sign'],
                           id=f'https://vault.example.invalid/keys/{crv}/1', name=str(crv))


@pytest.mark.skipif(azure_keys is None, reason='azure-keyvault-keys not installed')
class TestAzureCurveLabels:
    def test_unknown_curve_is_unknown_never_p256(self):
        provider = _azure_provider()
        key = _azure_ec_key('P-256K', ec.SECP256K1())
        assert provider._key_to_key_info(key).algorithm == 'UNKNOWN'
        assert provider._export_public_key(key) is None

    def test_a_key_without_curve_is_not_read_as_p256(self):
        provider = _azure_provider()
        key = _azure_ec_key(None, ec.SECP256R1())
        assert provider._key_to_key_info(key).algorithm == 'UNKNOWN'
        assert provider._export_public_key(key) is None

    def test_known_curves_keep_their_label(self):
        provider = _azure_provider()
        key = _azure_ec_key(azure_keys.KeyCurveName.p_384)
        assert provider._key_to_key_info(key).algorithm == 'EC-P384'
        assert 'BEGIN PUBLIC KEY' in provider._export_public_key(key)
        assert provider._key_to_key_info(_azure_ec_key('P-521', ec.SECP521R1())).algorithm == 'EC-P521'

    def test_a_key_that_cannot_be_fetched_is_reported(self):
        provider = _azure_provider()

        def get_key(name):
            raise RuntimeError('forbidden')
        provider._key_client = SimpleNamespace(
            list_properties_of_keys=lambda: [SimpleNamespace(name='k1')], get_key=get_key)
        assert provider.list_keys() == []
        assert len(provider.list_errors) == 1


# ---------------------------------------------------------------------------
# HsmService.sync_keys with a simulated provider
# ---------------------------------------------------------------------------

class _ListingProvider:
    def __init__(self, keys, errors=()):
        self.keys, self.list_errors = list(keys), list(errors)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def list_keys(self):
        return self.keys


def _info(identifier):
    return HsmKeyInfo(key_identifier=identifier, label=identifier, algorithm='EC-P256',
                      key_type='asymmetric', purpose='signing')


@contextmanager
def _provider_with_keys(app, tag, identifiers, bound=None):
    """A provider row holding *identifiers*; *bound* names the one a CA uses."""
    from models import db, CA
    from models.hsm import HsmProvider, HsmKey
    with app.app_context():
        provider = HsmProvider(name=f'sync-{tag}', type='pkcs11', config='{}')
        db.session.add(provider)
        db.session.commit()
        ids = {}
        for identifier in identifiers:
            key = HsmKey(provider_id=provider.id, key_identifier=identifier, label=identifier,
                         algorithm='EC-P256', key_type='asymmetric', purpose='signing')
            db.session.add(key)
            db.session.commit()
            ids[identifier] = key.id
        ca_id = None
        if bound:
            ca = CA(refid=f'sync-{tag}', descr=f'sync {tag}', crt='', prv=None, hsm_key_id=ids[bound])
            db.session.add(ca)
            db.session.commit()
            ca_id = ca.id
        provider_id = provider.id
    try:
        yield provider_id, ids, ca_id
    finally:
        with app.app_context():
            db.session.rollback()
            if ca_id:
                db.session.query(CA).filter_by(id=ca_id).delete()
            db.session.query(HsmKey).filter_by(provider_id=provider_id).delete()
            db.session.query(HsmProvider).filter_by(id=provider_id).delete()
            db.session.commit()


def _sync(app, provider_id, fake):
    from services.hsm import HsmService
    with app.app_context(), patch.object(HsmService, '_get_provider_instance', return_value=fake):
        return HsmService.sync_keys(provider_id)


def _surviving(app, provider_id):
    from models import db
    from models.hsm import HsmKey
    with app.app_context():
        return {k.key_identifier for k in db.session.query(HsmKey).filter_by(provider_id=provider_id)}


class TestSyncKeys:
    def test_a_key_bound_to_a_ca_survives_an_empty_listing(self, app):
        from models import db, CA
        with _provider_with_keys(app, 'bound', ['ca-key', 'loose'], bound='ca-key') as (pid, ids, ca_id):
            result = _sync(app, pid, _ListingProvider([]))
            assert result['removed'] == 1 and result['missing_kept'] == 1
            assert _surviving(app, pid) == {'ca-key'}
            with app.app_context():
                assert db.session.get(CA, ca_id).hsm_key_id == ids['ca-key']

    def test_nothing_is_removed_when_the_listing_had_errors(self, app):
        with _provider_with_keys(app, 'errors', ['a', 'b']) as (pid, _ids, _ca):
            result = _sync(app, pid, _ListingProvider([_info('a')], errors=['b: unreadable']))
            assert result['removed'] == 0
            assert result['listing_errors'] == 1 and result['missing_kept'] == 1
            assert _surviving(app, pid) == {'a', 'b'}

    def test_an_unreferenced_missing_key_is_still_removed(self, app):
        with _provider_with_keys(app, 'clean', ['a', 'gone']) as (pid, _ids, _ca):
            result = _sync(app, pid, _ListingProvider([_info('a'), _info('new')]))
            assert result == {'added': 1, 'removed': 1, 'unchanged': 1,
                              'missing_kept': 0, 'listing_errors': 0}
            assert _surviving(app, pid) == {'a', 'new'}


# ---------------------------------------------------------------------------
# Real token (SoftHSM)
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def softhsm_token(tmp_path_factory):
    root = tmp_path_factory.mktemp('softhsm')
    (root / 'tokens').mkdir()
    conf = root / 'softhsm2.conf'
    conf.write_text(f'directories.tokendir = {root / "tokens"}\n'
                    'objectstore.backend = file\nlog.level = ERROR\n')
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv('SOFTHSM2_CONF', str(conf))
        subprocess.run(['softhsm2-util', '--init-token', '--free', '--label', 'ucm-sync-test',
                        '--pin', '1234', '--so-pin', '5678'], check=True, capture_output=True)
        pkcs11.unload(SOFTHSM_MODULE)  # the library reads SOFTHSM2_CONF once, when loaded
        try:
            yield {'module_path': SOFTHSM_MODULE, 'token_label': 'ucm-sync-test', 'user_pin': '1234'}
        finally:
            pkcs11.unload(SOFTHSM_MODULE)


@needs_softhsm
class TestSoftHsm:
    def test_list_keys_labels_each_key_by_its_real_algorithm(self, softhsm_token):
        from services.hsm.pkcs11_provider import Pkcs11Provider
        provider = Pkcs11Provider(softhsm_token)
        with provider:
            generated = {provider.generate_key(f'list-{a}', a).key_identifier: a
                         for a in ('EC-P384', 'EC-P521', 'RSA-3072')}
            listed = {k.key_identifier: k.algorithm for k in provider.list_keys()}
        assert {i: listed.get(i) for i in generated} == generated
        assert provider.list_errors == []

    def test_sync_keeps_the_key_of_a_ca(self, app, softhsm_token):
        from models import db, CA
        from models.hsm import HsmProvider, HsmKey
        from services.hsm import HsmService
        with app.app_context():
            row = HsmProvider(name='sync-softhsm', type='pkcs11', config='{}')
            row.set_config(softhsm_token)
            db.session.add(row)
            db.session.commit()
            key_id = HsmService.generate_key(row.id, 'sync-ca-key', 'EC-P384').id
            ca = CA(refid='sync-softhsm', descr='sync softhsm', crt='', prv=None, hsm_key_id=key_id)
            db.session.add(ca)
            db.session.commit()
            provider_id, ca_id = row.id, ca.id
        try:
            with app.app_context():
                result = HsmService.sync_keys(provider_id)
                assert result['removed'] == 0 and result['listing_errors'] == 0
                key = db.session.get(HsmKey, key_id)
                assert key is not None and key.algorithm == 'EC-P384'
                assert db.session.get(CA, ca_id).hsm_key_id == key_id
        finally:
            with app.app_context():
                db.session.rollback()
                db.session.query(CA).filter_by(id=ca_id).delete()
                db.session.query(HsmKey).filter_by(provider_id=provider_id).delete()
                db.session.query(HsmProvider).filter_by(id=provider_id).delete()
                db.session.commit()

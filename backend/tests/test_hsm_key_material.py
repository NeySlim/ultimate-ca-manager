"""A token's current public half, not its slot name, identifies cached material."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from asn1crypto.core import OctetString
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from models import db
from models.hsm import HsmKey
from models.ssh import SSHCertificateAuthority
from services.hsm import HsmService
from services.hsm.openbao_provider import OpenBaoProvider
from tests.test_hsm_sync_and_listing import (
    Attribute, KeyType, ObjectClass, _FakeObject, _ec_private, _ec_public,
    _info, _ListingProvider, _provider_with_keys, _sync, fake_pkcs11,  # noqa: F401
    needs_softhsm, softhsm_token,  # noqa: F401
)


def pem(public):
    return public.public_bytes(serialization.Encoding.PEM,
                               serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def new_pem():
    return pem(ec.generate_private_key(ec.SECP256R1()).public_key())


@pytest.mark.parametrize('bound', ['x509', 'ssh', None])
def test_sync_replaces_same_algorithm_and_reports_bound_keys(app, bound):
    old, fresh = new_pem(), new_pem()
    with _provider_with_keys(app, f'material-{bound}', ['a'],
                             bound='a' if bound == 'x509' else None) as (pid, ids, _):
        with app.app_context():
            row = db.session.get(HsmKey, ids['a'])
            row.public_key_pem = old
            if bound == 'ssh':
                db.session.add(SSHCertificateAuthority(
                    refid='material-ssh', descr='material SSH', ca_type='user',
                    public_key='unused', private_key='', key_type='ecdsa-p256', fingerprint='test-material',
                    key_source='hsm', hsm_key_id=ids['a']))
            db.session.commit()
        try:
            listed = _info('a')
            listed.public_key_pem = fresh
            with patch.object(HsmService, 'forget_signing_hash') as forget:
                result = _sync(app, pid, _ListingProvider([listed]))
                forget.assert_called_once_with(ids['a'])
            assert result['changed_referenced_key_ids'] == ([ids['a']] if bound else [])
            with app.app_context():
                assert db.session.get(HsmKey, ids['a']).public_key_pem == fresh
            assert _sync(app, pid, _ListingProvider([listed]))['changed_referenced_key_ids'] == []
        finally:
            with app.app_context():
                SSHCertificateAuthority.query.filter_by(refid='material-ssh').delete()
                db.session.commit()


def test_same_spki_different_pem_layout_is_not_a_rotation(app):
    old = new_pem()
    with _provider_with_keys(app, 'pem-layout', ['a'], bound='a') as (pid, ids, _):
        with app.app_context():
            db.session.get(HsmKey, ids['a']).public_key_pem = old
            db.session.commit()
        listed = _info('a')
        listed.public_key_pem = old.replace('\n', '\r\n')
        with patch.object(HsmService, 'forget_signing_hash') as forget:
            result = _sync(app, pid, _ListingProvider([listed]))
        forget.assert_not_called()
        assert result['changed_referenced_key_ids'] == []


def test_corrected_label_on_the_same_spki_is_not_a_rotation(app):
    same = new_pem()
    with _provider_with_keys(app, 'relabel', ['a'], bound='a') as (pid, ids, _):
        with app.app_context():
            row = db.session.get(HsmKey, ids['a'])
            row.algorithm, row.public_key_pem = 'EC-P384', same
            db.session.commit()
        listed = _info('a')
        listed.public_key_pem = same
        with patch.object(HsmService, 'forget_signing_hash') as forget:
            result = _sync(app, pid, _ListingProvider([listed]))
        forget.assert_not_called()
        assert result['changed_referenced_key_ids'] == []
        with app.app_context():
            row = db.session.get(HsmKey, ids['a'])
            assert (row.algorithm, row.public_key_pem) == ('EC-P256', same)


@pytest.mark.parametrize('reading', [None, 'not a PEM'])
def test_unreadable_same_algorithm_does_not_destroy_cached_public_key(app, reading):
    old = new_pem()
    with _provider_with_keys(app, 'unreadable', ['a']) as (pid, ids, _):
        with app.app_context():
            db.session.get(HsmKey, ids['a']).public_key_pem = old
            db.session.commit()
        listed = _info('a')
        listed.public_key_pem = reading
        _sync(app, pid, _ListingProvider([listed]))
        with app.app_context():
            assert db.session.get(HsmKey, ids['a']).public_key_pem == old


def test_remote_node_digest_cache_cannot_follow_a_rotated_slot(app, monkeypatch):
    with _provider_with_keys(app, 'remote-cache', ['a']) as (pid, ids, _):
        monkeypatch.setattr(HsmService, '_signing_hash_cache', {})
        with app.app_context():
            db.session.get(HsmKey, ids['a']).public_key_pem = new_pem()
            db.session.commit()
            fake = SimpleNamespace(hash_for_key=lambda *a: 'sha256')
            with patch.object(HsmService, '_get_provider_instance', return_value=fake):
                assert HsmService.signing_hash(ids['a'], 'EC-P256') == 'sha256'
                remote_cache = HsmService._signing_hash_cache.copy()
        listed = _info('a')
        listed.public_key_pem = new_pem()
        _sync(app, pid, _ListingProvider([listed]))
        # A second process did not receive forget_signing_hash from the syncing node.
        HsmService._signing_hash_cache = remote_cache
        with app.app_context():
            fake = SimpleNamespace(hash_for_key=lambda *a: 'sha384')
            with patch.object(HsmService, '_get_provider_instance', return_value=fake):
                assert HsmService.signing_hash(ids['a'], 'EC-P256') == 'sha384'


def test_no_digest_is_cached_without_a_readable_public_key(app, monkeypatch):
    monkeypatch.setattr(HsmService, '_signing_hash_cache', {})
    with _provider_with_keys(app, 'no-spki', ['a']) as (_, ids, _):
        with app.app_context():
            fake = SimpleNamespace(hash_for_key=lambda *a: 'sha256')
            with patch.object(HsmService, '_get_provider_instance', return_value=fake):
                assert HsmService.signing_hash(ids['a'], 'EC-P256') == 'sha256'
                fake.hash_for_key = lambda *a: 'sha384'
                assert HsmService.signing_hash(ids['a'], 'EC-P256') == 'sha384'


def test_sync_route_audits_changed_referenced_key_ids(app, auth_client, monkeypatch):
    with _provider_with_keys(app, 'audit-material', ['a'], bound='a') as (pid, ids, _):
        with app.app_context():
            db.session.get(HsmKey, ids['a']).public_key_pem = new_pem()
            db.session.commit()
        listed = _info('a')
        listed.public_key_pem = new_pem()
        monkeypatch.setattr(HsmService, '_get_provider_instance', lambda *a: _ListingProvider([listed]))
        with patch('api.v2.hsm.AuditService.log_action') as audit:
            response = auth_client.post(f'/api/v2/hsm/providers/{pid}/sync')
        assert response.status_code == 200
        assert response.json['data']['changed_referenced_key_ids'] == [ids['a']]
        detail = audit.call_args.kwargs['details']
        assert f"Changed key material referenced by authorities: [{ids['a']}]" in detail


def test_openbao_latest_version_replaces_cached_spki(app):
    old, fresh = new_pem(), new_pem()
    provider = OpenBaoProvider.__new__(OpenBaoProvider)
    provider._api = lambda method, path: ({'data': {'keys': ['a']}} if method == 'LIST' else {
        'data': {'type': 'ecdsa-p256', 'latest_version': 2,
                 'keys': {'1': {'public_key': old}, '2': {'public_key': fresh}}}})
    with _provider_with_keys(app, 'bao-rotation', ['a']) as (pid, ids, _):
        with app.app_context():
            db.session.get(HsmKey, ids['a']).public_key_pem = old
            db.session.commit()
        _sync(app, pid, _ListingProvider(provider.list_keys()))
        with app.app_context():
            assert db.session.get(HsmKey, ids['a']).public_key_pem == fresh


@pytest.mark.parametrize('curve', [ec.SECP256R1(), ec.SECP384R1(), ec.SECP521R1()])
def test_pkcs11_listing_decodes_der_wrapped_ec_point(fake_pkcs11, curve):
    provider, listing = fake_pkcs11
    public = ec.generate_private_key(curve).public_key()
    pub = _ec_public(b'\x11', curve.name)
    pub._attrs[Attribute.EC_POINT] = OctetString(public.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)).dump()
    listed = listing([_ec_private(b'\x11', curve.name), pub])
    assert listed[f'ec-{curve.name}'].public_key_pem == pem(public)
    assert provider.list_errors == []


def test_pkcs11_listing_reads_rsa_public_attributes(fake_pkcs11):
    _, listing = fake_pkcs11
    public = rsa.generate_private_key(65537, 2048).public_key()
    numbers = public.public_numbers()
    priv = _FakeObject({Attribute.CLASS: ObjectClass.PRIVATE_KEY, Attribute.KEY_TYPE: KeyType.RSA,
                       Attribute.ID: b'\x12', Attribute.LABEL: 'rsa', Attribute.SIGN: True})
    pub = _FakeObject({Attribute.CLASS: ObjectClass.PUBLIC_KEY, Attribute.KEY_TYPE: KeyType.RSA,
                      Attribute.ID: b'\x12', Attribute.MODULUS: numbers.n.to_bytes(256, 'big'),
                      Attribute.PUBLIC_EXPONENT: numbers.e.to_bytes(3, 'big')})
    listed = listing([priv, pub])
    assert listed['rsa'].public_key_pem == pem(public)
    assert listed['rsa'].algorithm == 'RSA-2048'


def test_unreadable_public_half_does_not_abort_listing(fake_pkcs11):
    _, listing = fake_pkcs11
    keys = listing([_ec_private(b'\x01', 'secp256r1'), _ec_public(b'\x01', 'secp256r1'),
                    _ec_private(b'\x02', 'secp384r1')])
    assert len(keys) == 2
    assert keys['ec-secp256r1'].public_key_pem is None


def test_pkcs11_listing_drops_a_public_half_that_is_not_a_key(fake_pkcs11):
    provider, listing = fake_pkcs11
    pub = _ec_public(b'\x13', 'secp256r1')
    pub._attrs[Attribute.EC_POINT] = OctetString(b'\x04' + b'\x00' * 64).dump()  # not on the curve
    keys = listing([_ec_private(b'\x13', 'secp256r1'), pub, _ec_private(b'\x14', 'secp384r1')])
    assert len(keys) == 2
    assert keys['ec-secp256r1'].public_key_pem is None
    assert provider.list_errors == []


@needs_softhsm
@pytest.mark.parametrize('algorithm', ['RSA-2048', 'EC-P256', 'EC-P384', 'EC-P521'])
def test_real_token_listing_exports_current_spki(softhsm_token, algorithm):
    from services.hsm.pkcs11_provider import Pkcs11Provider
    with Pkcs11Provider(softhsm_token) as provider:
        generated = provider.generate_key(f'public-{algorithm}', algorithm)
        try:
            listed = {key.key_identifier: key for key in provider.list_keys()}
            assert listed[generated.key_identifier].public_key_pem == generated.public_key_pem
        finally:
            provider.delete_key(generated.key_identifier)

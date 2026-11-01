"""Smart import bounds the key derivations a request makes run: a cap on password
attempts per parse, and no derivation whose cost (PBKDF2 iterations, scrypt N,
PKCS#12 MAC iterations) is far above what OpenSSL or pyca produce. Counted, not timed."""
import base64
import datetime
import hashlib
import hmac
import json
import os
import shutil
import subprocess

import pytest
from asn1crypto import algos, cms
from asn1crypto import pkcs12 as asn1_pkcs12
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
from cryptography.hazmat.primitives import padding as sym_padding
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.serialization import PrivateFormat, pkcs12
from cryptography.x509.oid import NameOID
from pyasn1.codec.der import encoder
from pyasn1.type import univ
from pyasn1_modules import rfc5280, rfc7914, rfc8018

from services.smart_import import parser as parser_mod
from utils import pkcs12_layers
from services.smart_import.parser import (
    MAX_KDF_ITERATIONS, MAX_PASSWORD_ATTEMPTS, NOT_TRIED, WRONG_PASSWORD, SmartParser, kdf_refusal)

RIGHT = b'right-pass'


def _sealed_pem(key=None):
    key = key or ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(serialization.Encoding.PEM, PrivateFormat.PKCS8,
                             serialization.BestAvailableEncryption(RIGHT)).decode()


def _plain_pem():
    return ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM, PrivateFormat.PKCS8, serialization.NoEncryption()).decode()


@pytest.fixture
def key_tries(monkeypatch):
    """Calls of load_private_key_any with a password: each one derives a key."""
    tries = []
    real = parser_mod.load_private_key_any

    def counted(data, password=None):
        if password is not None:
            tries.append(password)
        return real(data, password=password)
    monkeypatch.setattr(parser_mod, 'load_private_key_any', counted)
    return tries


@pytest.fixture
def p12_tries(monkeypatch):
    tries = []
    real = parser_mod.load_key_and_certificates

    def counted(data, password):
        tries.append(password)
        return real(data, password)
    monkeypatch.setattr(parser_mod, 'load_key_and_certificates', counted)
    return tries


def test_password_attempts_stop_at_the_cap_and_say_so(key_tries):
    passwords = [f'wrong-{i}' for i in range(10)]
    objects = SmartParser().parse(''.join(_sealed_pem() for _ in range(10)), passwords)
    assert len(key_tries) == MAX_PASSWORD_ATTEMPTS
    errors = [o.error for o in objects]
    assert errors.count(WRONG_PASSWORD) == MAX_PASSWORD_ATTEMPTS // len(passwords)
    assert errors.count(NOT_TRIED) == 10 - MAX_PASSWORD_ATTEMPTS // len(passwords)
    assert WRONG_PASSWORD == 'Private key could not be decrypted with any of the passwords given'


def test_the_cap_is_per_parse(key_tries):
    parser = SmartParser()
    content = ''.join(_sealed_pem() for _ in range(MAX_PASSWORD_ATTEMPTS))
    for _ in range(2):
        assert all(o.error == WRONG_PASSWORD for o in parser.parse(content, 'wrong'))
    assert len(key_tries) == 2 * MAX_PASSWORD_ATTEMPTS


def test_keys_that_are_not_encrypted_spend_no_attempt(key_tries):
    objects = SmartParser().parse(''.join(_plain_pem() for _ in range(80)),
                                  [f'p-{i}' for i in range(32)])
    assert len(objects) == 80 and not any(o.error for o in objects)
    assert key_tries == []


def test_the_right_password_still_opens_a_key_after_wrong_ones(key_tries):
    [obj] = SmartParser().parse(_sealed_pem(), ['wrong-1', 'wrong-2', RIGHT.decode()])
    assert obj.error is None and obj.key_algorithm.startswith('EC')
    assert len(key_tries) == 3


def _with_iterations(der, iterations):
    from asn1crypto import keys as asn1_keys
    info = asn1_keys.EncryptedPrivateKeyInfo.load(der)
    info['encryption_algorithm']['parameters']['key_derivation_func']['parameters'][
        'iteration_count'] = iterations
    return info.dump(force=True)


@pytest.mark.parametrize('encoding', ['PEM', 'DER'])
def test_a_key_sealed_with_too_many_iterations_is_not_tried(key_tries, encoding):
    der = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.DER, PrivateFormat.PKCS8, serialization.BestAvailableEncryption(RIGHT))
    costly = _with_iterations(der, MAX_KDF_ITERATIONS + 1)
    content = costly if encoding == 'DER' else (
        '-----BEGIN ENCRYPTED PRIVATE KEY-----\n' + base64.encodebytes(costly).decode()
        + '-----END ENCRYPTED PRIVATE KEY-----\n')
    [obj] = SmartParser().parse(content, RIGHT.decode())
    assert key_tries == []
    assert obj.error and f'{MAX_KDF_ITERATIONS + 1} iterations' in obj.error


def test_the_iteration_cap_lets_the_default_encryptions_through():
    der = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.DER, PrivateFormat.PKCS8, serialization.BestAvailableEncryption(RIGHT))
    assert kdf_refusal(parser_mod._sealed_algorithm(_with_iterations(der, MAX_KDF_ITERATIONS))) is None


def _scrypt_pbes2(n, r=8, p=1):
    params = rfc7914.Scrypt_params()
    params['salt'] = b'\x00' * 16
    params['costParameter'] = n
    params['blockSize'] = r
    params['parallelizationParameter'] = p
    kdf = rfc5280.AlgorithmIdentifier()
    kdf['algorithm'] = univ.ObjectIdentifier('1.3.6.1.4.1.11591.4.11')
    kdf['parameters'] = univ.Any(encoder.encode(params))
    scheme = rfc5280.AlgorithmIdentifier()
    scheme['algorithm'] = univ.ObjectIdentifier('2.16.840.1.101.3.4.1.42')
    scheme['parameters'] = univ.Any(encoder.encode(univ.OctetString(b'\x00' * 16)))
    pbes2 = rfc8018.PBES2_params()
    pbes2['keyDerivationFunc']['algorithm'] = kdf['algorithm']
    pbes2['keyDerivationFunc']['parameters'] = kdf['parameters']
    pbes2['encryptionScheme']['algorithm'] = scheme['algorithm']
    pbes2['encryptionScheme']['parameters'] = scheme['parameters']
    alg = rfc5280.AlgorithmIdentifier()
    alg['algorithm'] = univ.ObjectIdentifier('1.2.840.113549.1.5.13')
    alg['parameters'] = univ.Any(encoder.encode(pbes2))
    return encoder.encode(alg)


@pytest.mark.parametrize('n,r,p,refused', [(1 << 14, 8, 1, False), (1 << 20, 8, 1, False),
                                           (1 << 21, 1, 1, True), (1 << 20, 8, 2, True)])
def test_scrypt_is_refused_above_its_cap(n, r, p, refused):
    assert bool(kdf_refusal(_scrypt_pbes2(n, r, p))) is refused


def _pkcs12(scheme=pkcs12.PBES.PBESv2SHA256AndAES256CBC):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'kdf-cap.example.com')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=1)).sign(key, hashes.SHA256()))
    encryption = (PrivateFormat.PKCS12.encryption_builder().kdf_rounds(1000)
                  .key_cert_algorithm(scheme).hmac_hash(hashes.SHA256()).build(RIGHT))
    return pkcs12.serialize_key_and_certificates(b'kdf', key, cert, None, encryption)


def _pseudo_pem(p12):
    return '-----BEGIN PKCS12-----\n' + base64.encodebytes(p12).decode() + '-----END PKCS12-----\n'


def test_a_pkcs12_with_a_costly_mac_is_not_tried(p12_tries):
    pfx = asn1_pkcs12.Pfx.load(_pkcs12())
    pfx['mac_data']['iterations'] = MAX_KDF_ITERATIONS + 1
    [obj] = SmartParser().parse(pfx.dump(force=True), RIGHT.decode())
    assert p12_tries == []
    assert 'PKCS#12 MAC' in obj.error


@pytest.mark.parametrize('scheme', [pkcs12.PBES.PBESv2SHA256AndAES256CBC,
                                    pkcs12.PBES.PBESv1SHA1And3KeyTripleDESCBC])
def test_a_pkcs12_with_a_costly_key_bag_is_not_tried(p12_tries, scheme):
    pfx = asn1_pkcs12.Pfx.load(_pkcs12(scheme))
    safe = pfx.authenticated_safe
    for info in safe:
        if info['content_type'].native == 'data':
            bags = asn1_pkcs12.SafeContents.load(info['content'].native)
            params = bags[0]['bag_value']['encryption_algorithm']['parameters']
            if scheme is pkcs12.PBES.PBESv1SHA1And3KeyTripleDESCBC:
                params['iterations'] = MAX_KDF_ITERATIONS + 1
            else:
                params['key_derivation_func']['parameters']['iteration_count'] = MAX_KDF_ITERATIONS + 1
            info['content'] = bags.dump(force=True)
    pfx['auth_safe']['content'] = safe.dump(force=True)
    [obj] = SmartParser().parse(_pseudo_pem(pfx.dump(force=True)), RIGHT.decode())
    assert p12_tries == []
    assert f'{MAX_KDF_ITERATIONS + 1} iterations' in obj.error


@pytest.fixture
def layer_opens(monkeypatch):
    """Calls of open_layer: each one derives the key of an encryptedData."""
    opens = []
    real = pkcs12_layers.open_layer

    def counted(layer, password):
        opens.append(password)
        return real(layer, password)
    monkeypatch.setattr(pkcs12_layers, 'open_layer', counted)
    return opens


def test_pkcs12_attempts_share_the_cap(p12_tries, layer_opens):
    content = ''.join(_pseudo_pem(_pkcs12()) for _ in range(3))
    objects = SmartParser().parse(content, [f'wrong-{i}' for i in range(32)])
    # A wrong password stops at the encryptedData layer opened here: pyca never runs
    assert len(layer_opens) == MAX_PASSWORD_ATTEMPTS and p12_tries == []
    assert [o.error for o in objects] == [NOT_TRIED]


def test_a_pkcs12_still_opens_with_its_password(p12_tries, layer_opens):
    objects = SmartParser().parse(_pseudo_pem(_pkcs12()), ['wrong', RIGHT.decode()])
    assert {o.type.value for o in objects} == {'certificate', 'private_key'}
    assert not any(o.error for o in objects)
    assert p12_tries == [RIGHT] and layer_opens == [b'wrong', RIGHT]


def test_a_pkcs12_open_costs_each_of_its_derivations(p12_tries):
    """MAC, the certificate layer (here, then in pyca) and the shrouded key: four of the budget."""
    parser = SmartParser(shared_budget=True)
    parser._attempts.left = 3
    [obj] = parser.parse(_pseudo_pem(_pkcs12()), RIGHT.decode())
    assert obj.error == NOT_TRIED and p12_tries == []
    parser._attempts.left = 4
    assert {o.type.value for o in parser.parse(_pseudo_pem(_pkcs12()), RIGHT.decode())} == {
        'certificate', 'private_key'}


# ---- a shrouded key inside an encryptedData ------------------------------------

def _bmp(password):
    return password.decode().encode('utf-16-be') + b'\x00\x00'


def _encrypted_data(safe_contents, scheme):
    """An encryptedData ContentInfo holding *safe_contents*, sealed with RIGHT."""
    salt, rounds = os.urandom(8), 1000
    if scheme == 'pbes2':
        key, iv = PBKDF2HMAC(hashes.SHA256(), 32, salt, rounds).derive(RIGHT), os.urandom(16)
        algorithm = {'algorithm': 'pbes2', 'parameters': {
            'key_derivation_func': {'algorithm': 'pbkdf2', 'parameters': {
                'salt': algos.Pbkdf2Salt(name='specified', value=salt), 'iteration_count': rounds,
                'prf': {'algorithm': 'sha256'}}},
            'encryption_scheme': {'algorithm': 'aes256_cbc', 'parameters': iv}}}
        block = algorithms.AES(key)
    else:
        key = pkcs12_layers.pkcs12_kdf(_bmp(RIGHT), salt, rounds, 1, 24)
        iv = pkcs12_layers.pkcs12_kdf(_bmp(RIGHT), salt, rounds, 2, 8)
        algorithm = {'algorithm': 'pkcs12_sha1_tripledes_3key',
                     'parameters': {'salt': salt, 'iterations': rounds}}
        block = TripleDES(key)
    padder = sym_padding.PKCS7(block.block_size).padder()
    encryptor = Cipher(block, modes.CBC(iv)).encryptor()
    sealed = encryptor.update(padder.update(safe_contents) + padder.finalize()) + encryptor.finalize()
    return cms.ContentInfo({'content_type': 'encrypted_data', 'content': cms.EncryptedData({
        'version': 'v0', 'encrypted_content_info': {
            'content_type': 'data', 'content_encryption_algorithm': algorithm,
            'encrypted_content': sealed}})})


def _key_sealed_in_a_layer(scheme, iterations=None, nested=False):
    """The PKCS#12 of ``_pkcs12`` with its shrouded key moved into an encryptedData
    (or, *nested*, into a safeContentsBag of the plain data), MAC recomputed."""
    pfx = asn1_pkcs12.Pfx.load(_pkcs12())
    infos = []
    for info in pfx.authenticated_safe:
        if info['content_type'].native != 'data':
            infos.append(info)
            continue
        bags = asn1_pkcs12.SafeContents.load(info['content'].native)
        if iterations is not None:
            bags[0]['bag_value']['encryption_algorithm']['parameters']['key_derivation_func'][
                'parameters']['iteration_count'] = iterations
        if nested:
            outer = asn1_pkcs12.SafeContents([{'bag_id': 'safe_contents', 'bag_value': bags}])
            infos.append(cms.ContentInfo({'content_type': 'data', 'content': outer.dump(force=True)}))
        else:
            infos.append(_encrypted_data(bags.dump(force=True), scheme))
    auth_safe = asn1_pkcs12.AuthenticatedSafe(infos).dump(force=True)
    salt, rounds = os.urandom(8), 2048
    mac_key = pkcs12_layers.pkcs12_kdf(_bmp(RIGHT), salt, rounds, 3, 20)
    return asn1_pkcs12.Pfx({
        'version': 'v3', 'auth_safe': {'content_type': 'data', 'content': auth_safe},
        'mac_data': {'mac': {'digest_algorithm': {'algorithm': 'sha1'},
                             'digest': hmac.new(mac_key, auth_safe, hashlib.sha1).digest()},
                     'mac_salt': salt, 'iterations': rounds}}).dump()


@pytest.mark.parametrize('scheme', ['pbes2', 'pkcs12_3des'])
def test_a_key_sealed_in_a_layer_opens_when_affordable(p12_tries, scheme):
    objects = SmartParser().parse(_pseudo_pem(_key_sealed_in_a_layer(scheme)), RIGHT.decode())
    assert {o.type.value for o in objects} == {'certificate', 'private_key'}
    assert not any(o.error for o in objects) and p12_tries == [RIGHT]


@pytest.mark.parametrize('scheme', ['pbes2', 'pkcs12_3des'])
def test_a_costly_key_sealed_in_a_layer_is_not_tried(p12_tries, scheme):
    data = _key_sealed_in_a_layer(scheme, iterations=MAX_KDF_ITERATIONS + 1)
    [obj] = SmartParser().parse(_pseudo_pem(data), RIGHT.decode())
    assert p12_tries == []
    assert f'{MAX_KDF_ITERATIONS + 1} iterations' in obj.error


def test_a_costly_key_in_a_nested_safe_contents_bag_is_not_tried(p12_tries):
    data = _key_sealed_in_a_layer(None, iterations=MAX_KDF_ITERATIONS + 1, nested=True)
    [obj] = SmartParser().parse(_pseudo_pem(data), RIGHT.decode())
    assert p12_tries == []
    assert f'{MAX_KDF_ITERATIONS + 1} iterations' in obj.error


def test_a_layer_that_cannot_be_opened_here_is_not_handed_on(p12_tries):
    pfx = asn1_pkcs12.Pfx.load(_pkcs12())
    safe = pfx.authenticated_safe
    for info in safe:
        if info['content_type'].native == 'encrypted_data':
            # PBES1 pbeWithSHA1AndDES-CBC: a scheme pyca may read and this module does not
            info['content']['encrypted_content_info']['content_encryption_algorithm'] = {
                'algorithm': 'pbes1_sha1_des', 'parameters': {'salt': b'\x00' * 8, 'iterations': 1}}
    pfx['auth_safe']['content'] = safe.dump(force=True)
    [obj] = SmartParser().parse(_pseudo_pem(pfx.dump(force=True)), RIGHT.decode())
    assert p12_tries == [] and 'is not supported' in obj.error


LEGACY_SCHEMES = ['PBE-SHA1-RC2-40', 'PBE-SHA1-RC2-128', 'PBE-SHA1-RC4-40', 'PBE-SHA1-RC4-128',
                  'PBE-SHA1-3DES', 'PBE-SHA1-2DES', 'AES-128-CBC', 'AES-256-CBC', 'DES-EDE3-CBC']


@pytest.mark.skipif(shutil.which('openssl') is None, reason='openssl CLI not available')
@pytest.mark.parametrize('scheme', LEGACY_SCHEMES)
def test_openssl_certificate_layers_open_here(tmp_path, p12_tries, scheme):
    """Every certificate encryption OpenSSL writes is opened here before pyca reads the archive."""
    key, cert = tmp_path / 'k.pem', tmp_path / 'c.pem'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:P-256',
                    '-nodes', '-keyout', key, '-out', cert, '-subj', '/CN=layers.test', '-days', '2'],
                   check=True, capture_output=True)
    out = tmp_path / 'b.p12'
    made = subprocess.run(['openssl', 'pkcs12', '-export', '-legacy', '-inkey', key, '-in', cert,
                           '-certpbe', scheme, '-keypbe', 'PBE-SHA1-3DES',
                           '-passout', 'pass:' + RIGHT.decode(), '-out', out], capture_output=True)
    if made.returncode:
        pytest.skip(f'this OpenSSL cannot write {scheme}')
    data = out.read_bytes()
    assert {o.type.value for o in SmartParser().parse(data, ['wrong', RIGHT.decode()])} == {
        'certificate', 'private_key'}
    assert p12_tries == [RIGHT]


def test_execute_without_write_cas_parses_once(app, auth_client, monkeypatch):
    calls = []
    real = SmartParser.parse

    def counted(self, content, password=None):
        calls.append(1)
        return real(self, content, password)
    monkeypatch.setattr(SmartParser, 'parse', counted)
    r = auth_client.post('/api/v2/account/apikeys', data=json.dumps(
        {'name': 'kdf-cap-no-cas', 'permissions': ['read:certificates', 'write:certificates']}),
        content_type='application/json')
    assert r.status_code == 201, r.data
    api_key = json.loads(r.data)['data']['key']
    r = app.test_client().post('/api/v2/import/execute', data=json.dumps(
        {'content': _sealed_pem(), 'password': 'wrong'}), content_type='application/json',
        headers={'X-API-Key': api_key})
    assert r.status_code == 200, r.data
    assert any(WRONG_PASSWORD in e for e in json.loads(r.data)['data']['errors'])
    assert len(calls) == 1


def test_one_parser_with_a_shared_budget_spends_it_across_parses(key_tries):
    parser = SmartParser(shared_budget=True)
    content = ''.join(_sealed_pem() for _ in range(MAX_PASSWORD_ATTEMPTS))
    assert all(o.error == WRONG_PASSWORD for o in parser.parse(content, 'wrong'))
    assert all(o.error == NOT_TRIED for o in parser.parse(content, 'wrong'))
    assert len(key_tries) == MAX_PASSWORD_ATTEMPTS


def test_the_converter_shares_one_budget_across_its_parses(auth_client, key_tries):
    sealed = ''.join(_sealed_pem() for _ in range(MAX_PASSWORD_ATTEMPTS))
    r = auth_client.post('/api/v2/tools/convert', data=json.dumps({
        'pem': sealed, 'private_key': sealed, 'password': 'wrong', 'output_format': 'pem'}),
        content_type='application/json')
    assert r.status_code == 400, r.data
    assert len(key_tries) == MAX_PASSWORD_ATTEMPTS

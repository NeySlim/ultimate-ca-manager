"""PKCS#12 layers opened before pyca: the MAC first, a wrong key refused at the last
block, pure Python RC2 capped, the formats OpenSSL writes all read. Counted, not timed."""
import datetime
import hashlib
import hmac
import os
import shutil
import subprocess

import pytest
from asn1crypto import algos, cms
from asn1crypto import pkcs12 as asn1_pkcs12
from cryptography import x509
from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives import padding as sym_padding
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.serialization import PrivateFormat, pkcs12
from cryptography.x509.oid import NameOID

from services.smart_import.parser import NOT_TRIED, SmartParser
from tests.test_smart_import_kdf_budget import derived, p12_tries  # noqa: F401 (fixtures)
from utils import pkcs12_layers

RIGHT = 'right-pass'
pytestmark = pytest.mark.skipif(shutil.which('openssl') is None, reason='openssl CLI not available')


@pytest.fixture(scope='module')
def pems(tmp_path_factory):
    folder = tmp_path_factory.mktemp('p12')
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'layers.test')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=2)).sign(key, hashes.SHA256()))
    (folder / 'k.pem').write_bytes(key.private_bytes(
        serialization.Encoding.PEM, PrivateFormat.PKCS8, serialization.NoEncryption()))
    (folder / 'c.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return folder


def _export(folder, *options, password=RIGHT):
    out = folder / 'out.p12'
    made = subprocess.run(['openssl', 'pkcs12', '-export', '-inkey', folder / 'k.pem',
                           '-in', folder / 'c.pem', *options, '-passout', 'pass:' + password,
                           '-out', out], capture_output=True)
    if made.returncode:
        pytest.skip(f'this OpenSSL cannot write {" ".join(options)}')
    return out.read_bytes()


def _layer_size(data):
    [layer] = pkcs12_layers.encrypted_layers(asn1_pkcs12.Pfx.load(data))
    return len(layer['encrypted_content'].native)


def _opens(data, password):
    objects = SmartParser().parse(data, password)
    return {o.type.value for o in objects} == {'certificate', 'private_key'} and not any(
        o.error for o in objects)


@pytest.fixture
def rc2_blocks(monkeypatch):
    """RC2 blocks decrypted in pure Python."""
    count = [0]
    real = pkcs12_layers._rc2_decrypt_block

    def counted(subkeys, block):
        count[0] += 1
        return real(subkeys, block)
    monkeypatch.setattr(pkcs12_layers, '_rc2_decrypt_block', counted)
    return count


# ---- cost of a wrong password ---------------------------------------------------

@pytest.mark.parametrize('password', ['wrong', None])
def test_a_wrong_password_stops_at_the_mac(pems, rc2_blocks, derived, p12_tries, password):  # noqa: F811
    data = _export(pems, '-legacy')  # RC2-40 certificate layer
    assert not _opens(data, password)
    assert rc2_blocks[0] == 0 and p12_tries == []
    # No password: tried absent, then empty, as OpenSSL does
    assert derived == [('mac', 3)] * (1 if password else 2)


def test_without_a_mac_a_wrong_password_decrypts_the_last_block_only(pems, rc2_blocks):
    # OpenSSL leaves the certificates unencrypted under -nomac unless -certpbe is given
    data = _export(pems, '-legacy', '-nomac', '-certpbe', 'PBE-SHA1-RC2-40')
    pfx, blocks = asn1_pkcs12.Pfx.load(data), _layer_size(data) // 8
    counts = []
    for i in range(16):
        rc2_blocks[0] = 0
        with pytest.raises(pkcs12_layers.WrongPassword):
            pkcs12_layers.open_pfx(pfx, f'wrong-{i}'.encode())
        counts.append(rc2_blocks[0])
    # About one wrong key in 256 unpads its last block by chance, then costs the layer
    assert set(counts) <= {1, 1 + blocks} and counts.count(1) >= 14, counts
    rc2_blocks[0] = 0
    assert len(pkcs12_layers.open_pfx(pfx, RIGHT.encode()).contents) == 1
    assert rc2_blocks[0] == 1 + blocks


def test_a_python_rc2_layer_above_the_cap_is_refused_before_any_derivation(
        pems, monkeypatch, rc2_blocks, derived, p12_tries):  # noqa: F811
    data = _export(pems, '-legacy')
    monkeypatch.setattr(pkcs12_layers, 'MAX_PYTHON_LAYER', _layer_size(data) - 1)
    [obj] = SmartParser().parse(data, RIGHT)
    assert 'RC2-40' in obj.error and 'refused' in obj.error
    assert derived == [] and rc2_blocks[0] == 0 and p12_tries == []
    monkeypatch.setattr(pkcs12_layers, 'MAX_PYTHON_LAYER', _layer_size(data))
    assert _opens(data, RIGHT)


@pytest.mark.parametrize('options', [[], ['-legacy', '-certpbe', 'PBE-SHA1-RC2-128'],
                                     ['-legacy', '-certpbe', 'PBE-SHA1-3DES']])
def test_the_cap_leaves_layers_pyca_decrypts_alone(pems, monkeypatch, rc2_blocks, options):
    data = _export(pems, *options)
    monkeypatch.setattr(pkcs12_layers, 'MAX_PYTHON_LAYER', 0)
    assert _opens(data, RIGHT) and rc2_blocks[0] == 0


# ---- PBES2 keyLength ----------------------------------------------------------------

def _with_layer_algorithm(data, change):
    pfx = asn1_pkcs12.Pfx.load(data)
    safe = pfx.authenticated_safe
    for info in safe:
        if info['content_type'].native == 'encrypted_data':
            change(info['content']['encrypted_content_info']['content_encryption_algorithm'])
    pfx['auth_safe']['content'] = safe.dump(force=True)
    return asn1_pkcs12.Pfx.load(pfx.dump(force=True))


@pytest.mark.parametrize('declared,opens', [(None, True), (32, True), (16, False), (32000, False)])
def test_a_pbes2_keylength_other_than_the_ciphers_is_refused(pems, derived, declared, opens):  # noqa: F811
    def change(algorithm):
        algorithm['parameters']['key_derivation_func']['parameters']['key_length'] = declared
    pfx = _with_layer_algorithm(_export(pems, '-nomac', '-certpbe', 'AES-256-CBC'), change)
    if opens:
        assert len(pkcs12_layers.open_pfx(pfx, RIGHT.encode()).contents) == 1
    else:
        with pytest.raises(pkcs12_layers.LayerUnsupported, match=f'keyLength {declared} does not match'):
            pkcs12_layers.open_pfx(pfx, RIGHT.encode())
        assert derived == []


# ---- layers resealed here: iterations below one, scrypt -----------------------------

def _bmp(password):
    return password.encode('utf-16-be') + b'\x00\x00'


def _resealed(algorithm, encrypt, block_bits, mac_iterations=2048):
    """A PKCS#12 whose certificate layer is resealed by *encrypt* under *algorithm*, MAC recomputed."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'reseal.test')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=1)).sign(key, hashes.SHA256()))
    original = asn1_pkcs12.Pfx.load(pkcs12.serialize_key_and_certificates(
        b'r', key, cert, None, serialization.BestAvailableEncryption(RIGHT.encode())))
    [contents] = pkcs12_layers.open_pfx(original, RIGHT.encode()).contents
    padder = sym_padding.PKCS7(block_bits).padder()
    sealed = encrypt(padder.update(contents) + padder.finalize())
    infos = [cms.ContentInfo({'content_type': 'encrypted_data', 'content': cms.EncryptedData({
        'version': 'v0', 'encrypted_content_info': {
            'content_type': 'data', 'content_encryption_algorithm': algorithm,
            'encrypted_content': sealed}})}) if info['content_type'].native == 'encrypted_data' else info
        for info in original.authenticated_safe]
    auth_safe = asn1_pkcs12.AuthenticatedSafe(infos).dump(force=True)
    salt = os.urandom(8)
    mac_key = pkcs12_layers.pkcs12_kdf(_bmp(RIGHT), salt, max(mac_iterations, 1), 3, 20)
    return asn1_pkcs12.Pfx({
        'version': 'v3', 'auth_safe': {'content_type': 'data', 'content': auth_safe},
        'mac_data': {'mac': {'digest_algorithm': {'algorithm': 'sha1'},
                             'digest': hmac.new(mac_key, auth_safe, hashlib.sha1).digest()},
                     'mac_salt': salt, 'iterations': mac_iterations}}).dump()


@pytest.mark.parametrize('iterations', [0, -1])
def test_iterations_below_one_hash_once_as_openssl_does(p12_tries, iterations):  # noqa: F811
    """OpenSSL hashes once for a count of zero, and refuses a negative one (both checked on pyca)."""
    salt = os.urandom(8)
    # The reference: one hash, which OpenSSL runs for any count below one
    key = pkcs12_layers.pkcs12_kdf(_bmp(RIGHT), salt, 1, 1, 24)
    iv = pkcs12_layers.pkcs12_kdf(_bmp(RIGHT), salt, 1, 2, 8)

    def encrypt(padded):
        encryptor = Cipher(TripleDES(key), modes.CBC(iv)).encryptor()
        return encryptor.update(padded) + encryptor.finalize()
    data = _resealed({'algorithm': 'pkcs12_sha1_tripledes_3key',
                      'parameters': {'salt': salt, 'iterations': iterations}}, encrypt, 64, iterations)
    if iterations < 0:
        with pytest.raises(ValueError):
            pkcs12.load_key_and_certificates(data, RIGHT.encode())
        [obj] = SmartParser().parse(data, RIGHT)
        assert 'iteration count -1 is negative' in obj.error and p12_tries == []
        return
    pkcs12.load_key_and_certificates(data, RIGHT.encode())  # pyca reads it so
    assert _opens(data, RIGHT) and p12_tries == [RIGHT.encode()]


def test_a_pbes2_scrypt_layer_opens_here(p12_tries):  # noqa: F811
    salt, iv = os.urandom(16), os.urandom(16)
    key = Scrypt(salt, 32, 1024, 8, 1).derive(RIGHT.encode())
    params = pkcs12_layers._ScryptParams({'salt': salt, 'cost_parameter': 1024, 'block_size': 8,
                                          'parallelization_parameter': 1})

    def encrypt(padded):
        encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
        return encryptor.update(padded) + encryptor.finalize()
    data = _resealed({'algorithm': 'pbes2', 'parameters': {
        'key_derivation_func': {'algorithm': '1.3.6.1.4.1.11591.4.11', 'parameters': params},
        'encryption_scheme': {'algorithm': 'aes256_cbc', 'parameters': iv}}}, encrypt, 128)
    pkcs12.load_key_and_certificates(data, RIGHT.encode())
    assert _opens(data, RIGHT) and p12_tries == [RIGHT.encode()]


def test_a_scrypt_layer_above_openssl_memory_is_refused_underived(p12_tries, monkeypatch):  # noqa: F811
    """N=2^15, r=8 needs 32 MiB and more: PKCS12_parse refuses it, nothing is derived here."""
    derivations = []
    monkeypatch.setattr(pkcs12_layers, 'Scrypt', lambda *a: derivations.append(a))
    salt, iv = os.urandom(16), os.urandom(16)
    params = pkcs12_layers._ScryptParams({'salt': salt, 'cost_parameter': 1 << 15, 'block_size': 8,
                                          'parallelization_parameter': 1})
    data = _resealed({'algorithm': 'pbes2', 'parameters': {
        'key_derivation_func': {'algorithm': '1.3.6.1.4.1.11591.4.11', 'parameters': params},
        'encryption_scheme': {'algorithm': 'aes256_cbc', 'parameters': iv}}}, lambda padded: padded, 128)
    objects = SmartParser().parse(data, RIGHT)
    assert any('scrypt with N=32768' in (o.error or '') for o in objects)
    with pytest.raises(pkcs12_layers.LayerUnsupported, match='more memory than OpenSSL allows'):
        pkcs12_layers.open_pfx(asn1_pkcs12.Pfx.load(data), RIGHT.encode())
    assert derivations == []


def test_a_pbmac1_salt_from_another_source_is_refused_not_crashed(pems):
    data = _export(pems, '-pbmac1_pbkdf2')
    pfx = asn1_pkcs12.Pfx.load(data)
    algorithm = pfx['mac_data']['mac']['digest_algorithm']
    params = algos.Pbmac1Params.load(algorithm['parameters'].dump())
    params['key_derivation_func']['parameters']['salt'] = algos.Pbkdf2Salt(
        name='other_source', value={'algorithm': '1.2.840.113549.1.5.12'})
    algorithm['parameters'] = params
    with pytest.raises(pkcs12_layers.LayerUnsupported, match='PBMAC1 salt'):
        pkcs12_layers.open_pfx(asn1_pkcs12.Pfx.load(pfx.dump(force=True)), RIGHT.encode())


# ---- what OpenSSL writes ---------------------------------------------------------------

SCHEMES = ['PBE-SHA1-RC2-40', 'PBE-SHA1-RC2-128', 'PBE-SHA1-RC4-40', 'PBE-SHA1-RC4-128',
           'PBE-SHA1-3DES', 'PBE-SHA1-2DES', 'PBE-MD5-DES', 'PBE-SHA1-DES', 'PBE-SHA1-RC2-64',
           'PBE-MD5-RC2-64', 'AES-128-CBC', 'AES-192-CBC', 'AES-256-CBC', 'AES-128-OFB',
           'AES-256-CFB', 'DES-EDE3-CBC', 'DES-CBC', 'RC2-CBC', 'RC2-40-CBC', 'RC2-64-CBC',
           'CAMELLIA-128-CBC', 'CAMELLIA-192-CBC', 'CAMELLIA-256-CBC', 'SM4-CBC', 'SM4-OFB',
           'SEED-CBC', 'BF-CBC', 'CAST5-CBC']


@pytest.mark.parametrize('legacy', [True, False], ids=['legacy', 'default'])
@pytest.mark.parametrize('scheme', SCHEMES)
@pytest.mark.parametrize('layer', ['-certpbe', '-keypbe'])
def test_openssl_encryptions_open_here(pems, p12_tries, layer, scheme, legacy):  # noqa: F811
    data = _export(pems, *(['-legacy'] if legacy else []), layer, scheme)
    assert _opens(data, ['wrong', RIGHT]) and p12_tries == [RIGHT.encode()]


@pytest.mark.parametrize('scheme', ['ARIA-128-CBC', 'ARIA-256-CBC'])
def test_an_aria_layer_is_refused_by_name(pems, p12_tries, derived, scheme):  # noqa: F811
    [obj] = SmartParser().parse(_export(pems, '-certpbe', scheme), RIGHT)
    assert 'ARIA' in obj.error and 'not supported' in obj.error
    assert p12_tries == [] and derived == []


@pytest.mark.parametrize('options', [
    ['-nomac', '-certpbe', 'AES-256-CBC'], ['-legacy', '-nomac', '-certpbe', 'PBE-SHA1-RC2-40'],
    ['-macalg', 'sha1'], ['-macalg', 'md5'],
    ['-macalg', 'sha512'], ['-macalg', 'sha3-256'], ['-macalg', 'sm3'], ['-macalg', 'ripemd160'],
    ['-pbmac1_pbkdf2'], ['-pbmac1_pbkdf2', '-pbmac1_pbkdf2_md', 'sha512'], ['-iter', '1'],
    ['-legacy', '-noiter'], ['-legacy', '-nomaciter']])
def test_openssl_macs_open_here(pems, p12_tries, options):  # noqa: F811
    assert _opens(_export(pems, *options), ['wrong', RIGHT]) and p12_tries == [RIGHT.encode()]


@pytest.mark.parametrize('options', [[], ['-legacy'], ['-nomac', '-certpbe', 'AES-256-CBC']])
@pytest.mark.parametrize('given', [None, ''])
def test_an_archive_without_password_opens_as_pyca_reads_it(pems, p12_tries, options, given):  # noqa: F811
    data = _export(pems, *options, password='')
    assert _opens(data, given) and len(p12_tries) == 1


def test_without_a_mac_an_empty_password_is_read_as_absent(pems, p12_tries):  # noqa: F811
    """OpenSSL opens a MAC-less archive with no password at all, never an empty BMPString."""
    data = _export(pems, '-legacy', '-nomac', '-certpbe', 'PBE-SHA1-RC2-40', password='')
    with pytest.raises(ValueError):
        pkcs12.load_key_and_certificates(data, None)
    assert not _opens(data, None) and p12_tries == []


# ---- the budget counts each derivation -------------------------------------------------

@pytest.mark.parametrize('options,password,cost', [
    ([], RIGHT, 5),            # AES: MAC and layer here, then MAC, layer and key in pyca
    (['-legacy'], RIGHT, 8),   # PKCS#12 PBE derives key and IV: MAC 1 + 2 here, 1 + 2 + 2 in pyca
    (['-legacy'], '', 10),     # no password: the MAC is tried absent, then empty, twice over
    (['-certpbe', 'NONE'], RIGHT, 2),  # no layer: pyca's MAC and key only
    (['-certpbe', 'NONE'], '', 3),     # pyca's two MAC tries, then its key
])
def test_a_pkcs12_open_spends_its_real_derivations(pems, p12_tries, options, password, cost):  # noqa: F811
    data = _export(pems, *options, password=password)
    parser = SmartParser(shared_budget=True)
    parser._attempts.left = cost - 1
    [obj] = parser.parse(data, password or None)
    assert obj.error == NOT_TRIED and p12_tries == []
    parser._attempts.left = cost
    assert {o.type.value for o in parser.parse(data, password or None)} == {'certificate', 'private_key'}
    assert parser._attempts.left == 0

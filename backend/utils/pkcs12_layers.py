"""The encryptedData layers of a PKCS#12 (RFC 7292 §4.1), opened here with a
candidate password so the bags inside are inspected before pyca derives any of
their keys. As in OpenSSL, the MAC is verified first and picks the one secret the
layers are opened with. PBES2 (PBKDF2 or scrypt, with the ciphers of _PBES2_CIPHERS),
PBES1 (RFC 8018 §6.1) and the six PKCS#12 PBE schemes of RFC 7292 Appendix C are
opened; anything else is refused, never handed on unseen."""
import hashlib
import hmac
from collections import namedtuple

from asn1crypto import algos, cms, core
from asn1crypto import pkcs12 as asn1_pkcs12
from cryptography.hazmat.decrepit.ciphers import algorithms as decrepit
from cryptography.hazmat.decrepit.ciphers import modes as decrepit_modes
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

# SafeContents nested in safeContentsBags deeper than this are refused
MAX_NESTING = 4
# RC2 at 40 or 64 effective bits is decrypted in pure Python: larger layers are refused
MAX_PYTHON_LAYER = 512 * 1024
# EVP_PBE_scrypt's default maxmem: OpenSSL refuses a costlier scrypt before deriving
SCRYPT_MAX_MEM = 32 * 1024 * 1024

_PBKDF2_HASHES = {'sha1': hashes.SHA1, 'sha224': hashes.SHA224, 'sha256': hashes.SHA256,
                  'sha384': hashes.SHA384, 'sha512': hashes.SHA512,
                  'sha512_224': hashes.SHA512_224, 'sha512_256': hashes.SHA512_256,
                  'sha3_224': hashes.SHA3_224, 'sha3_256': hashes.SHA3_256,
                  'sha3_384': hashes.SHA3_384, 'sha3_512': hashes.SHA3_512,
                  '1.2.840.113549.2.6': hashes.MD5}
_CBC, _OFB, _CFB = modes.CBC, decrepit_modes.OFB, decrepit_modes.CFB
# PBES2 encryption schemes OpenSSL reads (an OCTET STRING IV): OID -> name, cipher, key size, mode
_PBES2_CIPHERS = {
    '2.16.840.1.101.3.4.1.2': ('aes-128-cbc', algorithms.AES, 16, _CBC),
    '2.16.840.1.101.3.4.1.22': ('aes-192-cbc', algorithms.AES, 24, _CBC),
    '2.16.840.1.101.3.4.1.42': ('aes-256-cbc', algorithms.AES, 32, _CBC),
    '2.16.840.1.101.3.4.1.3': ('aes-128-ofb', algorithms.AES, 16, _OFB),
    '2.16.840.1.101.3.4.1.23': ('aes-192-ofb', algorithms.AES, 24, _OFB),
    '2.16.840.1.101.3.4.1.43': ('aes-256-ofb', algorithms.AES, 32, _OFB),
    '2.16.840.1.101.3.4.1.4': ('aes-128-cfb', algorithms.AES, 16, _CFB),
    '2.16.840.1.101.3.4.1.24': ('aes-192-cfb', algorithms.AES, 24, _CFB),
    '2.16.840.1.101.3.4.1.44': ('aes-256-cfb', algorithms.AES, 32, _CFB),
    '1.2.840.113549.3.7': ('des-ede3-cbc', decrepit.TripleDES, 24, _CBC),
    '1.3.14.3.2.7': ('des-cbc', lambda key: decrepit.TripleDES(key * 3), 8, _CBC),
    '1.2.392.200011.61.1.1.1.2': ('camellia-128-cbc', decrepit.Camellia, 16, _CBC),
    '1.2.392.200011.61.1.1.1.3': ('camellia-192-cbc', decrepit.Camellia, 24, _CBC),
    '1.2.392.200011.61.1.1.1.4': ('camellia-256-cbc', decrepit.Camellia, 32, _CBC),
    '1.2.156.10197.1.104.2': ('sm4-cbc', algorithms.SM4, 16, _CBC),
    '1.2.156.10197.1.104.3': ('sm4-ofb', algorithms.SM4, 16, _OFB),
    '1.2.156.10197.1.104.4': ('sm4-cfb', algorithms.SM4, 16, _CFB),
    '1.2.410.200004.1.4': ('seed-cbc', decrepit.SEED, 16, _CBC),
    '1.3.6.1.4.1.3029.1.2': ('bf-cbc', decrepit.Blowfish, 16, _CBC),
    '1.2.840.113533.7.66.10': ('cast5-cbc', decrepit.CAST5, 16, _CBC),
}
_RC2_CBC = '1.2.840.113549.3.2'
_RC2_VERSIONS = {160: 40, 120: 64, 58: 128}  # RFC 8018 B.2.3; OpenSSL reads these three only
_ARIA_ARC = '1.2.410.200046.1.1.'
_SCRYPT = '1.3.6.1.4.1.11591.4.11'
_PBES1 = {'pbes1_md5_des': ('md5', 'des'), 'pbes1_sha1_des': ('sha1', 'des'),
          'pbes1_md5_rc2': ('md5', 'rc2'), 'pbes1_sha1_rc2': ('sha1', 'rc2')}
_PBMAC1 = '1.2.840.113549.1.5.14'
_MAC_DIGESTS = {'1.2.156.10197.1.401': 'sm3', '1.3.36.3.2.1': 'ripemd160'}  # unnamed by asn1crypto
_MAX_MD_SIZE = 64  # OpenSSL refuses a PBMAC1 keyLength above EVP_MAX_MD_SIZE

# What pyca derives again for the MAC and the layers once the password is right
Opened = namedtuple('Opened', 'contents derivations')


class LayerUnsupported(ValueError):
    """An encryptedData this module cannot open, so its bags cannot be inspected."""


class WrongPassword(ValueError):
    """The candidate password does not open an encryptedData."""


class _ScryptParams(core.Sequence):
    _fields = [('salt', core.OctetString), ('cost_parameter', core.Integer),
               ('block_size', core.Integer), ('parallelization_parameter', core.Integer),
               ('key_length', core.Integer, {'optional': True})]


def encrypted_layers(pfx: asn1_pkcs12.Pfx) -> list:
    """The EncryptedContentInfo of each encryptedData in *pfx*'s AuthenticatedSafe."""
    return [info['content']['encrypted_content_info'] for info in pfx.authenticated_safe
            if info['content_type'].native == 'encrypted_data']


def plain_safe_contents(pfx: asn1_pkcs12.Pfx) -> list:
    """DER of each SafeContents held in a data ContentInfo, readable without a password."""
    return [info['content'].native for info in pfx.authenticated_safe
            if info['content_type'].native == 'data']


def shrouded_algorithms(safe_contents, depth: int = 0) -> list:
    """DER of the encryptionAlgorithm of every pkcs8ShroudedKeyBag in a SafeContents (DER
    or parsed), nested safeContentsBags included (OpenSSL opens those too)."""
    if depth > MAX_NESTING:
        raise LayerUnsupported('PKCS#12 bags nested too deep')
    if isinstance(safe_contents, (bytes, bytearray)):
        safe_contents = asn1_pkcs12.SafeContents.load(bytes(safe_contents), strict=True)
    found = []
    for bag in safe_contents:
        kind = bag['bag_id'].native
        if kind == 'pkcs8_shrouded_key_bag':
            found.append(bag['bag_value']['encryption_algorithm'].dump())
        elif kind == 'safe_contents':
            found += shrouded_algorithms(bag['bag_value'], depth + 1)
    return found


def derivations(algorithm) -> int:
    """Key derivations one secret costs under an encryption AlgorithmIdentifier (DER or
    parsed): two for a PKCS#12 PBE with an IV (key, then IV), one otherwise."""
    if isinstance(algorithm, (bytes, bytearray)):
        algorithm = algos.EncryptionAlgorithm.load(bytes(algorithm))
    name = algorithm['algorithm'].native
    return 2 if name.startswith('pkcs12_sha1_') and 'rc4' not in name else 1


def open_pfx(pfx: asn1_pkcs12.Pfx, password, spend=lambda count: None) -> Opened:
    """The SafeContents DER of every encryptedData of *pfx*, opened the way OpenSSL's
    PKCS12_parse does: the MAC picks the secret (an empty password is tried absent, then
    empty), each layer is opened with it. *spend(n)* runs before every n derivations."""
    layers = [_scheme(layer) for layer in encrypted_layers(pfx)]
    if not layers:
        # Nothing to open: pyca verifies the MAC, absent then empty for no password
        has_mac = not isinstance(pfx['mac_data'], core.Void)
        return Opened([], (1 if password else 2) if has_mac else 0)
    mac = _mac(pfx)
    if mac is None:
        secret, tries = password or None, 0
    else:
        for tries, secret in enumerate([password] if password else [None, b''], 1):
            spend(1)
            if mac(secret):
                break
        else:
            raise WrongPassword('Invalid password or PKCS12 data')
    contents = [_open(scheme, [secret], spend) for scheme in layers]
    return Opened(contents, tries + sum(scheme.derivations for scheme in layers))


def open_layer(layer: cms.EncryptedContentInfo, password, spend=lambda count: None) -> bytes:
    """The SafeContents DER an encryptedData holds, decrypted with *password* (bytes or
    None; for None both an absent and an empty one), without the MAC to pick the secret."""
    return _open(_scheme(layer), [password] if password else [None, b''], spend)


_Scheme = namedtuple('_Scheme', 'encode derive decrypt block derivations ciphertext')


def _open(scheme: _Scheme, secrets: list, spend) -> bytes:
    tried = []
    for secret in secrets:
        encoded = scheme.encode(secret)
        if encoded in tried:
            continue
        tried.append(encoded)
        spend(scheme.derivations)
        try:
            plain = _decrypt(scheme, encoded)
            shrouded_algorithms(plain)  # a wrong password leaves no SafeContents
            return plain
        except LayerUnsupported:
            raise
        except Exception:  # noqa: BLE001: padding or structure, both the password's
            continue
    raise WrongPassword('Invalid password or PKCS12 data')


def _decrypt(scheme: _Scheme, secret: bytes) -> bytes:
    key, iv = scheme.derive(secret)
    data, size = scheme.ciphertext, scheme.block
    if not size:
        return scheme.decrypt(key, iv, data)
    if not data or len(data) % size:
        raise ValueError('ciphertext is not whole blocks')
    # The last block alone, its predecessor as IV: a wrong key fails its padding at constant cost
    _unpad(scheme.decrypt(key, data[-2 * size:-size] if len(data) > size else iv, data[-size:]), size)
    return _unpad(scheme.decrypt(key, iv, data), size)


def _scheme(layer: cms.EncryptedContentInfo) -> _Scheme:
    """The decryption *layer* names, refused here (before any derivation) when it cannot run."""
    algorithm = layer['content_encryption_algorithm']
    ciphertext = layer['encrypted_content'].native
    if ciphertext is None:
        raise LayerUnsupported('PKCS#12 encryptedData without content')
    name = algorithm['algorithm'].native
    try:
        if name.startswith('pkcs12_sha1_'):
            return _pkcs12_pbe(algorithm, ciphertext)
        if name == 'pbes2':
            return _pbes2(algorithm, ciphertext)
        if name in _PBES1:
            return _pbes1(algorithm, ciphertext)
    except LayerUnsupported:
        raise
    except Exception as e:  # noqa: BLE001: parameters asn1crypto cannot read
        raise LayerUnsupported(f'PKCS#12 encryption {name} has parameters that cannot be read') from e
    if name.startswith('pbes1_md2'):
        raise LayerUnsupported(f'PKCS#12 encryption {name} is not supported: MD2 is not available')
    raise LayerUnsupported(f'PKCS#12 encryption {algorithm["algorithm"].dotted} is not supported')


def _raw(secret):
    return secret or b''


def _bmp(password) -> bytes:
    """OpenSSL's BMPString of a password: absent is empty, invalid UTF-8 is read as Latin-1."""
    if password is None:
        return b''
    try:
        text = password.decode('utf-8')
    except UnicodeDecodeError:
        text = password.decode('latin-1')
    return text.encode('utf-16-be') + b'\x00\x00'


def _pyca(factory, mode):
    def decrypt(key, iv, data):
        decryptor = Cipher(factory(key), mode(iv)).decryptor()
        return decryptor.update(data) + decryptor.finalize()
    return decrypt


def _python_rc2(effective_bits, ciphertext):
    if len(ciphertext) > MAX_PYTHON_LAYER:
        raise LayerUnsupported(f'PKCS#12 RC2-{effective_bits} encryptedData of {len(ciphertext)} '
                               f'bytes refused: at most {MAX_PYTHON_LAYER} are decrypted here')
    return lambda key, iv, data: rc2_cbc_decrypt(key, effective_bits, iv, data)


def _rc2(effective_bits, ciphertext):
    """RC2-CBC: pyca's at 128 effective bits, the pure Python one below that."""
    if effective_bits == 128:
        return _pyca(decrepit.RC2, _CBC)
    return _python_rc2(effective_bits, ciphertext)


def _pbes2(algorithm, ciphertext) -> _Scheme:
    params = algorithm['parameters']
    scheme = params['encryption_scheme']
    oid = scheme['algorithm'].dotted
    raw_params = scheme['parameters'].dump()
    if oid == _RC2_CBC:
        rc2 = algos.Rc2Params.load(raw_params)
        bits = _RC2_VERSIONS.get(rc2['rc2_parameter_version'].native)
        if bits is None:
            raise LayerUnsupported('PKCS#12 PBES2 rc2-cbc without an effective key size OpenSSL reads')
        label, key_size, block, iv = f'rc2-{bits}-cbc', bits // 8, 8, rc2['iv'].native
        if len(iv) != 8:
            raise LayerUnsupported('PKCS#12 PBES2 rc2-cbc with an IV of the wrong size')
        decrypt = _rc2(bits, ciphertext)
    elif oid in _PBES2_CIPHERS:
        label, factory, key_size, mode = _PBES2_CIPHERS[oid]
        size, iv = factory(bytes(key_size)).block_size // 8, core.OctetString.load(raw_params).native
        decrypt, block = _pyca(factory, mode), (size if mode is _CBC else 0)
        if len(iv) != size:
            raise LayerUnsupported(f'PKCS#12 PBES2 {label} with an IV of the wrong size')
    elif oid.startswith(_ARIA_ARC):
        raise LayerUnsupported(f'PKCS#12 PBES2 encryption ARIA ({oid}) is not supported')
    else:
        raise LayerUnsupported(f'PKCS#12 PBES2 encryption {oid} is not supported')
    derive_key = _pbes2_kdf(params['key_derivation_func'], key_size, label)
    return _Scheme(_raw, lambda secret: (derive_key(secret), iv), decrypt, block, 1, ciphertext)


def scrypt_refused(n, r, p) -> bool:
    """True for scrypt parameters OpenSSL refuses or that need more than SCRYPT_MAX_MEM."""
    if n < 2 or n & (n - 1) or r < 1 or p < 1:
        return True
    return 128 * r * (n + 2) + 128 * r * p > SCRYPT_MAX_MEM


def _pbes2_kdf(kdf, key_size, label):
    """PBKDF2 or scrypt at the cipher's key size; OpenSSL refuses another declared keyLength."""
    oid = kdf['algorithm'].dotted
    if oid == _SCRYPT:
        p = _ScryptParams.load(kdf['parameters'].dump())
        declared = p['key_length'].native
        salt, n = p['salt'].native, p['cost_parameter'].native
        r, par = p['block_size'].native, p['parallelization_parameter'].native
        if scrypt_refused(n, r, par):
            raise LayerUnsupported(f'PKCS#12 scrypt with N={n}, r={r}, p={par} needs more memory '
                                   'than OpenSSL allows')
        derive = lambda secret: Scrypt(salt, key_size, n, r, par).derive(secret)  # noqa: E731
    elif kdf['algorithm'].native == 'pbkdf2':
        p = kdf['parameters']
        digest = _PBKDF2_HASHES.get(p['prf']['algorithm'].native)
        if digest is None:
            raise LayerUnsupported(f'PKCS#12 PBKDF2 PRF {p["prf"]["algorithm"].dotted} is not supported')
        if p['salt'].name != 'specified':
            raise LayerUnsupported('PKCS#12 PBKDF2 salt from another source is not supported')
        declared, salt, rounds = p['key_length'].native, p['salt'].chosen.native, p['iteration_count'].native
        if rounds < 1:
            raise LayerUnsupported('PKCS#12 PBKDF2 with fewer than one iteration')
        derive = lambda secret: _pbkdf2(digest, key_size, salt, rounds, secret)  # noqa: E731
    else:
        raise LayerUnsupported(f'PKCS#12 PBES2 key derivation {oid} is not supported')
    if declared is not None and declared != key_size:
        raise LayerUnsupported(f'PKCS#12 PBES2 keyLength {declared} does not match {label}')
    return derive


def _pbkdf2(digest, size, salt, rounds, secret) -> bytes:
    return PBKDF2HMAC(digest(), size, salt, rounds).derive(secret)


def _pbes1(algorithm, ciphertext) -> _Scheme:
    digest, cipher = _PBES1[algorithm['algorithm'].native]
    salt, rounds = algorithm['parameters']['salt'].native, _iterations(algorithm['parameters']['iterations'])
    decrypt = _rc2(64, ciphertext) if cipher == 'rc2' else _pyca(lambda key: decrepit.TripleDES(key * 3), _CBC)

    def derive(secret):
        dk = pbkdf1(digest, secret, salt, rounds)
        return dk[:8], dk[8:16]
    return _Scheme(_raw, derive, decrypt, 8, 1, ciphertext)


def pbkdf1(digest: str, password: bytes, salt: bytes, iterations: int) -> bytes:
    """RFC 8018 §5.1, iterations below one counted as one, as OpenSSL does."""
    out = hashlib.new(digest, password + salt).digest()
    for _ in range(max(iterations, 1) - 1):
        out = hashlib.new(digest, out).digest()
    return out


def _pkcs12_pbe(algorithm, ciphertext) -> _Scheme:
    salt, size = algorithm.kdf_salt, algorithm.key_length
    rounds = _iterations(algorithm['parameters']['iterations'])
    cipher = algorithm.encryption_cipher
    if cipher == 'rc4':
        return _Scheme(_bmp, lambda secret: (pkcs12_kdf(secret, salt, rounds, 1, size), None),
                       lambda key, iv, data: Cipher(decrepit.ARC4(key), None).decryptor().update(data),
                       0, 1, ciphertext)
    if cipher == 'tripledes':
        # A two-key 3DES key is K1 K2 K1
        decrypt = _pyca(lambda key: decrepit.TripleDES(key if len(key) == 24 else key + key[:8]), _CBC)
    else:
        decrypt = _rc2(size * 8, ciphertext)
    return _Scheme(_bmp, lambda secret: (pkcs12_kdf(secret, salt, rounds, 1, size),
                                         pkcs12_kdf(secret, salt, rounds, 2, 8)),
                   decrypt, 8, 2, ciphertext)


def _mac(pfx: asn1_pkcs12.Pfx):
    """``verify(secret)`` for the MAC of *pfx* (PKCS12_verify_mac), None when it has none."""
    mac_data = pfx['mac_data']
    if isinstance(mac_data, core.Void):
        return None
    algorithm = mac_data['mac']['digest_algorithm']
    expected = mac_data['mac']['digest'].native
    content = pfx['auth_safe']['content'].native
    if algorithm['algorithm'].dotted == _PBMAC1:
        try:
            params = algos.Pbmac1Params.load(algorithm['parameters'].dump())
            kdf, digest = params['key_derivation_func'], params['message_auth_scheme']['algorithm'].native
            p = kdf['parameters']
            prf, size = _PBKDF2_HASHES.get(p['prf']['algorithm'].native), p['key_length'].native
            salt, rounds = p['salt'].chosen.native, p['iteration_count'].native
        except Exception as e:  # noqa: BLE001
            raise LayerUnsupported('PKCS#12 PBMAC1 parameters cannot be read') from e
        if p['salt'].name != 'specified':
            raise LayerUnsupported('PKCS#12 PBMAC1 salt from another source is not supported')
        if prf is None or kdf['algorithm'].native != 'pbkdf2' or not _hash_available(digest):
            raise LayerUnsupported('PKCS#12 PBMAC1 algorithms are not supported')
        if size is None or not 0 < size <= _MAX_MD_SIZE:
            raise LayerUnsupported(f'PKCS#12 PBMAC1 keyLength {size} is not supported')
        if rounds < 1:
            raise LayerUnsupported('PKCS#12 PBMAC1 with fewer than one iteration')
        key = lambda secret: _pbkdf2(prf, size, salt, rounds, _raw(secret))  # noqa: E731
    else:
        digest = _MAC_DIGESTS.get(algorithm['algorithm'].dotted, algorithm['algorithm'].native)
        if not _hash_available(digest):
            raise LayerUnsupported(f'PKCS#12 MAC digest {algorithm["algorithm"].dotted} is not supported')
        salt, rounds = mac_data['mac_salt'].native, _iterations(mac_data['iterations'])
        size = hashlib.new(digest).digest_size
        key = lambda secret: pkcs12_kdf(_bmp(secret), salt, rounds, 3, size, digest)  # noqa: E731
    return lambda secret: hmac.compare_digest(hmac.new(key(secret), content, digest).digest(), expected)


def _iterations(value) -> int:
    """A PKCS#12 KDF or PBKDF1 count: OpenSSL hashes once below one, but refuses a negative one."""
    if value.native < 0:
        raise LayerUnsupported(f'PKCS#12 iteration count {value.native} is negative')
    return value.native


def _hash_available(name) -> bool:
    try:
        return hashlib.new(name).digest_size > 0  # SHAKE has no fixed size
    except (TypeError, ValueError):
        return False


def _unpad(data: bytes, size: int) -> bytes:
    pad = data[-1] if data else 0
    if not data or len(data) % size or not 1 <= pad <= size or data[-pad:] != bytes([pad]) * pad:
        raise ValueError('bad padding')
    return data[:-pad]


def pkcs12_kdf(password: bytes, salt: bytes, iterations: int, purpose: int, size: int,
               digest: str = 'sha1') -> bytes:
    """RFC 7292 Appendix B.2; *password* is already a BMPString. OpenSSL hashes at least once."""
    u, v = hashlib.new(digest).digest_size, hashlib.new(digest).block_size
    new = getattr(hashlib, digest, None) or (lambda data: hashlib.new(digest, data))

    def fill(data):
        length = v * -(-len(data) // v)
        return (data * (length // len(data) + 1))[:length] if data else b''

    i = bytearray(fill(salt) + fill(password))
    out = b''
    while len(out) < size:
        a = bytes([purpose]) * v + bytes(i)
        for _ in range(max(iterations, 1)):
            a = new(a).digest()
        out += a
        b = int.from_bytes((a * (v // u + 1))[:v], 'big')
        for j in range(0, len(i), v):
            block = (int.from_bytes(i[j:j + v], 'big') + b + 1) % (1 << (8 * v))
            i[j:j + v] = block.to_bytes(v, 'big')
    return out[:size]


# RFC 2268 §2: PITABLE, a permutation of 0..255 derived from the digits of pi
_PITABLE = bytes.fromhex(
    'd978f9c419ddb5ed28e9fd794aa0d89dc67e37832b76538e624c6488448bfba2'
    '179a59f587b34f1361456d8d09817d32bd8f40eb86b77b0bf09521225c6b4e82'
    '54d66593ce60b21c7356c014a78cf1dc1275ca1f3bbee4d1423dd430a33cb626'
    '6fbf0eda4669075727f21d9bbc944303f811c7f690ef3ee706c3d52fc8661ed7'
    '08e8eade8052eef784aa72ac354d6a2a961ad2715a1549744b9fd05e0418a4ec'
    'c2e0416e0f51cbcc2491af50a1f47039997c3a8523b8b47afc02365b25559731'
    '2d5dfa98e38a92ae05df2910676cbac9d300e6cfe19ea82c6316013f58e289a9'
    '0d38341bab33ffb0bb480c5fb9b1cd2ec5f3db47e5a59c770aa62068fe7fc1ad')


def _rc2_key_schedule(key: bytes, effective_bits: int) -> list:
    """RFC 2268 §2: the 64 16-bit subkeys of *key* at *effective_bits*."""
    t, t8 = len(key), (effective_bits + 7) // 8
    tm = 255 % (1 << (8 + effective_bits - 8 * t8))
    expanded = bytearray(128)
    expanded[:t] = key
    for i in range(t, 128):
        expanded[i] = _PITABLE[(expanded[i - 1] + expanded[i - t]) & 0xff]
    expanded[128 - t8] = _PITABLE[expanded[128 - t8] & tm]
    for i in range(127 - t8, -1, -1):
        expanded[i] = _PITABLE[expanded[i + 1] ^ expanded[i + t8]]
    return [expanded[2 * i] | expanded[2 * i + 1] << 8 for i in range(64)]


def _rc2_decrypt_block(subkeys: list, block: bytes) -> bytes:
    """RFC 2268 §4: one 64-bit block decrypted."""
    r = [block[2 * i] | block[2 * i + 1] << 8 for i in range(4)]
    shifts = (1, 2, 3, 5)
    j = 63

    def unmix():
        nonlocal j
        for i in (3, 2, 1, 0):
            s = shifts[i]
            r[i] = ((r[i] >> s) | (r[i] << (16 - s))) & 0xffff
            r[i] = (r[i] - subkeys[j] - (r[i - 1] & r[i - 2]) - (~r[i - 1] & r[i - 3])) & 0xffff
            j -= 1

    def unmash():
        for i in (3, 2, 1, 0):
            r[i] = (r[i] - subkeys[r[i - 1] & 63]) & 0xffff

    for rounds in (5, None, 6, None, 5):
        if rounds is None:
            unmash()
        else:
            for _ in range(rounds):
                unmix()
    return b''.join(word.to_bytes(2, 'little') for word in r)


def rc2_cbc_decrypt(key: bytes, effective_bits: int, iv: bytes, ciphertext: bytes) -> bytes:
    """RC2-CBC decryption without unpadding; pyca has RC2 at 128 effective bits only."""
    if len(ciphertext) % 8:
        raise ValueError('RC2 ciphertext is not whole blocks')
    subkeys = _rc2_key_schedule(key, effective_bits)
    out, previous = bytearray(), iv
    for k in range(0, len(ciphertext), 8):
        block = ciphertext[k:k + 8]
        out += bytes(x ^ y for x, y in zip(_rc2_decrypt_block(subkeys, block), previous))
        previous = block
    return bytes(out)

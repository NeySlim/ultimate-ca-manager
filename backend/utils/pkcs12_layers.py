"""The encryptedData layers of a PKCS#12 (RFC 7292 §4.1), opened here with a
candidate password so the bags inside are inspected before pyca derives any of
their keys. PBES2 (PBKDF2, AES-CBC or 3DES) and the six PKCS#12 PBE schemes of
RFC 7292 Appendix C; anything else is refused, never handed on unseen."""
import hashlib

from asn1crypto import cms
from asn1crypto import pkcs12 as asn1_pkcs12
from cryptography.hazmat.decrepit.ciphers import algorithms as decrepit
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# SafeContents nested in safeContentsBags deeper than this are refused
MAX_NESTING = 4

_PBKDF2_HASHES = {'sha1': hashes.SHA1, 'sha224': hashes.SHA224, 'sha256': hashes.SHA256,
                  'sha384': hashes.SHA384, 'sha512': hashes.SHA512,
                  'sha512_224': hashes.SHA512_224, 'sha512_256': hashes.SHA512_256}
_PBES2_CIPHERS = {'aes128_cbc': 'aes', 'aes192_cbc': 'aes', 'aes256_cbc': 'aes',
                  'tripledes_3key': 'tripledes'}


class LayerUnsupported(ValueError):
    """An encryptedData this module cannot open, so its bags cannot be inspected."""


class WrongPassword(ValueError):
    """The candidate password does not open an encryptedData."""


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


def open_layer(layer: cms.EncryptedContentInfo, password) -> bytes:
    """The SafeContents DER an encryptedData holds, decrypted with *password* (bytes or None)."""
    algorithm = layer['content_encryption_algorithm']
    ciphertext = layer['encrypted_content'].native
    if ciphertext is None:
        raise LayerUnsupported('PKCS#12 encryptedData without content')
    name = algorithm['algorithm'].native
    if name.startswith('pkcs12_sha1_'):
        # OpenSSL reads an absent password as an empty BMPString, an empty one as its terminator
        attempts = [_bmp(password)] if password else [b'', b'\x00\x00']
        decrypt = _pkcs12_pbe
    elif name == 'pbes2':
        attempts = [password or b'']
        decrypt = _pbes2
    else:
        raise LayerUnsupported(f'PKCS#12 encryption {algorithm["algorithm"].dotted} is not supported')
    for secret in attempts:
        try:
            plain = decrypt(algorithm, secret, ciphertext)
            shrouded_algorithms(plain)  # a wrong password leaves no SafeContents
            return plain
        except LayerUnsupported:
            raise
        except Exception:  # noqa: BLE001: padding or structure, both the password's
            continue
    raise WrongPassword('Invalid password or PKCS12 data')


def _bmp(password: bytes) -> bytes:
    return password.decode('utf-8').encode('utf-16-be') + b'\x00\x00'


def _pbes2(algorithm, password: bytes, ciphertext: bytes) -> bytes:
    if algorithm.kdf != 'pbkdf2':
        raise LayerUnsupported(f'PKCS#12 PBES2 key derivation {algorithm.kdf} is not supported')
    digest = _PBKDF2_HASHES.get(algorithm.kdf_hmac)
    cipher = _PBES2_CIPHERS.get(algorithm['parameters']['encryption_scheme']['algorithm'].native)
    if digest is None or cipher is None:
        raise LayerUnsupported('PKCS#12 PBES2 parameters are not supported')
    key = PBKDF2HMAC(digest(), algorithm.key_length, algorithm.kdf_salt,
                     algorithm.kdf_iterations).derive(password)
    block = algorithms.AES(key) if cipher == 'aes' else decrepit.TripleDES(key)
    return _cbc(block, algorithm.encryption_iv, ciphertext)


def _pkcs12_pbe(algorithm, password: bytes, ciphertext: bytes) -> bytes:
    salt, rounds, size = algorithm.kdf_salt, algorithm.kdf_iterations, algorithm.key_length
    key = pkcs12_kdf(password, salt, rounds, 1, size)
    cipher = algorithm.encryption_cipher
    if cipher == 'rc4':
        return Cipher(decrepit.ARC4(key), None).decryptor().update(ciphertext)
    iv = pkcs12_kdf(password, salt, rounds, 2, 8)
    if cipher == 'tripledes':
        # A two-key 3DES key is K1 K2 K1
        return _cbc(decrepit.TripleDES(key if len(key) == 24 else key + key[:8]), iv, ciphertext)
    return _unpad(rc2_cbc_decrypt(key, size * 8, iv, ciphertext), 8)


def _cbc(block, iv: bytes, ciphertext: bytes) -> bytes:
    decryptor = Cipher(block, modes.CBC(iv)).decryptor()
    return _unpad(decryptor.update(ciphertext) + decryptor.finalize(), block.block_size // 8)


def _unpad(data: bytes, size: int) -> bytes:
    pad = data[-1] if data else 0
    if not data or len(data) % size or not 1 <= pad <= size or data[-pad:] != bytes([pad]) * pad:
        raise ValueError('bad padding')
    return data[:-pad]


def pkcs12_kdf(password: bytes, salt: bytes, iterations: int, purpose: int, size: int) -> bytes:
    """RFC 7292 Appendix B.2 with SHA-1; *password* is already a BMPString."""
    u, v = 20, 64

    def fill(data):
        length = v * -(-len(data) // v)
        return (data * (length // len(data) + 1))[:length] if data else b''

    i = bytearray(fill(salt) + fill(password))
    out = b''
    while len(out) < size:
        a = bytes([purpose]) * v + bytes(i)
        for _ in range(iterations):
            a = hashlib.sha1(a).digest()
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

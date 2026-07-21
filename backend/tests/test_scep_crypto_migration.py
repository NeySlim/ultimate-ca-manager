"""Regression test for the SCEP pyCrypto -> cryptography migration.

The SCEP crypto modules must not import the unmaintained pyCrypto (`Crypto`), and the
CBC ciphers they now use (AES-128/256-CBC and 3DES-CBC) must round-trip. These are standard
algorithms, so the ciphertext is byte-identical to what pyCrypto produced — existing SCEP
clients' messages keep decrypting unchanged.
"""
import ast
import os
import secrets

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES

SCEP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "services", "scep")


def _imports_pycrypto(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[0] == "Crypto":
            return True
        if isinstance(n, ast.Import) and any(a.name.split(".")[0] == "Crypto" for a in n.names):
            return True
    return False


def test_scep_modules_do_not_import_pycrypto():
    offenders = [f for f in ("crypto_helpers.py", "message_parser.py")
                 if _imports_pycrypto(os.path.join(SCEP, f))]
    assert not offenders, f"SCEP still imports the unmaintained pyCrypto: {offenders}"


def _cbc_roundtrip(alg, key_len, block):
    key, iv = secrets.token_bytes(key_len), secrets.token_bytes(block)
    data = b"SCEP degenerate pkcs7 payload " * 3
    pad = block - (len(data) % block)
    padded = data + bytes([pad] * pad)
    enc = Cipher(alg(key), modes.CBC(iv)).encryptor()
    ct = enc.update(padded) + enc.finalize()
    dec = Cipher(alg(key), modes.CBC(iv)).decryptor()
    pt = dec.update(ct) + dec.finalize()
    assert pt[:-pt[-1]] == data


def test_aes128_cbc_roundtrip():
    _cbc_roundtrip(algorithms.AES, 16, 16)


def test_aes256_cbc_roundtrip():
    _cbc_roundtrip(algorithms.AES, 32, 16)


def test_3des_cbc_roundtrip():
    _cbc_roundtrip(TripleDES, 24, 8)

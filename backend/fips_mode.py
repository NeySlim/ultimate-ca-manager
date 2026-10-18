"""FIPS mode: asked for with UCM_FIPS=1, in force only while the crypto
libraries run on an active FIPS provider; enforce_at_startup() refuses to
start when the two disagree."""
import ctypes
import os

PROBLEM_TYPE = 'urn:ucm:problem:fips-restricted'


class FipsRestricted(ValueError):
    """An operation FIPS mode refuses; the message names it."""


def requested() -> bool:
    return os.environ.get('UCM_FIPS', '').strip().lower() in ('1', 'true', 'yes', 'on')


def provider_active() -> bool:
    """Both libraries on a FIPS provider: cryptography for keys and
    certificates, hashlib and ssl for password hashes and TLS."""
    from cryptography.hazmat.bindings._rust import openssl as rust_openssl
    import _hashlib
    get_fips_mode = getattr(_hashlib, 'get_fips_mode', None)
    return bool(rust_openssl.is_fips_enabled()) and bool(get_fips_mode and get_fips_mode())


def enabled() -> bool:
    return requested() and provider_active()


def refuse(what: str) -> None:
    """Raise FipsRestricted for ``what`` ('Ed25519 keys') in FIPS mode."""
    if enabled():
        raise FipsRestricted(f'{what} not available in FIPS mode')


def library_version() -> str:
    from cryptography.hazmat.backends.openssl.backend import backend
    return backend.openssl_version_text()


class _Param(ctypes.Structure):
    _fields_ = [('key', ctypes.c_char_p), ('data_type', ctypes.c_uint),
                ('data', ctypes.c_void_p), ('data_size', ctypes.c_size_t),
                ('return_size', ctypes.c_size_t)]


_UTF8_PTR = 6
_PROVIDER_CB = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)


def provider_info():
    """Name, version and build of the loaded 'fips' provider, read from the
    process's libcrypto; None when no such provider is loaded."""
    try:
        lib = ctypes.CDLL('libcrypto.so.3')
        lib.OSSL_PROVIDER_get0_name.restype = ctypes.c_char_p
        lib.OSSL_PROVIDER_get0_name.argtypes = [ctypes.c_void_p]
        lib.OSSL_PROVIDER_get_params.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        lib.OSSL_PROVIDER_do_all.argtypes = [ctypes.c_void_p, _PROVIDER_CB, ctypes.c_void_p]
    except (OSError, AttributeError):
        return None
    found = []

    def visit(prov, _data):
        if lib.OSSL_PROVIDER_get0_name(prov) == b'fips':
            found.append(prov)
        return 1

    lib.OSSL_PROVIDER_do_all(None, _PROVIDER_CB(visit), None)
    if not found:
        return None
    keys = ('name', 'version', 'buildinfo')
    values = [ctypes.c_char_p() for _ in keys]
    params = (_Param * (len(keys) + 1))(*[
        _Param(k.encode(), _UTF8_PTR, ctypes.cast(ctypes.byref(v), ctypes.c_void_p),
               ctypes.sizeof(v), 0) for k, v in zip(keys, values)])
    if not lib.OSSL_PROVIDER_get_params(found[0], params):
        return None
    return {k: (v.value or b'').decode() for k, v in zip(keys, values)}


def self_tests() -> None:
    """Raise RuntimeError unless approved operations work and refused ones
    fail, in both libraries: proof that the provider, not a fallback, answers."""
    import hashlib
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    try:
        key = ec.derive_private_key(0x5EED, ec.SECP256R1())
        signature = key.sign(b'ucm', ec.ECDSA(hashes.SHA256()))
        key.public_key().verify(signature, b'ucm', ec.ECDSA(hashes.SHA256()))
        aes = AESGCM(bytes(32))
        if aes.decrypt(bytes(12), aes.encrypt(bytes(12), b'ucm', None), None) != b'ucm':
            raise RuntimeError('AES-GCM round trip differs')
        hashlib.pbkdf2_hmac('sha256', b'ucm-self-test', b'0123456789abcdef', 1000)
    except (InvalidSignature, ValueError) as e:
        raise RuntimeError(f'approved operation failed: {e}') from e
    for name, refused in (('MD5 in cryptography', lambda: hashes.Hash(hashes.MD5())),
                          ('scrypt in hashlib', lambda: hashlib.scrypt(
                              b'x', salt=b'0123456789abcdef', n=2, r=1, p=1))):
        try:
            refused()
        except Exception:
            continue
        raise RuntimeError(f'{name} still works: the FIPS provider is not the one answering')


def status() -> dict:
    """What the API shows: asked for, in force, library and provider."""
    active = provider_active()
    return {'fips_requested': requested(), 'fips_active': requested() and active,
            'provider_active': active, 'library': library_version(),
            'provider': provider_info() if active else None}


def enforce_at_startup(log, database_url: str = '') -> None:
    """UCM_FIPS=1 without an active provider, with a failed self-test or with a
    PostgreSQL connection outside TLS stops the process before it serves anything."""
    if not requested():
        return
    from cryptography.hazmat.bindings._rust import openssl as rust_openssl
    import _hashlib
    missing = []
    if not rust_openssl.is_fips_enabled():
        missing.append('cryptography is not running on a FIPS provider')
    if not getattr(_hashlib, 'get_fips_mode', lambda: 0)():
        missing.append('hashlib is not running on a FIPS provider')
    if missing:
        log.error('UCM_FIPS=1 but %s (check OPENSSL_CONF); refusing to start', '; '.join(missing))
        raise SystemExit(1)
    try:
        self_tests()
    except RuntimeError as e:
        log.error('FIPS self-test failed: %s; refusing to start', e)
        raise SystemExit(1)
    from utils.db_url import postgres_tls_problem
    problem = postgres_tls_problem(database_url)
    if problem:
        log.error('UCM_FIPS=1 but DATABASE_URL reaches PostgreSQL over TCP with %s: '
                  'use sslmode=require or stricter, or a Unix socket; refusing to start', problem)
        raise SystemExit(1)
    info = provider_info() or {}
    log.info('FIPS mode active: %s %s (library %s)', info.get('name', 'unknown provider'),
             info.get('version', ''), library_version())

"""FIPS mode: asked for with UCM_FIPS=1, in force only while the crypto
libraries run on an active FIPS provider. Refusing to start when the two
disagree is the startup check's job, not this module's."""
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

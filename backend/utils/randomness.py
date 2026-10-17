"""Random bytes for keys, IVs, salts and nonces (#399)."""
import os
import ssl

import fips_mode


def csp_bytes(n: int) -> bytes:
    """n bytes from the FIPS provider's DRBG in FIPS mode, os.urandom otherwise."""
    if fips_mode.enabled():
        return ssl.RAND_bytes(n)
    return os.urandom(n)

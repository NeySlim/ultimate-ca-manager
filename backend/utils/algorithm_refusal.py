"""Refusals tied to a key algorithm: an ML-DSA key in PKCS#12 or JKS, an ML-DSA key
file without its seed. Answered 400 with their own problem type and the stable
reason ``unsupported_for_key_algorithm``; they derive from FipsRestricted so every
route that already lets FIPS refusals through lets these through too."""
import fips_mode

PROBLEM_TYPE = 'urn:ucm:problem:unsupported-for-key-algorithm'
REASON = 'unsupported_for_key_algorithm'


class UnsupportedForKeyAlgorithm(fips_mode.FipsRestricted):
    """What was asked cannot be done with this key algorithm; the message says why."""

    def __init__(self, message, *, key_algorithm=None, export_format=None):
        super().__init__(message)
        self.details = {'reason': REASON, 'key_algorithm': key_algorithm, 'format': export_format}


_CONTAINER_NAMES = {'pkcs12': 'PKCS#12', 'p12': 'PKCS#12', 'pfx': 'PKCS#12', 'jks': 'JKS'}
PEM_INSTEAD = 'export the certificate and the private key as PEM (PKCS#8) instead'


def refuse_unexportable_key(private_key, export_format: str, hint=PEM_INSTEAD) -> None:
    """UnsupportedForKeyAlgorithm when *private_key* cannot go into *export_format*
    ('pkcs12', 'pfx', 'jks'); called before the container is built. *hint* is the way
    out the caller's route offers, None when it offers none."""
    from utils import key_algorithms
    fmt = 'pkcs12' if export_format == 'p12' else export_format
    if fmt in key_algorithms.export_formats_for(private_key):
        return
    label = key_algorithms.label_for_private_key(private_key)
    name = _CONTAINER_NAMES.get(export_format, export_format)
    raise UnsupportedForKeyAlgorithm(
        f'{label} keys cannot be exported as {name}' + (f': {hint}' if hint else ''),
        key_algorithm=label, export_format=name)

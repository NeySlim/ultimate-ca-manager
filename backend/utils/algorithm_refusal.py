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

"""Whether a CA can be configured as a signer (review of #343).

The protocol endpoints refuse a CA that cannot sign at request time; the
settings that name a CA apply the same rule when the CA is chosen, so an
enrolment does not fail later for a reason the operator was never told.
"""
from utils import key_algorithms


def signing_ca_problem(ca):
    """Why *ca* cannot sign, or None."""
    if ca is None:
        return 'CA not found'
    if ca.is_pending or not ca.crt:
        return 'CA is awaiting its certificate'
    if ca.is_revoked:
        return 'CA is revoked'
    if ca.revoked_in_chain:
        return 'A CA above this one is revoked'
    if ca.offline:
        return 'CA is offline'
    if not ca.has_private_key:
        return 'CA has no private key'
    return None


def scep_ca_problem(ca):
    """Why *ca* cannot serve SCEP, or None: clients encrypt their request to the CA's RSA key."""
    problem = signing_ca_problem(ca)
    if problem:
        return f'Selected CA cannot sign: {problem}'
    if ca.uses_hsm:
        return ('Selected CA is HSM-backed: SCEP requires RSA envelope decryption, '
                'unavailable for HSM keys')
    if not str(ca.key_type).startswith('RSA'):
        return (f'Selected CA key is {ca.key_type}: SCEP clients encrypt their request '
                'to an RSA key')
    return None


def xcep_ca_problem(ca):
    """Why *ca* cannot be the XCEP/WSTEP CA, or None: Windows validates no EdDSA signature."""
    problem = signing_ca_problem(ca)
    if problem:
        return problem
    alg = key_algorithms.get(ca.key_type)
    if alg is not None and alg.family in ('ED25519', 'ED448'):
        return (f'Selected CA key is {ca.key_type}: Windows (CryptoAPI/CNG) does not '
                'validate certificates signed with EdDSA')
    return None

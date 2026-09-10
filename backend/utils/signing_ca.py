"""Whether a CA can be configured as a signer (review of #343).

The protocol endpoints refuse a CA that cannot sign at request time; the
settings that name a CA apply the same rule when the CA is chosen, so an
enrolment does not fail later for a reason the operator was never told.
"""


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

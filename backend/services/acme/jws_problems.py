"""Registered ACME problem types for verify_jws failures (RFC 8555 §6.7)."""
from services.acme.account_requests import CLOSED_ACCOUNT

UNKNOWN_ACCOUNT = "No account matches the JWS kid"
_BAD_KEY_MARKERS = ('Invalid JWK:', 'Unsupported key type:', 'Key is not a dict')


def jws_problem(error_type: str, detail: str, status: int):
    """(type, status) for a problem, refining the 'malformed' verify_jws reports."""
    if error_type != 'malformed' or not detail:
        return error_type, status
    if detail.endswith('Invalid or expired nonce'):
        return 'badNonce', status
    if any(marker in detail for marker in _BAD_KEY_MARKERS):
        return 'badPublicKey', status
    if CLOSED_ACCOUNT in detail:
        return 'unauthorized', 401
    if detail.endswith(UNKNOWN_ACCOUNT):
        return 'accountDoesNotExist', status
    return error_type, status

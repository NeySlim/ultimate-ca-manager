"""
Trusted proxy detection.

Used to gate code paths that trust reverse-proxy-injected headers
(SSL_CLIENT_CERT, X-SSL-Client-*, X-Forwarded-*, etc.). These headers
MUST never be honored when the request originates from an untrusted
source — otherwise an attacker who can reach gunicorn directly (or
poison a header through a misconfigured proxy) can spoof client
certificate authentication and obtain arbitrary certificates.

Configuration:
    UCM_TRUSTED_PROXIES   Comma-separated list of proxy IPs that are
                          allowed to set client-cert / forwarded-for
                          headers. Examples:
                              UCM_TRUSTED_PROXIES=127.0.0.1,::1
                              UCM_TRUSTED_PROXIES=10.0.0.5
                              UCM_TRUSTED_PROXIES=*           (trust all — dangerous)

    Default (unset) trusts loopback only (127.0.0.1, ::1) — safe for
    nginx/apache running on the same host and the most common deploy.
"""
import logging
import os

from flask import request

logger = logging.getLogger(__name__)


def _trusted_proxy_set():
    proxies_str = os.environ.get('UCM_TRUSTED_PROXIES', '').strip()
    if not proxies_str:
        return {'127.0.0.1', '::1'}
    if proxies_str == '*':
        return None  # explicit opt-in to trust everyone
    return {p.strip() for p in proxies_str.split(',') if p.strip()}


def is_request_from_trusted_proxy() -> bool:
    """
    Return True iff the current request's immediate peer is in the
    trusted-proxy set (or the operator opted in to trust all).

    MUST be called inside a Flask request context.
    """
    trusted = _trusted_proxy_set()
    if trusted is None:
        return True  # explicit '*' opt-in
    remote = request.remote_addr or ''
    return remote in trusted


def reject_untrusted_proxy_headers(*header_names) -> bool:
    """
    Convenience: returns True when the named headers should be IGNORED
    because the request did not come from a trusted proxy. Logs a
    warning when one of the headers IS present from an untrusted peer
    (likely a spoof attempt).
    """
    if is_request_from_trusted_proxy():
        return False
    present = [h for h in header_names if request.headers.get(h) or request.environ.get(h)]
    if present:
        logger.warning(
            "Ignoring proxy headers %s from untrusted peer %s",
            present, request.remote_addr,
        )
    return True


def client_ip() -> str:
    """
    Return the best-effort real client IP for audit logging.

    Behind a trusted reverse proxy (UCM_TRUSTED_PROXIES contains the
    immediate peer) the left-most entry of X-Forwarded-For is taken
    as the original client IP. Otherwise — including when the request
    comes directly from gunicorn or from a peer NOT in the trusted
    set — request.remote_addr is returned and any X-Forwarded-* on
    the request is ignored. This is the same gating that protects
    SSL_CLIENT_* headers; spoofed XFF from untrusted peers must NEVER
    end up in the audit trail as if it were the real client.

    Always returns a non-empty string ('unknown' as last resort).
    """
    if is_request_from_trusted_proxy():
        xff = request.headers.get('X-Forwarded-For') or ''
        if xff:
            # Left-most IP is the originating client per RFC 7239.
            first = xff.split(',', 1)[0].strip()
            if first:
                return first
        real_ip = request.headers.get('X-Real-IP')
        if real_ip:
            return real_ip.strip()
    return request.remote_addr or 'unknown'

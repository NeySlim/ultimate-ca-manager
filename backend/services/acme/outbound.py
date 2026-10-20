"""What both ACME clients do to talk to a CA they did not choose.

UCM speaks ACME as a client twice: ``acme_client_service`` orders its own
certificates, and ``acme_proxy_service`` relays a local client's order upstream.
The two grew the same pieces separately and ended up with one each:

- the outbound URL guard was written twice, byte for byte;
- the nonce reserve and the badNonce retry (RFC 8555 §6.5) existed only on the
  proxy side, so a badNonce was a hard failure for the client;
- the newNonce backoff existed only on the client side, so one slow upstream
  HEAD failed a proxied request outright;
- and each fetched its nonce on a hard-coded timeout -- 30 on one side, 15 on
  the other -- while the operator's configured HTTP timeout sat unused.

The pieces live here so both callers get all of them.
"""

import logging
import threading
import time
from typing import Optional

from services.acme.dns_selfcheck import acme_allow_loopback_upstream
from utils import ssrf_protection

logger = logging.getLogger(__name__)

BAD_NONCE = 'urn:ietf:params:acme:error:badNonce'

# A pooled nonce is single-use and short-lived: spending a stale one costs the
# badNonce round-trip the pool exists to avoid.
NONCE_POOL_MAX = 8
NONCE_POOL_TTL_SEC = 60

# How many times a newNonce HEAD is attempted. Some CAs (ZeroSSL has been the
# case in practice) answer slowly or intermittently, and a single transient
# timeout would otherwise fail challenge submission, polling and finalization.
NONCE_FETCH_ATTEMPTS = 3

_pool_lock = threading.Lock()
# PLANB-C.10: à implémenter selon SPEC (réserve de nonces par URL d'annuaire amont)

def validate_outbound_acme_url(url: str) -> None:
    """Block loopback/cloud-metadata targets for ACME sub-URLs.

    The sub-URLs come out of the directory JSON, which is upstream-controlled.
    Loopback is allowed only when the operator opts in for a colocated upstream
    (see acme_allow_loopback_upstream); metadata stays blocked either way.
    """
    try:
        ssrf_protection.validate_url_not_cloud_metadata(
            url, allow_loopback=acme_allow_loopback_upstream())
    except ValueError as exc:
        raise ValueError(f'ACME outbound URL blocked: {exc}') from exc


def nonce_pool_pop(directory_url: str) -> Optional[str]:
    """Newest first, and anything older than NONCE_POOL_TTL_SEC is discarded
    rather than spent."""
    # PLANB-C.10: à implémenter selon SPEC (dépiler un nonce à usage unique)
    return None


def nonce_pool_push(directory_url: str, nonce: Optional[str]) -> None:
    # PLANB-C.10: à implémenter selon SPEC (empiler un nonce reçu, borné à NONCE_POOL_MAX)
    return None


def reset_nonce_pool() -> None:
    """Drop every pooled nonce (process-level cache, so also test-level)."""
    # PLANB-C.10: à implémenter selon SPEC (vider la réserve)


def fetch_nonce(nonce_url: str, *, timeout: int, verify: bool,
                headers: Optional[dict] = None,
                attempts: int = NONCE_FETCH_ATTEMPTS) -> str:
    """HEAD newNonce, retried with backoff, and return the Replay-Nonce.

    Raises the last exception when every attempt failed. The wait happens
    between attempts only -- sleeping after the last one delayed the failure
    without ever retrying it.
    """
    validate_outbound_acme_url(nonce_url)
    last_exc: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            resp = ssrf_protection.safe_request_head(
                nonce_url,
                allow_loopback=acme_allow_loopback_upstream(),
                timeout=timeout,
                verify=verify,
                headers=dict(headers) if headers else None,
            )
            resp.raise_for_status()
            return resp.headers['Replay-Nonce']
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning(
                f'newNonce fetch failed (attempt {attempt + 1}/{attempts}): {exc}')
            if attempt + 1 < attempts:
                time.sleep(2 * (attempt + 1))
    raise last_exc  # type: ignore[misc]


def bad_nonce_retry_value(resp) -> Optional[str]:
    """The fresh nonce to retry with when *resp* is a badNonce error, else None.

    RFC 8555 §6.5: on badNonce the server MUST return a fresh nonce in
    Replay-Nonce and the client MUST retry the request once with it.
    """
    if getattr(resp, 'status_code', None) != 400:
        return None
    try:
        problem = resp.json()
    except Exception:  # noqa: BLE001 - any body that is not JSON
        return None
    if not isinstance(problem, dict) or problem.get('type') != BAD_NONCE:
        return None
    return resp.headers.get('Replay-Nonce') or None

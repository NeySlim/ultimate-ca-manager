"""HTTP-01 (RFC 8555 §8.3): fetching a challenge URL, serving the client's own tokens."""
import logging
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
import urllib3

from models.acme_models import AcmeClientOrder
from utils.acme_ip import format_ip_for_url
from utils.ssrf_protection import (
    pin_host, validate_host_not_private, validate_url_not_cloud_metadata, validated_addresses,
    watch_sockets,
)

logger = logging.getLogger(__name__)

# Set once: catch_warnings() is not thread-safe and probes run in parallel.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Validators SHOULD follow redirects: site-wide http→https 301s cover the
# challenge path and public CAs (Boulder) follow them. Each hop is re-vetted.
REDIRECT_STATUSES = frozenset((301, 302, 303, 307, 308))
MAX_REDIRECTS = 5
# The body is the key authorization (~87 bytes, RFC 8555 §8.3): anything past
# this is refused unread. A timer bounds the whole chain in real time.
MAX_BODY_BYTES = 1024
TOTAL_TIMEOUT_FACTOR = 3

# Order states in which the CA may still fetch the token.
_AWAITING_VALIDATION = ('pending', 'processing', 'validating')
SELFCHECK_INTERVAL = 2
# Self-checks run inside a request: short per-hop timeout, all identifiers probed at once.
SELFCHECK_TIMEOUT = 5
_SELFCHECK_WORKERS = 8


class IncorrectResponse(ValueError):
    """The challenge server answered something HTTP-01 does not accept."""


class ResponseTooLarge(IncorrectResponse):
    """The challenge body exceeded MAX_BODY_BYTES."""


class _HopDeadline:
    """Shuts down every socket of one hop at the deadline, so a blocked read (headers,
    chunk line, body) fails at once; the fds are dups, closed only after the timer ended."""

    def __init__(self, delay: float):
        self._lock = threading.Lock()
        self._socks = []
        self.fired = False
        self._timer = threading.Timer(max(0.0, delay), self._fire)
        self._timer.daemon = True

    def watch(self, sock):
        dup = sock.dup()
        with self._lock:
            self._socks.append(dup)
            fired = self.fired
        if fired:
            _shutdown(dup)

    def _fire(self):
        with self._lock:
            self.fired = True
            socks = list(self._socks)
        for sock in socks:
            _shutdown(sock)

    def __enter__(self):
        self._timer.start()
        return self

    def __exit__(self, *exc):
        self._timer.cancel()
        self._timer.join()
        for sock in self._socks:
            sock.close()
        return False


def _shutdown(sock):
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


def _read_bounded(response, deadline: float):
    """Load at most MAX_BODY_BYTES of *response* before *deadline*, then close it.
    A redirect or error body is never compared, so it is not read at all."""
    body = bytearray()
    try:
        if response.status_code in REDIRECT_STATUSES or response.status_code >= 400:
            response._content = b''
            return response
        encoding = (response.headers.get('Content-Encoding') or 'identity').strip().lower()
        if encoding != 'identity':
            raise IncorrectResponse(f'http-01 response has Content-Encoding {encoding}, not identity')
        for chunk in response.iter_content(chunk_size=1):
            body += chunk
            if len(body) > MAX_BODY_BYTES:
                raise ResponseTooLarge(f'http-01 response larger than {MAX_BODY_BYTES} bytes')
            if time.monotonic() > deadline:
                raise requests.Timeout('http-01 response not received in time')
    finally:
        response.close()
    response._content = bytes(body)
    return response


def _get(url: str, pin, timeout: float, deadline: float):
    """One unredirected GET, body read bounded, finished by *deadline* or requests.Timeout.
    TLS is not verified: an https hop usually presents the certificate being renewed,
    and HTTP-01 derives no security from TLS."""
    kwargs = dict(timeout=timeout, allow_redirects=False, verify=False, stream=True,
                  headers={'Accept-Encoding': 'identity'})
    with _HopDeadline(deadline - time.monotonic()) as hop:
        try:
            with watch_sockets(hop.watch):
                if pin is None:
                    response = _read_bounded(requests.get(url, **kwargs), deadline)  # nosec B501
                else:
                    with pin_host(*pin):
                        response = _read_bounded(requests.get(url, **kwargs), deadline)  # nosec B501
        except IncorrectResponse:
            raise
        except Exception as exc:
            if hop.fired:
                raise requests.Timeout('http-01 response not received in time') from exc
            raise
        # A shut-down socket can also read as a clean end of a close-delimited body
        if hop.fired:
            raise requests.Timeout('http-01 response not received in time')
        return response


def fetch_following_redirects(url: str, pin, allow_private: bool, timeout: int = 10):
    """GET *url*, following redirects on http/https and ports 80/443 only.

    Cloud metadata is always refused, private addresses unless *allow_private*;
    every hop is pinned to what was checked. Raises ValueError on a policy violation,
    IncorrectResponse on a body past MAX_BODY_BYTES or not identity-encoded,
    requests.Timeout once TOTAL_TIMEOUT_FACTOR * timeout of wall clock has passed: a connected
    socket is shut down at that instant, a connect attempt ends within its own timeout.
    """
    deadline = time.monotonic() + TOTAL_TIMEOUT_FACTOR * timeout
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise requests.Timeout('http-01 redirect chain not completed in time')
        response = _get(current, pin, min(timeout, remaining), deadline)
        if response.status_code not in REDIRECT_STATUSES:
            return response
        location = response.headers.get('Location')
        if not location:
            raise ValueError('redirect without a Location header')
        current = urljoin(current, location)
        parsed = urlparse(current)
        scheme = (parsed.scheme or '').lower()
        if scheme not in ('http', 'https'):
            raise ValueError(f"redirect to unsupported scheme '{scheme}'")
        if not parsed.hostname:
            raise ValueError('redirect without a hostname')
        if parsed.port not in (None, 80, 443):
            raise ValueError('redirect to a non-standard port')
        validate_url_not_cloud_metadata(current, allow_loopback=allow_private)
        # Every hop is pinned to what was vetted, whichever the policy
        pin = (parsed.hostname, validated_addresses(current, allow_loopback=True)[1]
               if allow_private else validate_host_not_private(parsed.hostname))
    raise ValueError(f'more than {MAX_REDIRECTS} redirects during http-01 validation')


def challenge_url(identifier: str, token: str) -> str:
    return f'http://{format_ip_for_url(identifier)}/.well-known/acme-challenge/{token}'


def key_authorization_for_token(token: str) -> Optional[str]:
    """Key authorization of a client order awaiting HTTP-01 validation, or None.

    Proxy orders are excluded: their ACME client answers its own challenges.
    """
    candidates = AcmeClientOrder.query.filter(
        AcmeClientOrder.challenge_type == 'http-01',
        AcmeClientOrder.status.in_(_AWAITING_VALIDATION),
        AcmeClientOrder.challenges_data.contains(token, autoescape=True),
    ).all()
    for order in candidates:
        if order.is_proxy_order:
            continue
        for challenge in order.challenges_dict.values():
            if challenge.get('token') == token and challenge.get('key_authorization'):
                return challenge['key_authorization']
    return None


def challenge_reachable(identifier: str, challenge: dict) -> tuple:
    """(ok, reason): does the challenge URL serve the key authorization from here?

    UCM's view can differ from the CA's (split-horizon DNS), hence a `force`
    bypass wherever this gates a submission.
    """
    url = challenge_url(identifier, challenge['token'])
    try:
        # The first hop is pinned to what the check vetted, like every redirect
        pin = validated_addresses(url, allow_loopback=True)
        response = fetch_following_redirects(url, pin, allow_private=True, timeout=SELFCHECK_TIMEOUT)
    except ResponseTooLarge:
        return False, f'{url}: response too large'
    except IncorrectResponse:
        return False, f'{url}: unexpected content encoding'
    except ValueError:
        return False, f'{url}: name not resolvable or address refused'
    except requests.Timeout:
        return False, f'{url}: timed out'
    except requests.ConnectionError:
        return False, f'{url}: connection failed'
    except Exception:
        return False, f'{url}: request failed'
    if response.status_code != 200:
        return False, f'{url}: HTTP {response.status_code}'
    if response.text.strip() != challenge['key_authorization']:
        return False, f'{url}: unexpected content'
    return True, url


def wait_for_http01(challenges: dict, timeout: int) -> dict:
    """Probe every HTTP-01 challenge until reachable or *timeout* (0 = one pass).

    Returns {'ok', 'missing': [identifiers], 'reasons': {identifier: reason}}.
    """
    pending = {d: c for d, c in challenges.items() if c.get('token') and c.get('key_authorization')}
    reasons = {}
    deadline = time.monotonic() + max(0, timeout)
    while True:
        with ThreadPoolExecutor(max_workers=min(_SELFCHECK_WORKERS, max(1, len(pending)))) as pool:
            results = dict(zip(pending, pool.map(lambda i: challenge_reachable(i, pending[i]), list(pending))))
        for identifier, (ok, reason) in results.items():
            if ok:
                del pending[identifier]
                reasons.pop(identifier, None)
            else:
                reasons[identifier] = reason
        if not pending or time.monotonic() >= deadline:
            break
        time.sleep(SELFCHECK_INTERVAL)
    if pending:
        logger.warning('HTTP-01 self-check failed: %s', '; '.join(reasons.values()))
    return {'ok': not pending, 'missing': sorted(pending), 'reasons': reasons}

"""HTTP-01 (RFC 8555 §8.3): fetching a challenge URL, serving the client's own tokens."""
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
import urllib3

from models.acme_models import AcmeClientOrder
from utils.acme_ip import format_ip_for_url
from utils.ssrf_protection import pin_host, validate_host_not_private, validate_url_not_cloud_metadata

logger = logging.getLogger(__name__)

# Set once: catch_warnings() is not thread-safe and probes run in parallel.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Validators SHOULD follow redirects: site-wide http→https 301s cover the
# challenge path and public CAs (Boulder) follow them. Each hop is re-vetted.
REDIRECT_STATUSES = frozenset((301, 302, 303, 307, 308))
MAX_REDIRECTS = 5

# Order states in which the CA may still fetch the token.
_AWAITING_VALIDATION = ('pending', 'processing', 'validating')
SELFCHECK_INTERVAL = 2
# Self-checks run inside a request: short per-hop timeout, all identifiers probed at once.
SELFCHECK_TIMEOUT = 5
_SELFCHECK_WORKERS = 8


def _get(url: str, pin, timeout: int = 10):
    """One unredirected GET. TLS is not verified: an https hop usually presents
    the certificate being renewed, and HTTP-01 derives no security from TLS."""
    if pin is not None:
        host, ips = pin
        with pin_host(host, ips):
            return requests.get(url, timeout=timeout, allow_redirects=False, verify=False)
    return requests.get(url, timeout=timeout, allow_redirects=False, verify=False)


def fetch_following_redirects(url: str, pin, allow_private: bool, timeout: int = 10):
    """GET *url*, following redirects on http/https and ports 80/443 only.

    Cloud metadata is always refused; without *allow_private* every hop is
    resolved, checked and pinned. Raises ValueError on a policy violation.
    """
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        response = _get(current, pin, timeout)
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
        pin = None if allow_private else (parsed.hostname, validate_host_not_private(parsed.hostname))
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
        validate_url_not_cloud_metadata(url, allow_loopback=True)
        response = fetch_following_redirects(url, None, allow_private=True, timeout=SELFCHECK_TIMEOUT)
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

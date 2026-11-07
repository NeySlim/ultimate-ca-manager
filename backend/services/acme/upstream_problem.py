"""Upstream ACME errors as the proxy hands them to its clients (RFC 8555 §6.6, §6.7)."""
import re
from email.utils import parsedate_to_datetime

ACME_ERROR_PREFIX = 'urn:ietf:params:acme:error:'

# Problems about the proxy's own JWS or upstream account: relayed, they would
# send the client after its nonce, key or account, none of which is at fault.
_PROXY_SIDE_TYPES = frozenset({
    'badNonce', 'badPublicKey', 'badSignatureAlgorithm', 'accountDoesNotExist',
    'externalAccountRequired', 'userActionRequired', 'invalidContact',
    'unsupportedContact',
})
_DELTA_SECONDS = re.compile(r'^\d{1,10}$')


def retry_after_of(response):
    """The upstream Retry-After value when it is valid RFC 9110 syntax, else None."""
    value = (getattr(response, 'headers', None) or {}).get('Retry-After')
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if _DELTA_SECONDS.match(value):
        return value
    try:
        parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    return value


class UpstreamProblem(Exception):
    """A non-success upstream ACME response, kept with its problem document."""

    def __init__(self, status, problem=None, retry_after=None):
        self.status = status
        self.problem = problem
        self.retry_after = retry_after
        kind = (problem or {}).get('type', 'no problem document')
        super().__init__(f"Upstream HTTP {status}: {kind} {(problem or {}).get('detail', '')}".strip())

    @classmethod
    def from_response(cls, response):
        try:
            body = response.json()
        except Exception:
            body = None
        problem = None
        if (isinstance(body, dict) and isinstance(body.get('type'), str)
                and body['type'].startswith(ACME_ERROR_PREFIX)):
            problem = body
        return cls(getattr(response, 'status_code', 500), problem, retry_after_of(response))

    @property
    def type_name(self):
        return (self.problem or {}).get('type', '')[len(ACME_ERROR_PREFIX):] or None

    def client_problem(self):
        """(problem document, HTTP status) served to the proxy client."""
        status = self.status if isinstance(self.status, int) and 400 <= self.status < 600 else 500
        name = self.type_name
        if name is None or name in _PROXY_SIDE_TYPES:
            if name is not None:
                status = 500
            return {
                'type': f'{ACME_ERROR_PREFIX}serverInternal',
                'detail': f'The upstream CA refused the request (HTTP {self.status}'
                          + (f', {name}' if name else '') + ')',
                'status': status,
            }, status
        relayed = {key: self.problem[key] for key in ('type', 'detail', 'subproblems')
                   if key in self.problem}
        relayed['status'] = status
        return relayed, status

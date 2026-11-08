"""ACME problem documents for the requests no ACME route serves under /acme."""
from flask import current_app, jsonify, make_response, request
from werkzeug.exceptions import HTTPException

from services.acme.acme_proxy_account import ProxyEndpointNotConfiguredError, resolve_proxy_by_slug
from utils.acme_public_url import get_acme_proxy_public_base, get_acme_public_origin

_PROXY_PREFIX = '/acme/proxy/'
_SPA_ENDPOINTS = frozenset({'ui.spa', 'ui.index'})
_METHODS = ('GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS')
_DETAILS = {404: 'No ACME resource at this URL', 405: 'Method not allowed on this ACME resource'}


def is_acme_path(path: str) -> bool:
    return path == '/acme' or path.startswith('/acme/')


def _directory_url() -> str:
    """The directory of the server or proxy endpoint the path falls under."""
    path = request.path
    if path != '/acme/proxy' and not path.startswith(_PROXY_PREFIX):
        return f'{get_acme_public_origin(request)}/acme/directory'
    base = get_acme_proxy_public_base(request)
    segment = path[len(_PROXY_PREFIX):].split('/', 1)[0]
    if segment:
        try:
            return f'{base}/{resolve_proxy_by_slug(segment).proxy_slug}/directory'
        except (ValueError, ProxyEndpointNotConfiguredError):
            pass  # an endpoint name, or no enabled endpoint: the default proxy
    return f'{base}/directory'


def _routed_methods() -> list:
    """Methods an ACME route serves at this path; the SPA catch-all does not count."""
    adapter = current_app.url_map.bind_to_environ(request.environ)
    allowed = []
    for method in _METHODS:
        try:
            endpoint, _args = adapter.match(request.path, method=method)
        except HTTPException:
            continue
        if endpoint not in _SPA_ENDPOINTS:
            allowed.append(method)
    return allowed


def routing_problem(error):
    """RFC 8555 §6.7 problem linked to its directory (§7.1): 405 with Allow when another
    method is served (§6.3, RFC 9110 §15.5.6), else 404; a POST gets a nonce (§6.5)."""
    status, allow = error.code, None
    if request.url_rule is None or request.endpoint in _SPA_ENDPOINTS:
        allow = _routed_methods()
        status = 405 if allow else 404
    response = make_response(jsonify({
        'type': 'urn:ietf:params:acme:error:malformed',
        'detail': _DETAILS.get(status, 'Request refused'),
        'status': status,
    }), status)
    response.headers['Content-Type'] = 'application/problem+json'
    if allow:
        response.headers['Allow'] = ', '.join(allow)
    elif status == 405:
        response.headers.extend((k, v) for k, v in error.get_headers() if k.lower() == 'allow')
    response.headers.add('Link', f'<{_directory_url()}>;rel="index"')
    if request.method == 'POST':
        from services.acme import AcmeService
        response.headers['Replay-Nonce'] = AcmeService().generate_nonce()
    return response

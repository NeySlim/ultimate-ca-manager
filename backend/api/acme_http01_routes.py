"""HTTP-01 key authorizations of UCM's own ACME client orders (RFC 8555 §8.3)."""
import re

from flask import Blueprint, Response

from services.acme.http01 import key_authorization_for_token

acme_http01_bp = Blueprint('acme_http01', __name__)

# RFC 8555 §8.1: base64url, at least 128 bits of entropy.
_TOKEN_RE = re.compile(r'[A-Za-z0-9_-]{22,256}')


@acme_http01_bp.route('/.well-known/acme-challenge/<token>', methods=['GET'])
def serve_http01_token(token):
    key_authorization = key_authorization_for_token(token) if _TOKEN_RE.fullmatch(token) else None
    if key_authorization is None:
        return Response('Not found', status=404, mimetype='text/plain')
    return Response(key_authorization, status=200, mimetype='application/octet-stream')

"""
Standard API Response Helpers
Consistent response format across all endpoints

Error bodies are a **superset**: they carry the RFC 7807 (Problem Details)
members *and* UCM's historical `error`/`message`/`code` keys. Existing clients
keep reading `message`; new clients get a conformant `application/problem+json`
document. Dropping the legacy keys would be a breaking change and is a separate,
deliberate decision — not something this helper does implicitly.

Protocol endpoints (ACME, EST) build their own problem documents with their own
registered type URNs and must NOT go through here.
"""

from flask import jsonify, has_request_context, request
from werkzeug.http import HTTP_STATUS_CODES

# RFC 7807 §4.2: "about:blank" means the problem has no semantics beyond the
# HTTP status code, and the title is then the status phrase. UCM does not
# publish per-problem documentation URIs, so this is the honest default rather
# than inventing URLs that resolve to nothing.
PROBLEM_TYPE_BLANK = 'about:blank'
PROBLEM_CONTENT_TYPE = 'application/problem+json'


def success_response(data=None, message=None, meta=None, status=200):
    """
    Standard success response
    
    Args:
        data: Response data (list, dict, etc.)
        message: Optional success message
        meta: Optional metadata (pagination, etc.)
        status: HTTP status code (default: 200)
    
    Returns:
        Flask response with JSON
    
    Example:
        return success_response(
            data=[...],
            meta={'total': 42, 'page': 1}
        )
    """
    response = {}
    
    if data is not None:
        response['data'] = data
    
    if message:
        response['message'] = message
    
    if meta:
        response['meta'] = meta
    
    return jsonify(response), status


def build_problem(message, code=400, details=None, problem_type=None, title=None):
    """Build the RFC 7807 + legacy superset body for an error.

    Args:
        message: Human-readable explanation (becomes `detail` and `message`)
        code: HTTP status code (becomes `status` and `code`)
        details: Optional structured details (kept as a 7807 extension member)
        problem_type: Optional type URI; defaults to "about:blank"
        title: Optional short summary; defaults to the HTTP status phrase

    Returns:
        dict ready to serialise
    """
    status = int(code) if str(code).isdigit() else 400
    body = {
        # --- RFC 7807 members ---
        'type': problem_type or PROBLEM_TYPE_BLANK,
        'title': title or HTTP_STATUS_CODES.get(status, 'Error'),
        'status': status,
        'detail': message,
        # --- legacy members, kept for existing clients ---
        'error': True,
        'message': message,
        'code': code,
    }

    # `instance` identifies the specific occurrence — the requested path.
    if has_request_context():
        try:
            body['instance'] = request.path
        except Exception:
            pass

    if details:
        body['details'] = details

    return body


def error_response(message, code=400, details=None, problem_type=None, title=None):
    """
    Standard error response — RFC 7807 problem details plus the legacy keys.

    Args:
        message: Error message
        code: HTTP status code
        details: Optional error details
        problem_type: Optional RFC 7807 type URI
        title: Optional RFC 7807 title (defaults to the status phrase)

    Returns:
        Flask response with application/problem+json

    Example:
        return error_response('Invalid input', 400, {'field': 'name'})
    """
    response = jsonify(build_problem(message, code, details, problem_type, title))
    response.mimetype = PROBLEM_CONTENT_TYPE
    return response, code


def created_response(data, message='Created successfully'):
    """Shortcut for 201 Created"""
    return success_response(data=data, message=message, status=201)


def no_content_response():
    """Shortcut for 204 No Content"""
    return '', 204

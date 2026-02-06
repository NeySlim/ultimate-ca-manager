"""
Standard API Response Helpers
Consistent response format across all endpoints
"""

from flask import jsonify


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


def error_response(message, code=400, details=None):
    """
    Standard error response
    
    Args:
        message: Error message
        code: HTTP status code
        details: Optional error details
    
    Returns:
        Flask response with JSON
    
    Example:
        return error_response('Invalid input', 400, {'field': 'name'})
    """
    response = {
        'error': True,
        'message': message,
        'code': code
    }
    
    if details:
        response['details'] = details
    
    return jsonify(response), code


def created_response(data, message='Created successfully'):
    """Shortcut for 201 Created"""
    return success_response(data=data, message=message, status=201)


def no_content_response():
    """Shortcut for 204 No Content"""
    return '', 204

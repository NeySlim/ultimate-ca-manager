"""
Pagination Helper
Simple pagination for SQLAlchemy queries
"""

import math
from datetime import datetime
from flask import request


def paginate(query, page=1, per_page=20):
    """
    Paginate SQLAlchemy query
    
    Args:
        query: SQLAlchemy query object
        page: Page number (1-indexed)
        per_page: Items per page
    
    Returns:
        dict: {items, meta}
    """
    if page < 1:
        page = 1
    if per_page < 1:
        per_page = 20
    if per_page > 100:
        per_page = 100
    
    total = query.count()
    total_pages = math.ceil(total / per_page) if total > 0 else 0
    
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    
    return {
        'items': items,
        'meta': {
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': total_pages,
            'has_next': page < total_pages,
            'has_prev': page > 1
        }
    }


def parse_request_pagination(default_per_page=25, max_per_page=100):
    """
    Parse pagination parameters from Flask request args.

    Uses the Flask request context directly (no parameter needed).

    Returns:
        tuple: (page, per_page) with defaults and bounds applied
    """
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(max(1, request.args.get('per_page', default_per_page, type=int)), max_per_page)
    return page, per_page


def parse_date_filter(from_arg='date_from', to_arg='date_to'):
    """
    Parse ISO 8601 date range parameters from Flask request args.

    Args:
        from_arg: Query param name for the start date (default: 'date_from')
        to_arg: Query param name for the end date (default: 'date_to')

    Returns:
        tuple: (date_from, date_to) as datetime objects or None if not provided/invalid
    """
    date_from = None
    date_to = None
    if request.args.get(from_arg):
        try:
            date_from = datetime.fromisoformat(request.args.get(from_arg).replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            pass
    if request.args.get(to_arg):
        try:
            date_to = datetime.fromisoformat(request.args.get(to_arg).replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            pass
    return date_from, date_to

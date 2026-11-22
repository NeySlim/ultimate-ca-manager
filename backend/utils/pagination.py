"""
Pagination Helper
Simple pagination for SQLAlchemy queries
"""

import math
from collections import namedtuple
from datetime import datetime
from flask import request
from sqlalchemy import String, case
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement


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


def parse_request_limit(default_limit, max_limit, arg='limit'):
    """Row count asked for by the client, floored at 1 and capped at *max_limit*.

    The listings that page use ``per_page`` and go through
    :func:`parse_request_pagination`. A second family of routes hands the
    client's number straight to ``.limit()`` instead, and those had the
    unbounded-page-size bug the listings were fixed for, one layer down:

    * with no ceiling, ``?limit=1000000`` loads and serialises the whole
      table -- the dashboard widgets did this from an ordinary account;
    * with no floor, ``?limit=-1`` reaches the query as ``LIMIT -1``, which
      SQLite reads as *no limit* and PostgreSQL refuses outright, so the same
      request returned the whole table on one backend and a 500 on the other.

    A value that is not a number is not a refusal either: it falls back to
    *default_limit*, which is what ``type=int`` already did for the page size.
    """
    raw = request.args.get(arg, default_limit)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default_limit
    return min(max(1, value), max_limit)


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


class InvalidSort(ValueError):
    """A ``sort_by`` or ``sort_order`` the list does not know: answered 400 with the allowed keys."""

    def __init__(self, message, allowed):
        super().__init__(message)
        self.allowed = list(allowed)


class folded_text(FunctionElement):
    """A text sort value folded to ASCII lower case and compared byte by byte, on both engines."""
    type = String()
    name = 'folded_text'
    inherit_cache = True


@compiles(folded_text)
def _folded_text_sqlite(element, compiler, **kw):
    # SQLite's lower() folds ASCII only and BINARY compares UTF-8 bytes
    return 'lower(%s)' % compiler.process(element.clauses, **kw)


@compiles(folded_text, 'postgresql')
def _folded_text_pg(element, compiler, **kw):
    # Under "C" lower() folds ASCII only and the comparison is bytewise: SQLite's result exactly
    return 'lower((%s) COLLATE "C") COLLATE "C"' % compiler.process(element.clauses, **kw)


def rank_of(column, order):
    """SQL rank of *column* among the values *order* lists; any other value ranks after them."""
    return case({value: index for index, value in enumerate(order)}, value=column, else_=len(order))


def _never_null(expression):
    """True for a mapped column declared NOT NULL (or a primary key)."""
    columns = getattr(getattr(expression, 'property', None), 'columns', None)
    column = columns[0] if columns else expression
    return getattr(column, 'primary_key', False) or getattr(column, 'nullable', True) is False


def _ordering(expression, descending):
    """``expression`` in the requested direction, text folded, absent values last."""
    if isinstance(expression.type, String):
        expression = folded_text(expression)
        clause = expression.desc() if descending else expression.asc()
        return clause.nulls_last()
    clause = expression.desc() if descending else expression.asc()
    return clause if _never_null(expression) else clause.nulls_last()


Sort = namedtuple('Sort', 'key descending clauses')


def parse_request_sort(allowed, default, tiebreak=None):
    """The ORDER BY a list asks for with ``sort_by`` and ``sort_order``.

    *allowed* maps each key to an expression, a tuple of expressions, a
    callable ``f(descending) -> [clauses]`` or None (the route orders that key
    itself). *default* is ``(key, 'asc'|'desc')``; *tiebreak* (the primary key)
    ends every ORDER BY in the same direction, so pages never share a row.
    A key or direction the list does not know raises :class:`InvalidSort`.
    """
    key = (request.args.get('sort_by') or '').strip() or default[0]
    order = (request.args.get('sort_order') or '').strip().lower() or default[1]
    keys = sorted(allowed)
    if key not in allowed:
        raise InvalidSort(f"Unknown sort_by '{key[:64]}'; allowed: {', '.join(keys)}", keys)
    if order not in ('asc', 'desc'):
        raise InvalidSort(f"Unknown sort_order '{order[:16]}'; allowed: asc, desc", keys)
    descending = order == 'desc'
    spec = allowed[key]
    if spec is None:
        clauses = []
    elif callable(spec) and not hasattr(spec, 'type'):
        clauses = list(spec(descending))
    else:
        clauses = [_ordering(expr, descending) for expr in (spec if isinstance(spec, tuple) else (spec,))]
    if tiebreak is not None:
        clauses.append(tiebreak.desc() if descending else tiebreak.asc())
    return Sort(key, descending, clauses)

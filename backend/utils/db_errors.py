"""PostgreSQL errors without the values they quote.

The server quotes the refused row (``Failing row contains``) and the refused
input (class 22) whatever the driver and ``hide_parameters``; psycopg2, which
binds on the client, also puts the values in the quoted statement (``LINE n:``).
"""
import re

from sqlalchemy import event
from sqlalchemy.engine import Engine

# Sections of a server message; continuation lines belong to the section above
_SECTION = re.compile(r'^(LINE \d+|DETAIL|HINT|QUERY|CONTEXT|WHERE|STATEMENT):')
_KEPT = ('DETAIL', 'HINT')
# NOT NULL and CHECK refusals (23502, 23514) quote the whole row
_ROW_DETAIL = re.compile(r'^DETAIL:\s+Failing row contains')
# Data exceptions (class 22) quote the input on their primary line and in their DETAIL
_QUOTED = re.compile(r'"[^"]*"')


def sqlstate(orig):
    """The SQLSTATE of a driver error: ``sqlstate`` on psycopg 3, ``pgcode`` on psycopg2."""
    return getattr(orig, 'sqlstate', None) or getattr(orig, 'pgcode', None)


def scrub_postgres_message(message, pgcode=None):
    """The primary line, DETAIL and HINT of a server message, without the statement,
    the refused row or, for a data exception (class 22), the refused input."""
    data_exception = bool(pgcode) and pgcode.startswith('22')
    lines = message.split('\n')
    primary = _QUOTED.sub('"\u2026"', lines[0]) if data_exception else lines[0]
    kept, keep = [primary], True
    for line in lines[1:]:
        section = _SECTION.match(line)
        if section:
            keep = (section.group(1) in _KEPT and not _ROW_DETAIL.match(line)
                    and not (data_exception and section.group(1) == 'DETAIL'))
        if keep and line:
            kept.append(line)
    return '\n'.join(kept) + ('\n' if message.endswith('\n') else '')


def _scrub(context):
    # A failure here must never replace the error being reported
    try:
        _scrub_error(context)
    except Exception:
        return None
    return None


def _scrub_error(context):
    if context.dialect.name != 'postgresql':
        return None
    orig = context.original_exception
    if len(getattr(orig, 'args', ())) != 1 or not isinstance(orig.args[0], str):
        return None
    clean = scrub_postgres_message(orig.args[0], sqlstate(orig))
    if clean == orig.args[0]:
        return None
    # SQLSTATE and diag stay; psycopg2's pgerror keeps the raw text and nothing here reads it
    orig.args = (clean,)
    wrapped = context.sqlalchemy_exception
    if wrapped is not None and len(wrapped.args) == 1:
        wrapped.args = (f'({type(orig).__module__}.{type(orig).__name__}) {clean}',)
    return None


def install():
    if not event.contains(Engine, 'handle_error', _scrub):
        event.listen(Engine, 'handle_error', _scrub)

"""PostgreSQL errors without the statement text they quote.

psycopg2 binds parameters on the client, so a server error that quotes the
statement (``LINE n:`` with its caret, ``QUERY:``, ``CONTEXT:``) carries the
bound values, private keys included, whatever ``hide_parameters`` says.
"""
import re

from sqlalchemy import event
from sqlalchemy.engine import Engine

# Sections of a server message; continuation lines belong to the section above
_SECTION = re.compile(r'^(LINE \d+|DETAIL|HINT|QUERY|CONTEXT|WHERE|STATEMENT):')
_KEPT = ('DETAIL', 'HINT')
# NOT NULL and CHECK refusals (23502, 23514) quote the whole row
_ROW_DETAIL = re.compile(r'^DETAIL:\s+Failing row contains')
# Data exceptions (class 22) end their primary line with the input: `...: "<value>"`
_QUOTED_INPUT = re.compile(r': ".*"$')


def scrub_postgres_message(message, pgcode=None):
    """The primary line, DETAIL and HINT of a server message; never the statement,
    a refused row or a refused input."""
    lines = message.split('\n')
    primary = lines[0]
    if pgcode and pgcode.startswith('22'):
        primary = _QUOTED_INPUT.sub(': "\u2026"', primary, count=1)
    kept, keep = [primary], True
    for line in lines[1:]:
        section = _SECTION.match(line)
        if section:
            keep = section.group(1) in _KEPT and not _ROW_DETAIL.match(line)
        if keep and line:
            kept.append(line)
    return '\n'.join(kept) + ('\n' if message.endswith('\n') else '')


def _scrub(context):
    if context.dialect.name != 'postgresql':
        return None
    orig = context.original_exception
    if len(getattr(orig, 'args', ())) != 1 or not isinstance(orig.args[0], str):
        return None
    clean = scrub_postgres_message(orig.args[0], getattr(orig, 'pgcode', None))
    if clean == orig.args[0]:
        return None
    # SQLSTATE and diag stay; pgerror keeps the raw text and nothing here reads it
    orig.args = (clean,)
    wrapped = context.sqlalchemy_exception
    if wrapped is not None and len(wrapped.args) == 1:
        wrapped.args = (f'({type(orig).__module__}.{type(orig).__name__}) {clean}',)
    return None


def install():
    if not event.contains(Engine, 'handle_error', _scrub):
        event.listen(Engine, 'handle_error', _scrub)

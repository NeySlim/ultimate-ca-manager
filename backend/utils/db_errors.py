"""PostgreSQL errors without the values they quote.

The server quotes the refused row (``Failing row contains``) and the refused
input (class 22) whatever ``hide_parameters`` says, private keys included, and
in its own language: the message is rebuilt from the error's fields, never parsed.
"""
from sqlalchemy import event
from sqlalchemy.engine import Engine

# NOT NULL, CHECK and WITH CHECK OPTION refusals quote the whole row in their DETAIL
_ROW_DETAIL = ('23502', '23514', '44000')


def sqlstate(orig):
    """The SQLSTATE of a psycopg error, None for any other."""
    return getattr(orig, 'sqlstate', None)


def postgres_message(primary, detail=None, hint=None, pgcode=None):
    """The primary line, DETAIL and HINT of a server error, without the refused row;
    a data exception (class 22) quotes its input anywhere and keeps its SQLSTATE only."""
    if pgcode and pgcode.startswith('22'):
        return f'invalid input value (SQLSTATE {pgcode}), not shown'
    lines = [primary]
    if detail and pgcode not in _ROW_DETAIL:
        lines.append(f'DETAIL:  {detail}')
    if hint:
        lines.append(f'HINT:  {hint}')
    return '\n'.join(lines)


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
    diag = getattr(orig, 'diag', None)
    primary = getattr(diag, 'message_primary', None)
    if not primary:
        return None  # not from a server result: a client-side or connection error
    clean = postgres_message(primary, diag.message_detail, diag.message_hint, sqlstate(orig))
    if clean == orig.args[0]:
        return None
    # SQLSTATE and diag stay: diag keeps the raw text and nothing here reads it
    orig.args = (clean,)
    wrapped = context.sqlalchemy_exception
    if wrapped is not None and len(wrapped.args) == 1:
        wrapped.args = (f'({type(orig).__module__}.{type(orig).__name__}) {clean}',)
    return None


def install():
    if not event.contains(Engine, 'handle_error', _scrub):
        event.listen(Engine, 'handle_error', _scrub)

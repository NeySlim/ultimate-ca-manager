"""U+0000 in text: PostgreSQL stores none in a text or JSON value, SQLite does."""

NUL = '\x00'


def escape_nul(text: str) -> str:
    """``text`` with each U+0000 written as the two characters ``\\0``: the same on every backend."""
    return text.replace(NUL, '\\0') if NUL in text else text

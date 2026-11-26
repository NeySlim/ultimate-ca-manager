"""The display name and free-text description of a CA (issue #459): what the operator writes,
never read from or written to the certificate."""
import unicodedata

NAME_MAX = 255
DESCRIPTION_MAX = 1000
# Line feed and tab are the only control characters a description keeps
_CONTROLS_ALLOWED = frozenset('\n\t')


def name_error(value):
    """Why *value* cannot be a display name (a non-blank string of at most NAME_MAX once trimmed), else None."""
    if not isinstance(value, str) or not value.strip():
        return 'name must be a non-empty string'
    if len(value.strip()) > NAME_MAX:
        return f'name must be {NAME_MAX} characters or fewer'
    if any(unicodedata.category(ch) == 'Cc' for ch in value.strip()):
        return 'name may not hold control characters'
    return None


def description_error(value):
    """Why *value* cannot be a description (None or a string of at most DESCRIPTION_MAX), else None."""
    if value is None:
        return None
    if not isinstance(value, str):
        return 'description must be a string or null'
    if len(value) > DESCRIPTION_MAX:
        return f'description must be {DESCRIPTION_MAX} characters or fewer'
    if any(unicodedata.category(ch) == 'Cc' and ch not in _CONTROLS_ALLOWED for ch in value):
        return 'description may not hold control characters other than line feed and tab'
    return None


def stored_description(value):
    """The column value of an accepted description: NULL for none or blank text."""
    return value if value and value.strip() else None

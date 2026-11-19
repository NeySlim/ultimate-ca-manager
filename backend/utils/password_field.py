"""A password field that is present must be a string, checked before it is read as "absent"."""


def password_type_error(value, field='password'):
    """Message for a *value* that is neither missing (None) nor a string, else None.

    Falsy non-strings (`0`, `false`, `[]`, `{}`) must not collapse into "no password",
    which on a key export means the key leaves unencrypted.
    """
    if value is None or isinstance(value, str):
        return None
    return f'{field} must be a string'

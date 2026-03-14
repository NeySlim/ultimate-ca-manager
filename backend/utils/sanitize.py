"""Sanitization utilities for user-controlled input."""

import re


def sanitize_filename(name):
    """Sanitize a string for safe use in Content-Disposition headers.

    Removes/replaces characters that could cause header injection or
    filesystem issues.
    """
    if not name:
        return 'download'
    # Remove any control characters and CRLF
    name = re.sub(r'[\x00-\x1f\x7f\r\n]', '', name)
    # Remove path separators
    name = re.sub(r'[/\\]', '_', name)
    # Remove quotes
    name = name.replace('"', '')
    # Limit length
    name = name[:200]
    return name or 'download'

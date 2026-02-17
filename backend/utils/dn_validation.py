"""
DN (Distinguished Name) field validation utilities.

SECURITY: Validates DN fields to prevent injection attacks.
Shared across CAs, Certificates, and CSR modules.
"""

import re

# DN field validation regex patterns
DN_FIELD_PATTERNS = {
    'CN': re.compile(r'^[\w\s\-\.\,\'\@\(\)\*]+$', re.UNICODE),  # CN allows wildcards
    'O': re.compile(r'^[\w\s\-\.\,\'\&]+$', re.UNICODE),
    'OU': re.compile(r'^[\w\s\-\.\,\'\&]+$', re.UNICODE),
    'C': re.compile(r'^[A-Z]{2}$'),
    'ST': re.compile(r'^[\w\s\-\.]+$', re.UNICODE),
    'L': re.compile(r'^[\w\s\-\.]+$', re.UNICODE),
}

MAX_DN_FIELD_LENGTH = 64


def validate_dn_field(field_name, value):
    """
    SECURITY: Validate a single DN field to prevent injection attacks.
    Returns (is_valid, error_message)
    """
    if not value:
        return True, None

    value = str(value).strip()

    if len(value) > MAX_DN_FIELD_LENGTH:
        return False, f"{field_name} must be {MAX_DN_FIELD_LENGTH} characters or less"

    if field_name in DN_FIELD_PATTERNS:
        if not DN_FIELD_PATTERNS[field_name].match(value):
            return False, f"Invalid characters in {field_name}"

    # Block common injection patterns
    dangerous_patterns = [';', '|', '`', '$', '\\n', '\\r', '\x00', '\n', '\r']
    for pattern in dangerous_patterns:
        if pattern in value:
            return False, f"Invalid character in {field_name}"

    return True, None


def validate_dn(dn_dict):
    """Validate all DN fields in a dict."""
    for field, value in dn_dict.items():
        if value:
            is_valid, error = validate_dn_field(field, value)
            if not is_valid:
                return False, error
    return True, None

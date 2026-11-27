"""Shared validation for SSH CA setup script parameters."""

import re

_SETUP_HOSTNAME_RE = re.compile(r'^[a-zA-Z0-9._-]+$')


def validate_setup_hostname(hostname: str) -> str | None:
    """Return an error message if hostname is invalid, else None.

    Hostnames are embedded into generated shell/PowerShell scripts; only a
    conservative charset is allowed (same rule as the authenticated endpoint).
    """
    if not hostname:
        return None
    if not _SETUP_HOSTNAME_RE.match(hostname):
        return 'Invalid hostname format'
    return None


def validate_ca_descr(descr: str) -> str | None:
    """The description is printed in the setup scripts and the interface: one line of text."""
    from .script_quoting import has_control_character
    if has_control_character(descr):
        return 'Description must not contain control characters or line breaks'
    return None

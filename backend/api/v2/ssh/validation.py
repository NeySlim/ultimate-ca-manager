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

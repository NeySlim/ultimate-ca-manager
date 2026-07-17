"""Sanitization utilities for user-controlled input."""

import re


def sanitize_filename(name):
    """Sanitize a string for safe use in Content-Disposition headers.

    Removes/replaces characters that could cause header injection or
    filesystem issues.
    """
    if not name:
        return "download"
    # Remove any control characters and CRLF
    name = re.sub(r"[\x00-\x1f\x7f\r\n]", "", name)
    # Remove path separators
    name = re.sub(r"[/\\]", "_", name)
    # Remove quotes
    name = name.replace('"', "")
    # Limit length
    name = name[:200]
    return name or "download"


def slugify_filename_component(name: str, *, max_len: int = 48) -> str:
    """Filesystem-/header-safe slug for human-readable CRL download names."""
    if not name:
        return "ca"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip())
    slug = re.sub(r"-{2,}", "-", slug).strip("-._")
    slug = sanitize_filename(slug)[:max_len].rstrip("-._")
    return slug or "ca"


def crl_download_filename(ca, *, delta: bool = False) -> str:
    """Human-readable CRL attachment name: ``{slug}-{refid8}.crl``."""
    slug = slugify_filename_component(getattr(ca, "descr", None) or "ca")
    ref = (getattr(ca, "refid", None) or "unknown")[:8]
    suffix = "-delta.crl" if delta else ".crl"
    return f"{slug}-{ref}{suffix}"

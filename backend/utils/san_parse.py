"""Parse and validate Subject Alternative Name entries for CSR creation."""
from __future__ import annotations

import re
from ipaddress import ip_address
from typing import Dict, List, Tuple
from urllib.parse import urlparse

from utils.upn_san import is_valid_upn

SanBuckets = Dict[str, List[str]]

_EMAIL_RE = re.compile(
    r'^[a-zA-Z0-9.!#$%&\'*+\/=?^_`{|}~-]+'
    r'@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?'
    r'(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$'
)


def _empty_buckets() -> SanBuckets:
    return {
        'san_dns': [],
        'san_ip': [],
        'san_email': [],
        'san_uri': [],
        'san_upn': [],
    }


def is_valid_san_email(value: str) -> bool:
    if not value or not isinstance(value, str):
        return False
    return bool(_EMAIL_RE.match(value.strip()))


def is_valid_san_uri(value: str) -> bool:
    """RFC 5280 uniformResourceIdentifier — absolute URI with scheme."""
    v = (value or '').strip()
    if not v:
        return False
    parsed = urlparse(v)
    if not parsed.scheme:
        return False
    return bool(re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*$', parsed.scheme))


def _looks_like_ip(value: str) -> bool:
    try:
        ip_address(value.strip())
        return True
    except ValueError:
        return False


def validate_dns_san(value: str) -> str | None:
    if _looks_like_ip(value):
        return (
            f'Use IP type for IP addresses: {value}. '
            'DNS SAN is for hostnames and FQDNs only.'
        )
    if '@' in value:
        return f'Use Email type for addresses like {value}'
    if '://' in value:
        return f'Use URI type for URIs like {value}'
    return None


def validate_ip_san(value: str) -> str | None:
    if _looks_like_ip(value):
        return None
    return (
        f'Invalid IP address for IP SAN: {value}. '
        'Use DNS type for hostnames and FQDNs.'
    )


def validate_email_san(value: str) -> str | None:
    if is_valid_san_email(value):
        return None
    if '@' not in value:
        return (
            f'Invalid Email SAN: {value}. '
            'Use DNS type for hostnames; Email type requires user@domain.'
        )
    return f'Invalid email address: {value}'


def validate_uri_san(value: str) -> str | None:
    if is_valid_san_uri(value):
        return None
    if '@' in value and is_valid_san_email(value):
        return f'Use Email type for {value}'
    return (
        f'URI SAN must include a scheme (e.g. https://example.com): {value}'
    )


def validate_upn_san(value: str) -> str | None:
    if is_valid_upn(value):
        return None
    return f'Invalid UPN format: {value} (expected user@domain)'


def parse_csr_san_entries(entries: List[str]) -> Tuple[SanBuckets, str | None]:
    """Parse SAN list from CSR UI (``DNS:host``, ``IP:1.2.3.4``, …)."""
    buckets = _empty_buckets()

    for raw in entries or []:
        entry = (raw or '').strip()
        if not entry:
            continue
        lower = entry.lower()

        if lower.startswith('email:'):
            val = entry[6:].strip()
            if not val:
                continue
            err = validate_email_san(val)
            if err:
                return buckets, err
            buckets['san_email'].append(val)
            continue

        if lower.startswith('uri:'):
            val = entry[4:].strip()
            if not val:
                continue
            err = validate_uri_san(val)
            if err:
                return buckets, err
            buckets['san_uri'].append(val)
            continue

        if lower.startswith('upn:'):
            val = entry[4:].strip()
            if not val:
                continue
            err = validate_upn_san(val)
            if err:
                return buckets, err
            buckets['san_upn'].append(val)
            continue

        if lower.startswith('ip:'):
            val = re.sub(r'^IP:\s*', '', entry, flags=re.IGNORECASE).strip()
            if not val:
                continue
            err = validate_ip_san(val)
            if err:
                return buckets, err
            buckets['san_ip'].append(str(ip_address(val)))
            continue

        if lower.startswith('dns:'):
            val = re.sub(r'^DNS:\s*', '', entry, flags=re.IGNORECASE).strip()
            if not val:
                continue
            err = validate_dns_san(val)
            if err:
                return buckets, err
            buckets['san_dns'].append(val)
            continue

        # Legacy / unprefixed: auto-detect
        if _looks_like_ip(entry):
            buckets['san_ip'].append(str(ip_address(entry)))
        elif '@' in entry and is_valid_san_email(entry):
            buckets['san_email'].append(entry)
        elif is_valid_san_uri(entry):
            buckets['san_uri'].append(entry)
        elif is_valid_upn(entry):
            buckets['san_upn'].append(entry)
        else:
            buckets['san_dns'].append(entry)

    return buckets, None

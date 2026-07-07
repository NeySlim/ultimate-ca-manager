"""
CAA (Certificate Authority Authorization) Record Checker
Implements RFC 6844 + RFC 8555 §8.1

Checks DNS CAA records to determine if a CA is authorized to issue
certificates for a domain. Used by ACME protocol before issuance.

Rules:
- No CAA record at domain or any parent → issuance ALLOWED
- CAA record exists with matching issuer → issuance ALLOWED
- CAA record exists without matching issuer → issuance DENIED
- issuewild tag controls wildcard issuance specifically
"""
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


def check_caa(domain: str, issuer_domains: Optional[List[str]] = None) -> Tuple[bool, str]:
    """Check CAA records for a domain (RFC 6844).
    
    Walks up the domain hierarchy until a CAA record is found or
    the public suffix is reached.
    
    Args:
        domain: The domain to check (e.g. "www.example.com")
        issuer_domains: List of issuer domain identifiers this CA uses
                       (e.g. ["ucm.local", "ucm.tools"]). If None, any
                       CAA record with an issue tag will deny issuance.
    
    Returns:
        Tuple of (allowed: bool, reason: str)
    """
    import dns.resolver
    import dns.exception

    if not issuer_domains:
        issuer_domains = []

    # Strip wildcard prefix for lookup (only the leading "*." label, not an
    # arbitrary set of leading '*'/'.' characters as lstrip('*.') would do)
    is_wildcard = domain.startswith('*.')
    check_domain = domain[2:] if is_wildcard else domain

    # Walk up the domain tree (RFC 6844 §4)
    parts = check_domain.split('.')
    for i in range(len(parts)):
        lookup_domain = '.'.join(parts[i:])
        if not lookup_domain or '.' not in lookup_domain:
            break

        try:
            answers = dns.resolver.resolve(lookup_domain, 'CAA')
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            continue
        except dns.exception.DNSException as e:
            logger.warning(f"CAA DNS lookup failed for {lookup_domain}: {e}")
            continue

        # CAA records found — check them
        issue_tags = []
        issuewild_tags = []

        for rdata in answers:
            flag = rdata.flags
            tag = rdata.tag.decode().lower() if isinstance(rdata.tag, bytes) else rdata.tag.lower()
            value = rdata.value.decode().strip() if isinstance(rdata.value, bytes) else rdata.value.strip()

            # Strip any parameters (e.g. "letsencrypt.org; accounturi=...")
            issuer_value = value.split(';')[0].strip().strip('"')

            if tag == 'issue':
                issue_tags.append(issuer_value)
            elif tag == 'issuewild':
                issuewild_tags.append(issuer_value)

        # For wildcard certs, check issuewild first, fall back to issue
        if is_wildcard and issuewild_tags:
            tags_to_check = issuewild_tags
        elif is_wildcard and issue_tags:
            tags_to_check = issue_tags
        else:
            tags_to_check = issue_tags

        if not tags_to_check:
            # CAA record exists but no issue/issuewild tags → allowed
            return True, f"CAA record at {lookup_domain} has no issue tags"

        # Empty value in issue tag means "deny all"
        if '' in tags_to_check and len(tags_to_check) == 1:
            return False, f"CAA record at {lookup_domain} denies all issuance (issue \";\")"

        # Check if any issuer_domain matches
        for issuer in issuer_domains:
            issuer_lower = issuer.lower()
            for tag_value in tags_to_check:
                if tag_value.lower() == issuer_lower:
                    return True, f"CAA authorized: {issuer} matches at {lookup_domain}"

        # CAA records exist but no match
        denied_msg = f"CAA at {lookup_domain} allows {tags_to_check}, not {issuer_domains}"
        return False, denied_msg

    # No CAA record found anywhere → issuance allowed (RFC 6844 §4)
    return True, "No CAA record found (issuance allowed by default)"


def check_caa_for_domains(
    domains: List[str],
    issuer_domains: Optional[List[str]] = None
) -> Tuple[bool, str]:
    """Check CAA records for multiple domains.
    
    All domains must pass CAA check for issuance to be allowed.
    
    Args:
        domains: List of domains to check
        issuer_domains: CA's issuer identifiers
    
    Returns:
        Tuple of (all_allowed: bool, reason: str)
    """
    for domain in domains:
        allowed, reason = check_caa(domain, issuer_domains)
        if not allowed:
            return False, f"CAA check failed for {domain}: {reason}"

    return True, "All domains passed CAA check"

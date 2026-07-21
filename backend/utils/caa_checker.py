"""
CAA (Certificate Authority Authorization) record checker.

Implements RFC 8659 CAA processing and the RFC 8657 ``accounturi`` and
``validationmethods`` issuer parameters used by ACME issuance.
"""
import logging
from typing import Dict, List, Mapping, Optional, Tuple

logger = logging.getLogger(__name__)

_KNOWN_PROPERTY_TAGS = frozenset({'issue', 'issuewild', 'iodef'})
_CRITICAL_FLAG = 128


def _parse_issuer_value(value: str) -> Tuple[str, Dict[str, List[str]]]:
    """Return the issuer domain and its case-insensitive parameter names."""
    segments = value.strip().strip('"').split(';')
    issuer = segments[0].strip()
    parameters: Dict[str, List[str]] = {}
    for segment in segments[1:]:
        if '=' not in segment:
            continue
        name, parameter_value = segment.split('=', 1)
        normalized_name = name.strip().lower()
        if not normalized_name:
            continue
        parameters.setdefault(normalized_name, []).append(
            parameter_value.strip().strip('"')
        )
    return issuer, parameters


def _parameters_allow(
    parameters: Mapping[str, List[str]],
    account_url: Optional[str],
    validation_method: Optional[str],
) -> Tuple[bool, Optional[str]]:
    account_uris = parameters.get('accounturi', [])
    if account_uris and (
        account_url is None or any(uri != account_url for uri in account_uris)
    ):
        return False, 'accounturi does not match the requesting ACME account'

    method_parameters = parameters.get('validationmethods', [])
    if method_parameters:
        normalized_method = validation_method.lower() if validation_method else None
        allowed_method_sets = [
            {method.strip().lower() for method in value.split(',') if method.strip()}
            for value in method_parameters
        ]
        if normalized_method is None or any(
            normalized_method not in allowed_methods
            for allowed_methods in allowed_method_sets
        ):
            return False, 'validationmethods does not allow the validation method used'

    return True, None


def check_caa(
    domain: str,
    issuer_domains: Optional[List[str]] = None,
    account_url: Optional[str] = None,
    validation_method: Optional[str] = None,
) -> Tuple[bool, str]:
    """Check whether CAA authorizes issuance for one DNS identifier.

    ``account_url`` is compared exactly when an RFC 8657 ``accounturi``
    parameter is present. ``validation_method`` is the ACME challenge type
    actually used for this authorization (for example ``dns-01``).
    """
    import dns.exception
    import dns.resolver

    issuers = issuer_domains or []
    is_wildcard = domain.startswith('*.')
    check_domain = domain[2:] if is_wildcard else domain

    # Walk up the domain tree until the first CAA RRset is found.
    parts = check_domain.split('.')
    for i in range(len(parts)):
        lookup_domain = '.'.join(parts[i:])
        if not lookup_domain or '.' not in lookup_domain:
            break

        try:
            answers = dns.resolver.resolve(lookup_domain, 'CAA')
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            continue
        except dns.exception.DNSException as exc:
            logger.warning("CAA DNS lookup failed for %s: %s", lookup_domain, exc)
            return False, f"CAA DNS lookup failed for {lookup_domain}"

        issue_records = []
        issuewild_records = []

        for rdata in answers:
            flags = int(rdata.flags)
            tag = rdata.tag.decode() if isinstance(rdata.tag, bytes) else rdata.tag
            tag = tag.lower()
            value = rdata.value.decode() if isinstance(rdata.value, bytes) else rdata.value
            value = value.strip()

            if tag not in _KNOWN_PROPERTY_TAGS and flags & _CRITICAL_FLAG:
                return False, (
                    f"CAA at {lookup_domain} has unknown critical property {tag}"
                )

            if tag == 'iodef':
                logger.info("CAA iodef for %s: %s", lookup_domain, value)
                continue

            if tag not in ('issue', 'issuewild'):
                continue

            issuer, parameters = _parse_issuer_value(value)
            record = (issuer, parameters)
            if tag == 'issue':
                issue_records.append(record)
            else:
                issuewild_records.append(record)

        if is_wildcard and issuewild_records:
            records_to_check = issuewild_records
        else:
            records_to_check = issue_records

        if not records_to_check:
            return True, f"CAA record at {lookup_domain} has no issue tags"

        issuer_values = [issuer for issuer, _parameters in records_to_check]
        if issuer_values == ['']:
            return False, (
                f'CAA record at {lookup_domain} denies all issuance (issue ";")'
            )

        restriction_failures = []
        for configured_issuer in issuers:
            for record_issuer, parameters in records_to_check:
                if record_issuer.lower() != configured_issuer.lower():
                    continue
                allowed, failure = _parameters_allow(
                    parameters,
                    account_url,
                    validation_method,
                )
                if allowed:
                    return True, (
                        f"CAA authorized: {configured_issuer} matches at {lookup_domain}"
                    )
                if failure:
                    restriction_failures.append(failure)

        if restriction_failures:
            failures = ', '.join(dict.fromkeys(restriction_failures))
            return False, f"CAA at {lookup_domain} denies issuance: {failures}"

        return False, (
            f"CAA at {lookup_domain} allows {issuer_values}, not {issuers}"
        )

    return True, "No CAA record found (issuance allowed by default)"


def check_caa_for_domains(
    domains: List[str],
    issuer_domains: Optional[List[str]] = None,
    account_url: Optional[str] = None,
    validation_methods: Optional[Mapping[str, Optional[str]]] = None,
) -> Tuple[bool, str]:
    """Check CAA for multiple domains; every domain must be authorized."""
    methods = validation_methods or {}
    for domain in domains:
        allowed, reason = check_caa(
            domain,
            issuer_domains,
            account_url=account_url,
            validation_method=methods.get(domain),
        )
        if not allowed:
            return False, f"CAA check failed for {domain}: {reason}"

    return True, "All domains passed CAA check"

"""dns-persist-01 — persistent DNS TXT record validation.

Implements the CA side of draft-ietf-acme-dns-persist-01
(ACME Challenge for Persistent DNS TXT Record Validation). Wire summary:

- Challenge type ``dns-persist-01``; the object carries ``accounturi`` and
  ``issuer-domain-names``.
- The client provisions a TXT record at ``_validation-persist.<FQDN>``.
- Record RDATA is RFC 8659 issue-value syntax:
  ``<issuer-domain-name>; accounturi=<URI>[; policy=wildcard][; persistUntil=<unix>]``
- Optional ``policy=wildcard`` (case-insensitive value) extends the
  authorization to wildcard certs and subdomains of the validated FQDN.
- ``persistUntil`` bounds the record's usable lifetime for NEW validation
  attempts; a non-integer value makes the record malformed.

This module holds pure parsing/matching helpers plus the SystemConfig
plumbing. The DNS lookup orchestration lives in
``services/acme/mixins/challenge.py::validate_dns_persist01_challenge``.

SECURITY: this method gives long-lived issuance capability bound to an ACME
account (draft §7.1/§7.2) — a leaked account key can issue for the domain
as long as the record exists. That is why the feature is opt-in
(``acme.dns_persist_enabled``, default off) and its enabling toggle carries
an explicit warning in the UI.
"""
import logging
import re

logger = logging.getLogger(__name__)

CONFIG_ENABLED_KEY = 'acme.dns_persist_enabled'
# Issuer domain names derive from the CAA issuer configuration when present
# (draft §3.1 note: caaIdentities and issuer-domain-names SHOULD be
# consistent), and fall back to the ACME public hostname otherwise.
CAA_IDENTIFIERS_KEY = 'acme_caa_identifiers'

VALIDATION_LABEL = '_validation-persist'
_MAX_ISSUER_DOMAINS = 10  # draft §3.1

_DOMAIN_RE = re.compile(r'^(?=.{1,253}$)[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$')


def is_enabled() -> bool:
    """Whether the server offers and validates dns-persist-01 challenges.

    Never raises — a DB lookup failure means the feature stays off."""
    try:
        from models import SystemConfig
        row = SystemConfig.query.filter_by(key=CONFIG_ENABLED_KEY).first()
        return bool(row and (row.value or '').strip().lower() == 'true')
    except Exception:
        return False


def normalize_domain(name: str) -> str:
    """Draft §9.2 normalization (subset): lowercase + no trailing dot.

    Numeric IDN A-label conversion is expected to have happened upstream —
    ACME identifiers in UCM are already stored in DNS form.
    """
    return (name or '').strip().rstrip('.').lower()


def get_issuer_domain_names(fallback_host: str = None) -> list:
    """Issuer-domain-names advertised in dns-persist-01 challenges.

    Prefers the configured CAA issuer identifiers (draft recommends
    consistency with caaIdentities); falls back to the ACME public hostname.
    Always normalized per draft §3.1 (lowercase, no trailing dot) and capped
    at 10 entries.
    """
    try:
        from models import SystemConfig
        row = SystemConfig.query.filter_by(key=CAA_IDENTIFIERS_KEY).first()
    except Exception:
        row = None
    if row and (row.value or '').strip():
        domains = [normalize_domain(d) for d in row.value.split(',') if d.strip()]
        domains = [d for d in domains if d]
        if domains:
            return domains[:_MAX_ISSUER_DOMAINS]
    host = normalize_domain(fallback_host or '')
    return [host] if host else []


def parse_issue_value(record: str):
    """Parse an RFC 8659 issue-value string.

    Returns ``(issuer_domain, params_dict)`` with lowercase tag keys and raw
    values (whitespace-stripped). Raises ValueError('malformed: ...') on
    syntactic violations that the draft calls out as *malformed* (duplicate
    parameters, invalid persistUntil). Unknown tags are ignored per
    draft §4.1 item 1.
    """
    parts = record.split(';')
    issuer = normalize_domain(parts[0])
    if not issuer or not _DOMAIN_RE.match(issuer):
        raise ValueError(f'malformed: invalid issuer-domain-name: {issuer!r}')

    params = {}
    seen = set()
    for chunk in parts[1:]:
        if not chunk.strip():
            continue
        if '=' not in chunk:
            # tolerate bare tags? RFC 8659 requires tag=value — treat as
            # malformed only for tags we know; ignore unknown ones.
            tag = chunk.strip().lower()
            if tag in ('accounturi', 'policy', 'persistuntil'):
                raise ValueError(f'malformed: missing value for {tag}')
            continue
        tag, _, value = chunk.partition('=')
        tag = tag.strip().lower()
        value = value.strip()
        if tag in seen:
            raise ValueError(f'malformed: duplicate parameter: {tag}')
        seen.add(tag)
        if tag not in ('accounturi', 'policy', 'persistuntil'):
            continue  # draft §4.1 item 1 — forward compatibility
        params[tag] = value

    # persistUntil must be a base-10 integer when present (§4.1 item 5)
    if 'persistuntil' in params:
        pu = params['persistuntil']
        if not pu.isdigit():
            raise ValueError(f'malformed: persistUntil is not a base-10 integer: {pu!r}')
        params['persistuntil'] = int(pu)

    return issuer, params


def rdata_strings(rdata) -> list:
    """dnspython TXT rdata → list of full string values.

    Joins multi-string RDATA (RFC 1035 255-octet chunks, §9.1 of the
    draft) back into one logical value per record.
    """
    try:
        return [b''.join(rdata.strings).decode('utf-8', errors='replace')]
    except AttributeError:
        return [str(rdata).strip('"')]


def check_record_against(issuer, params, issuer_domains, account_uri,
                         is_exact_fqdn: bool, is_wildcard_request: bool,
                         now_ts: int):
    """Validate one parsed record. Returns ``(ok, error_type, detail)``.

    error_type follows draft §9.3.1: 'malformed' for record syntax issues,
    'unauthorized' for authorization mismatches.
    """
    if issuer not in issuer_domains:
        return False, None, None  # not ours — record ignored entirely

    account_in_record = params.get('accounturi')
    if not account_in_record:
        return False, 'malformed', (
            'dns-persist-01 record is missing the mandatory accounturi parameter'
        )

    # persistUntil: bound on NEW validation attempts (§4.1 item 5)
    persist_until = params.get('persistuntil')
    if persist_until is not None and now_ts > persist_until:
        return False, 'unauthorized', (
            'dns-persist-01 record persistUntil has expired — refresh the record'
        )

    # accounturi — Simple String Comparison (RFC 3986 §6.2.1): exact match
    if account_in_record != account_uri:
        return False, 'unauthorized', (
            'dns-persist-01 record accounturi does not identify this ACME account'
        )

    policy_wildcard = params.get('policy', '').lower() == 'wildcard'
    # Exact-FQDN record authorizes the plain FQDN with or without a wildcard
    # policy; a wildcard request and any ancestor (subdomain-authorizing)
    # record REQUIRE policy=wildcard (§5, §6.2).
    if (is_wildcard_request or not is_exact_fqdn) and not policy_wildcard:
        return False, 'unauthorized', (
            'dns-persist-01 record needs policy=wildcard to authorize '
            'wildcard or subdomain identifiers'
        )

    return True, None, None

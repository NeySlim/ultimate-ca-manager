"""
LDAP client for the Active Directory Connector.

Two things live here:

1. Kerberos principal parsing (``parse_kerberos_principal``, ``is_machine_principal``)
   -- a real Kerberos machine account principal from ``services/kerberos/
   negotiate_auth.py`` looks like ``WIN11$@HAGLAND.DOMAIN`` (confirmed
   against the lab); the trailing ``$`` on the pre-@ part is how AD marks a
   computer account's sAMAccountName, and is how WSTEP tells a machine from a
   user. The template comes from the request (311.21.7 or 311.20.2, else its
   EKUs, see wstep_service.py's ``_match_template``), never the principal.

2. The actual AD lookups, each against the connector its caller passes: the SID
   checks of WSTEP issuance and of EST, SCEP and WSTEP renewals
   (``lookup_object_sid``, ``lookup_account_by_sid``), group membership, and
   ``lookup_computer_dns_hostname``/``lookup_user_ad_identity``, which MS-WSTEP's
   Kerberos issuance path uses to resolve a naked (subject-less) CSR's identity: real Windows unattended
   GPO autoenrollment intentionally submits a CSR with no CN/SAN for
   templates configured to build the subject from Active Directory,
   trusting the CA to derive it server-side -- ``CN=<computer's AD
   dnsHostName>`` for a machine account, or the user object's own
   directory-path DN plus its ``userPrincipalName`` as a SAN OtherName for
   a person account -- exactly what real ADCS does from the requester's AD
   object. UCM has no other source for that identity, hence this connector.

Bind/search mechanics mirror ``api/v2/sso/connection_tests.py``'s
``_ldap_authenticate_user``/``api/v2/sso/helpers.py``'s ``_build_ldap_tls``
(same ``ldap3`` conventions), but operate on the ``ADConnectorConfig`` row the caller passes
-- not ``SSOProvider`` -- and fix a leaked
temp CA-bundle file that exists in that code (no matching cleanup there).

The public lookups never raise: they answer None (or False) when the connector is
off or the object is not found (``NO_ACCOUNT`` for a principal or SID naming no
account), and the falsy ``UNREACHABLE`` when no DC binds, a
search raises or returns an LDAP error result, or the enabled connector lacks a server
or base DN, so a caller can refuse the request or fault on its own side.
"""
import contextvars
import logging
import os
import re
import ssl
import tempfile
import time

logger = logging.getLogger(__name__)


class _Falsy:
    """A falsy lookup answer told apart from None ("not found") by identity."""
    __slots__ = ('_name',)

    def __init__(self, name):
        self._name = name

    def __bool__(self):
        return False

    def __repr__(self):
        return self._name


# No DC bound, a search failed, or the enabled connector has no server or base DN.
UNREACHABLE = _Falsy('UNREACHABLE')
# The account exists but has no userPrincipalName.
NO_UPN = _Falsy('NO_UPN')
# The account exists but its objectSid is missing or malformed.
UNUSABLE_SID = _Falsy('UNUSABLE_SID')
# The Kerberos principal or the SID names no account (a SID matching a non-account
# object, such as a foreignSecurityPrincipal, included); FOREIGN_REALM: a realm the
# connector does not serve.
NO_ACCOUNT = _Falsy('NO_ACCOUNT')
FOREIGN_REALM = _Falsy('FOREIGN_REALM')


def _enabled_config(config):
    """(config, None) for a complete enabled connector; (None, None) when it is absent or
    disabled; (None, UNREACHABLE) when it is enabled but has no server or base DN."""
    if not config or not config.enabled:
        return None, None
    if not config.server or not config.base_dn:
        return None, UNREACHABLE
    return config, None


def parse_kerberos_principal(principal):
    """``'WIN11$@HAGLAND.DOMAIN'`` -> ``('WIN11$', 'HAGLAND.DOMAIN')``.

    The realm follows the last unescaped ``@`` (an uncanonicalized enterprise name,
    RFC 6806, keeps an escaped one). ``None`` for an empty part, or a name holding ``@`` or
    ``\\``, which no sAMAccountName does.
    """
    if not principal:
        return None
    at = next((i for i in range(len(principal) - 1, -1, -1)
               if principal[i] == '@' and (i == 0 or principal[i - 1] != '\\')), None)
    if at is None:
        return None
    local, realm = principal[:at], principal[at + 1:]
    if not local or not realm or '@' in local or '\\' in local:
        return None
    return local, realm


def _normalized_dn(dn):
    """``dn`` with the spaces around unescaped separators dropped and ``;`` read as ``,``:
    AD accepts that writing and RFC 4514 §3 lets a reader accept other forms."""
    out, i = [], 0
    dn = dn.lstrip(' ')
    n = len(dn)
    while i < n:
        c = dn[i]
        if c == '\\' and i + 1 < n:
            out.append(dn[i:i + 2])
            i += 2
            continue
        if c in ',;=+':
            while out and out[-1] == ' ':
                out.pop()
            out.append(',' if c == ';' else c)
            i += 1
            while i < n and dn[i] == ' ':
                i += 1
            continue
        out.append(c)
        i += 1
    while out and out[-1] == ' ':
        out.pop()
    return ''.join(out)


def realm_of_base_dn(base_dn):
    """``'DC=hagland,DC=domain'`` -> ``'HAGLAND.DOMAIN'`` -- the standard AD
    convention of domain DNS name == Kerberos realm (upper-cased). ``None``
    if the DN does not parse or has no DC components at all."""
    from ldap3.utils.dn import parse_dn

    if not base_dn:
        return None
    try:
        components = parse_dn(_normalized_dn(base_dn))
    except Exception:
        return None
    dc_values = [value for attr, value, _sep in components if attr.upper() == 'DC']
    if not dc_values:
        return None
    return '.'.join(dc_values).upper()


def domain_head_dn(base_dn):
    """The DN made of the DC components of ``base_dn`` alone (the domain head), escapes
    kept; None when it has none."""
    from ldap3.utils.dn import parse_dn

    if not base_dn:
        return None
    try:
        components = parse_dn(_normalized_dn(base_dn))
    except Exception:
        return None
    head = [f'{attr}={value}' for attr, value, _sep in components if attr.upper() == 'DC']
    return ','.join(head) or None


def realm_matches_connector(config, realm):
    """Whether ``realm`` (from an authenticated Kerberos principal, e.g.
    ``'HAGLAND.DOMAIN'``) matches the domain this AD Connector is configured
    against, so a caller can refuse to map a principal from an unexpected
    realm to a same-named ``sAMAccountName`` in *this* domain -- Kerberos
    cross-realm trust means a client_principal's realm isn't necessarily the
    domain UCM's AD Connector actually points at, and ``sAMAccountName``
    alone (what ``parse_kerberos_principal`` splits it into) is not globally
    unique the way a realm-qualified principal is.

    False (fail closed) if the connector isn't configured/enabled, its
    base_dn doesn't parse to a realm, or ``realm`` is empty -- callers must
    treat that identically to "lookup not possible", not "skip the check".
    Never raises.
    """
    if not realm:
        return False
    if not config or not config.enabled or not config.base_dn:
        return False
    connector_realm = realm_of_base_dn(config.base_dn)
    # RFC 4120 §6.1: realm names compare exactly; AD's is its domain in capitals
    return bool(connector_realm) and connector_realm == realm


def _config_fault(config):
    if not config.server:
        return 'no server is configured'
    if not config.base_dn:
        return 'no base DN is configured'
    if not realm_of_base_dn(config.base_dn):
        return 'the base DN has no DC component to name its realm'
    return None


def connector_config_fault(config):
    """Why the enabled connector ``config`` cannot resolve a principal, or None."""
    if not config or not config.enabled:
        return None
    return _config_fault(config)


def connector_account(config, principal):
    """The sAMAccountName the enabled connector ``config`` checks ``principal`` against.

    None when the connector is absent or disabled; the falsy ``UNREACHABLE`` when it is
    enabled without a server or a base DN that names a realm; the falsy ``NO_ACCOUNT``
    or ``FOREIGN_REALM`` when the principal is malformed or of another realm, which a
    caller refuses rather than issuing without the checks the connector enforces.
    """
    if not config or not config.enabled:
        return None
    if _config_fault(config):
        return UNREACHABLE
    parsed = parse_kerberos_principal(principal)
    if not parsed:
        return NO_ACCOUNT
    if not realm_matches_connector(config, parsed[1]):
        return FOREIGN_REALM
    return parsed[0]


def is_machine_principal(principal):
    """Whether a Kerberos principal looks like a computer account.

    Never raises -- malformed input (no ``@``, empty string) is just not a
    machine principal, not an error.
    """
    parsed = parse_kerberos_principal(principal)
    return bool(parsed) and parsed[0].endswith('$')


def _build_tls(config):
    """``ldap3.Tls`` from a config-like object's ``use_ssl``/``verify_ssl``/
    ``ca_bundle``. Returns ``(tls, cleanup)`` -- ``cleanup()`` must always be
    called once the connection using it is done, to remove any temp
    CA-bundle file this created.
    """
    import ldap3

    verify_ssl = config.verify_ssl if config.verify_ssl is not None else True
    ca_path = None

    def cleanup():
        if ca_path:
            try:
                os.unlink(ca_path)
            except OSError:
                pass

    if not config.use_ssl and not verify_ssl:
        return None, cleanup
    if not verify_ssl:
        return ldap3.Tls(validate=ssl.CERT_NONE), cleanup

    ca_bundle = getattr(config, 'ca_bundle', None)
    if ca_bundle:
        fd, ca_path = tempfile.mkstemp(suffix='.pem', prefix='ucm_ad_connector_ca_')
        try:
            try:
                os.write(fd, ca_bundle.encode('utf-8') if isinstance(ca_bundle, str) else ca_bundle)
            finally:
                os.close(fd)
            return ldap3.Tls(ca_certs_file=ca_path, validate=ssl.CERT_REQUIRED), cleanup
        except Exception:
            # The caller never gets cleanup when this raises, so remove the file here.
            cleanup()
            raise

    # Verify requested, no explicit bundle: validate against the system
    # trust store rather than leaving ldap3 on its unvalidated default.
    return ldap3.Tls(validate=ssl.CERT_REQUIRED), cleanup


# ldap3 binds anonymously whenever either half of the credential is missing,
# and this connector reads the objects a certificate's subject is derived
# from. Every bind path refuses that rather than making it.
BIND_CREDENTIAL_MISSING = 'bind credentials missing, refusing anonymous bind'


def has_bind_credentials(config):
    """Whether a config-like object carries both halves of the bind credential."""
    return bool(getattr(config, 'bind_dn', None) and getattr(config, 'bind_password', None))


class ADConnectorConnectionError(Exception):
    """Every configured DC refused or failed. Carries the per-server reason
    list so a caller can show *why each one* failed rather than only the
    last error -- with several DCs the failures are often different
    (one down, one with a cert whose SAN doesn't match)."""

    def __init__(self, failures):
        self.failures = list(failures)
        super().__init__('; '.join(f'{host}: {err}' for host, err in self.failures))


def split_servers(raw):
    """A ``server`` field -> the domain controllers it names, in failover
    order, de-duplicated with first-occurrence order preserved.

    Accepts a list (what the settings form now sends) or a single string
    -- the string form keeps every config saved before this field became a
    list readable. Every entry is itself split on commas/newlines, list or
    not, so a pasted ``"dc1.corp.local, dc2.corp.local"`` does the obvious
    thing in a row of the form just as it does in the older single field,
    and what is stored matches what is read back.

    Never raises: it is called on the enrollment path and on a column that
    could have been hand-edited, so anything that is not a string -- a
    number in the list, a dict where the list should be -- is skipped
    rather than blowing up a lookup. The API rejects those shapes with a
    400 before they can be stored (``api/v2/ad_connector.py``).

    Each entry must be the DC's **own** hostname, not the domain name: a
    bare domain (``corp.local``) round-robins across every DC while TLS
    still verifies the certificate against the domain name, and a DC
    certificate issued from the stock Domain Controller template carries
    only that DC's own FQDN in its SAN -- so verification fails against
    whichever DC answers. Listing the DCs individually is what makes
    ``verify_ssl`` usable at all on a multi-DC domain.
    """
    if not raw:
        return []
    entries = raw if isinstance(raw, (list, tuple)) else [raw]
    servers = []
    for entry in entries:
        if not isinstance(entry, str):
            continue
        for part in re.split(r'[,\n]', entry):
            host = part.strip()
            if host and host not in servers:
                servers.append(host)
    return servers


def join_servers(servers):
    """``split_servers``' inverse, for the single ``server`` text column."""
    return '\n'.join(split_servers(servers))


def config_servers(config):
    """The DCs on a config-like object (saved row or form ``SimpleNamespace``)."""
    return split_servers(getattr(config, 'server', None))


# Every lookup here runs synchronously inside a WSTEP/XCEP request handler
# (gevent-cooperative, but still blocking that greenlet) -- a black-holed
# or firewall-dropped DC with no timeout would stall the enrollment request
# indefinitely instead of failing closed like every other error mode here.
_LDAP_CONNECT_TIMEOUT_SECONDS = 10
_LDAP_RECEIVE_TIMEOUT_SECONDS = 10
_clock = time.monotonic
# Set by a caller that must not wait one connect timeout per DC: no new bind starts past it
_bind_deadline = contextvars.ContextVar('ad_connector_bind_deadline', default=None)


def _connect_to(config, host, tls, connect_timeout=None):
    """Bind as the connector's service account against one DC. Raises on
    any failure. ``tls`` is built once by the caller and shared across
    every host -- it carries no per-host state, and rebuilding it per
    attempt would re-write the temp CA file for each DC."""
    import ldap3

    server = ldap3.Server(
        host, port=config.port, use_ssl=config.use_ssl,
        tls=tls, get_info=ldap3.ALL, connect_timeout=connect_timeout or _LDAP_CONNECT_TIMEOUT_SECONDS,
    )
    return ldap3.Connection(
        server, user=config.bind_dn, password=config.bind_password,
        auto_bind=True, check_names=False, receive_timeout=_LDAP_RECEIVE_TIMEOUT_SECONDS,
    )


def _connect(config):
    """Bind as the connector's service account. Returns an open, bound
    ``ldap3.Connection`` to the first configured DC that accepts it, so a
    single DC being down or presenting a certificate this connector won't
    verify does not take certificate enrollment down with it.

    Raises ``ADConnectorConnectionError`` (naming every DC and its own
    failure) if none of them bind, or ``ValueError`` if none are
    configured -- callers translate that into their own fail-safe
    behavior.
    """
    servers = config_servers(config)
    if not servers:
        raise ValueError('AD Connector has no server configured')
    if not has_bind_credentials(config):
        raise ValueError(BIND_CREDENTIAL_MISSING)

    # A DC the scheduled probe has already found unreachable is moved out of
    # the way, so an enrollment doesn't pay its connect timeout to rediscover
    # that. Advisory only: see services/ad_connector/health.py's prioritise,
    # which never returns an empty list and ignores a stale verdict.
    from services.ad_connector import health
    servers = health.prioritise(servers, getattr(config, 'health', None),
                                getattr(config, 'health_probe_interval', None))

    tls, cleanup = _build_tls(config)
    try:
        failures = []
        deadline = _bind_deadline.get()
        for host in servers:
            if failures and deadline is not None and _clock() >= deadline:
                break
            try:
                return _connect_to(config, host, tls)
            except Exception as e:
                # Info, not warning: with several DCs configured, one
                # refusing is the normal case this failover exists for.
                # Only exhausting every DC is worth a warning, and the
                # callers below already log that.
                logger.info('AD Connector: %s did not accept the bind: %s', host, e)
                failures.append((host, str(e)))
        raise ADConnectorConnectionError(failures)
    finally:
        # Deferred to here, not to the first successful bind: every
        # attempt above needs the CA bundle, and auto_bind=True has
        # completed each handshake synchronously by the time we arrive.
        cleanup()


_RESULT_SUCCESS = 0
_RESULT_SIZE_LIMIT_EXCEEDED = 4


def _search(conn, base_dn, search_filter, attributes):
    """The entries of a search the directory answered, else ``UNREACHABLE``.

    Connections skip raise_exceptions, so an error result (busy, unavailable, referral,
    noSuchObject on the base DN, insufficientAccessRights...) comes back with no entries
    and must not read as "not found"; a size-limited answer counts only for what it found.
    """
    conn.search(base_dn, search_filter, attributes=attributes)
    result = conn.result if isinstance(getattr(conn, 'result', None), dict) else {}
    code = result.get('result')
    if code == _RESULT_SUCCESS or (code == _RESULT_SIZE_LIMIT_EXCEEDED and conn.entries):
        return conn.entries
    logger.warning('AD Connector: search under %r failed: %s (%s) %s', base_dn,
                   result.get('description'), code, result.get('message') or '')
    return UNREACHABLE


def _single_entry(entries, sam_account_name, what='named'):
    """The one entry of an account search, None when there is none, else ``UNREACHABLE``:
    a Global Catalog also answers for child domains, whose accounts may share the name."""
    if entries is UNREACHABLE or not entries:
        return entries if entries is UNREACHABLE else None
    if len(entries) > 1:
        logger.warning("AD Connector: %d accounts %s %r (%s); point the connector at a "
                       "domain controller of the realm, not a global catalog", len(entries),
                       what, sam_account_name, ', '.join(e.entry_dn for e in entries))
        return UNREACHABLE
    return entries[0]


def lookup_computer_dns_hostname(config, sam_account_name):
    """The AD computer object's ``dNSHostName`` for ``sam_account_name``
    (e.g. ``'WIN11$'``, trailing ``$`` included -- it's a real part of the
    attribute value, not an LDAP filter metacharacter to strip).

    Returns ``None`` when the connector is not configured or disabled, the entry
    is not found or the attribute is empty/missing, and the falsy ``UNREACHABLE``
    when no DC binds or the search fails. Never raises.
    """
    from ldap3.utils.conv import escape_filter_chars

    config, fault = _enabled_config(config)
    if config is None:
        return fault

    try:
        conn = _connect(config)
    except Exception as e:
        logger.warning("AD Connector: bind failed during computer lookup: %s", e)
        return UNREACHABLE

    try:
        safe_sam = escape_filter_chars(sam_account_name)
        entries = _search(conn, config.base_dn, f'(&(objectClass=computer)(sAMAccountName={safe_sam}))',
                          ['dNSHostName'])
        entry = _single_entry(entries, sam_account_name)
        # Compared by identity: None and UNREACHABLE are the only non-entry answers
        if entry is None or entry is UNREACHABLE:
            return entry
        if 'dNSHostName' not in entry or not entry.dNSHostName.value:
            return None
        return str(entry.dNSHostName.value)
    except Exception as e:
        logger.warning("AD Connector: computer lookup failed: %s", e)
        return UNREACHABLE
    finally:
        try:
            conn.unbind()
        except Exception:
            pass


def _sid_bytes_to_string(raw):
    """Windows binary SID -> ``"S-1-5-21-...-<RID>"`` string form.

    Layout: ``byte[0]`` revision, ``byte[1]`` sub-authority count,
    ``bytes[2:8]`` big-endian identifier authority, then N x 4-byte
    little-endian sub-authorities. Verified against a real captured SID
    (both a live LDAP query for a lab machine account and the SID string
    embedded in a real ADCS-issued certificate's security extension agree
    on the domain-SID prefix) -- not spec-derived.

    ``None`` on any malformed input (wrong length for the declared
    sub-authority count, empty bytes) rather than raising -- this is
    untrusted binary data straight from a directory attribute.
    """
    if not raw or len(raw) < 8:
        return None
    revision = raw[0]
    sub_count = raw[1]
    expected_len = 8 + sub_count * 4
    if len(raw) != expected_len:
        return None
    authority = int.from_bytes(raw[2:8], 'big')
    sub_authorities = [
        int.from_bytes(raw[8 + i * 4:12 + i * 4], 'little')
        for i in range(sub_count)
    ]
    return f"S-{revision}-{authority}-" + "-".join(str(s) for s in sub_authorities)


def sid_domain(sid):
    """``'S-1-5-21-a-b-c-1105'`` -> ``'S-1-5-21-a-b-c'``: the domain an account SID belongs
    to, its last sub-authority being the RID (MS-DTYP 2.4.2.4); None when it has none."""
    head, sep, rid = (sid or '').rpartition('-')
    return head if sep and rid.isdecimal() and head.count('-') >= 3 else None


def lookup_object_sid(config, sam_account_name):
    """The AD object's ``objectSid`` (user or computer -- no ``objectClass``
    filter needed since ``sAMAccountName`` is domain-unique, machine
    accounts keep their trailing ``$``), as a ``"S-1-5-21-..."`` string --
    the exact form real ADCS embeds in the SID security extension
    (``szOID_NTDS_CA_SECURITY_EXT``, see services/trust_store/
    csr_operations_mixin.py's ``_ad_security_extension``) for KB5014754
    strong certificate mapping.

    ``ldap3`` does not auto-format ``objectSid`` -- ``entry.objectSid.value``
    returns the raw bytes mis-decoded as a string, so this reads
    ``raw_values[0]`` (the real binary SID) and converts it via
    ``_sid_bytes_to_string``.

    ``None`` when the connector is off or the entry is not found; the falsy ``UNUSABLE_SID``
    when its SID is missing, malformed or outside the connector's ``domain_sid`` (when known),
    so a base DN reaching another domain cannot lend its SID; the falsy ``UNREACHABLE`` when the directory cannot
    answer. Never raises. A caller telling "connector off" from "not found" resolves the
    account with ``connector_account`` first.
    """
    from ldap3.utils.conv import escape_filter_chars

    config, fault = _enabled_config(config)
    if config is None:
        return fault

    try:
        conn = _connect(config)
    except Exception as e:
        logger.warning("AD Connector: bind failed during SID lookup: %s", e)
        return UNREACHABLE

    try:
        safe_sam = escape_filter_chars(sam_account_name)
        entries = _search(conn, config.base_dn, f'(sAMAccountName={safe_sam})', ['objectSid'])
        entry = _single_entry(entries, sam_account_name)
        # Compared by identity: None and UNREACHABLE are the only non-entry answers
        if entry is None or entry is UNREACHABLE:
            return entry
        if 'objectSid' not in entry or not entry.objectSid.raw_values:
            return UNUSABLE_SID
        sid = _sid_bytes_to_string(entry.objectSid.raw_values[0])
        domain = getattr(config, 'domain_sid', None)
        if sid and domain and sid_domain(sid) != domain:
            logger.warning("AD Connector: %r has SID %s, outside the connector's domain %s",
                           sam_account_name, sid, domain)
            return UNUSABLE_SID
        return sid or UNUSABLE_SID
    except Exception as e:
        logger.warning("AD Connector: SID lookup failed: %s", e)
        return UNREACHABLE
    finally:
        try:
            conn.unbind()
        except Exception:
            pass


def _sid_string_to_bytes(sid):
    """``"S-1-5-21-...-<RID>"`` -> binary SID (inverse of ``_sid_bytes_to_string``), None if malformed."""
    parts = (sid or '').split('-')
    if len(parts) < 4 or parts[0] != 'S' or not all(p.isdecimal() and p.isascii() for p in parts[1:]):
        return None
    revision, authority, subs = int(parts[1]), int(parts[2]), [int(p) for p in parts[3:]]
    if revision != 1 or authority >= 1 << 48 or len(subs) > 15 or any(s >= 1 << 32 for s in subs):
        return None
    return (bytes([revision, len(subs)]) + authority.to_bytes(6, 'big')
            + b''.join(s.to_bytes(4, 'little') for s in subs))


def lookup_account_by_sid(config, sid):
    """The ``sAMAccountName`` of the one directory object whose ``objectSid`` is ``sid``.

    None when the connector is off; the falsy ``NO_ACCOUNT`` when ``sid`` is malformed or
    names no account (no object, one without ``sAMAccountName``, or one whose returned
    ``objectSid`` is not ``sid``) under the base DN; the falsy ``UNREACHABLE`` when the
    directory cannot answer or several objects match. Never raises.
    """
    from ldap3.utils.conv import escape_bytes

    config, fault = _enabled_config(config)
    if config is None:
        return fault
    raw = _sid_string_to_bytes(sid)
    if raw is None:
        return NO_ACCOUNT

    try:
        conn = _connect(config)
    except Exception as e:
        logger.warning("AD Connector: bind failed during SID lookup: %s", e)
        return UNREACHABLE

    try:
        entries = _search(conn, config.base_dn, f'(objectSid={escape_bytes(raw)})',
                          ['sAMAccountName', 'objectSid'])
        entry = _single_entry(entries, sid, 'with the SID')
        if entry is None:
            return NO_ACCOUNT
        if entry is UNREACHABLE:
            return entry
        # The directory's own answer must carry the SID searched for
        if 'objectSid' not in entry or not entry.objectSid.raw_values \
                or _sid_bytes_to_string(entry.objectSid.raw_values[0]) != sid:
            return NO_ACCOUNT
        # objectSid alone matches non-accounts too (a foreignSecurityPrincipal): an account has a name
        name = entry.sAMAccountName.value if 'sAMAccountName' in entry else None
        return str(name) if name else NO_ACCOUNT
    except Exception as e:
        logger.warning("AD Connector: account lookup by SID failed: %s", e)
        return UNREACHABLE
    finally:
        try:
            conn.unbind()
        except Exception:
            pass


def lookup_user_ad_identity(config, sam_account_name):
    """The AD user object's directory path (as ordered RDN components, for
    building an x509.Name matching real ADCS's directory-path subject),
    userPrincipalName, and mail (if set), for ``sam_account_name`` (no
    trailing ``$`` -- a real person account, not a computer -- see
    ``is_machine_principal``).

    Returns ``{'dn_components': [(attr, value), ...], 'upn': str, 'mail':
    str | None}`` -- the DN components ordered exactly as AD returns them
    (leaf to root, e.g. ``[('CN', 'Roy Hagland'), ('CN', 'Users'), ('DC',
    'hagland'), ('DC', 'domain')]``), confirmed against a real ADCS-issued
    User certificate's subject in the lab. ``None`` when the connector is not
    configured/disabled or the entry is not found; the falsy ``NO_UPN`` when the entry has no
    ``userPrincipalName``; the falsy ``UNREACHABLE`` when no DC binds or the search fails. Never raises.

    ``mail`` is deliberately optional (``None`` when unset), not a failure
    mode: real ADCS's own CT_FLAG_SUBJECT_REQUIRE_EMAIL hard-declines
    autoenrollment outright for any user with no ``mail`` attribute, which
    would make a single template unusable for a mixed user base. Callers
    include the email in the issued cert's subject/SAN when present and
    simply omit it otherwise, rather than advertising it as a policy-level
    requirement (see wstep_service.py's issue()).
    """
    from ldap3.utils.conv import escape_filter_chars
    from ldap3.utils.dn import parse_dn

    config, fault = _enabled_config(config)
    if config is None:
        return fault

    try:
        conn = _connect(config)
    except Exception as e:
        logger.warning("AD Connector: bind failed during user lookup: %s", e)
        return UNREACHABLE

    try:
        safe_sam = escape_filter_chars(sam_account_name)
        entries = _search(conn, config.base_dn,
                          f'(&(objectCategory=person)(objectClass=user)(sAMAccountName={safe_sam}))',
                          ['userPrincipalName', 'mail'])
        entry = _single_entry(entries, sam_account_name)
        # Compared by identity: None and UNREACHABLE are the only non-entry answers
        if entry is None or entry is UNREACHABLE:
            return entry
        if 'userPrincipalName' not in entry or not entry.userPrincipalName.value:
            return NO_UPN
        upn = str(entry.userPrincipalName.value)
        mail = str(entry.mail.value) if 'mail' in entry and entry.mail.value else None
        dn_components = [(attr, value) for attr, value, _sep in parse_dn(entry.entry_dn)]
        if not dn_components:
            return None
        return {'dn_components': dn_components, 'upn': upn, 'mail': mail}
    except Exception as e:
        logger.warning("AD Connector: user identity lookup failed: %s", e)
        return UNREACHABLE
    finally:
        try:
            conn.unbind()
        except Exception:
            pass


def _looks_like_dn(value):
    """Cheap DN heuristic (``'CN=Foo,OU=Groups,DC=hagland,DC=domain'``) vs a
    plain name (``'Foo'``, ``'VPN-Enroll'``) -- good enough to route
    ``is_member_of_group``'s group argument without requiring admins to
    always type a full DN. A false negative just means an extra lookup, not
    a security problem: the group is still resolved by name search below.
    """
    return '=' in value and ',' in value


def is_member_of_group(config, sam_account_name, group):
    """Whether the AD account ``sam_account_name`` (no trailing ``$``
    stripped -- caller passes it exactly as parsed from the Kerberos
    principal, so a machine account keeps its ``$``) is a member of
    ``group``, given either as a full DN or a plain name (``sAMAccountName``
    or ``cn``) -- resolved to a DN first via search if it doesn't already
    look like one (see ``_looks_like_dn``).

    Uses AD's ``LDAP_MATCHING_RULE_IN_CHAIN`` (``:1.2.840.113556.1.4.1941:``)
    on ``memberOf`` so nested group membership counts, matching how a real
    ADCS Enroll ACL evaluates a principal's full token group list rather
    than only direct membership.

    Fails closed to ``False`` -- connector not configured/disabled, group not
    found, or account not found/not a member -- and to the falsy ``UNREACHABLE``
    when no DC binds, a search fails or the group name matches several groups.
    Never raises. Callers must treat either as "deny", never "skip the check":
    this is a security gate.
    """
    from ldap3.utils.conv import escape_filter_chars

    if not sam_account_name or not group:
        return False

    config, fault = _enabled_config(config)
    if config is None:
        return fault if fault is not None else False

    try:
        conn = _connect(config)
    except Exception as e:
        logger.warning("AD Connector: bind failed during group membership check: %s", e)
        return UNREACHABLE

    try:
        if _looks_like_dn(group):
            group_dn = group
        else:
            safe_group = escape_filter_chars(group)
            entries = _search(conn, config.base_dn,
                              f'(&(objectClass=group)(|(sAMAccountName={safe_group})(cn={safe_group})))',
                              ['distinguishedName'])
            if entries is UNREACHABLE:
                return UNREACHABLE
            if not entries:
                logger.warning("AD Connector: group %r not found for Enroll ACL check", group)
                return False
            # A cn is unique only within its container: never pick one of several groups
            if len(entries) > 1:
                logger.warning("AD Connector: ambiguous group %r for Enroll ACL check (%s); "
                               "name it by its DN", group, ', '.join(e.entry_dn for e in entries))
                return UNREACHABLE
            group_dn = entries[0].entry_dn

        safe_sam = escape_filter_chars(sam_account_name)
        safe_group_dn = escape_filter_chars(group_dn)
        entries = _search(conn, config.base_dn,
                          f'(&(sAMAccountName={safe_sam})'
                          f'(memberOf:1.2.840.113556.1.4.1941:={safe_group_dn}))',
                          ['sAMAccountName'])
        return entries if entries is UNREACHABLE else bool(entries)
    except Exception as e:
        logger.warning("AD Connector: group membership check failed: %s", e)
        return UNREACHABLE
    finally:
        try:
            conn.unbind()
        except Exception:
            pass


def read_domain_sid(conn, base_dn):
    """The ``objectSid`` of the domain head the base DN sits under, as a string, None
    when it cannot be read. Never raises."""
    import ldap3

    head = domain_head_dn(base_dn)
    if not head:
        return None
    try:
        conn.search(head, '(objectClass=*)', search_scope=ldap3.BASE, attributes=['objectSid'])
        entries = conn.entries if isinstance(getattr(conn, 'result', None), dict) \
            and conn.result.get('result') == _RESULT_SUCCESS else []
        if len(entries) != 1 or 'objectSid' not in entries[0] or not entries[0].objectSid.raw_values:
            return None
        return _sid_bytes_to_string(entries[0].objectSid.raw_values[0])
    except Exception as e:
        logger.warning('AD Connector: could not read the domain SID under %r: %s', base_dn, e)
        return None


def fetch_domain_sid(config):
    """``read_domain_sid`` over a fresh bind to the first DC that accepts it; None when
    no DC binds. A save waits for it: no bind starts once the per-DC connect timeout of the
    connection test (``_LDAP_CONNECT_TIMEOUT_SECONDS``) has passed. Never raises."""
    if not config_servers(config) or not has_bind_credentials(config):
        return None
    token = _bind_deadline.set(_clock() + _LDAP_CONNECT_TIMEOUT_SECONDS)
    try:
        conn = _connect(config)
    except Exception as e:
        logger.warning('AD Connector: could not bind to read the domain SID: %s', e)
        return None
    finally:
        _bind_deadline.reset(token)
    try:
        return read_domain_sid(conn, getattr(config, 'base_dn', None))
    finally:
        try:
            conn.unbind()
        except Exception:
            pass


def test_connection(config):
    """Test connectivity + bind for a config-like object -- either the
    saved ``ADConnectorConfig`` row or an unsaved ``SimpleNamespace`` built
    from a settings form (mirrors ``MicrosoftCAConnectionMixin``'s
    inline-vs-saved test pattern). Never raises.

    Every configured DC is tried, not just enough of them to reach a
    verdict: ``_connect`` stops at the first DC that binds, which would
    leave a second DC that is down -- or presenting a certificate this
    connector can't verify -- silently untested until the first one fails
    in production. Returns::

        {'success': bool, 'partial': bool, 'message': str,
         'servers': [{'server': str, 'success': bool, 'message': str}, ...]}

    ``success`` is "at least one DC bound", because that is exactly the
    condition under which lookups work. ``partial`` distinguishes that
    from "all of them bound" so the caller can warn rather than report a
    clean pass.
    """
    servers = config_servers(config)
    if not servers:
        return {'success': False, 'partial': False,
                'message': 'Server is required', 'servers': []}
    if not has_bind_credentials(config):
        logger.warning('AD Connector: %s', BIND_CREDENTIAL_MISSING)
        return {'success': False, 'partial': False,
                'message': 'Bind DN and password are required', 'servers': []}

    try:
        tls, cleanup = _build_tls(config)
    except Exception as e:
        # Writing the temp CA bundle can fail; a test that raises here would
        # be a 500 on a route whose whole job is to report what went wrong.
        logger.warning('AD Connector: could not prepare the connection test: %s', e)
        return {'success': False, 'partial': False,
                'message': 'Connection failed: could not prepare the TLS settings', 'servers': []}

    results = []
    domain_sid = None
    try:
        for host in servers:
            try:
                conn = _connect_to(config, host, tls)
            except Exception as e:
                results.append({'server': host, 'success': False, 'message': str(e)})
                continue
            results.append({'server': host, 'success': True,
                            'message': 'Connected and bound successfully'})
            if domain_sid is None:
                domain_sid = read_domain_sid(conn, getattr(config, 'base_dn', None))
            try:
                conn.unbind()
            except Exception:
                pass
    finally:
        cleanup()

    failed = [r for r in results if not r['success']]
    ok_count = len(results) - len(failed)
    detail = '; '.join(f"{r['server']}: {r['message']}" for r in failed)

    if not ok_count:
        return {'success': False, 'partial': False,
                'message': f'Connection failed: {detail}', 'servers': results, 'domain_sid': domain_sid}
    if failed:
        return {'success': True, 'partial': True,
                'message': f'{ok_count} of {len(results)} servers connected -- {detail}',
                'servers': results, 'domain_sid': domain_sid}
    if len(results) == 1:
        return {'success': True, 'partial': False,
                'message': 'Connected and bound successfully', 'servers': results, 'domain_sid': domain_sid}
    return {'success': True, 'partial': False,
            'message': f'All {len(results)} servers connected and bound successfully',
            'servers': results, 'domain_sid': domain_sid}

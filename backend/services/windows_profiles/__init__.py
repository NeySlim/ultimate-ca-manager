"""Access to the Windows enrollment profiles (XCEP, WSTEP, Kerberos).

A Kerberos request is served by the profile whose realm is the principal's, and only while
it is enabled; the UsernamePassword binding by the default profile alone (A2).
"""
import logging

from sqlalchemy.exc import IntegrityError

from sqlalchemy import select

from models import CA, ADConnectorConfig, WindowsEnrollmentProfile, db

from .legacy import DEFAULT_NAME, NO_REALM, resolve_realm

logger = logging.getLogger(__name__)


def default_profile():
    return WindowsEnrollmentProfile.query.filter_by(is_default=True).first()


def lowest_connector():
    """The connector row with the lowest id, the one a 2.x install has alone."""
    return db.session.scalars(select(ADConnectorConfig).order_by(ADConnectorConfig.id).limit(1)).one_or_none()


def profile_connector(profile):
    """The connector *profile* searches the directory with, None when it names none."""
    if profile is None or not profile.connector_id:
        return None
    return db.session.get(ADConnectorConfig, profile.connector_id)


def default_connector():
    """The default profile's connector; with no default profile, the lowest-id row, as
    an install that never configured Windows enrollment has at most one."""
    profile = default_profile()
    return lowest_connector() if profile is None else profile_connector(profile)


def sid_connectors(sid):
    """The enabled connectors to ask for the account of *sid* (A9), in order. Those whose
    ``domain_sid`` is the SID's domain; none when only disabled ones are (the SID is carried
    over); for a domain no connector names, the enabled ones of unknown domain, the default
    profile's first."""
    from services.ad_connector.lookup import sid_domain
    domain = sid_domain(sid)
    rows = ADConnectorConfig.query.order_by(ADConnectorConfig.id)
    known = rows.filter(ADConnectorConfig.domain_sid == domain).all() if domain else []
    if known:
        return [c for c in known if c.enabled]
    unknown = rows.filter(ADConnectorConfig.domain_sid.is_(None), ADConnectorConfig.enabled.is_(True)).all()
    default = default_connector()
    return sorted(unknown, key=lambda c: default is None or c.id != default.id)


def profile_sid_connectors(profile, sid):
    """``sid_connectors`` within *profile*: its connector when enabled and of the SID's domain or
    of a domain not known yet; none otherwise (the SID is carried over, A9). Never another's."""
    from services.ad_connector.lookup import sid_domain
    connector = profile_connector(profile)
    if connector is None or not connector.enabled:
        return []
    if connector.domain_sid and connector.domain_sid != sid_domain(sid):
        return []
    return [connector]


def serving_profile():
    """The default profile when it may serve, else None."""
    profile = default_profile()
    return profile if profile is not None and profile.enabled else None


def kerberos_refusal(profile=None):
    """Why *profile* (the default when omitted) serves no Kerberos client, None when it may (A1)."""
    profile = profile if profile is not None else default_profile()
    if profile is None:
        return 'no Windows enrollment profile'
    if not profile.enabled:
        return f'profile {profile.name} is disabled'
    if profile.realm:
        return None
    return NO_REALM if profile.is_default else f'profile {profile.name} has no realm: Kerberos refused until one is set'


def kerberos_binding_reason():
    """Why the Kerberos binding authenticates nobody (library, switch, SPN, keytab), None when set up."""
    from services.kerberos import negotiate_auth
    if not negotiate_auth.is_library_available():
        return 'the Kerberos library is not installed'
    return negotiate_auth.not_configured_reason()


def served_key_realms():
    """The realms of the keys in the keytab file this node's acceptor reads, None when unreadable."""
    from services.kerberos import negotiate_auth
    from .legacy import keytab_realms
    try:
        return keytab_realms(negotiate_auth.KEYTAB_PATH.read_bytes())
    except OSError:
        return None


def kerberos_unserved_reason(profile=None, binding_reason=False, key_realms=False):
    """Why Kerberos reaches no client of *profile*: the binding itself first (library, switch,
    SPN, keytab), then the profile (``kerberos_refusal``), then its key: a realm with no key,
    in its own keytab or in the served file, is a 401 at the acceptor. None when it is served.
    A list passes the binding's reason and the served realms it read once."""
    if binding_reason is False:
        binding_reason = kerberos_binding_reason()
    reason = binding_reason or kerberos_refusal(profile)
    if reason is None and profile is not None and not profile.keytab:
        if key_realms is False:
            key_realms = served_key_realms()
        # The served file may hold this realm's key under another profile's keytab
        if profile.realm not in (key_realms or ()):
            return f'no key for realm {profile.realm}: upload the keytab of this profile'
    return reason


UNKNOWN_REALM = 'no profile serves this realm'
PROFILE_DISABLED = 'the profile of this realm is disabled'
MALFORMED_PRINCIPAL = 'the principal names no realm'


def profile_for_realm(realm):
    """The profile of *realm*, compared exactly (RFC 4120 §6.1) by the unique index."""
    if not realm:
        return None
    return WindowsEnrollmentProfile.query.filter(WindowsEnrollmentProfile.realm == realm).one_or_none()


def kerberos_route(principal):
    """``(profile, realm, refusal)`` for an authenticated Kerberos *principal*: the profile
    of its realm, with the reason it does not serve when disabled; None and why when no
    profile holds the realm. Never the default for another realm."""
    from services.ad_connector.lookup import parse_kerberos_principal
    parsed = parse_kerberos_principal(principal)
    if parsed is None:
        return None, None, MALFORMED_PRINCIPAL
    realm = parsed[1]
    profile = profile_for_realm(realm)
    if profile is None:
        return None, realm, UNKNOWN_REALM
    if not profile.enabled:
        return profile, realm, PROFILE_DISABLED
    return profile, realm, None


def audit_kerberos_refusal(binding, principal, realm, profile, reason):
    """One audit entry per refused Kerberos request: Windows shows the requester a generic code."""
    from services.audit.staging import stage_audit_entry
    from utils.db_transaction import safe_commit
    from utils.trusted_proxy import client_ip
    name = profile.name if profile is not None else None
    stage_audit_entry(
        action='windows_enrollment.refused', resource_type='windows_profile',
        resource_id=str(profile.id) if profile is not None else None, resource_name=name,
        username=principal, success=False,
        details=(f'{binding} Kerberos request from {client_ip()} refused: {reason} '
                 f'(principal {principal}, realm {realm or "-"}, profile {name or "-"})'))
    safe_commit(logger, 'Windows enrollment refusal audit commit failed')


def serve_kerberos(principal, binding):
    """The profile serving an authenticated Kerberos *principal* on *binding* (CEP, CES), or
    None once the refusal is logged and audited."""
    profile, realm, refusal = kerberos_route(principal)
    if refusal is not None:
        logger.warning('%s Kerberos request of %r refused: %s (realm %s)', binding, principal, refusal, realm)
        audit_kerberos_refusal(binding, principal, realm, profile, refusal)
        return None
    return profile


CERTIFICATE_PROFILE_GONE = 'The Windows enrollment profile of this certificate no longer exists'
NOT_WINDOWS_ENROLLED = 'The certificate was not issued through Windows enrollment'
AMBIGUOUS_PROFILE = 'The certificate is recorded under several Windows enrollment profiles'


def certificate_profile(row):
    """``(profile, refusal)`` of a stored certificate: the profile recorded on it, the default for
    a ``wstep`` row recording none (C-01); a profile gone or disabled refuses, never another one."""
    if row.windows_profile_id is not None:
        profile = db.session.get(WindowsEnrollmentProfile, row.windows_profile_id)
    elif row.source == 'wstep':
        profile = default_profile()
    else:
        return None, NOT_WINDOWS_ENROLLED
    if profile is None:
        return None, CERTIFICATE_PROFILE_GONE
    if not profile.enabled:
        return profile, f'The Windows enrollment profile {profile.name} is disabled'
    return profile, None


PROTOCOL_RENEWAL_REFUSED = 'The certificate belongs to a Windows enrollment profile and renews through it'


def audit_protocol_renewal_refusal(protocol, row, requester):
    """One audit entry per EST or SCEP renewal refused to a certificate of a Windows profile,
    naming the profile and why it does not serve, committed at once (the refusal stores nothing)."""
    from services.audit.staging import stage_audit_entry
    from utils.db_transaction import safe_commit
    profile, why = certificate_profile(row)
    name = profile.name if profile is not None else None
    stage_audit_entry(
        action='windows_enrollment.refused', resource_type='windows_profile',
        resource_id=str(profile.id) if profile is not None else None, resource_name=name,
        username=requester, success=False,
        details=(f'{protocol} renewal refused: {PROTOCOL_RENEWAL_REFUSED} '
                 f'(certificate {row.descr or row.subject} serial {row.serial_number}, '
                 f'profile {name or row.windows_profile_id or "-"}'
                 f'{f": {why}" if why else ""})'))
    safe_commit(logger, 'Windows profile renewal refusal audit commit failed')


def presented_certificate_profile(cert):
    """``(profile, refusal, served)`` for a certificate presented to renew: the profile its stored
    rows record (``certificate_profile``), whichever CA they sit under, and how an audit names it.
    ``served`` None: no row holds it byte for byte, it names no profile and its refusal is not audited."""
    from services.cert.issued_lookup import find_stored_rows
    rows = find_stored_rows(cert)
    if not rows:
        return None, None, None
    windows = [row for row in rows if row.windows_profile_id is not None or row.source == 'wstep']
    answers = {}
    for row in windows or rows[:1]:
        profile, refusal = certificate_profile(row)
        answers[(getattr(profile, 'id', None), refusal)] = (profile, refusal)
    profile, refusal = next(iter(answers.values())) if len(answers) == 1 else (None, AMBIGUOUS_PROFILE)
    if profile is not None:
        return profile, refusal, f'profile {profile.name}'
    # A profile row gone still has its id on the certificate: the audit names that one
    ids = sorted({row.windows_profile_id for row in windows if row.windows_profile_id is not None})
    return None, refusal, 'profile ' + (', '.join(f'#{i}' for i in ids) or '-')


def profile_template_ids(profile):
    """The ids of the templates *profile* lists; empty: it offers those of its CA (A3)."""
    if profile is None or profile.id is None:
        return set()
    from models import WindowsProfileTemplate
    return set(db.session.scalars(select(WindowsProfileTemplate.template_id)
                                  .where(WindowsProfileTemplate.profile_id == profile.id)))


def profile_group(profile):
    """The AD group *profile* requires in place of the template's, None when unset (A3)."""
    group = (profile.allowed_ad_group or '').strip() if profile is not None else ''
    return group or None


def _ca(refid):
    return CA.query.filter_by(refid=refid).first() if refid else None


def issuing_ca(profile):
    return _ca(profile.issuing_ca_refid) if profile is not None else None


def policy_ca(profile):
    """The CA XCEP announces: the policy CA, else the issuing CA (A4)."""
    return _ca(profile.policy_refid) if profile is not None else None


def _connector_values(connector):
    if connector is None:
        return None
    return {'id': connector.id, 'enabled': bool(connector.enabled), 'base_dn': connector.base_dn}


def keytab_absent(profile):
    """No keytab exists for this installation: none in *profile* (None: no profile), none
    stored for the nodes, no file on this node. An undecryptable one is not absent, and in
    HA a node cannot tell: another one may still hold the file."""
    from config.settings import Config
    from models import SharedFile
    from services import shared_files
    from services.kerberos import negotiate_auth
    if (profile is not None and profile.keytab) or Config.HA_MODE:
        return False
    return (db.session.get(SharedFile, shared_files.KERBEROS_KEYTAB) is None
            and not negotiate_auth.KEYTAB_PATH.exists())


def fill_realm(profile):
    """Give a profile without a realm the one A1 determines now; never replaces a realm."""
    if profile.realm is not None:
        return
    from services.kerberos import negotiate_auth
    connector = db.session.get(ADConnectorConfig, profile.connector_id) if profile.connector_id else None
    try:
        keytab = profile.keytab_bytes()
    except ValueError:
        keytab = None
    realm = resolve_realm(_connector_values(connector), negotiate_auth.get_spn(), keytab,
                          keytab_absent(profile))
    taken = realm and WindowsEnrollmentProfile.query.filter(
        WindowsEnrollmentProfile.realm == realm, WindowsEnrollmentProfile.id != profile.id).first()
    if realm and not taken:
        profile.realm = realm


def realm_problem(realm, profile):
    """(message, status) when *realm* cannot be *profile*'s (None: a new one), else None:
    capitals as AD writes it, named by its keytab when it has one, held by no other profile."""
    from .legacy import keytab_realms
    if not isinstance(realm, str) or not realm.strip() or realm != realm.strip().upper():
        return 'realm must be a non-empty name in capitals, such as CORP.EXAMPLE', 400
    try:
        keytab = profile.keytab_bytes() if profile is not None else None
    except ValueError:
        return f'the keytab of profile {profile.name} cannot be decrypted here', 409
    if keytab:
        realms = keytab_realms(keytab)
        if realms is None:
            return 'the realms of the keytab cannot be read', 400
        if realm not in realms:
            return f"realm {realm} is not in the keytab ({', '.join(sorted(realms))})", 400
    other = WindowsEnrollmentProfile.query.filter(WindowsEnrollmentProfile.realm == realm)
    if profile is not None and profile.id is not None:
        other = other.filter(WindowsEnrollmentProfile.id != profile.id)
    if other.first() is not None:
        return f'realm {realm} is already served by another profile', 409
    return None


def _unused_name():
    """DEFAULT_NAME, or the first ``default-N`` no profile holds."""
    name, n = DEFAULT_NAME, 1
    while WindowsEnrollmentProfile.query.filter_by(name=name).first() is not None:
        n += 1
        name = f'{DEFAULT_NAME}-{n}'
    return name


def default_for_write(actor=None, fill=True):
    """The default profile the configuration routes write, created by the first write.
    ``fill=False``: the caller sets a keytab first and fills the realm itself."""
    profile = default_profile()
    if profile is None:
        connector = lowest_connector()
        # A concurrent writer may take the default or the name first: the default row wins,
        # a taken name is chosen again
        for _attempt in range(10):
            try:
                with db.session.begin_nested():
                    profile = WindowsEnrollmentProfile(
                        name=_unused_name(), is_default=True, enabled=True,
                        connector_id=connector.id if connector else None, created_by=actor)
                    db.session.add(profile)
                break
            except IntegrityError:
                profile = default_profile()
                if profile is not None:
                    break
        else:
            raise RuntimeError('no free name for the default Windows enrollment profile')
    profile.updated_by = actor
    if fill:
        fill_realm(profile)
    return profile


def keytab_holders():
    """The profiles holding a keytab, enabled or not, by id; read afresh, so a composition made
    under the keytab row lock sees what committed before it rather than the identity map."""
    return (WindowsEnrollmentProfile.query.filter(WindowsEnrollmentProfile.keytab.isnot(None))
            .order_by(WindowsEnrollmentProfile.id).populate_existing().all())


# The composed file is refused beyond this: 150 realms of three keys are about 40 KiB
MAX_COMPOSED_KEYTAB_SIZE = 1024 * 1024


def composed_keytab():
    """The keytab the acceptor reads: the entries of every profile's keytab, enabled or not, so a
    disabled profile is refused by realm after authentication (fault and audit, never a 401).
    None without any. One keytab is served as stored; one whose entries cannot be read is left
    out of a composition. Raises ValueError when a keytab cannot be decrypted here."""
    from services.kerberos.keytab_format import compose, read_entries
    # The holders are read afresh: a keytab set and not yet flushed must reach the database first
    db.session.flush()
    sources = [(p, p.keytab_bytes()) for p in keytab_holders()]
    sources = [(p, data) for p, data in sources if data]
    if len(sources) == 1:
        return _within_size(sources[0][1])
    entries = []
    for profile, data in sources:
        read = read_entries(data)
        if read is None:
            logger.error("Kerberos: the keytab of profile %s cannot be read, its realm is not served",
                         profile.name)
            continue
        entries.extend(read)
    return _within_size(compose(entries)) if sources else None


def _within_size(data):
    if len(data) > MAX_COMPOSED_KEYTAB_SIZE:
        raise ValueError(f'the keytabs of the profiles make {len(data)} bytes, '
                         f'above the {MAX_COMPOSED_KEYTAB_SIZE} bytes a node serves')
    return data


def publish_keytab(actor='system'):
    """The node keytab file (shared_files) recomposed from the profiles, in the caller's transaction.
    The file's row is locked before composing, so a concurrent upload composes after this one commits."""
    from models import SharedFile
    from services import shared_files
    name = shared_files.KERBEROS_KEYTAB
    for attempt in (1, 2):
        row = (db.session.query(SharedFile).filter_by(name=name)
               .with_for_update().populate_existing().first())
        data = composed_keytab()
        if not data:
            shared_files.drop_file(name)
            return data
        if row is not None:
            shared_files.store_file(name, data, actor=actor)
            return data
        try:
            # A concurrent first insert wins: lock its row and compose again
            with db.session.begin_nested():
                shared_files.store_file(name, data, actor=actor)
            return data
        except IntegrityError:
            if attempt == 2:
                raise
    return None

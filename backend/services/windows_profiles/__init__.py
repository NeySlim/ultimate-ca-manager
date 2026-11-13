"""Access to the Windows enrollment profiles (XCEP, WSTEP, Kerberos).

Until routing by realm exists, every request is served by the default profile, and only
while it is enabled: a disabled profile serves nothing.
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


def serving_profile():
    """The default profile when it may serve, else None."""
    profile = default_profile()
    return profile if profile is not None and profile.enabled else None


def kerberos_refusal():
    """Why the default profile serves no Kerberos client, None when it may (A1)."""
    profile = default_profile()
    if profile is None:
        return 'no Windows enrollment profile'
    if not profile.enabled:
        return 'default profile is disabled'
    return None if profile.realm else NO_REALM


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


def default_for_write(actor=None, fill=True):
    """The default profile the configuration routes write, created by the first write.
    ``fill=False``: the caller sets a keytab first and fills the realm itself."""
    profile = default_profile()
    if profile is None:
        connector = lowest_connector()
        try:
            # A concurrent writer may create it first: its row is the default then
            with db.session.begin_nested():
                profile = WindowsEnrollmentProfile(name=DEFAULT_NAME, is_default=True, enabled=True,
                                                   connector_id=connector.id if connector else None,
                                                   created_by=actor)
                db.session.add(profile)
        except IntegrityError:
            profile = WindowsEnrollmentProfile.query.filter_by(is_default=True).one()
    profile.updated_by = actor
    if fill:
        fill_realm(profile)
    return profile


def keytab_holders():
    """The profiles holding a keytab, enabled or not, by id; read afresh, so a composition made
    under the keytab row lock sees what committed before it rather than the identity map."""
    return (WindowsEnrollmentProfile.query.filter(WindowsEnrollmentProfile.keytab.isnot(None))
            .order_by(WindowsEnrollmentProfile.id).populate_existing().all())


def composed_keytab():
    """The keytab the acceptor reads: the entries of every enabled profile's keytab, None
    without any. One keytab is served as stored; one whose entries cannot be read is left out
    of a composition. Raises ValueError when a keytab cannot be decrypted here."""
    from services.kerberos.keytab_format import compose, read_entries
    # The holders are read afresh: a keytab set and not yet flushed must reach the database first
    db.session.flush()
    sources = [(p, p.keytab_bytes()) for p in keytab_holders() if p.enabled]
    sources = [(p, data) for p, data in sources if data]
    if len(sources) == 1:
        return sources[0][1]
    entries = []
    for profile, data in sources:
        read = read_entries(data)
        if read is None:
            logger.error("Kerberos: the keytab of profile %s cannot be read, its realm is not served",
                         profile.name)
            continue
        entries.extend(read)
    return compose(entries) if sources else None


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

"""Access to the Windows enrollment profiles (XCEP, WSTEP, Kerberos).

Until routing by realm exists, every request is served by the default profile, and only
while it is enabled: a disabled profile serves nothing.
"""
import logging

from models import CA, ADConnectorConfig, WindowsEnrollmentProfile, db

from .legacy import DEFAULT_NAME, NO_REALM, resolve_realm

logger = logging.getLogger(__name__)


def default_profile():
    return WindowsEnrollmentProfile.query.filter_by(is_default=True).first()


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
    realm = resolve_realm(_connector_values(connector), negotiate_auth.get_spn(), keytab)
    taken = realm and WindowsEnrollmentProfile.query.filter(
        WindowsEnrollmentProfile.realm == realm, WindowsEnrollmentProfile.id != profile.id).first()
    if realm and not taken:
        profile.realm = realm


def default_for_write(actor=None):
    """The default profile the configuration routes write, created by the first write."""
    profile = default_profile()
    if profile is None:
        connector = ADConnectorConfig.get_singleton()
        profile = WindowsEnrollmentProfile(name=DEFAULT_NAME, is_default=True, enabled=True,
                                           connector_id=connector.id if connector else None,
                                           created_by=actor)
        db.session.add(profile)
        db.session.flush()
    profile.updated_by = actor
    fill_realm(profile)
    return profile


def publish_keytab(actor='system'):
    """The node keytab file (shared_files) rebuilt from the profiles, in the caller's transaction."""
    from services import shared_files
    profile = default_profile()
    data = profile.keytab_bytes() if profile is not None else None
    if data:
        shared_files.store_file(shared_files.KERBEROS_KEYTAB, data, actor=actor)
    else:
        shared_files.drop_file(shared_files.KERBEROS_KEYTAB)
    return data

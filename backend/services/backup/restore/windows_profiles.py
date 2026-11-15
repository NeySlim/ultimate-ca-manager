"""A 2.x archive's Windows enrollment settings as the default profile, before the plan is built.

The same conversion as migration 155 (services.windows_profiles.legacy): the settings it
replaces leave the configuration section, a windows_enrollment_profiles section takes them,
the WSTEP certificates point at it, and the connector rows get the name they are found by.
A 2.x archive never carried the keytab: the one this installation holds stays with the profile.
"""
import base64
import logging
from typing import Any, Dict, Optional, Tuple

from services.windows_profiles.legacy import (MIGRATED_KEYS, connector_names, has_windows_configuration,
                                              keytab_realms, profile_from_2x, switches_from_2x)
from utils.policy_identity import identity_for

from ..export_generic import REFERENCE_SUFFIX

logger = logging.getLogger(__name__)

PROFILES = 'windows_enrollment_profiles'
# The policy identity a profile serves (policyID, template OID root), applied by restored_identity
IDENTITY = ('policy_id', 'policy_oid_root')


def _keytab_here() -> Tuple[Optional[bytes], bool]:
    """This installation's keytab, and whether there is none at all (not merely unreadable)."""
    from services.windows_profiles import default_profile, keytab_absent
    profile = default_profile()
    try:
        return (profile.keytab_bytes() if profile is not None else None), keytab_absent(profile)
    except ValueError:
        logger.warning("Restore: the keytab of this installation cannot be decrypted; "
                       "the restored default profile has none")
        return None, False


def _name_connectors(backup_data) -> list:
    rows = backup_data.get('ad_connector') if 'ad_connector' in backup_data else None
    if not isinstance(rows, list):
        return []
    rows = [r for r in rows if isinstance(r, dict)]
    numbered = [r for r in rows if isinstance(r.get('id'), int)]
    for row_id, name in connector_names([(r['id'], r.get('name')) for r in numbered]):
        next(r for r in numbered if r['id'] == row_id)['name'] = name
    for position, row in enumerate(rows):
        if not row.get('name'):
            row['name'] = 'default' if position == 0 else f'connector-{position + 1}'
    return sorted(rows, key=lambda r: r['id'] if isinstance(r.get('id'), int) else 0)


def _describes(backup_data, name) -> bool:
    """Whether the archive says what section *name* holds: written, and not excluded at export."""
    from ..section_store import section_kind
    excluded = (backup_data.get('metadata') or {}).get('excluded_sections') or []
    return section_kind(backup_data, name) == 'list' and name not in excluded


def upgrade_archived_windows_profiles(backup_data, warnings=None) -> Optional[Dict[str, Any]]:
    """Convert a 2.x archive in place; returns the profile row written, None for a 3.0 archive.
    What the operator must know is appended to *warnings*."""
    connectors = _name_connectors(backup_data)
    configuration = backup_data.get('configuration') if 'configuration' in backup_data else None
    settings = configuration.get('settings') if isinstance(configuration, dict) else None
    if not isinstance(settings, dict):
        return None
    migrated = {key: settings.pop(key) for key in MIGRATED_KEYS if key in settings}
    if isinstance(configuration.get('encrypted_settings'), list):
        configuration['encrypted_settings'] = [k for k in configuration['encrypted_settings']
                                               if k not in MIGRATED_KEYS]
    if PROFILES in backup_data:
        # A 3.0 archive: every section is named in it, excluded ones too
        return None
    first = connectors[0] if connectors else None
    connector = ({'id': first.get('id'), 'enabled': bool(first.get('enabled')),
                  'base_dn': first.get('base_dn')} if first else None)
    archived = {**settings, **migrated}
    # The archive alone carries a configuration or not; the keytab here only gives the realm
    if not has_windows_configuration(archived):
        return None
    keytab, absent = _keytab_here()
    settings.update(switches_from_2x(archived))
    profile = profile_from_2x(archived, connector, keytab, absent)
    realms = keytab_realms(keytab) if keytab else None
    if keytab and profile['realm'] and profile['realm'] not in (realms or ()):
        message = (f"windows_enrollment_profiles: the realm {profile['realm']} of the default profile "
                   f"is not in this installation's keytab ({', '.join(sorted(realms or ())) or 'unreadable'}): "
                   "Kerberos clients of that realm fail until a keytab for it is uploaded")
        if warnings is not None:
            warnings.append(message)
    row = dict(profile, keytab=base64.b64encode(keytab).decode('ascii') if keytab else None)
    if _describes(backup_data, 'ad_connector'):
        row[f'connector_id{REFERENCE_SUFFIX}'] = {'name': first['name']} if first else None
    else:
        # Written without its connectors, the archive does not say the profile has none: a merge keeps the link
        row.pop('connector_id', None)
    backup_data[PROFILES] = [row]
    for cert in backup_data.get('certificates') or []:
        if isinstance(cert, dict) and cert.get('source') == 'wstep' and not cert.get('windows_profile_id'):
            # The number is the archive's own; the identity beside it is what the restore resolves
            cert['windows_profile_id'] = 1
            cert[f'windows_profile_id{REFERENCE_SUFFIX}'] = {'name': profile['name']}
    logger.info("Restore: the 2.x Windows enrollment settings became the default profile (realm %s)",
                profile['realm'])
    return row


def link_restored_connectors(backup_data) -> None:
    """Connectors restored without the profiles: a default profile naming none takes the
    lowest-id row, as a connector created by the API does, so the protocols and the screen agree."""
    from services.windows_profiles import default_profile, lowest_connector
    from ..restore_core import _carries
    if not _carries(backup_data, 'ad_connector') or _carries(backup_data, PROFILES):
        return
    profile, connector = default_profile(), lowest_connector()
    if profile is not None and profile.connector_id is None and connector is not None:
        profile.connector_id = connector.id


def _held_elsewhere(instance):
    """The policy identities of the other profiles, flushed or still pending in this restore."""
    from models import WindowsEnrollmentProfile, db
    with db.session.no_autoflush:
        rows = WindowsEnrollmentProfile.query.all()
    others = [p for p in {*rows, *db.session.new} if isinstance(p, WindowsEnrollmentProfile) and p is not instance]
    return {p.policy_id for p in others}, {p.policy_oid_root for p in others}


def restored_identity(instance, row, *, new, replacing, warnings=None) -> Dict[str, Any]:
    """The identity columns a restored profile takes, so a restore never moves what clients registered.
    A replacement takes the archive's (it becomes the instance); a merge keeps an existing profile's.
    An archive from before these columns derives them from the CA, as migration 155 does; an
    identity another profile here already serves is drawn again, two never share one."""
    archived = tuple(row.get(column) for column in IDENTITY)
    complete = all(isinstance(v, str) and v for v in archived)
    if not new and not (replacing and complete):
        return {}
    taken_ids, taken_roots = _held_elsewhere(instance)
    if complete and archived[0] not in taken_ids and archived[1] not in taken_roots:
        return dict(zip(IDENTITY, archived, strict=True))
    if complete:
        message = (f"windows_enrollment_profiles: profile {row.get('name')} gets a new policy identity, "
                   "another profile here serves the archived one: its clients register the policy server again")
        logger.warning("Restore: %s", message)
        if warnings is not None:
            warnings.append(message)
        refid = None
    else:
        refid = row.get('policy_ca_refid') or row.get('issuing_ca_refid')
    return dict(zip(IDENTITY, identity_for(refid, taken_ids, taken_roots), strict=True))

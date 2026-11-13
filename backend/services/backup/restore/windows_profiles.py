"""A 2.x archive's Windows enrollment settings as the default profile, before the plan is built.

The same conversion as migration 155 (services.windows_profiles.legacy): the settings it
replaces leave the configuration section, a windows_enrollment_profiles section takes them,
the WSTEP certificates point at it, and the connector rows get the name they are found by.
A 2.x archive never carried the keytab: the one this installation holds stays with the profile.
"""
import base64
import logging
from typing import Any, Dict, Optional

from services.windows_profiles.legacy import (MIGRATED_KEYS, connector_names, has_windows_configuration,
                                              keytab_realms, profile_from_2x, switches_from_2x)

from ..export_generic import REFERENCE_SUFFIX

logger = logging.getLogger(__name__)

PROFILES = 'windows_enrollment_profiles'


def _keytab_here() -> Optional[bytes]:
    from services.windows_profiles import default_profile
    profile = default_profile()
    try:
        return profile.keytab_bytes() if profile is not None else None
    except ValueError:
        logger.warning("Restore: the keytab of this installation cannot be decrypted; "
                       "the restored default profile has none")
        return None


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
    keytab = _keytab_here()
    settings.update(switches_from_2x(archived))
    profile = profile_from_2x(archived, connector, keytab)
    realms = keytab_realms(keytab) if keytab else None
    if keytab and profile['realm'] and profile['realm'] not in (realms or ()):
        message = (f"windows_enrollment_profiles: the realm {profile['realm']} of the default profile "
                   f"is not in this installation's keytab ({', '.join(sorted(realms or ())) or 'unreadable'}): "
                   "Kerberos clients of that realm fail until a keytab for it is uploaded")
        if warnings is not None:
            warnings.append(message)
    row = dict(profile, keytab=base64.b64encode(keytab).decode('ascii') if keytab else None)
    row[f'connector_id{REFERENCE_SUFFIX}'] = {'name': first['name']} if first else None
    backup_data[PROFILES] = [row]
    for cert in backup_data.get('certificates') or []:
        if isinstance(cert, dict) and cert.get('source') == 'wstep' and not cert.get('windows_profile_id'):
            # The number is the archive's own; the identity beside it is what the restore resolves
            cert['windows_profile_id'] = 1
            cert[f'windows_profile_id{REFERENCE_SUFFIX}'] = {'name': profile['name']}
    logger.info("Restore: the 2.x Windows enrollment settings became the default profile (realm %s)",
                profile['realm'])
    return row

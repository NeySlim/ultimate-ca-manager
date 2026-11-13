"""The 2.x Windows enrollment settings as the default profile, for the migration and the restore.

Pure functions over plain values: migration 155 reads them from the database, a restore
from a 2.x archive. One conversion, so both produce the same profile.
"""
import logging
import struct

logger = logging.getLogger(__name__)

DEFAULT_NAME = 'default'
DEFAULT_VALIDITY_DAYS = 365

# SystemConfig keys the profile replaces; the protocol switches and the SPN stay settings
MIGRATED_KEYS = ('xcep_ca_refid', 'xcep_username', 'xcep_password', 'wstep_ca_refid',
                 'wstep_username', 'wstep_password', 'wstep_validity_days')


def connector_names(rows):
    """``(id, name)`` for the unnamed connector rows ``(id, name)``: the oldest is 'default'."""
    taken = {name for _id, name in rows if name}
    out = []
    for row_id, name in sorted(rows, key=lambda r: r[0]):
        if name:
            continue
        wanted = DEFAULT_NAME if DEFAULT_NAME not in taken else f'connector-{row_id}'
        taken.add(wanted)
        out.append((row_id, wanted))
    return out


def keytab_realms(data):
    """The realms of the entries of an MIT keytab (format 0x0501 or 0x0502), None when unreadable."""
    if not data or len(data) < 2 or data[0] != 5 or data[1] not in (1, 2):
        return None
    order = '>' if data[1] == 2 else '='
    realms, pos = set(), 2
    try:
        while pos + 4 <= len(data):
            (size,) = struct.unpack_from(f'{order}i', data, pos)
            pos += 4
            if size < 0:   # a hole left by a deleted entry
                pos += -size
                continue
            if size == 0 or pos + size > len(data):
                break
            entry = data[pos:pos + size]
            (components,) = struct.unpack_from(f'{order}H', entry, 0)
            if data[1] == 1:
                components -= 1   # 0x0501 counted the realm as a component
            (length,) = struct.unpack_from(f'{order}H', entry, 2)
            if components < 1 or 4 + length > len(entry):
                return None
            realms.add(entry[4:4 + length].decode('utf-8'))
            pos += size
    except (struct.error, UnicodeDecodeError):
        return None
    return realms


def spn_realm(spn):
    """The realm after ``@`` in ``HTTP/host@REALM``, in capitals as AD writes it; None without one."""
    realm = (spn or '').rpartition('@')[2] if '@' in (spn or '') else ''
    return realm.strip().upper() or None


def _connector_realm(connector):
    from services.ad_connector.lookup import realm_of_base_dn
    return realm_of_base_dn(connector['base_dn']) if connector and connector.get('base_dn') else None


def resolve_realm(connector, spn, keytab, keytab_absent=False):
    """A1: the realm of the enabled connector's base DN, else of the SPN, else the single
    realm of the keytab entries, else the disabled connector's when the keytab holds it
    (or *keytab_absent* establishes there is none); None when none of them says."""
    named = _connector_realm(connector)
    if named and connector.get('enabled'):
        return named
    realm = spn_realm(spn)
    if realm:
        return realm
    realms = keytab_realms(keytab) if keytab else None
    if realms and len(realms) == 1:
        return next(iter(realms))
    # 2.x served the SPN's or the keytab's realm while the connector was disabled
    # A keytab not read is not an absent one: its realms may exclude the connector's
    if named and ((keytab_absent and not keytab) or (realms and named in realms)):
        return named
    return None


NO_REALM = 'default profile has no realm: Kerberos refused until one is set'


def warn_without_realm(realm, kerberos_enabled, spn, keytab):
    """Log A1's one change to 2.x: Kerberos 2.x served (enabled, SPN, keytab) and no realm now."""
    if realm is None and kerberos_enabled and spn and keytab:
        logger.warning('Windows enrollment: %s', NO_REALM)
        return True
    return False


def has_windows_configuration(settings, keytab=None):
    """Whether a 2.x installation had anything a default profile must carry."""
    return bool(any(settings.get(k) for k in MIGRATED_KEYS)
                or settings.get('kerberos_spn') or keytab)


def switches_from_2x(settings):
    """The protocol switches the conversion changes: 2.x answered 503 to GetPolicies without
    an XCEP CA, the profile would serve the issuing CA's policy (A4); XCEP goes off instead."""
    if (str(settings.get('xcep_enabled') or '').lower() == 'true'
            and not settings.get('xcep_ca_refid') and settings.get('wstep_ca_refid')):
        logger.warning("Windows enrollment: XCEP had no CA of its own and served no policy; it is "
                       "switched off, switch it on to serve the policy of the issuing CA")
        return {'xcep_enabled': 'false'}
    return {}


def _validity(value):
    try:
        return int(value) if value else DEFAULT_VALIDITY_DAYS
    except (TypeError, ValueError):
        return DEFAULT_VALIDITY_DAYS


def profile_from_2x(settings, connector=None, keytab=None, keytab_absent=False):
    """The default profile's columns from 2.x ``settings`` (key -> value), the connector row
    (dict with ``id``, ``enabled``, ``base_dn``) and the keytab bytes; None without configuration.
    *keytab_absent*: no keytab exists anywhere, not merely none was read.

    Always enabled: without a realm only Kerberos is refused (A1), the other bindings serve as in 2.x.
    """
    if not has_windows_configuration(settings, keytab):
        return None
    spn = settings.get('kerberos_spn')
    realm = resolve_realm(connector, spn, keytab, keytab_absent)
    warn_without_realm(realm, str(settings.get('kerberos_enabled') or '').lower() == 'true', spn, keytab)
    named = _connector_realm(connector)
    # Without a keytab read the realm is not chosen yet: the start or the upload sets it
    if named and realm != named and (realm or keytab or keytab_absent):
        logger.warning("Windows enrollment: the default profile's realm %s differs from the realm of "
                       "the connector's base DN, %s", realm or 'none', named)
    return {
        'name': DEFAULT_NAME,
        'realm': realm,
        'is_default': True,
        'enabled': True,
        'connector_id': connector.get('id') if connector else None,
        'issuing_ca_refid': settings.get('wstep_ca_refid') or None,
        'policy_ca_refid': settings.get('xcep_ca_refid') or None,
        'validity_days': _validity(settings.get('wstep_validity_days')),
        'xcep_username': settings.get('xcep_username') or None,
        'xcep_password': settings.get('xcep_password') or None,
        'wstep_username': settings.get('wstep_username') or None,
        'wstep_password': settings.get('wstep_password') or None,
    }

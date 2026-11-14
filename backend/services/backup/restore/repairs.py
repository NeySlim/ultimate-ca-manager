"""Repair migrations replayed on what a restore wrote.

Restores run after the migrations, so rows an older archive brings back never
pass through the migration that repaired that shape on the source. Each repair
below names its migration and touches only what the restore wrote; what tells
an older archive apart is in the archive itself (a setting nothing writes any
more, a column the row does not carry).
"""
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Set

from sqlalchemy import bindparam, text

from models import db

from . import legacy_repairs as legacy

logger = logging.getLogger(__name__)

_ORDER_DUPLICATES = '121_acme_renewal_order_duplicates'


def restored_setting_keys(backup_data: Dict[str, Any]) -> Set[str]:
    """The setting keys the archive carries, which the restore wrote."""
    configuration = backup_data.get('configuration')
    if not isinstance(configuration, dict):
        return set()
    return set(configuration.get('settings') or {})


def _archived_rows(backup_data: Dict[str, Any], section: str) -> List[Dict[str, Any]]:
    return [row for row in backup_data.get(section) or [] if isinstance(row, dict)]


def _settings_here() -> Dict[str, Any]:
    from models import SystemConfig
    return {row.key: row.value for row in SystemConfig.query.all()}


def _set(key: str, value: str) -> None:
    from models import SystemConfig
    row = SystemConfig.query.filter_by(key=key).first()
    if row is None:
        db.session.add(SystemConfig(key=key, value=value))
    else:
        row.value = value


def _delete_settings(keys: Iterable[str]) -> int:
    from models import SystemConfig
    keys = sorted(keys)
    if not keys:
        return 0
    return SystemConfig.query.filter(SystemConfig.key.in_(keys)).delete(synchronize_session=False)


def replay_order_repairs(ids: Iterable[int]) -> Dict[str, int]:
    """Migration 121 on the ACME client orders a restore wrote: renewal schedule and leftovers.

    A row it did not write is left alone, as a merge leaves it."""
    db.session.flush()
    ids = sorted(ids)
    if not ids:
        return {'reissued': 0, 'dropped': 0}
    restored = ' AND acme_client_orders.id IN :ids'
    reissued = db.session.execute(text(legacy.REISSUE + restored).bindparams(
        bindparam('ids', expanding=True)), {'ids': ids}).rowcount
    dropped = db.session.execute(text(legacy.DROP_LEFTOVERS + restored).bindparams(
        bindparam('ids', expanding=True)), {'ids': ids}).rowcount
    # A renewal of a dropped row names nothing: same outcome as ON DELETE SET NULL, on every engine
    db.session.execute(text(
        'UPDATE acme_client_orders SET renewal_of_order_id = NULL '
        'WHERE renewal_of_order_id IS NOT NULL AND renewal_of_order_id NOT IN '
        '(SELECT id FROM acme_client_orders)'))
    db.session.expire_all()
    if reissued or dropped:
        logger.info("Restore: migration 121 replayed, %s order(s) back on the schedule, "
                    "%s leftover(s) removed", reissued, dropped)
    return {'reissued': reissued, 'dropped': dropped}


# First release whose hold lift deletes every record of the serial: an archive from an older
# one may carry the suspension records such a lift left behind (migration 154's leftovers)
FIRST_RELEASE_LIFTING_EVERY_RECORD = (2, 254)
_HOLD_REASONS = ('certificateHold', 'certificate_hold')


def archive_may_hold_lifted_holds(backup_data) -> bool:
    """Whether the archive's ``ucm_version`` predates ``FIRST_RELEASE_LIFTING_EVERY_RECORD``
    (an archive that names no readable version counts as older). It carries no list of the
    migrations its base had applied, so its release is what tells."""
    import re
    metadata = backup_data.get('metadata')
    version = metadata.get('ucm_version') if isinstance(metadata, dict) else None
    match = re.match(r'v?(\d+)\.(\d+)', str(version or '').strip())
    return match is None or (int(match[1]), int(match[2])) < FIRST_RELEASE_LIFTING_EVERY_RECORD


def archived_lifted_holds(backup_data) -> Set[int]:
    """Positions in the archive's ``revoked_serials`` of the holds an older release left
    behind a lift: migration 154's rule, judged on the archive alone (a suspension linked to
    the archived, unrevoked certificate of the same serial under its CA or a twin of its key)."""
    import base64
    from utils.serial_format import canonical_serial
    if not archive_may_hold_lifted_holds(backup_data):
        return set()
    certificates = {row.get('refid'): row for row in _archived_rows(backup_data, 'certificates')}
    pems = {row.get('refid'): row.get('certificate_pem')
            for row in _archived_rows(backup_data, 'certificate_authorities')}
    candidates = []
    for position, record in enumerate(backup_data.get('revoked_serials') or []):
        if not isinstance(record, dict) or record.get('revoke_reason') not in _HOLD_REASONS:
            continue
        link = record.get('certificate_id_ref')
        row = certificates.get(link.get('refid')) if isinstance(link, dict) else None
        if row is None or row.get('revoked'):
            continue
        serial = canonical_serial(record.get('serial_number'))
        if serial and serial == canonical_serial(row.get('serial_number')):
            candidates.append((position, record.get('caref'), row.get('caref')))

    def ca_crt(refid):
        pem = pems.get(refid)
        return base64.b64encode(pem.encode()).decode() if isinstance(pem, str) else None
    return set(legacy.leftovers(candidates, ca_crt))


def _eab_keys_blob(backup_data, plan) -> int:
    """101: a restored `acme_eab_keys` blob becomes credentials, as on the source."""
    if 'acme_eab_keys' not in restored_setting_keys(backup_data):
        return 0
    from models.acme_models import AcmeEabCredential
    entries, leftover = legacy.eab_entries(_settings_here().get('acme_eab_keys'))
    imported = 0
    for kid, key in entries:
        if AcmeEabCredential.query.filter_by(kid=kid).first() is not None:
            continue
        db.session.add(AcmeEabCredential(kid=kid, hmac_key_b64=legacy.encrypt(key),
                                         label=legacy.LABEL, status='active'))
        imported += 1
    if leftover is None:
        _delete_settings(['acme_eab_keys'])
    else:
        _set('acme_eab_keys', leftover)
    return imported


def _dead_settings(backup_data, plan) -> int:
    """102: dead settings, dead policy rule keys, the built-in templates' SAN types."""
    changed = 0
    carried = restored_setting_keys(backup_data)
    if carried & set(legacy.DEAD_KEYS):
        here = _settings_here()
        for key, value in {**legacy.legacy_schedules(here), **legacy.system_name(here)}.items():
            _set(key, value)
            changed += 1
        changed += _delete_settings(carried & set(legacy.DEAD_KEYS))

    from models.certificate_template import CertificateTemplate
    from models.policy import CertificatePolicy
    for row in _archived_rows(backup_data, 'certificate_policies'):
        policy = CertificatePolicy.query.filter_by(name=row.get('name')).first()
        cleaned = legacy.cleaned_rules(policy.rules) if policy is not None else None
        if cleaned is not None:
            policy.rules = cleaned
            changed += 1
    # A template row without the column 102 added comes from before 102
    for row in _archived_rows(backup_data, 'certificate_templates'):
        if 'enforce_san_types' in row:
            continue
        template = CertificateTemplate.query.filter_by(name=row.get('name')).first()
        widened = (legacy.widened_system_extensions(
            template.name, template.is_system, template.extensions_template)
            if template is not None else None)
        if widened is not None:
            template.extensions_template = widened
            changed += 1
    return changed


def _saml_strict(backup_data, plan) -> int:
    """103: a provider from before the switch keeps IdP-initiated logins, unsigned requests."""
    from models.sso import SSOProvider
    changed = 0
    for row in _archived_rows(backup_data, 'sso_providers'):
        if 'saml_allow_idp_initiated' in row:
            continue
        provider = SSOProvider.query.filter_by(name=row.get('name')).first()
        if provider is not None:
            provider.saml_allow_idp_initiated = True
            provider.saml_sign_requests = False
            changed += 1
    return changed


def _group_permission_lists(backup_data, plan) -> int:
    """104: a group archived with its permissions as JSON text gets the list of grantable scopes."""
    from models.group import Group
    grantable = legacy.grantable_scopes()
    changed = 0
    for row in _archived_rows(backup_data, 'groups'):
        if not isinstance(row.get('permissions'), str):
            continue    # a list: written after 104
        group = Group.query.filter_by(name=row.get('name')).first()
        fixed = legacy.grantable_list(group.permissions, grantable) if group is not None else None
        if fixed is None or fixed == group.permissions:
            continue
        if group.description == legacy.ADMIN_GROUP_SEEDED and not fixed:
            group.description = legacy.ADMIN_GROUP_NOW
        group.permissions = fixed
        changed += 1
    return changed


def _legacy_ldap_settings(backup_data, plan) -> int:
    """105: the global `ldap_*` keys, a bind password among them, are not kept."""
    return _delete_settings(restored_setting_keys(backup_data) & set(legacy.LEGACY_LDAP_KEYS))


def _order_duplicates(backup_data, plan):
    written = plan.written.get('acme_client_orders')
    return replay_order_repairs(written) if written else None


@dataclass(frozen=True)
class Repair:
    migration: str
    scope: str
    run: Callable[[Dict[str, Any], Any], Any]


# The other migrations from 100 on add columns or tables, or are applied on the
# way in: 116 by upgrade_archived_permissions, 122 by the CA restorer.
REPAIRS = (
    Repair('101_acme_eab_keys_import', 'the acme_eab_keys setting the restore wrote', _eab_keys_blob),
    Repair('102_dead_settings', 'the settings, policies and pre-102 templates the restore wrote',
           _dead_settings),
    Repair('103_saml_strict', 'the SSO providers the restore wrote from before 103', _saml_strict),
    Repair('104_group_permissions_lists', 'the groups the restore wrote as JSON text',
           _group_permission_lists),
    Repair('105_legacy_ldap_settings', 'the ldap_* settings the restore wrote', _legacy_ldap_settings),
    Repair(_ORDER_DUPLICATES, 'the ACME client orders the restore wrote', _order_duplicates),
)


def replay_repairs(backup_data: Dict[str, Any], plan) -> Dict[str, Any]:
    """Every declared repair, on what this restore wrote. Returns what each one changed."""
    db.session.flush()
    done = {}
    for repair in REPAIRS:
        outcome = repair.run(backup_data, plan)
        if outcome:
            done[repair.migration] = outcome
            logger.info("Restore: migration %s replayed on %s: %s",
                        repair.migration, repair.scope, outcome)
    db.session.flush()
    return done

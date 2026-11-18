"""One SSO provider per type at the end of every restore (uq_pro_sso_providers_provider_type).

Decided before the plan, on the archive itself, in either mode and for archives of 3.0 and of 2.254:

* an archive holding two providers of one type is refused, naming them;
* a replacement removes the provider here that holds the type (or the name) of an archived one
  under another name (or type) before the writes: its accounts become orphans of its IdP, which
  only a provider of that IdP takes back. Keeping its row for another IdP would hand the
  identities it bound to that IdP's subjects (OIDC Core §5.7: a sub is unique per issuer);
* a merge keeps the provider here and leaves the archived one out: the accounts the archive
  attaches to it come back as orphans of its IdP, or attached to the provider here when both
  speak to the same IdP (one subject of one IdP is one row).

Each case is a warning of the restore's report.
"""
from typing import Any, Dict, List, Optional, Set

from ..errors import BackupSchemaError
from ..export_generic import REFERENCE_SUFFIX

SECTION = 'sso_providers'
_IDP_FIELDS = ('provider_type', 'oauth2_issuer', 'oauth2_userinfo_url', 'saml_entity_id',
               'ldap_server', 'ldap_base_dn')


def _archived(backup_data) -> List[Dict[str, Any]]:
    rows = backup_data.get(SECTION)
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict) and isinstance(row.get('name'), str)]


def refuse_archived_shared_types(backup_data) -> None:
    """BackupSchemaError, before any write, when the archive itself holds two providers of one type."""
    by_type: Dict[str, List[str]] = {}
    for row in _archived(backup_data):
        by_type.setdefault(row.get('provider_type') or 'oauth2', []).append(row['name'])
    for kind, names in by_type.items():
        if len(names) > 1:
            raise BackupSchemaError(
                f"Cannot restore: the archive holds {len(names)} SSO providers of type {kind}: "
                f"{', '.join(repr(n) for n in names)}. UCM uses one SSO provider per type: restore "
                "it on the release that wrote it, keep one provider of each type, then take a new "
                "backup. Nothing has been changed.")


def _idp_key(row: Dict[str, Any]) -> Optional[str]:
    from models.sso import SSOProvider
    return SSOProvider(**{field: row.get(field) for field in _IDP_FIELDS}).idp_key()


def settle_provider_types(backup_data, replacing: bool, warnings: List[str],
                          displaced: Dict[str, Set[Any]]) -> None:
    """Make the archive's providers and those here one per type, as the module says.

    ``replacing``: the restore prunes the section; the rows here it removes land in ``displaced``.
    """
    from models.sso import SSOProvider
    rows = _archived(backup_data)
    if not rows:
        return
    here = SSOProvider.query.order_by(SSOProvider.id).all()
    by_name = {p.name: p for p in here}
    by_type: Dict[str, List[Any]] = {}
    for provider in here:
        by_type.setdefault(provider.provider_type, []).append(provider)
    left_out, removed = [], set()
    for row in rows:
        kind = row.get('provider_type') or 'oauth2'
        holder = by_name.get(row['name'])
        clashes = [holder] if holder is not None and holder.provider_type != kind else []
        clashes += [p for p in by_type.get(kind, ()) if p.name != row['name']]
        if not clashes:
            continue
        if replacing:
            for provider in clashes:
                if provider.id in removed:
                    continue
                removed.add(provider.id)
                displaced.setdefault(SECTION, set()).add(provider.id)
                warnings.append(
                    f"sso_providers: the {provider.provider_type} provider {provider.name!r} "
                    f"(#{provider.id}) is replaced by the archive's {kind} provider {row['name']!r}: "
                    "one provider per type; the accounts it opened here keep its IdP as orphans")
            continue
        provider = clashes[0]
        held = (f"a {provider.provider_type} provider holds its name here" if provider is holder
                else f"this installation's {kind} provider is {provider.name!r}")
        # Only the provider here of the same type can speak to the same IdP (the key holds the type)
        peer = next((p for p in clashes if p.provider_type == kind), None)
        if peer is not None and peer is not provider:
            held += f" (#{provider.id}) and this installation's {kind} provider is {peer.name!r}"
            provider = peer
        same_idp = peer is not None and _idp_key(row) is not None and _idp_key(row) == peer.idp_key()
        fate = (f"it speaks to the same IdP, so the accounts the archive attaches to it are attached "
                f"to {peer.name!r}" if same_idp
                else "the accounts the archive attaches to it come back as orphans of its IdP")
        warnings.append(
            f"sso_providers: the archive's {kind} provider {row['name']!r} is not restored: {held} "
            f"(#{provider.id}), and there is one provider per type; {fate}")
        left_out.append((row, peer.name if same_idp else None))
    if left_out:
        _leave_out(backup_data, left_out)


def _leave_out(backup_data, rows: List[Any]) -> None:
    """Drop the archived ``(row, here)`` from the archive. What names a row goes to the provider
    ``here`` of the same IdP key, else becomes an orphan of its IdP: one subject, one row."""
    fates = {row['name']: (_idp_key(row), here) for row, here in rows}
    backup_data[SECTION] = [row for row in backup_data.get(SECTION)
                            if not any(row is r for r, _here in rows)]

    def fate(ref):
        return fates.get(ref.get('name')) if isinstance(ref, dict) else None

    for row in backup_data.get('user_sso_identities') or []:
        ref = row.get(f'provider_id{REFERENCE_SUFFIX}') if isinstance(row, dict) else None
        found = fate(ref)
        if found and found[1] is not None:
            row[f'provider_id{REFERENCE_SUFFIX}'] = {'name': found[1]}
        elif found:
            row.update({'provider_id': None, f'provider_id{REFERENCE_SUFFIX}': None,
                        'orphan_of': found[0]})
    # An archive of 2.254 names the provider on the account row
    for row in backup_data.get('users') or []:
        ref = row.get(f'sso_provider_id{REFERENCE_SUFFIX}') if isinstance(row, dict) else None
        found = fate(ref)
        if found and found[1] is not None:
            row[f'sso_provider_id{REFERENCE_SUFFIX}'] = {'name': found[1]}
        elif found:
            row.update({'sso_provider_id': None, f'sso_provider_id{REFERENCE_SUFFIX}': None,
                        'sso_orphan_of': row.get('sso_orphan_of') or found[0]})

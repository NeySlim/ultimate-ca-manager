"""One SSO provider per type at the end of every restore (uq_pro_sso_providers_provider_type).

Decided before the plan, on the archive itself, in either mode and for archives of 3.0 and of 2.254:

* an archive holding two providers of one type is refused, naming them;
* a replacement removes the provider here that holds the type (or the name) of an archived one
  under another name (or type) before the writes: its accounts become orphans of its IdP, which
  only a provider of that IdP takes back. Keeping its row for another IdP would hand the
  identities it bound to that IdP's subjects (OIDC Core §5.7: a sub is unique per issuer);
* a merge keeps the provider here and leaves the archived one out: the accounts the archive
  attaches to it come back as orphans of its IdP.

An archived provider with the name and the type of the one here but another IdP key is another
provider, and is treated as one under another name.

Each case is a warning of the restore's report.
"""
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlsplit, urlunsplit

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
    """BackupSchemaError, before any write, when the archive itself holds two providers of one type
    or a provider whose type is not one the product knows (an absent type is oauth2)."""
    from models.sso import SSOProvider
    rows = backup_data.get(SECTION)
    # Every row the restorer would write is checked: one without a text name escapes _archived.
    # A blank name is text: an instance that let one be created must restore its own backup
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and not isinstance(row.get('name'), str):
            raise BackupSchemaError(
                "Cannot restore: one of the archive's SSO providers has no name, or a name "
                "that is not text. Nothing has been changed.")
    by_type: Dict[str, List[str]] = {}
    for row in _archived(backup_data):
        kind = row.get('provider_type', 'oauth2')
        if kind is not None and not isinstance(kind, str):
            raise BackupSchemaError(
                f"Cannot restore: the type of the archive's SSO provider {row['name']!r} is not "
                "text. Nothing has been changed.")
        if kind not in SSOProvider.TYPES:
            raise BackupSchemaError(
                f"Cannot restore: the archive's SSO provider {row['name']!r} has the type "
                f"{kind!r}, which is none of {', '.join(SSOProvider.TYPES)}. Nothing has been "
                "changed.")
        by_type.setdefault(kind, []).append(row['name'])
    for kind, names in by_type.items():
        if len(names) > 1:
            raise BackupSchemaError(
                f"Cannot restore: the archive holds {len(names)} SSO providers of type {kind}: "
                f"{', '.join(repr(n) for n in names)}. UCM uses one SSO provider per type: restore "
                "it on the release that wrote it, keep one provider of each type, then take a new "
                "backup. Nothing has been changed.")


def _key_of(fields: Dict[str, Any]) -> Optional[str]:
    """The IdP ``fields`` name; a value that is not text is read as absent."""
    from models.sso import SSOProvider
    return SSOProvider(**{field: value if isinstance(value, str) else None
                          for field, value in fields.items()}).idp_key()


def _idp_key(row: Dict[str, Any]) -> Optional[str]:
    return _key_of({field: row.get(field) for field in _IDP_FIELDS})


def _comparable(key: Optional[str]) -> Optional[str]:
    """``key`` with the scheme and host of an OIDC issuer in lower case (RFC 3986 §6.2.2.1)."""
    if not key or not key.startswith('oauth2:'):
        return key
    try:
        parts = urlsplit(key[len('oauth2:'):])
    except ValueError:  # not a URL (an unclosed bracket): compared as written
        return key
    return 'oauth2:' + urlunsplit(parts._replace(scheme=parts.scheme.lower(),
                                                 netloc=parts.netloc.lower()))


def _another_idp(provider, row: Dict[str, Any]) -> bool:
    """Whether the archived ``row`` would point ``provider`` here at another IdP.

    A field the row does not carry keeps its value here, as the restore does. A provider whose
    key the restore leaves as it is (even unknown on both sides) keeps its accounts."""
    here = _key_of({field: getattr(provider, field) for field in _IDP_FIELDS})
    there = _key_of({field: row[field] if field in row else getattr(provider, field)
                     for field in _IDP_FIELDS})
    here, there = _comparable(here), _comparable(there)
    return here != there


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
        kind = row.get('provider_type', 'oauth2')  # in TYPES: refuse_archived_shared_types
        holder = by_name.get(row['name'])
        # The holder of the name is another provider when its type or its IdP differs
        elsewhere = holder is not None and holder.provider_type == kind and _another_idp(holder, row)
        clashes = [holder] if holder is not None and (holder.provider_type != kind or elsewhere) else []
        clashes += [p for p in by_type.get(kind, ()) if p.name != row['name']]
        if not clashes:
            continue
        if replacing:
            for provider in clashes:
                if provider.id in removed:
                    continue
                removed.add(provider.id)
                reason = ('it signs in through another IdP' if provider is holder and elsewhere
                          else 'one provider per type')
                displaced.setdefault(SECTION, set()).add(provider.id)
                warnings.append(
                    f"sso_providers: the {provider.provider_type} provider {provider.name!r} "
                    f"(#{provider.id}) is replaced by the archive's {kind} provider {row['name']!r}: "
                    f"{reason}; the accounts it opened here keep its IdP as orphans")
            continue
        provider = clashes[0]
        if provider is holder and elsewhere:
            held = f"the {kind} provider of that name here signs in through another IdP"
        elif provider is holder:
            held = f"a {provider.provider_type} provider holds its name here"
        else:
            held = f"this installation's {kind} provider is {provider.name!r}"
        warnings.append(
            f"sso_providers: the archive's {kind} provider {row['name']!r} is not restored: {held} "
            f"(#{provider.id}), and there is one provider per type; the accounts the archive "
            "attaches to it come back as orphans of its IdP")
        left_out.append(row)
    if left_out:
        _leave_out(backup_data, left_out)


def _held_here(account, key: Optional[str], external_id) -> bool:
    """Whether the account ``account`` names is already bound here to ``external_id`` by a
    provider of the IdP ``key``: an orphan of that identity would never be signed in with."""
    from models import User, UserSSOIdentity
    from models.sso import SSOProvider
    if (key is None or not isinstance(external_id, str) or not external_id
            or not isinstance(account, dict) or not isinstance(account.get('username'), str)):
        return False
    providers = (SSOProvider.query
                 .join(UserSSOIdentity, UserSSOIdentity.provider_id == SSOProvider.id)
                 .join(User, User.id == UserSSOIdentity.user_id)
                 .filter(User.username == account['username'],
                         UserSSOIdentity.external_id == external_id))
    return any(_comparable(provider.idp_key()) == _comparable(key) for provider in providers)


def _leave_out(backup_data, rows: List[Dict[str, Any]]) -> None:
    """Drop ``rows`` from the archive; what names them becomes an orphan of their IdP, unless
    the account already holds that identity here."""
    keys = {row['name']: _idp_key(row) for row in rows}
    backup_data[SECTION] = [row for row in backup_data.get(SECTION) if not any(row is r for r in rows)]

    def named(ref):
        return isinstance(ref, dict) and ref.get('name') in keys

    identities = backup_data.get('user_sso_identities')
    redundant = []
    for row in identities if isinstance(identities, list) else []:
        ref = row.get(f'provider_id{REFERENCE_SUFFIX}') if isinstance(row, dict) else None
        if named(ref):
            if _held_here(row.get(f'user_id{REFERENCE_SUFFIX}'), keys[ref['name']],
                          row.get('external_id')):
                redundant.append(row)
                continue
            row.update({'provider_id': None, f'provider_id{REFERENCE_SUFFIX}': None,
                        'orphan_of': keys[ref['name']]})
    if redundant:
        backup_data['user_sso_identities'] = [
            row for row in identities if not any(row is r for r in redundant)]
    # An archive of 2.254 names the provider on the account row
    for row in backup_data.get('users') or []:
        ref = row.get(f'sso_provider_id{REFERENCE_SUFFIX}') if isinstance(row, dict) else None
        if named(ref):
            row.update({'sso_provider_id': None, f'sso_provider_id{REFERENCE_SUFFIX}': None,
                        'sso_orphan_of': row.get('sso_orphan_of') or keys[ref['name']]})

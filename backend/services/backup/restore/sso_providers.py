"""An archived SSO provider whose name is taken here by a provider of another IdP.

Providers are found again by name. When the one of that name here talks to
another IdP (OIDC issuer, SAML entity ID, LDAP server and base DN), rewriting it
in place would hand the accounts it bound to that IdP's subjects (OIDC Core 5.7:
a `sub` is unique per issuer only). Decided on the archive, before the plan:

* a replacement removes the provider here before the writes, and its accounts
  become orphans of its IdP, as deleting it does; the archived one is created;
* a merge keeps the provider here and leaves the archived one out: the accounts
  the archive binds to it come back as orphans of its IdP.

Each case is a warning of the restore's report.
"""
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlsplit, urlunsplit

from models import db

from ..export_generic import REFERENCE_SUFFIX

SECTION = 'sso_providers'
_IDP_FIELDS = ('provider_type', 'oauth2_issuer', 'oauth2_userinfo_url', 'saml_entity_id',
               'ldap_server', 'ldap_base_dn')


def _key_of(fields: Dict[str, Any]) -> Optional[str]:
    """The IdP of ``fields``; an archived value that is not text names no IdP."""
    from models.sso import SSOProvider
    return SSOProvider(**{field: value if isinstance(value, str) else None
                          for field, value in fields.items()}).idp_key()


def _comparable(key: Optional[str]) -> Optional[str]:
    """``key`` with the scheme and host of an OIDC issuer in lower case (RFC 3986 6.2.2.1)."""
    if not key or not key.startswith('oauth2:'):
        return key
    try:
        parts = urlsplit(key[len('oauth2:'):])
    except ValueError:      # not a URL: compared as written
        return key
    return 'oauth2:' + urlunsplit(parts._replace(scheme=parts.scheme.lower(),
                                                 netloc=parts.netloc.lower()))


def another_idp(provider, row: Dict[str, Any]) -> bool:
    """Whether applying the archived ``row`` would point ``provider`` at another IdP.

    A field the row does not carry keeps its value here, as the restore does; a key
    unknown on both sides is the same IdP."""
    after = {field: row[field] if field in row else getattr(provider, field)
             for field in _IDP_FIELDS}
    after['provider_type'] = after['provider_type'] or 'oauth2'
    return _comparable(provider.idp_key()) != _comparable(_key_of(after))


def settle_other_idp_providers(backup_data: Dict[str, Any], replacing: bool,
                               warnings: List[str], displaced: Dict[str, Set[Any]]) -> None:
    """Apply the module's rule to the archive; ``displaced`` gets the rows a replacement removes."""
    from models.sso import SSOProvider
    rows = backup_data.get(SECTION)
    if not isinstance(rows, list):
        return
    left_out = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('name'), str):
            continue
        here = SSOProvider.query.filter_by(name=row['name']).first()
        if here is None or not another_idp(here, row):
            continue
        if replacing:
            displaced.setdefault(SECTION, set()).add(here.id)
            warnings.append(
                f"sso_providers: the provider {here.name!r} (#{here.id}) signs in through "
                "another IdP than the archive's provider of that name, which replaces it; "
                "the accounts it opened here keep its IdP as orphans")
        else:
            left_out.append(row)
            warnings.append(
                f"sso_providers: the archive's provider {row['name']!r} is not restored: the "
                f"provider of that name here (#{here.id}) signs in through another IdP; the "
                "accounts the archive attaches to it come back as orphans of its IdP")
    if left_out:
        _leave_out(backup_data, left_out)


def _leave_out(backup_data: Dict[str, Any], rows: List[Dict[str, Any]]) -> None:
    """Drop ``rows`` from the archive; the accounts naming them become orphans of their IdP."""
    keys = {row['name']: _key_of({'provider_type': row.get('provider_type') or 'oauth2',
                                  **{f: row.get(f) for f in _IDP_FIELDS[1:]}})
            for row in rows}
    backup_data[SECTION] = [row for row in backup_data[SECTION]
                            if not any(row is gone for gone in rows)]
    for user in backup_data.get('users') or []:
        ref = user.get(f'sso_provider_id{REFERENCE_SUFFIX}') if isinstance(user, dict) else None
        if isinstance(ref, dict) and ref.get('name') in keys:
            user.update({'sso_provider_id': None, f'sso_provider_id{REFERENCE_SUFFIX}': None,
                         'sso_orphan_of': user.get('sso_orphan_of') or keys[ref['name']]})


def orphan_accounts_of(provider_ids) -> int:
    """Accounts of the providers displaced by an archived provider of another IdP keep their IdP."""
    from models import User
    from models.sso import SSOProvider
    orphaned = 0
    for provider in SSOProvider.query.filter(SSOProvider.id.in_(list(provider_ids or ()))):
        # SQLite does not apply ON DELETE SET NULL: unlinked on both backends
        orphaned += User.query.filter_by(sso_provider_id=provider.id).update(
            {User.sso_provider_id: None, User.sso_orphan_of: provider.idp_key()},
            synchronize_session=False)
    return orphaned

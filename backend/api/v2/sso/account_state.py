"""Where an account stands with respect to a provider, in words an administrator acts on.

An account belongs to one provider and one stable identity; these texts go to the
server log and the audit log only, never to the person signing in.
"""
from models import db
from models.sso import SSOProvider

SSO_NO_PASSWORD = '!SSO_NO_PASSWORD!'


def sso_only(user) -> bool:
    """An account bound to a provider and without a local password: the provider alone
    opens it, so no password door may hand it a password."""
    return (user.auth_source or 'local') != 'local' and user.password_hash == SSO_NO_PASSWORD
ID_BOUND = 64


def bounded(value, limit=ID_BOUND):
    """``value`` cut to ``limit`` characters: an IdP chooses its identifiers."""
    value = str(value)
    return value if len(value) <= limit else value[:limit] + '...'


def _provider_name(provider_id):
    row = db.session.get(SSOProvider, provider_id)
    return row.name if row else f'#{provider_id}'


def orphan_text(user):
    if user.sso_orphan_of:
        return f"no provider (orphan of {bounded(user.sso_orphan_of)!r})"
    return "no provider (its IdP is unknown)"


def describe_conflict(user, provider):
    """(state, remedy) of an account of that name ``provider`` may not open."""
    target = repr(provider.name)
    if user.sso_provider_id is not None and user.sso_provider_id != provider.id:
        former = _provider_name(user.sso_provider_id)
        return (f"is linked to provider {former!r}",
                f"if it is the same person, Link to SSO moves it to {target}, "
                f"after which {former!r} no longer opens it")
    if user.sso_provider_id == provider.id:
        if user.sso_external_id:
            return (f"is bound to another identity of {target} ({bounded(user.sso_external_id)!r})",
                    "if the identity changed at the IdP, Link to SSO resets its identity "
                    "and the next sign-in through this provider binds the new one")
        return (f"is of type {user.auth_source!r}, not {provider.provider_type!r}",
                f"Link to SSO attaches it to {target}")
    if (user.auth_source or 'local') == 'local' and not user.sso_orphan_of:
        return ("is a local account",
                f"if it is the same person, Link to SSO attaches it to {target}")
    state = "has " + orphan_text(user)
    if user.sso_external_id:
        state += f", bound to identity {bounded(user.sso_external_id)!r}"
    return state, f"if it is the same person, Link to SSO attaches it to {target}"


def describe_origin(user, provider):
    """Where an account Link to SSO attaches to ``provider`` comes from."""
    ident = f", identity {bounded(user.sso_external_id)!r}" if user.sso_external_id else ''
    if user.sso_provider_id == provider.id:
        return (f"identity {bounded(user.sso_external_id)!r} reset" if user.sso_external_id
                else "already linked to it, not bound yet")
    if user.sso_provider_id is not None:
        return f"was linked to provider {_provider_name(user.sso_provider_id)!r}{ident}"
    if (user.auth_source or 'local') == 'local' and not user.sso_orphan_of:
        return "was a local account" + ident
    return "had " + orphan_text(user) + ident

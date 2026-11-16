"""Where an account stands with respect to a provider, in words an administrator acts on.

An account is opened by the providers it has a row for in ``user_sso_identities``, each with
one stable identity; these texts go to the server log and the audit log only, never to the
person signing in.
"""
from models import db
from models.sso import SSOProvider

SSO_NO_PASSWORD = '!SSO_NO_PASSWORD!'
ID_BOUND = 64


def own_identity(user, provider):
    """The row attaching ``user`` to ``provider``, or None."""
    return next((row for row in user.sso_identities if row.provider_id == provider.id), None)


def legacy_sso_account(user) -> bool:
    """An SSO account from before migration 024: no row, no password, owing no change.
    Detaching the last provider leaves a password change owed, so such an account is not one."""
    return user.is_local and user.password_hash == SSO_NO_PASSWORD and not user.force_password_change


def sso_only(user) -> bool:
    """An account without a local password that its providers alone open: no self-service
    door may hand it one. An account detached to set a password (a change owed) is not one."""
    if user.password_hash != SSO_NO_PASSWORD:
        return False
    return not user.is_local or not user.force_password_change


def bounded(value, limit=ID_BOUND):
    """``value`` cut to ``limit`` characters: an IdP chooses its identifiers."""
    value = str(value)
    return value if len(value) <= limit else value[:limit] + '...'


def _provider_name(provider_id):
    row = db.session.get(SSOProvider, provider_id)
    return row.name if row else f'#{provider_id}'


def orphan_text(row):
    if row.orphan_of:
        return f"no provider (orphan of {bounded(row.orphan_of)!r})"
    return "no provider (its IdP is unknown)"


def identity_text(row):
    """One row, as the audit names it."""
    ident = f", identity {bounded(row.external_id)!r}" if row.external_id else ''
    if row.provider_id is not None:
        return f"provider {_provider_name(row.provider_id)!r}{ident}"
    return orphan_text(row) + ident


def attachments_text(user):
    """Every row of ``user``, or that it has none."""
    if user.is_local:
        return "a local account"
    return '; '.join(identity_text(row) for row in user.sso_identities)


def describe_conflict(user, provider):
    """(state, remedy) of an account of that name ``provider`` may not open."""
    target = repr(provider.name)
    attach = f"if it is the same person, attach provider {target} to the account"
    own = own_identity(user, provider)
    if own is not None and own.external_id:
        return (f"is bound to another identity of {target} ({bounded(own.external_id)!r})",
                f"if the identity changed at the IdP, reset the identity of its {target} "
                "attachment and the next sign-in through this provider binds the new one")
    if user.is_local:
        return "is a local account", attach
    live = [row for row in user.sso_identities if row.provider_id is not None]
    gone = [row for row in user.sso_identities if row.provider_id is None]
    parts = []
    if live:
        parts.append("is attached to " + ', '.join(
            f"provider {_provider_name(row.provider_id)!r}" for row in live))
    for row in gone:
        text = "has " + orphan_text(row)
        if row.external_id:
            text += f", bound to identity {bounded(row.external_id)!r}"
        parts.append(text)
    keep = "; the providers it is attached to keep opening it" if live else ''
    return '; it '.join(parts), attach + keep

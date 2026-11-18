"""Accounts described as 2.254 held them (``auth_source``, ``sso_provider_id``, ``sso_external_id``,
``sso_orphan_of``), built with the identity rows the upgrade (step 167) gives them, and the reads
the tests make of those rows."""
from models import db, User, UserSSOIdentity
from models.user import sync_sso_flags
from utils.sso_identity_upgrade import identity_rows, ids_here

LEGACY = ('auth_source', 'sso_provider_id', 'sso_external_id', 'sso_orphan_of')


def legacy_user(**columns):
    """A pending User; ``columns`` may name the 2.254 SSO columns."""
    from models.sso import SSOProvider
    legacy = {name: columns.pop(name, None) for name in LEGACY}
    user = User(**columns)
    # The id given is a provider the account has, even a test double's
    providers = {pid for (pid,) in db.session.query(SSOProvider.id)} | {legacy['sso_provider_id']}
    for _uid, provider_id, orphan_of, external_id in identity_rows(
            [(0, legacy['auth_source'] or 'local', legacy['sso_provider_id'], legacy['sso_external_id'],
              legacy['sso_orphan_of'], columns.get('password_hash'),
              columns.get('force_password_change'))], ids_here(providers)):
        row = UserSSOIdentity(provider_id=provider_id, orphan_of=orphan_of)
        row.bind(external_id)
        user.sso_identities.append(row)
    return user


def identities(user):
    """(provider_id, external_id, orphan_of) of each row of ``user``, oldest first."""
    return [(row.provider_id, row.external_id, row.orphan_of) for row in user.sso_identities]


def identity_for(user, provider_id):
    return next((row for row in user.sso_identities if row.provider_id == provider_id), None)


def users_of(provider_id):
    """The accounts a provider is attached to."""
    return User.query.filter(User.sso_identities.any(UserSSOIdentity.provider_id == provider_id))


def delete_users_of(provider_id):
    """Removes the accounts a provider is attached to, with their rows; the caller commits."""
    for user in users_of(provider_id).all():
        db.session.delete(user)


def by_identity(external_id):
    """The accounts bound to that stable identity, at any provider."""
    return User.query.filter(User.sso_identities.any(UserSSOIdentity.external_id == external_id))


def attach(username, provider_id, external_id=None):
    """Gives the account ``username`` a row for that provider; the caller commits."""
    user = User.query.filter_by(username=username).one()
    row = UserSSOIdentity(provider_id=provider_id)
    row.bind(external_id)
    user.sso_identities.append(row)
    return row


def attach_from_another_node(username, provider_id, external_id=None):
    """The same row, written outside this session as another node would."""
    from sqlalchemy import select
    table, users = UserSSOIdentity.__table__, User.__table__
    with db.engine.begin() as conn:
        user_id = conn.execute(select(users.c.id).where(users.c.username == username)).scalar_one()
        conn.execute(table.insert().values(user_id=user_id, provider_id=provider_id,
                                           external_id=external_id))
        sync_sso_flags(conn, [user_id])


def only(user):
    """The one row of an account a test gives a single provider, or None."""
    rows = list(user.sso_identities)
    assert len(rows) <= 1, identities(user)
    return rows[0] if rows else None


def ext(user):
    """The stable identity of that row (2.254: ``sso_external_id``)."""
    row = only(user)
    return row.external_id if row else None


def prov(user):
    """Its provider (2.254: ``sso_provider_id``)."""
    row = only(user)
    return row.provider_id if row else None


def orphan(user):
    """The IdP key a deleted provider left on it (2.254: ``sso_orphan_of``)."""
    row = only(user)
    return row.orphan_of if row else None

"""The identity rows a 2.254 account gets, shared by upgrade step 167 and the restore of an
archive whose account rows still carry their provider, which must run without the migrations."""
import logging

logger = logging.getLogger(__name__)

NO_PASSWORD = '!SSO_NO_PASSWORD!'


def identity_rows(users, here):
    """The rows the accounts of a 2.254 database get, as (user_id, provider_id, orphan_of,
    external_id). ``users``: (id, auth_source, provider, sso_external_id, sso_orphan_of,
    password_hash, force_password_change), ascending ids, ``provider`` the stored reference to
    the account's provider (None: none) and ``here`` the provider id each reference has here.
    A reference ``here`` does not place leaves an orphan of an unknown IdP, as 2.254 read a
    deleted provider; so does a stable identity a lower id already holds for the same provider
    (2.254 matched the first account only), so that no account becomes claimable by name."""
    rows, taken = [], set()
    for uid, source, stored, external_id, orphan_of, password_hash, force_change in users:
        if (source or 'local') == 'local':
            legacy = password_hash == NO_PASSWORD and not force_change
            # 2.254 opened by its name only a legacy account carrying no provider, key or identity
            if not legacy or (stored is None and orphan_of is None and not external_id):
                continue
        provider_id = here.get(stored) if stored is not None else None
        if provider_id is not None:
            orphan_of = None
            if external_id and (provider_id, external_id) in taken:
                logger.warning("[167] account %s shares a stable identity of provider %s with an "
                               "older account: left as an orphan of an unknown IdP", uid, provider_id)
                provider_id = None
            elif external_id:
                taken.add((provider_id, external_id))
        rows.append((uid, provider_id, orphan_of, external_id or None))
    return rows


def ids_here(provider_ids):
    """``here`` for a database whose references are its own provider ids."""
    return {pid: pid for pid in provider_ids}

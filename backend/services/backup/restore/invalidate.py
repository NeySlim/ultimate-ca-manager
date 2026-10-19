"""What a restore leaves valid behind it: open sessions and warm caches.

A restore replaces the identities (accounts, password hashes, API keys,
client certificates) and the PKI (CA keys, templates, revocations) with the
ones the archive carries. The running process notices none of it: a browser
session opened before the restore still resolves to a user id that now
belongs to somebody else, and the process-level caches keep answering with
the state that was just replaced -- upstream ACME directories, parsed CRL
entries, cached OCSP responses signed by a key this instance no longer has.

So once the transaction has committed and the files are published, the
sessions are revoked and the caches dropped. The two are not equally
negotiable:

- A session that survives a restore is an access granted under identities
  the instance no longer has. Failing to revoke one is a security outcome,
  not a degraded one, so a failure here is raised and the restore cannot be
  reported as clean.
- A cache that survives is a stale answer with a bounded lifetime. Failing
  to drop one must neither stop the other purges nor turn a successful
  restore into an error: each purge is isolated, a failure is logged, and
  only the caches that were really dropped are reported.

The restart is asked for last and only when the caller asks for it, through
``utils.service_manager`` -- the one mechanism that works across packagings
(systemd, DEB/RPM, container) and needs no privilege of its own. A restart
is what makes the guarantee whole: this process can only clear the caches it
holds itself, while the other workers of the same install hold their own.
"""
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from flask import current_app

from models import SSOSession, UserSession, db
from utils import service_manager

logger = logging.getLogger(__name__)


def _revoke_database_sessions() -> Dict[str, int]:
    """Delete every session row, or raise.

    Both tables are excluded from the archive on purpose (they describe who
    is connected to *this* install, not what it is), which is precisely why
    they survive a restore untouched and have to be emptied here.

    Each table is emptied in its own transaction so a failure on the second
    does not take back the first: what has been revoked stays revoked, and
    the failure still surfaces.
    """
    revoked = {}
    for key, model in (('user_sessions', UserSession), ('sso_sessions', SSOSession)):
        try:
            revoked[key] = model.query.delete(synchronize_session=False)
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.error(
                "Restore: sessions in %s could not be revoked; access granted "
                "before the restore may still be usable",
                model.__tablename__,
            )
            raise
    return revoked


def _session_directory() -> Optional[Path]:
    """The server-side session store, when it is a directory on this host."""
    try:
        config = current_app.config
    except RuntimeError:
        # Called outside an application context: nothing to resolve the
        # store against, and the caller is not in a restore.
        logger.warning("Restore: no application context, session files left in place")
        return None

    configured = config.get('SESSION_FILE_DIR')
    if not configured:
        if str(config.get('SESSION_TYPE') or '').lower() == 'redis':
            # The rows are gone and the restart follows, but the Redis
            # entries themselves are not ours to delete here.
            logger.warning(
                "Restore: sessions are stored in Redis; their entries are not "
                "removed by the restore"
            )
        return None

    path = Path(configured)
    if not path.is_dir():
        return None
    return path


def _remove_session_files() -> int:
    """Remove the session files, which are what a cookie actually resolves to.

    The database rows are the operator-visible list of sessions; the file in
    this directory is the session itself, holding the authenticated user id
    and the CSRF token. A file left behind is a cookie that still works.

    One file that cannot be removed is logged and does not stop the others:
    the count returned says how many really went.
    """
    directory = _session_directory()
    if directory is None:
        return 0

    removed = 0
    try:
        entries = list(os.scandir(directory))
    except OSError as exc:
        logger.error("Restore: session store %s could not be read: %s", directory, exc)
        return 0

    for entry in entries:
        try:
            if not entry.is_file(follow_symlinks=False):
                continue
            os.unlink(entry.path)
            removed += 1
        except OSError as exc:
            logger.error(
                "Restore: session file %s could not be removed, the session it "
                "holds may still be usable: %s", entry.path, exc,
            )
    return removed


# Every purge below imports what it touches when it runs rather than at module
# import: a cache lives in an optional or heavy module, and one that cannot
# even be imported must fail alone, like one that fails to clear.

def _purge_acme_proxy_caches() -> None:
    """Upstream directories, finalize URLs, challenge->order map, nonce pool.

    Keyed on upstream URLs and on order ids of the instance being replaced.
    """
    from services.acme.acme_proxy_service import reset_proxy_caches
    reset_proxy_caches()


def _purge_acme_renewal_info_cache() -> None:
    """Cached ARI windows, keyed by (client account id, certificate id).

    Both ids are renumbered by the restore, so an entry would hand a renewal
    window of one certificate to another.
    """
    from services import acme_renewal_service
    acme_renewal_service._ARI_CACHE.clear()


def _purge_external_crl_cache() -> None:
    """Revocation entries parsed from the CRLs uploaded for each CA."""
    from services.crl import external
    with external._ENTRY_CACHE_GUARD:
        external._ENTRY_CACHE.clear()


def _purge_ocsp_responses() -> None:
    """Drop the cached OCSP responses of every CA.

    This cache is a table, so it is the one that survives the restore in the
    database itself: a response signed by the key of the replaced instance
    would keep being served, with its own next_update, until it expired.
    The archive does not carry it (responses are rebuilt on demand).
    """
    from models.ocsp import OCSPResponse
    from services.ocsp_service import OCSPService

    ca_ids = [row[0] for row in db.session.query(OCSPResponse.ca_id).distinct().all()]
    for ca_id in ca_ids:
        OCSPService.invalidate_ca_cache(ca_id)

    # invalidate_ca_cache logs and returns 0 rather than raising, so what is
    # left in the table is the only honest report of what was purged.
    remaining = db.session.query(OCSPResponse).count()
    if remaining:
        raise RuntimeError(f"{remaining} cached OCSP responses are still stored")


def _purge_fingerprint_cache() -> None:
    """The SHA-256 -> certificate id index used by discovery.

    It maps fingerprints to the numeric ids of the previous inventory.
    """
    from services.discovery.fingerprint import FingerprintMixin
    FingerprintMixin.invalidate_fingerprint_cache()


def _purge_oidc_cache() -> None:
    """OIDC discovery documents and JWKS of the SSO providers.

    The providers come from the archive; their issuers and signing keys may
    not be the ones this process fetched.
    """
    from services.oidc_id_token import clear_oidc_cache
    clear_oidc_cache()


def _purge_smtp_oauth_tokens() -> None:
    """Access tokens obtained with the SMTP credentials that were replaced."""
    from services import smtp_oauth
    for config_id in list(smtp_oauth._token_cache):
        smtp_oauth.invalidate_cache(config_id)


def _purge_kerberos_contexts() -> None:
    """SPNEGO negotiations started before the restore, keyed by client IP.

    They authenticate against the realm configuration that was just
    replaced; the clients retry and negotiate again.
    """
    from services.kerberos import negotiate_auth
    negotiate_auth._pending_contexts.clear()


def _purge_ca_request_caches() -> None:
    """The per-request chain walk cached on ``flask.g`` (issuer, revocation).

    A no-op outside a request; inside the request that ran the restore, it
    still holds the chain of the CAs that were just replaced.
    """
    from models.ca import clear_request_caches
    clear_request_caches()


#: Ordered so the caches that answer public protocol requests (ACME, OCSP,
#: CRL) go first: they are the ones that would serve the replaced PKI.
CACHE_PURGES: Tuple[Tuple[str, Callable[[], None]], ...] = (
    ('acme_proxy', _purge_acme_proxy_caches),
    ('acme_renewal_info', _purge_acme_renewal_info_cache),
    ('external_crl_entries', _purge_external_crl_cache),
    ('ocsp_responses', _purge_ocsp_responses),
    ('certificate_fingerprints', _purge_fingerprint_cache),
    ('oidc_discovery', _purge_oidc_cache),
    ('smtp_oauth_tokens', _purge_smtp_oauth_tokens),
    ('kerberos_contexts', _purge_kerberos_contexts),
    ('ca_request_chain', _purge_ca_request_caches),
)


def _request_restart() -> bool:
    """Ask the centralized mechanism to restart, and say whether it accepted.

    Never raises: the restore is already committed at this point, and an
    install where the restart cannot be requested (no signal file, read-only
    path) must still be told what was restored -- and told to restart by
    hand, which is what the returned flag lets the caller say.
    """
    try:
        outcome = service_manager.restart_service()
    except Exception as exc:
        logger.warning("Restore: the restart could not be requested: %s", exc)
        return False

    if isinstance(outcome, tuple) and len(outcome) == 2:
        accepted, message = outcome
    else:  # a caller-supplied stand-in that does not follow the contract
        accepted, message = outcome is not False, ''

    if not accepted:
        logger.warning("Restore: the restart was refused: %s", message)
        return False

    logger.info("Restore: restart requested (%s)", message)
    return True


def invalidate_after_restore(*, request_restart: bool = False) -> Dict[str, Any]:
    """Revoke the sessions, drop the caches, optionally ask for the restart.

    Call once the restore transaction has committed and its files are
    published: this deliberately invalidates the state of the *new* content,
    so running it earlier would purge caches that the rest of the restore
    would then repopulate from the state being replaced.

    Raises whatever the session revocation raises, without touching the
    caches or the restart: an access kept across a restore is the failure
    this function exists to prevent, and the caller must not report a clean
    restore over it.

    Returns what was actually done::

        {'sessions_revoked': int,       # rows deleted from user_sessions
         'sso_sessions_revoked': int,   # rows deleted from pro_sso_sessions
         'session_files_removed': int,  # files deleted from the session store
         'caches_cleared': [str],       # caches really dropped
         'caches_failed': [str],        # caches that refused to drop
         'restart_requested': bool}     # the mechanism accepted the request
    """
    revoked = _revoke_database_sessions()

    summary: Dict[str, Any] = {
        'sessions_revoked': revoked['user_sessions'],
        'sso_sessions_revoked': revoked['sso_sessions'],
        'session_files_removed': _remove_session_files(),
        'caches_cleared': [],
        'caches_failed': [],
        'restart_requested': False,
    }

    for name, purge in CACHE_PURGES:
        try:
            purge()
        except Exception as exc:
            # One stale cache is a wrong answer for a bounded time; stopping
            # here would leave every other cache stale as well.
            logger.warning("Restore: the %s cache was not cleared: %s", name, exc)
            summary['caches_failed'].append(name)
        else:
            summary['caches_cleared'].append(name)

    if request_restart:
        summary['restart_requested'] = _request_restart()

    logger.info(
        "Restore: revoked %s sessions and %s SSO sessions, removed %s session "
        "files, cleared %s caches (%s failed), restart requested: %s",
        summary['sessions_revoked'], summary['sso_sessions_revoked'],
        summary['session_files_removed'], len(summary['caches_cleared']),
        len(summary['caches_failed']), summary['restart_requested'],
    )
    return summary


__all__ = ['invalidate_after_restore', 'CACHE_PURGES']

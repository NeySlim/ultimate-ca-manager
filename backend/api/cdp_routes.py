"""
CDP (CRL Distribution Point) Routes
Serves CRLs from database (RFC 5280 §4.2.1.13)
Supports both refid-based (preferred) and legacy numeric ID-based URLs.
"""

import logging
import threading

from flask import Blueprint, Response, abort
from models import CA, db
from services.crl_service import CRLService
from utils.datetime_utils import utc_now
from utils.sanitize import crl_download_filename

logger = logging.getLogger(__name__)

cdp_bp = Blueprint("cdp", __name__)


# Per-CA in-memory locks for on-demand CRL generation. /cdp/<ca>.crl is a
# public, unauthenticated endpoint (RFC 5280 — relying parties must reach
# it without credentials). Without serialisation, N concurrent clients
# requesting the same CA's CRL while no CRL is cached would each trigger
# CRLService.generate_crl() — N parallel CA-signed-CRL operations that
# all touch the CA private key. A single attacker opening 50 parallel
# connections during a fresh CA's first CRL fetch could pin the CPU and
# starve legitimate revocation lookups.
#
# Strategy: per-CA lock with a short acquire timeout. The first request
# generates; the rest wait briefly and re-read the now-cached row from
# the DB. If generation is still in progress past the timeout, the late
# requester returns 503 (try-again-later) rather than piling on.
_CRL_GEN_LOCKS_GUARD = threading.Lock()
_CRL_GEN_LOCKS = {}
_CRL_GEN_TIMEOUT_SECONDS = 30


def _crl_lock_for(ca_id: int) -> threading.Lock:
    with _CRL_GEN_LOCKS_GUARD:
        lock = _CRL_GEN_LOCKS.get(ca_id)
        if lock is None:
            lock = threading.Lock()
            _CRL_GEN_LOCKS[ca_id] = lock
        return lock


def _resolve_ca(ca_ref):
    """Resolve CA by refid (UUID) or legacy numeric ID"""
    # Try refid first (preferred, non-sequential)
    ca = CA.query.filter_by(refid=ca_ref).first()
    if ca:
        return ca
    # Fallback to numeric ID for backwards compatibility
    try:
        ca_id_int = int(ca_ref)
        return db.session.get(CA, ca_id_int)
    except (ValueError, TypeError):
        return None


@cdp_bp.route("/<ca_ref>.crl")
def get_crl(ca_ref):
    """
    Serve CRL file from database.
    Falls back to generating a fresh CRL if none cached, but serialises
    on-demand generation per CA to avoid a stampede on a public,
    unauthenticated endpoint.
    """
    ca = _resolve_ca(ca_ref)
    if not ca:
        abort(404)

    # Get latest CRL from database
    crl_meta = CRLService.get_latest_crl(ca.id)

    # RFC 5280 §5.1.2.5 — relying parties may reject CRLs past nextUpdate.
    # If we hold the signing key, regenerate proactively.
    needs_regen = False
    if crl_meta and crl_meta.next_update:
        nu = crl_meta.next_update
        # Compare in UTC; DB stores naive UTC.
        now_naive = utc_now().replace(tzinfo=None) if utc_now().tzinfo else utc_now()
        nu_naive = nu.replace(tzinfo=None) if getattr(nu, "tzinfo", None) else nu
        if nu_naive <= now_naive:
            needs_regen = True

    if not crl_meta or not crl_meta.crl_der or needs_regen:
        # No CRL in DB or it's expired — try to generate one if CA can sign.
        if ca.has_private_key and ca.cdp_enabled:
            lock = _crl_lock_for(ca.id)
            acquired = lock.acquire(timeout=_CRL_GEN_TIMEOUT_SECONDS)
            if not acquired:
                # Another generation is in flight and still hasn't
                # finished — shed load instead of piling on.
                logger.warning(
                    "CDP: CRL generation for CA %s busy >%ds, returning 503",
                    ca.refid,
                    _CRL_GEN_TIMEOUT_SECONDS,
                )
                return Response(
                    "CRL generation in progress, retry shortly",
                    status=503,
                    headers={"Retry-After": "5"},
                )
            try:
                # Re-check the cache: the request that held the lock
                # before us may have just populated it.
                fresh = CRLService.get_latest_crl(ca.id)
                fresh_expired = (
                    fresh
                    and fresh.next_update
                    and (
                        fresh.next_update.replace(tzinfo=None)
                        if getattr(fresh.next_update, "tzinfo", None)
                        else fresh.next_update
                    )
                    <= (
                        utc_now().replace(tzinfo=None)
                        if utc_now().tzinfo
                        else utc_now()
                    )
                )
                if not fresh or not fresh.crl_der or fresh_expired:
                    try:
                        crl_meta = CRLService.generate_crl(ca.id)
                    except Exception as e:
                        logger.error(
                            f"CDP: failed to generate CRL for CA {ca.refid}: {e}"
                        )
                        if not crl_meta or not crl_meta.crl_der:
                            abort(404)
                        # Fall through with the (expired) cached CRL rather
                        # than 404'ing relying parties — better stale than
                        # nothing per RFC 5280 §6.3.3 step (a).
                else:
                    crl_meta = fresh
            finally:
                lock.release()
        elif not crl_meta or not crl_meta.crl_der:
            abort(404)

    return Response(
        crl_meta.crl_der,
        status=200,
        mimetype="application/pkix-crl",
        headers={
            "Content-Disposition": f'attachment; filename="{crl_download_filename(ca)}"',
            "Cache-Control": "public, max-age=3600, must-revalidate",
            "Last-Modified": crl_meta.this_update.strftime("%a, %d %b %Y %H:%M:%S GMT"),
        },
    )


@cdp_bp.route("/<ca_ref>-delta.crl")
def get_delta_crl(ca_ref):
    """Serve delta CRL file from database"""
    ca = _resolve_ca(ca_ref)
    if not ca:
        abort(404)

    delta_crl = CRLService.get_latest_delta_crl(ca.id)

    if not delta_crl or not delta_crl.crl_der:
        abort(404)

    return Response(
        delta_crl.crl_der,
        status=200,
        mimetype="application/pkix-crl",
        headers={
            "Content-Disposition": f'attachment; filename="{crl_download_filename(ca, delta=True)}"',
            "Cache-Control": "public, max-age=900, must-revalidate",
            "Last-Modified": delta_crl.this_update.strftime(
                "%a, %d %b %Y %H:%M:%S GMT"
            ),
        },
    )

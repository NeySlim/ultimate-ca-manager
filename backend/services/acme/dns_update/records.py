"""Expected TXT values for the DNS UPDATE (RFC 2136) listener.

The ACME proxy stores, per proxy order, the TXT value a client may publish
at ``_acme-challenge.<identifier>.`` (table ``acme_proxy_dns_challenges``).
The listener accepts a record only when its (name, value) pair is stored
here and the row is active.

Every function needs a Flask application context. The caller provides it.
Nothing here raises to the caller on a database error: writes are best
effort and must never change the outcome of an ACME proxy request.
"""
import base64
import hashlib
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, FrozenSet, Iterable, List, NamedTuple, Optional, Tuple

from sqlalchemy.exc import IntegrityError

from models import db
from utils.datetime_utils import to_naive_utc, utc_now

logger = logging.getLogger(__name__)

# A row is never active longer than this, whatever the upstream authz says.
ACTIVE_MAX_AGE = timedelta(hours=24)
# Rows whose expires_at is older than this are deleted on the next write.
PURGE_AFTER = timedelta(days=7)
# Maximum age of the active-row snapshot, in seconds.
CACHE_MAX_AGE_S = 5

_CHALLENGE_LABEL = '_acme-challenge'

# RFC 8555 section 7.1.6: final states in which the validation failed. Rows
# are closed only then: a client that fetched a pending authorization may
# still send its update after UCM's own automation made the challenge
# processing or valid, and must not be refused for that. Success closes the
# rows when the certificate is downloaded (close_for_order).
FAILED_STATES = frozenset({'invalid', 'expired', 'deactivated', 'revoked'})


def is_failed_state(status) -> bool:
    return status in FAILED_STATES


def record_name_for(identifier: str) -> str:
    """Record name of a dns-01 challenge: RFC 8555 section 8.4 and 7.1.4.

    A wildcard identifier is validated at the name without ``*.``."""
    name = (identifier or '').strip().lower().rstrip('.')
    if name.startswith('*.'):
        name = name[2:]
    return f'{_CHALLENGE_LABEL}.{name}.'


def expected_value(token: str, thumbprint: str) -> str:
    """TXT value: base64url(SHA-256(token "." thumbprint)), no padding.

    RFC 8555 section 8.1 and 8.4, RFC 4648 section 5. The result has 43
    characters."""
    digest = hashlib.sha256(f'{token}.{thumbprint}'.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b'=').decode()


def zone_for(identifier: str) -> Optional[str]:
    """Apex of the ACME Domains entry that covers the identifier.

    Absolute, lowercase, trailing dot. None when no entry matches."""
    from api.v2.acme_domains import find_provider_for_domain

    info = find_provider_for_domain(identifier)
    if not info:
        return None
    matched = info.get('matched_domain') if hasattr(info, 'get') else None
    if not matched:
        return None
    matched = str(matched).strip().lower().rstrip('.')
    if matched.startswith('*.'):
        matched = matched[2:]
    if not matched:
        return None
    return matched + '.'


def _parse_expires(value) -> Optional[datetime]:
    """Naive UTC datetime from an RFC 3339 string, or None."""
    if not value or not isinstance(value, str):
        return None
    try:
        text = value.strip()
        if text[-1:] in ('Z', 'z'):
            text = text[:-1] + '+00:00'
        return to_naive_utc(datetime.fromisoformat(text))
    except (ValueError, TypeError):
        return None


def _naive(now: Optional[datetime]) -> datetime:
    return to_naive_utc(now) if now is not None else utc_now()


def persist_expected_values(orders, identifier, token, challenge_url,
                            authz_expires, now) -> int:
    """Store one expected value per order. Returns the inserted row count.

    Each row uses the thumbprint, account_id and proxy account of ITS order.
    An order without a thumbprint gets no row. Best effort: any error rolls
    back the savepoint only, is logged without values and never raised."""
    from models import AcmeProxyDnsChallenge

    try:
        now = _naive(now)
        record_name = record_name_for(identifier)
        unique_orders = {}
        for order in orders or []:
            if getattr(order, 'id', None) is None:
                continue
            unique_orders.setdefault(order.id, order)
        if not unique_orders:
            return 0
        zone_name = zone_for(identifier)
        if zone_name is None:
            return 0
        expires_at = now + ACTIVE_MAX_AGE
        parsed = _parse_expires(authz_expires)
        if parsed is not None and parsed < expires_at:
            expires_at = parsed
        wanted = []
        for order in unique_orders.values():
            thumbprint = getattr(order, 'client_jwk_thumbprint', None)
            if not thumbprint:
                continue
            wanted.append((order, thumbprint,
                           expected_value(token, thumbprint)))
        if not wanted:
            return 0
        inserted = 0
        try:
            with db.session.begin_nested():
                existing = {
                    (row.order_id, row.txt_value)
                    for row in AcmeProxyDnsChallenge.query.filter(
                        AcmeProxyDnsChallenge.order_id.in_(
                            [o.id for o, _t, _v in wanted]),
                        AcmeProxyDnsChallenge.record_name == record_name,
                    ).all()
                }
                for order, thumbprint, value in wanted:
                    if (order.id, value) in existing:
                        continue
                    db.session.add(AcmeProxyDnsChallenge(
                        order_id=order.id,
                        acme_client_account_id=order.acme_client_account_id,
                        account_id=order.account_id,
                        client_jwk_thumbprint=thumbprint,
                        identifier=record_name[len(_CHALLENGE_LABEL) + 1:-1],
                        record_name=record_name,
                        txt_value=value,
                        zone_name=zone_name,
                        upstream_challenge_url=challenge_url,
                        status='pending',
                        created_at=now,
                        expires_at=expires_at,
                    ))
                    inserted += 1
                db.session.flush()
                AcmeProxyDnsChallenge.query.filter(
                    AcmeProxyDnsChallenge.expires_at < now - PURGE_AFTER,
                ).delete(synchronize_session=False)
        except IntegrityError:
            logger.warning(
                '[ACME DNS UPDATE] Expected value already stored '
                '(UNIQUE conflict); skipped')
            return 0
        except Exception as exc:
            logger.warning(
                '[ACME DNS UPDATE] Could not store expected values: %s',
                type(exc).__name__)
            return 0
        if not _commit():
            return 0
        invalidate_cache()
        return inserted
    except Exception as exc:
        logger.warning('[ACME DNS UPDATE] Expected values not stored: %s',
                       type(exc).__name__)
        return 0


def _commit() -> bool:
    """Commit; on failure roll back, log and return False."""
    try:
        db.session.commit()
        return True
    except Exception as exc:
        try:
            db.session.rollback()
        except Exception:
            pass
        logger.warning('[ACME DNS UPDATE] Commit failed: %s',
                       type(exc).__name__)
        return False


def _close_where(*criteria) -> None:
    from models import AcmeProxyDnsChallenge

    try:
        AcmeProxyDnsChallenge.query.filter(
            AcmeProxyDnsChallenge.status == 'pending', *criteria,
        ).update({'status': 'closed'}, synchronize_session=False)
    except Exception as exc:
        try:
            db.session.rollback()
        except Exception:
            pass
        logger.warning('[ACME DNS UPDATE] Could not close rows: %s',
                       type(exc).__name__)
        return
    if _commit():
        invalidate_cache()


def close_for_order(order_id) -> None:
    """Close the pending rows of one order. Never raises."""
    from models import AcmeProxyDnsChallenge

    if order_id is None:
        return
    _close_where(AcmeProxyDnsChallenge.order_id == order_id)


def close_for_challenge_urls(urls: Iterable[str]) -> None:
    """Close the pending rows of the given upstream challenge URLs."""
    from models import AcmeProxyDnsChallenge

    urls = [u for u in (urls or []) if u]
    if not urls:
        return
    _close_where(AcmeProxyDnsChallenge.upstream_challenge_url.in_(urls))


def mark_confirmed(row_ids: Iterable[int], now: Optional[datetime] = None) -> None:
    """Set client_confirmed_at on the rows. Never raises."""
    from models import AcmeProxyDnsChallenge

    row_ids = [i for i in (row_ids or []) if i is not None]
    if not row_ids:
        return
    try:
        AcmeProxyDnsChallenge.query.filter(
            AcmeProxyDnsChallenge.id.in_(row_ids),
        ).update({'client_confirmed_at': _naive(now)},
                 synchronize_session=False)
    except Exception as exc:
        try:
            db.session.rollback()
        except Exception:
            pass
        logger.warning('[ACME DNS UPDATE] Could not mark rows: %s',
                       type(exc).__name__)
        return
    _commit()


# ---------------------------------------------------------------------------
# Active-row cache (plan 2.4)
# ---------------------------------------------------------------------------

class ActiveRecord(NamedTuple):
    row_id: int
    order_id: int
    record_name: str
    txt_value: str
    zone_name: str
    acme_client_account_id: Optional[int]
    account_id: Optional[str]


class ActiveSnapshot(NamedTuple):
    """Immutable view of the active rows."""
    by_name: Dict[str, Tuple[ActiveRecord, ...]]
    zones: FrozenSet[str]


_EMPTY_SNAPSHOT = ActiveSnapshot({}, frozenset())


def _monotonic() -> float:
    return time.monotonic()


class ActiveRecordCache:
    """Snapshot of active rows. Reloaded after invalidate() or when older
    than CACHE_MAX_AGE_S. A reload error keeps the previous snapshot.

    The caller owns the session scope and ends its read transaction.
    The snapshot is not filtered again by time: a row that expires stays
    visible for at most CACHE_MAX_AGE_S seconds."""

    def __init__(self):
        self._lock = threading.Lock()
        self._snapshot = _EMPTY_SNAPSHOT
        self._loaded_at: Optional[float] = None
        self._generation = 0
        self._loaded_generation = -1

    def invalidate(self) -> None:
        self._generation += 1

    def _fresh(self) -> bool:
        return (self._loaded_at is not None
                and self._loaded_generation == self._generation
                and _monotonic() - self._loaded_at < CACHE_MAX_AGE_S)

    def snapshot(self, now: Optional[datetime] = None) -> ActiveSnapshot:
        if self._fresh():
            return self._snapshot
        with self._lock:
            if self._fresh():
                return self._snapshot
            generation = self._generation
            try:
                loaded = self._load(_naive(now))
            except Exception as exc:
                try:
                    db.session.rollback()
                except Exception:
                    pass
                logger.warning(
                    '[ACME DNS UPDATE] Active rows not reloaded, '
                    'previous snapshot kept: %s', type(exc).__name__)
                return self._snapshot
            self._snapshot = loaded
            self._loaded_at = _monotonic()
            self._loaded_generation = generation
            return self._snapshot

    @staticmethod
    def _load(now: datetime) -> ActiveSnapshot:
        from models import AcmeClientOrder, AcmeProxyDnsChallenge

        rows = (db.session.query(AcmeProxyDnsChallenge)
                .join(AcmeClientOrder,
                      AcmeClientOrder.id == AcmeProxyDnsChallenge.order_id)
                .filter(AcmeProxyDnsChallenge.status == 'pending',
                        AcmeProxyDnsChallenge.expires_at > now,
                        AcmeClientOrder.status == 'pending')
                .all())
        by_name: Dict[str, List[ActiveRecord]] = {}
        zones = set()
        for row in rows:
            by_name.setdefault(row.record_name, []).append(ActiveRecord(
                row.id, row.order_id, row.record_name, row.txt_value,
                row.zone_name, row.acme_client_account_id, row.account_id))
            zones.add(row.zone_name)
        return ActiveSnapshot(
            {k: tuple(v) for k, v in by_name.items()}, frozenset(zones))


_cache = ActiveRecordCache()


def get_active_snapshot(now: Optional[datetime] = None) -> ActiveSnapshot:
    """Current snapshot of active rows. Needs a Flask app context."""
    return _cache.snapshot(now)


def invalidate_cache() -> None:
    """Force the next snapshot() to reload from the database."""
    _cache.invalidate()

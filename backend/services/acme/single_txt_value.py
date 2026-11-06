"""DNS providers that hold one TXT value per name (DuckDNS, Hurricane Electric, FreeDNS)."""
import json
import logging
from datetime import timedelta
from typing import Iterable, List, Optional

from models.acme_models import AcmeClientOrder
from utils.datetime_utils import utc_now
from utils.san_parse import strip_wildcard

logger = logging.getLogger(__name__)

# Orders whose authorizations may still need their TXT: 'ready' has them all valid (RFC 8555
# §7.1.6); 'processing' is also set by UCM before validation, 'validating' is UCM's own
IN_PROGRESS = ('pending', 'processing', 'validating')
# An order without a CA expiry stops counting when a pending authorization would have expired
UNDATED_KEPT = timedelta(days=7)


def holds_one_value(provider) -> bool:
    return getattr(provider, 'SINGLE_TXT_VALUE', False) is True


def _normalised(domain: str) -> str:
    return domain.strip().lower().rstrip('.')


def _challenge_name(domain: str) -> str:
    return f"_acme-challenge.{strip_wildcard(_normalised(domain))}"


def txt_lock_name(provider, record_name: str) -> str:
    """The name the TXT lock serialises: the provider's one value, or the record itself."""
    return provider.single_value_key(record_name) if holds_one_value(provider) else record_name


def shared_challenge_names(domains: Iterable[str], provider_class) -> List[str]:
    """The distinct identifiers of one order whose dns-01 values the provider keeps under one key."""
    by_key = {}
    for domain in domains:
        names = by_key.setdefault(provider_class.single_value_key(_challenge_name(domain)), {})
        names.setdefault(_normalised(domain), domain)  # a repeated identifier is one, as for the CA
    return [d for names in by_key.values() if len(names) > 1 for d in names.values()]


def apex_and_wildcard_refusal(domains, provider_class) -> Optional[str]:
    """The refusal of an order that would need two values under one name of this provider."""
    if not holds_one_value(provider_class):
        return None
    shared = shared_challenge_names(domains, provider_class)
    if not shared:
        return None
    return (f"{provider_class.PROVIDER_NAME} holds one TXT value per name, so {', '.join(shared)} "
            "cannot be validated in the same order: request them in separate orders, one after the other")


def order_using_name(provider, record_name: str, except_order_id=None) -> Optional[int]:
    """Id of another order in progress whose dns-01 value the provider keeps with ``record_name``'s."""
    target = provider.single_value_key(record_name)
    now = utc_now()
    query = AcmeClientOrder.query.filter(AcmeClientOrder.status.in_(IN_PROGRESS),
                                         AcmeClientOrder.challenge_type == 'dns-01')
    if except_order_id is not None:
        query = query.filter(AcmeClientOrder.id != except_order_id)
    for order in query.all():
        if order.expires_at is not None:
            if order.expires_at <= now:
                continue
        elif order.created_at is not None and order.created_at < now - UNDATED_KEPT:
            continue
        try:
            domains = json.loads(order.domains or '[]')
        except (TypeError, ValueError):
            continue
        if any(isinstance(d, str) and provider.single_value_key(_challenge_name(d)) == target for d in domains):
            return order.id
    return None


def keep_for_another_order(provider, record_name: str, except_order_id=None) -> bool:
    """Whether a cleanup must leave ``record_name`` alone: on a one-value provider, clearing it
    would take the value of another order still validating it. Call under the name's TXT lock.
    A cleanup skipped here is not retried: the blocking order's own cleanup clears the name."""
    if not holds_one_value(provider):
        return False
    other = order_using_name(provider, record_name, except_order_id)
    if other is None:
        return False
    logger.info("DNS cleanup of %s left to ACME order %s, still in progress: %s holds one value per name",
                record_name, other, getattr(provider, 'PROVIDER_NAME', 'the provider'))
    return True

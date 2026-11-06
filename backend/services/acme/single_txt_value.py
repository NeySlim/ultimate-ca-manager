"""DNS providers that hold one TXT value per name (DuckDNS, Hurricane Electric, FreeDNS)."""
import json
import logging
from datetime import timedelta
from typing import Iterable, List, Optional

from models.acme_models import AcmeClientOrder
from utils.datetime_utils import utc_now
from utils.san_parse import strip_wildcard

logger = logging.getLogger(__name__)

# Not final (RFC 8555 §7.1.6), plus UCM's 'validating'
IN_PROGRESS = ('pending', 'ready', 'processing', 'validating')
# An order without a CA expiry stops counting when a pending authorization would have expired
UNDATED_KEPT = timedelta(days=7)


def holds_one_value(provider) -> bool:
    return getattr(provider, 'SINGLE_TXT_VALUE', False) is True


def _challenge_name(domain: str) -> str:
    return f"_acme-challenge.{strip_wildcard(domain.strip().lower().rstrip('.'))}"


def shared_challenge_names(domains: Iterable[str]) -> List[str]:
    """The identifiers of one order whose dns-01 records share a name (a domain and its wildcard)."""
    by_name = {}
    for domain in domains:
        by_name.setdefault(_challenge_name(domain), []).append(domain)
    return [d for names in by_name.values() if len(names) > 1 for d in names]


def apex_and_wildcard_refusal(domains, provider_class) -> Optional[str]:
    """The refusal of an order that would need two values under one name of this provider."""
    if not holds_one_value(provider_class):
        return None
    shared = shared_challenge_names(domains)
    if not shared:
        return None
    return (f"{provider_class.PROVIDER_NAME} holds one TXT value per name, so {', '.join(shared)} "
            "cannot be validated in the same order: request them in separate orders, one after the other")


def order_using_name(record_name: str, except_order_id=None) -> Optional[int]:
    """Id of another order in progress whose dns-01 challenge uses ``record_name``, else None."""
    target = record_name.strip().lower().rstrip('.')
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
        if any(isinstance(d, str) and _challenge_name(d) == target for d in domains):
            return order.id
    return None


def keep_for_another_order(provider, record_name: str, except_order_id=None) -> bool:
    """Whether a cleanup must leave ``record_name`` alone: on a one-value provider, clearing it
    would take the value of another order still validating it. Call under the name's TXT lock."""
    if not holds_one_value(provider):
        return False
    other = order_using_name(record_name, except_order_id)
    if other is None:
        return False
    logger.info("DNS cleanup of %s left to ACME order %s, still in progress: %s holds one value per name",
                record_name, other, getattr(provider, 'PROVIDER_NAME', 'the provider'))
    return True

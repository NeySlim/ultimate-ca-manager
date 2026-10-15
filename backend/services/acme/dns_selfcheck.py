"""
Shared DNS-01 propagation self-check helpers for ACME flows.
"""
import logging
import time
from typing import Optional

from models import SystemConfig
from utils.acme_debug import acme_log
from utils.dns_txt_lookup import txt_record_present
from utils.san_parse import strip_wildcard

logger = logging.getLogger(__name__)

DNS_SELFCHECK_DEFAULT_TIMEOUT = 120
DNS_SELFCHECK_INTERVAL = 5
DNS_PROPAGATION_DEFAULT_DELAY = 10
DNS_PROPAGATION_MAX_DELAY = 300


def _seconds_setting(config_key: str, default: int) -> int:
    cfg = SystemConfig.query.filter_by(key=config_key).first()
    try:
        if cfg and cfg.value is not None:
            return max(0, int(cfg.value))
    except (ValueError, TypeError):
        pass
    return default


def dns_propagation_timeout(config_key: str = 'acme.client.dns_propagation_timeout') -> int:
    """Read propagation timeout from SystemConfig, clamped to >= 0."""
    return _seconds_setting(config_key, DNS_SELFCHECK_DEFAULT_TIMEOUT)


def dns_propagation_delay() -> int:
    """Seconds to wait once the TXT is visible: anycast nodes of a DNS provider
    can lag the one UCM reaches."""
    return min(_seconds_setting('acme.client.dns_propagation_delay', DNS_PROPAGATION_DEFAULT_DELAY),
               DNS_PROPAGATION_MAX_DELAY)


def acme_allow_loopback_upstream() -> bool:
    """Opt-in (default False): allow ACME upstream traffic to a loopback address.

    UCM already permits RFC1918/.lan upstreams; loopback stays blocked by default
    (SSRF hardening). Operators running a colocated ACME CA (Pebble/step-ca on
    127.0.0.1) flip ``acme.client.allow_loopback_upstream`` to true to opt in.
    """
    try:
        cfg = SystemConfig.query.filter_by(key='acme.client.allow_loopback_upstream').first()
        if cfg is None or cfg.value is None:
            return False
        return str(cfg.value).strip().lower() in ('1', 'true', 'yes', 'on')
    except Exception:
        return False


def challenge_txt_name(domain: str, challenge: dict) -> str:
    """TXT owner name for a dns-01 challenge dict (renewal rows may omit dns_txt_name)."""
    return challenge.get('dns_txt_name') or f"_acme-challenge.{strip_wildcard(domain)}"


def wait_for_challenges(challenges: dict, timeout: int, delay: Optional[int] = None) -> dict:
    """
    Poll DNS until every dns-01 TXT record is visible, or timeout, then wait
    *delay* seconds (default: the configured propagation delay) when they all are.

    Returns {'ok': bool, 'missing': [domains], 'waited': seconds}.
    """
    pending = {d: c for d, c in challenges.items() if c.get('dns_txt_value')}
    checked = bool(pending)
    waited = 0
    started = time.monotonic()
    if pending:
        logger.info(
            'DNS propagation poll started: timeout=%ss, interval=%ss, domains=%s',
            timeout, DNS_SELFCHECK_INTERVAL, ', '.join(sorted(pending)),
        )
    while pending:
        for domain in list(pending):
            c = pending[domain]
            txt_name = challenge_txt_name(domain, c)
            txt_value = c['dns_txt_value']
            if txt_record_present(txt_name, txt_value):
                logger.info('DNS TXT confirmed for %s (%s)', domain, txt_name)
                del pending[domain]
            else:
                acme_log(
                    logger,
                    'DNS TXT still pending for %s (%s) after %ss',
                    domain, txt_name, waited,
                )
        # Wall clock too: slow lookups count against the timeout, not only sleeps.
        if not pending or max(waited, time.monotonic() - started) >= timeout:
            break
        time.sleep(DNS_SELFCHECK_INTERVAL)
        waited += DNS_SELFCHECK_INTERVAL
        if pending:
            acme_log(
                logger,
                'DNS propagation poll tick: waited=%ss, remaining=%s',
                waited, ', '.join(sorted(pending)),
            )
    waited = max(waited, int(time.monotonic() - started))
    if pending:
        logger.warning(
            'DNS propagation poll finished without all TXT records: waited=%ss, missing=%s',
            waited, ', '.join(sorted(pending)),
        )
    elif checked:
        delay = dns_propagation_delay() if delay is None else delay
        if delay > 0:
            logger.info('DNS TXT visible; waiting %ss before the CA validates', delay)
            time.sleep(delay)
            waited += delay
    return {'ok': not pending, 'missing': list(pending), 'waited': waited}


def wait_for_txt(name: str, value: str, timeout: int) -> dict:
    """Single-record wrapper around wait_for_challenges()."""
    return wait_for_challenges(
        {'_single_': {'dns_txt_name': name, 'dns_txt_value': value}},
        timeout,
    )

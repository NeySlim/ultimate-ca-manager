"""
Shared DNS-01 propagation self-check helpers for ACME flows.
"""
import logging
import time

from models import SystemConfig
from utils.acme_debug import acme_log
from utils.dns_txt_lookup import log_public_resolver_status, txt_record_present

logger = logging.getLogger(__name__)

DNS_SELFCHECK_DEFAULT_TIMEOUT = 120
DNS_SELFCHECK_INTERVAL = 5


def dns_propagation_timeout(config_key: str = 'acme.client.dns_propagation_timeout') -> int:
    """Read propagation timeout from SystemConfig, clamped to >= 0."""
    cfg = SystemConfig.query.filter_by(key=config_key).first()
    try:
        if cfg and cfg.value is not None:
            return max(0, int(cfg.value))
    except (ValueError, TypeError):
        pass
    return DNS_SELFCHECK_DEFAULT_TIMEOUT


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
    # Strip a leading '*.' prefix only — lstrip('*.') would eat any run of
    # '*' and '.' characters (same class of bug as the CAA wildcard strip).
    base = domain[2:] if domain.startswith('*.') else domain
    return challenge.get('dns_txt_name') or f"_acme-challenge.{base}"


def wait_for_challenges(challenges: dict, timeout: int) -> dict:
    """
    Poll DNS until every dns-01 TXT record is visible, or timeout.

    Returns {'ok': bool, 'missing': [domains], 'waited': seconds}.
    """
    pending = {d: c for d, c in challenges.items() if c.get('dns_txt_value')}
    waited = 0
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
                log_public_resolver_status(txt_name, txt_value)
        if not pending or waited >= timeout:
            break
        time.sleep(DNS_SELFCHECK_INTERVAL)
        waited += DNS_SELFCHECK_INTERVAL
        if pending:
            acme_log(
                logger,
                'DNS propagation poll tick: waited=%ss, remaining=%s',
                waited, ', '.join(sorted(pending)),
            )
    if pending:
        logger.warning(
            'DNS propagation poll finished without all TXT records: waited=%ss, missing=%s',
            waited, ', '.join(sorted(pending)),
        )
    return {'ok': not pending, 'missing': list(pending), 'waited': waited}


def wait_for_txt(name: str, value: str, timeout: int) -> dict:
    """Single-record wrapper around wait_for_challenges()."""
    return wait_for_challenges(
        {'_single_': {'dns_txt_name': name, 'dns_txt_value': value}},
        timeout,
    )

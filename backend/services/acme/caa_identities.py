"""The CAA issuer domain names of the local ACME server."""
import logging

logger = logging.getLogger(__name__)


def caa_identities(req=None) -> list:
    """The configured ``acme_caa_identifiers``, else the public ACME host.

    The directory's ``caaIdentities`` and the finalize CAA check both read this
    list (RFC 8555 §7.1.1: the same strings the server expects in CAA records).
    """
    from models import SystemConfig
    try:
        cfg = SystemConfig.query.filter_by(key='acme_caa_identifiers').first()
        configured = [v.strip() for v in (cfg.value or '').split(',') if v.strip()] if cfg else []
    except Exception as exc:
        logger.warning(f"Could not read acme_caa_identifiers: {exc}")
        configured = []
    if configured:
        return configured
    try:
        from flask import request
        from utils.acme_public_url import get_acme_public_host
        return [get_acme_public_host(req if req is not None else request)]
    except Exception:
        return []

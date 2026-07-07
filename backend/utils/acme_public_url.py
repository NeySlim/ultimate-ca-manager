"""Helpers for public ACME endpoint URLs exposed to clients."""

from models import SystemConfig


def _configured_acme_host_port():
    host_cfg = SystemConfig.query.filter_by(key='acme_public_vhost').first()
    port_cfg = SystemConfig.query.filter_by(key='acme_public_port').first()
    host = (host_cfg.value.strip() if host_cfg and host_cfg.value else '')
    port_raw = (port_cfg.value.strip() if port_cfg and port_cfg.value else '')
    try:
        port = int(port_raw) if port_raw else 443
    except (TypeError, ValueError):
        port = 443
    return host, port


def get_acme_public_origin(flask_request) -> str:
    """Public origin for ACME endpoints (configured vhost/port or request host)."""
    host, port = _configured_acme_host_port()
    if host:
        host_part = host if port == 443 else f'{host}:{port}'
        return f'https://{host_part}'
    return f'{flask_request.scheme}://{flask_request.host}'


"""Canonical admin redirect and public Host-role enforcement."""

from __future__ import annotations

import ipaddress
import logging

from flask import current_app, redirect, request

from utils.public_endpoints import (
    build_canonical_redirect_url,
    check_host_access,
    get_admin_base_url,
    get_admin_public_host,
    host_is_ip,
    is_admin_ui_path,
    skip_public_host_middleware,
)
from utils.response import error_response

logger = logging.getLogger(__name__)

_LOCAL_HOSTNAMES = frozenset({'localhost', '127.0.0.1', '::1'})


def _peer_is_loopback(remote_addr: str | None) -> bool:
    if not remote_addr:
        return False
    try:
        return ipaddress.ip_address(remote_addr).is_loopback
    except ValueError:
        return False


def _is_trusted_local_request() -> bool:
    """True only when the TCP peer is loopback AND Host names localhost."""
    host = request.host.split(':')[0].lower()
    return host in _LOCAL_HOSTNAMES and _peer_is_loopback(request.remote_addr)


def _remote_is_trusted_proxy() -> bool:
    """True only when the immediate TCP peer is in UCM_TRUSTED_PROXIES (see utils.trusted_proxy)."""
    from utils.trusted_proxy import is_request_from_trusted_proxy

    return is_request_from_trusted_proxy()


def _proxy_header_spoof_attempt() -> bool:
    """Direct client sent X-Forwarded-Host while ProxyFix trust is enabled."""
    hops = current_app.config.get('TRUSTED_PROXY_HOPS', 0)
    if hops <= 0:
        return False
    if not request.headers.get('X-Forwarded-Host'):
        return False
    return not _remote_is_trusted_proxy()


def init_public_host_middleware(app):
    @app.before_request
    def enforce_public_host_roles():
        path = request.path
        if skip_public_host_middleware(path):
            return None

        if _proxy_header_spoof_attempt() and is_admin_ui_path(path):
            return error_response(
                'Untrusted X-Forwarded-Host from non-proxy client',
                403,
            )

        host = request.host.split(':')[0].lower()
        denied = check_host_access(path, host)
        if denied:
            status, message = denied
            if status == 404 and not path.startswith('/api/'):
                return message, 404
            return error_response(message, status)

        return None

    @app.before_request
    def redirect_to_canonical_admin():
        path = request.path
        if skip_public_host_middleware(path):
            return None
        if not is_admin_ui_path(path):
            return None

        if _is_trusted_local_request():
            return None

        current_host = request.host.split(':')[0].lower()
        admin_base = get_admin_base_url()

        # Explicit base_url: redirect IP and alias hostnames to canonical admin URL.
        if admin_base:
            admin_host = get_admin_public_host()
            if admin_host and current_host != admin_host:
                target = build_canonical_redirect_url(request.full_path.rstrip('?'))
                if target:
                    return redirect(target, code=302)
            return None

        # No base_url in DB: legacy IP-only redirect using env FQDN / hostname -f.
        admin_host = get_admin_public_host()
        if not admin_host or not host_is_ip(current_host):
            return None
        if current_host == admin_host:
            return None
        scheme = 'https' if request.is_secure else 'http'
        port_str = request.host.split(':')[1] if ':' in request.host else None
        if port_str:
            new_url = f"{scheme}://{admin_host}:{port_str}{request.full_path.rstrip('?')}"
        else:
            https_port = current_app.config.get('HTTPS_PORT', 8443)
            new_url = f"{scheme}://{admin_host}:{https_port}{request.full_path.rstrip('?')}"
        return redirect(new_url, code=302)

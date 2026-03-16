"""
Protocol URL helper
Provides the base URL for PKI protocol endpoints (CDP, OCSP, EST, SCEP).
Users can configure a separate base URL (e.g. http://) to avoid TLS
verification loops when clients fetch CRLs or OCSP responses.
"""
from flask import request as flask_request
from models import SystemConfig


def get_protocol_base_url():
    """
    Get the base URL for protocol endpoints.
    Uses protocol_base_url setting if configured, otherwise falls back
    to the current request's host URL.
    """
    config = SystemConfig.query.filter_by(key='protocol_base_url').first()
    if config and config.value:
        return config.value.rstrip('/')
    return flask_request.host_url.rstrip('/')

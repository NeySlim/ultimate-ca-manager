from . import bp, logger
from flask import request
from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.ssrf_protection import validate_url_not_cloud_metadata, safe_request_get
from models.sso import SSOProvider, SSOSession
from services.audit_service import AuditService
from utils.datetime_utils import utc_now
import tempfile
import os
import requests as http_requests
from .helpers import _get_ssl_verify, _cleanup_ssl_verify
from .saml_routes import _parse_saml_metadata
from models import db


@bp.route('/api/v2/sso/sessions', methods=['GET'])
@require_auth(['read:sso'])
def list_sessions():
    """List active SSO sessions"""
    sessions = SSOSession.query.filter(
        SSOSession.expires_at > utc_now()
    ).all()
    return success_response(data=[s.to_dict() for s in sessions])


# ============ SAML Metadata ============

def _typed_ssl_verify(verify, ca_bundle):
    """requests `verify` value for a typed flag and CA bundle PEM (a temp file path for a bundle)."""
    if not verify:
        return False
    if not ca_bundle:
        return True
    fd, path = tempfile.mkstemp(suffix='.pem', prefix='ucm_sso_ca_')
    try:
        os.write(fd, ca_bundle.encode('utf-8') if isinstance(ca_bundle, str) else ca_bundle)
    finally:
        os.close(fd)
    return path


@bp.route('/api/v2/sso/saml/metadata/fetch', methods=['POST'])
@require_auth(['write:sso'])
def fetch_idp_metadata():
    """Fetch and parse IDP metadata XML from a URL"""
    data = request.get_json()
    metadata_url = data.get('metadata_url')
    if not metadata_url:
        return error_response("metadata_url is required", 400)

    # Validate URL scheme to prevent SSRF
    from urllib.parse import urlparse
    parsed = urlparse(metadata_url)
    if parsed.scheme not in ('http', 'https'):
        return error_response("metadata_url must use http or https scheme", 400)
    if not parsed.hostname:
        return error_response("metadata_url must include a hostname", 400)
    # Narrow SSRF guard — internal Keycloak/IdP on RFC1918 is legitimate,
    # but cloud metadata + loopback must always be blocked (and the old
    # literal-IP check silently accepted any hostname, even ones that
    # resolve to cloud metadata IPs).
    try:
        validate_url_not_cloud_metadata(metadata_url)
    except ValueError:
        return error_response("metadata_url cannot target cloud metadata or loopback", 400)

    verify = True
    try:
        # Values typed in the form (tested before saving) win; the saved provider fills the rest
        provider_id = data.get('provider_id')
        provider = db.session.get(SSOProvider, provider_id) if provider_id else None
        typed_verify = data.get('verify_ssl')
        typed_ca = data.get('ca_bundle')
        if provider and typed_verify is None and not typed_ca:
            verify = _get_ssl_verify(provider, 'saml')
        elif provider:
            if typed_verify is None:
                typed_verify = provider.saml_verify_ssl is not False
            ca_bundle = typed_ca or provider.saml_ca_bundle
            verify = _typed_ssl_verify(typed_verify, ca_bundle)
        else:
            # Check if verify_ssl was explicitly passed (for new providers not yet saved)
            verify = _typed_ssl_verify(data.get('verify_ssl', True), typed_ca)

        resp = safe_request_get(metadata_url, timeout=10, verify=verify)
        resp.raise_for_status()
    except http_requests.exceptions.SSLError as e:
        logger.error(f"Failed to fetch IDP metadata (SSL): {e}")
        return error_response(
            "SSL certificate verification failed. Upload the CA certificate that signed the "
            "IdP certificate, or turn SSL verification off for this provider.", 400)
    except Exception as e:
        logger.error(f"Failed to fetch IDP metadata: {e}")
        return error_response("Failed to fetch metadata. Check the URL is reachable.", 400)
    finally:
        if isinstance(verify, str) and verify.startswith(tempfile.gettempdir()):
            _cleanup_ssl_verify(verify)

    try:
        parsed = _parse_saml_metadata(resp.text)
        return success_response(data=parsed, message="IDP metadata parsed successfully")
    except Exception as e:
        logger.error(f"Failed to parse IDP metadata XML: {e}")
        return error_response("Failed to parse metadata XML. Ensure the URL returns valid SAML metadata.", 400)

"""
CAs CRUD Operations
"""

from . import bp
from flask import request, g, jsonify
import base64
import re
import logging
import traceback
import uuid
from datetime import datetime, timezone

from auth.unified import require_auth, has_permission
from utils.response import success_response, error_response, created_response, no_content_response
from utils.pagination import paginate
from utils.dn_validation import validate_dn_field, validate_dn
from utils.protocol_url import get_protocol_base_url
from services.ca_service import CAService
from services.audit_service import AuditService
from services.notification_service import NotificationService
from models import Certificate, CA, db
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from websocket.emitters import on_ca_created, on_ca_updated, on_ca_deleted

logger = logging.getLogger(__name__)


def _needs_protocol_url(current_url):
    """Check if a protocol URL needs (re)generation.
    Returns True if URL is empty or uses https:// (protocol URLs must be http://).
    """
    if not current_url:
        return True
    return current_url.startswith('https://')


@bp.route('/api/v2/cas', methods=['GET'])
@require_auth(['read:cas'])
def list_cas():
    """
    List CAs for current user
    Query: ?page=1&per_page=20&search=xxx&type=xxx
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    paginated = 'page' in request.args or 'per_page' in request.args
    search = request.args.get('search', '')
    ca_type = request.args.get('type', '')

    # Get all CAs
    all_cas = CAService.list_cas()

    # Filter
    filtered_cas = []
    for ca in all_cas:
        if search and search.lower() not in ca.descr.lower():
            continue

        # Optional: Filter by 'orphan' logic if requested
        if ca_type == 'orphan':
             # Orphan = Intermediate (caref set) but parent not found in list?
             # Or imported manually without parent link?
             # For now, we'll return manual imports that have no caref but are not self-signed?
             if ca.imported_from == 'manual' and not ca.is_root and not ca.caref:
                 filtered_cas.append(ca)
             continue

        filtered_cas.append(ca)

    # Paginate manually since list_cas returns list
    total = len(filtered_cas)
    if paginated:
        start = (page - 1) * per_page
        end = start + per_page
        paginated_cas = filtered_cas[start:end]
    else:
        # No explicit pagination requested -> return all so the UI (which has no
        # pagination controls) doesn't silently truncate the list. See issue #89.
        paginated_cas = filtered_cas

    # Add certificate count for each CA
    result = []
    for ca in paginated_cas:
        ca_dict = ca.to_dict()
        # Count certificates by refid first, then by issuer CN
        cert_count = Certificate.query.filter_by(caref=ca.refid).count()
        if cert_count == 0 and ca_dict.get('common_name'):
            cn = ca_dict.get('common_name')
            cert_count = Certificate.query.filter(
                Certificate.issuer.ilike(f'CN={cn},%') |
                Certificate.issuer.ilike(f'%,CN={cn},%') |
                Certificate.issuer.ilike(f'%,CN={cn}')
            ).count()
        ca_dict['certs'] = cert_count
        result.append(ca_dict)

    return success_response(
        data=result,
        meta={
            'total': total,
            'page': page if paginated else 1,
            'per_page': per_page if paginated else total,
            'total_pages': ((total + per_page - 1) // per_page) if paginated else 1
        }
    )


@bp.route('/api/v2/cas', methods=['POST'])
@require_auth(['write:cas'])
def create_ca():
    """
    Create new CA
    Body: {commonName, organization, country, keyAlgo, keySize, validityYears, type...}
    """
    data = request.json

    if not data or not data.get('commonName'):
        return error_response('Common Name is required', 400)

    try:
        # Map frontend fields to backend expected fields
        dn = {
            'CN': data.get('commonName'),
            'O': data.get('organization'),
            'OU': data.get('organizationalUnit') or None,
            'C': (data.get('country') or '').upper() or None,
            'ST': data.get('state') or None,
            'L': data.get('locality') or None
        }

        # SECURITY: Validate DN fields
        is_valid, error = validate_dn(dn)
        if not is_valid:
            return error_response(error, 400)

        # Determine key type
        key_type = '2048'  # Default
        if data.get('keyAlgo') == 'RSA':
            key_size = int(data.get('keySize') or 2048)
            if key_size < 2048:
                return error_response('RSA key size must be at least 2048 bits', 400)
            key_type = str(key_size)
        elif data.get('keyAlgo') == 'ECDSA':
            key_type = data.get('keySize') or 'prime256v1'

        # ----- HSM key selection (Issue #77.3) -----
        hsm_provider_id = data.get('hsm_provider_id') or data.get('hsmProviderId')
        hsm_key_id = data.get('hsm_key_id') or data.get('hsmKeyId')
        hsm_key_label = data.get('hsm_key_label') or data.get('hsmKeyLabel')
        hsm_key_algorithm = data.get('hsm_key_algorithm') or data.get('hsmKeyAlgorithm')

        # Mutually exclusive: local vs existing-HSM-key vs new-HSM-key
        modes = []
        if hsm_key_id:
            modes.append('existing-hsm-key')
        if hsm_provider_id and hsm_key_label and hsm_key_algorithm:
            modes.append('new-hsm-key')
        if (hsm_provider_id or hsm_key_label or hsm_key_algorithm) and 'new-hsm-key' not in modes and not hsm_key_id:
            return error_response(
                'To generate a new HSM key, hsm_provider_id, hsm_key_label '
                'and hsm_key_algorithm are all required',
                400,
            )
        if len(modes) > 1:
            return error_response(
                'Provide either hsm_key_id (existing) OR '
                'hsm_provider_id+hsm_key_label+hsm_key_algorithm (new), not both',
                400,
            )

        # Resolve parent CA for intermediate CAs
        caref = None
        if data.get('type') == 'intermediate' and data.get('parentCAId'):
            parent_ca = CA.query.get(int(data['parentCAId']))
            if not parent_ca:
                return error_response('Parent CA not found', 400)
            if not parent_ca.has_private_key:
                return error_response('Parent CA has no private key', 400)
            # Check parent CA is not expired
            parent_cert = x509.load_pem_x509_certificate(
                base64.b64decode(parent_ca.crt), default_backend()
            )
            if datetime.now(timezone.utc) > parent_cert.not_valid_after_utc:
                return error_response('Parent CA certificate has expired', 400)
            caref = parent_ca.refid

        username = g.user.username if hasattr(g, 'user') else (g.current_user.username if hasattr(g, 'current_user') else 'system')

        ca = CAService.create_internal_ca(
            descr=data.get('description') or data.get('commonName'),
            dn=dn,
            key_type=key_type,
            validity_days=int(data.get('validityYears') or 10) * 365,
            caref=caref,
            username=username,
            path_length=data.get('pathLength'),
            name_constraints_permitted=data.get('nameConstraintsPermitted'),
            name_constraints_excluded=data.get('nameConstraintsExcluded'),
            policy_constraints_require=data.get('policyConstraintsRequire'),
            policy_constraints_inhibit=data.get('policyConstraintsInhibit'),
            inhibit_any_policy=data.get('inhibitAnyPolicy'),
            sia_urls=data.get('siaUrls'),
            hsm_provider_id=int(hsm_provider_id) if hsm_provider_id else None,
            hsm_key_id=int(hsm_key_id) if hsm_key_id else None,
            hsm_key_label=hsm_key_label,
            hsm_key_algorithm=hsm_key_algorithm,
        )

        # Send notification for CA creation
        try:
            NotificationService.on_ca_created(ca, username)
        except Exception:
            pass  # Non-blocking

        # WebSocket event
        try:
            on_ca_created(
                ca_id=ca.id,
                name=ca.name,
                common_name=ca.dn_commonname,
                created_by=username
            )
        except Exception:
            pass  # Non-blocking

        return created_response(
            data=ca.to_dict(),
            message='CA created successfully'
        )
    except ValueError as e:
        # Validation errors (HSM key conflicts, missing fields, etc.) -- surface to user
        logger.info(f"CA creation validation error: {e}")
        return error_response(str(e), 400)
    except Exception as e:
        logger.error(f"Failed to create CA: {e}")
        return error_response("Failed to create CA", 500)


@bp.route('/api/v2/cas/<int:ca_id>', methods=['GET'])
@require_auth(['read:cas'])
def get_ca(ca_id):
    """Get CA details"""
    ca = CAService.get_ca(ca_id)
    if not ca:
        return error_response('CA not found', 404)

    # Get basic model data
    ca_data = ca.to_dict()

    # Add certificate count
    cert_count = Certificate.query.filter_by(caref=ca.refid).count()
    if cert_count == 0 and ca_data.get('common_name'):
        cn = ca_data.get('common_name')
        cert_count = Certificate.query.filter(
            Certificate.issuer.ilike(f'CN={cn},%') |
            Certificate.issuer.ilike(f'%,CN={cn},%') |
            Certificate.issuer.ilike(f'%,CN={cn}')
        ).count()
    ca_data['certs'] = cert_count

    # Get CRL status
    crl_status = 'Not Generated'
    next_crl_update = 'N/A'
    try:
        from services.crl_service import CRLService
        crl_info = CRLService.get_crl_info(ca_id)
        if crl_info and crl_info.get('exists'):
            crl_status = 'Active'
            next_crl_update = crl_info.get('next_update', 'N/A')
    except Exception:
        pass

    # Get parsed certificate details
    try:
        details = CAService.get_ca_details(ca_id)
        # Merge details into response
        ca_data.update({
            'commonName': details.get('subject', {}).get('CN', ca.descr),
            'org': details.get('subject', {}).get('O', ''),
            'country': details.get('subject', {}).get('C', ''),
            'keyAlgo': details.get('public_key', {}).get('algorithm', 'RSA'),
            'keySize': details.get('public_key', {}).get('size', 2048),
            'fingerprint': details.get('fingerprints', {}).get('sha256', ''),
            'crlStatus': crl_status,
            'nextCrlUpdate': next_crl_update
        })
    except Exception as e:
        # Fallback if parsing fails
        pass

    # Parse X.509 extensions from CA certificate
    try:
        from utils.cert_extensions import parse_certificate_extensions
        ca_data['extensions'] = parse_certificate_extensions(ca.crt)
    except Exception:
        pass

    return success_response(data=ca_data)


@bp.route('/api/v2/cas/<int:ca_id>', methods=['PATCH'])
@require_auth(['write:cas'])
def update_ca(ca_id):
    """
    Update CA settings (OCSP, CDP, etc.)

    Body (all optional):
        name: Display name
        ocsp_enabled: bool - Enable OCSP responder
        ocsp_url: string - OCSP responder URL
        cdp_enabled: bool - Enable CRL Distribution Point
        cdp_url: string - CRL Distribution Point URL
        is_active: bool - Active status
    """

    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)

    data = request.json or {}

    # Update allowed fields
    if 'name' in data:
        ca.descr = data['name']
    if 'ocsp_enabled' in data:
        ca.ocsp_enabled = bool(data['ocsp_enabled'])
        primary_ocsp = ca.get_primary_ocsp_url()
        if ca.ocsp_enabled and _needs_protocol_url(primary_ocsp):
            base_url = get_protocol_base_url()
            if not base_url:
                return error_response('Cannot auto-generate OCSP URL: configure a FQDN or Protocol Base URL in Settings first', 400)
            ca.set_ocsp_urls([f"{base_url}/ocsp"])
    if 'ocsp_url' in data:
        ca.set_ocsp_urls([data['ocsp_url']] if isinstance(data['ocsp_url'], str) else data['ocsp_url'])
    if 'ocsp_urls' in data:
        ca.set_ocsp_urls(data['ocsp_urls'])
    if 'cdp_enabled' in data:
        ca.cdp_enabled = bool(data['cdp_enabled'])
        primary_cdp = ca.get_primary_cdp_url()
        if ca.cdp_enabled and _needs_protocol_url(primary_cdp):
            base_url = get_protocol_base_url()
            if not base_url:
                return error_response('Cannot auto-generate CDP URL: configure a FQDN or Protocol Base URL in Settings first', 400)
            ca.set_cdp_urls([f"{base_url}/cdp/{ca.refid}.crl"])
    if 'cdp_url' in data:
        ca.set_cdp_urls([data['cdp_url']] if isinstance(data['cdp_url'], str) else data['cdp_url'])
    if 'cdp_urls' in data:
        ca.set_cdp_urls(data['cdp_urls'])
    if 'aia_ca_issuers_enabled' in data:
        ca.aia_ca_issuers_enabled = bool(data['aia_ca_issuers_enabled'])
        primary_aia = ca.get_primary_aia_url()
        if ca.aia_ca_issuers_enabled and _needs_protocol_url(primary_aia):
            base_url = get_protocol_base_url()
            if not base_url:
                return error_response('Cannot auto-generate AIA URL: configure a FQDN or Protocol Base URL in Settings first', 400)
            ca.set_aia_urls([f"{base_url}/ca/{ca.refid}.cer"])
    if 'aia_ca_issuers_url' in data:
        ca.set_aia_urls([data['aia_ca_issuers_url']] if isinstance(data['aia_ca_issuers_url'], str) else data['aia_ca_issuers_url'])
    if 'aia_ca_issuers_urls' in data:
        ca.set_aia_urls(data['aia_ca_issuers_urls'])
    # CPS fields
    if 'cps_enabled' in data:
        ca.cps_enabled = bool(data['cps_enabled'])
    if 'cps_uri' in data:
        ca.cps_uri = data['cps_uri']
    if 'cps_oid' in data:
        ca.cps_oid = data['cps_oid'] or '2.5.29.32.0'
    if 'is_active' in data:
        ca.is_active = bool(data['is_active'])

    try:
        db.session.commit()

        # Audit log
        AuditService.log_action(
            action='ca_updated',
            resource_type='ca',
            resource_id=ca_id,
            resource_name=ca.descr,
            details=f'CA {ca.descr} settings updated',
            success=True
        )

        try:
            on_ca_updated(ca_id, ca.descr, {k: v for k, v in data.items()})
        except Exception:
            pass

        return success_response(data=ca.to_dict(), message='CA updated successfully')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update CA: {e}")
        return error_response('Failed to update CA', 500)


@bp.route('/api/v2/cas/<int:ca_id>', methods=['DELETE'])
@require_auth(['delete:cas'])
def delete_ca(ca_id):
    """Delete CA and all dependent records (CRLs, OCSP responses, etc.)"""

    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)

    ca_name = ca.descr or f'CA #{ca_id}'

    # Check for child CAs (intermediates signed by this CA)
    child_cas = CA.query.filter_by(caref=ca.refid).count()
    if child_cas > 0:
        return error_response(
            f'Cannot delete CA: {child_cas} intermediate CA(s) depend on it. Delete them first.',
            409
        )

    # Check for issued certificates
    issued_certs = Certificate.query.filter_by(caref=ca.refid).count()
    if issued_certs > 0:
        return error_response(
            f'Cannot delete CA: {issued_certs} certificate(s) were issued by it. Revoke and delete them first.',
            409
        )

    try:
        # Delete dependent records before deleting CA
        from models.crl import CRLMetadata
        from models.ocsp import OCSPResponse

        crl_count = CRLMetadata.query.filter_by(ca_id=ca_id).delete()
        ocsp_count = OCSPResponse.query.filter_by(ca_id=ca_id).delete()

        if crl_count or ocsp_count:
            logger.info(f"Deleted {crl_count} CRL(s) and {ocsp_count} OCSP response(s) for CA {ca_name}")

        db.session.delete(ca)
        db.session.commit()

        # Audit log
        AuditService.log_action(
            action='ca_deleted',
            resource_type='ca',
            resource_id=ca_id,
            resource_name=ca_name,
            details=f'Deleted CA: {ca_name} (cleaned {crl_count} CRLs, {ocsp_count} OCSP responses)',
            success=True
        )

        try:
            username = g.current_user.username if hasattr(g, 'current_user') else 'system'
            on_ca_deleted(ca_id, ca_name, username)
        except Exception:
            pass

        return no_content_response()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete CA {ca_name}: {e}")
        return error_response('Failed to delete CA', 500)

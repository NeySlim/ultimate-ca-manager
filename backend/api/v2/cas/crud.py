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
from utils.decorators import require_json_body
from utils.db_transaction import safe_commit
from services.ca_service import CAService
from services.audit_service import AuditService
from services.notification_service import NotificationService
from utils.ca_profile import (
    resolve_digest,
    validate_ca_key_usage,
    normalize_ca_eku,
    default_key_usage_for_ca,
)
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


# ---- Validation helpers (defense-in-depth: values land in extensions of
# every issued certificate, so we cap length, charset and list size). ----
_MAX_URL_LEN = 2048
_MAX_URLS_PER_FIELD = 8
_MAX_DESCR_LEN = 255
_MAX_DESCRIPTION_LEN = 1024
_MAX_OID_LEN = 100
_MAX_NAME_CONSTRAINTS = 32
_MAX_NAME_CONSTRAINT_LEN = 255
_MAX_SIA_URLS = 8
_MAX_PATH_LENGTH = 32
_OID_RE = re.compile(r'^[0-2](\.\d+)+$')


def _validate_protocol_url(url, field):
    """Validate a single AIA/CDP/OCSP/CPS URL: scheme + length cap."""
    if url is None or url == '':
        return None  # allowed: clears the field
    if not isinstance(url, str):
        return f'{field} must be a string'
    if len(url) > _MAX_URL_LEN:
        return f'{field} too long (max {_MAX_URL_LEN} chars)'
    lo = url.lower()
    if not (lo.startswith('http://') or lo.startswith('https://')):
        return f'{field} must use http:// or https:// (RFC 5280)'
    return None


def _normalize_url_list(value, field):
    """Accept str or list; return (list_or_none, error_str_or_none)."""
    if value is None:
        return None, None
    if isinstance(value, str):
        value = [value] if value else []
    if not isinstance(value, list):
        return None, f'{field} must be a string or array of strings'
    if len(value) > _MAX_URLS_PER_FIELD:
        return None, f'{field} accepts at most {_MAX_URLS_PER_FIELD} URLs'
    cleaned = []
    for u in value:
        err = _validate_protocol_url(u, field)
        if err:
            return None, err
        if u:
            cleaned.append(u)
    return cleaned, None


@bp.route('/api/v2/cas', methods=['GET'])
@require_auth(['read:cas'])
def list_cas():
    """
    List CAs for current user
    Query: ?page=1&per_page=20&search=xxx&type=xxx
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    if page < 1:
        page = 1
    if per_page < 1:
        per_page = 20
    if per_page > 100:
        per_page = 100
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

        # Determine key type — whitelist algorithms and parameters to prevent
        # DoS (huge RSA key generation) and unsupported curves.
        ALLOWED_RSA_SIZES = {2048, 3072, 4096}
        ALLOWED_EC_CURVES = {'prime256v1', 'secp384r1', 'secp521r1'}
        key_type = '2048'  # Default
        if data.get('keyAlgo') == 'RSA':
            try:
                key_size = int(data.get('keySize') or 2048)
            except (TypeError, ValueError):
                return error_response('Invalid RSA key size', 400)
            if key_size not in ALLOWED_RSA_SIZES:
                return error_response(
                    f'RSA key size must be one of {sorted(ALLOWED_RSA_SIZES)}', 400
                )
            key_type = str(key_size)
        elif data.get('keyAlgo') == 'ECDSA':
            curve = data.get('keySize') or 'prime256v1'
            if curve not in ALLOWED_EC_CURVES:
                return error_response(
                    f'ECDSA curve must be one of {sorted(ALLOWED_EC_CURVES)}', 400
                )
            key_type = curve

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

        # Validate validity period — cap at 50 years (CA/B Forum max for roots
        # is 25y; leave headroom for offline roots while preventing unbounded
        # values like 10000 years). Use explicit None check so 0 is rejected
        # (not silently replaced by the default).
        raw_validity = data.get('validityYears')
        if raw_validity is None or raw_validity == '':
            validity_years = 10
        else:
            try:
                validity_years = int(raw_validity)
            except (TypeError, ValueError):
                return error_response('Invalid validityYears', 400)
        if not 1 <= validity_years <= 50:
            return error_response('validityYears must be between 1 and 50', 400)

        # Cap description (stored in CA.descr, ends up in UI + audit logs)
        description = data.get('description') or data.get('commonName')
        if description and len(description) > _MAX_DESCRIPTION_LEN:
            return error_response(
                f'description too long (max {_MAX_DESCRIPTION_LEN} chars)', 400
            )

        # Validate optional X.509 extension parameters (defense-in-depth: these
        # land in the cert and must be sane integers / bounded lists).
        path_length = data.get('pathLength')
        if path_length is not None and path_length != '':
            try:
                path_length = int(path_length)
            except (TypeError, ValueError):
                return error_response('pathLength must be an integer', 400)
            if not 0 <= path_length <= _MAX_PATH_LENGTH:
                return error_response(
                    f'pathLength must be between 0 and {_MAX_PATH_LENGTH}', 400
                )
        else:
            path_length = None

        inhibit_any_policy = data.get('inhibitAnyPolicy')
        if inhibit_any_policy is not None and inhibit_any_policy != '':
            try:
                inhibit_any_policy = int(inhibit_any_policy)
            except (TypeError, ValueError):
                return error_response('inhibitAnyPolicy must be an integer', 400)
            if not 0 <= inhibit_any_policy <= _MAX_PATH_LENGTH:
                return error_response(
                    f'inhibitAnyPolicy must be between 0 and {_MAX_PATH_LENGTH}', 400
                )
        else:
            inhibit_any_policy = None

        for pc_field in ('policyConstraintsRequire', 'policyConstraintsInhibit'):
            pc_val = data.get(pc_field)
            if pc_val is not None and pc_val != '':
                try:
                    pc_int = int(pc_val)
                except (TypeError, ValueError):
                    return error_response(f'{pc_field} must be an integer', 400)
                if not 0 <= pc_int <= _MAX_PATH_LENGTH:
                    return error_response(
                        f'{pc_field} must be between 0 and {_MAX_PATH_LENGTH}', 400
                    )
                data[pc_field] = pc_int

        # Cap NameConstraints lists (count + per-item length)
        for nc_field in ('nameConstraintsPermitted', 'nameConstraintsExcluded'):
            nc_val = data.get(nc_field)
            if nc_val is None:
                continue
            if not isinstance(nc_val, list):
                return error_response(f'{nc_field} must be an array', 400)
            if len(nc_val) > _MAX_NAME_CONSTRAINTS:
                return error_response(
                    f'{nc_field} accepts at most {_MAX_NAME_CONSTRAINTS} entries', 400
                )
            for item in nc_val:
                if not isinstance(item, str) or len(item) > _MAX_NAME_CONSTRAINT_LEN:
                    return error_response(
                        f'{nc_field} entries must be strings ≤ {_MAX_NAME_CONSTRAINT_LEN} chars', 400
                    )

        # Validate SIA URLs (same rules as AIA/CDP/OCSP)
        sia_urls_validated, sia_err = _normalize_url_list(data.get('siaUrls'), 'siaUrls')
        if sia_err:
            return error_response(sia_err, 400)

        is_root = not caref
        raw_digest = data.get('digest') or data.get('hashAlgorithm')
        digest, digest_err = resolve_digest(raw_digest, key_type)
        if digest_err:
            return error_response(digest_err, 400)

        raw_ku = data.get('keyUsage')
        if raw_ku is None and data.get('key_usage') is not None:
            raw_ku = data.get('key_usage')
        if raw_ku is None:
            key_usage = default_key_usage_for_ca(is_root)
        else:
            ku_err = validate_ca_key_usage(raw_ku)
            if ku_err:
                return error_response(ku_err, 400)
            key_usage = list(dict.fromkeys(s.strip() for s in raw_ku if isinstance(s, str)))

        raw_eku = data.get('extendedKeyUsage')
        if raw_eku is None and data.get('extended_key_usage') is not None:
            raw_eku = data.get('extended_key_usage')
        if raw_eku is None:
            extended_key_usage = None
        else:
            extended_key_usage, eku_err = normalize_ca_eku(raw_eku, is_root)
            if eku_err:
                return error_response(eku_err, 400)

        ca = CAService.create_internal_ca(
            descr=description,
            dn=dn,
            key_type=key_type,
            validity_days=validity_years * 365,
            digest=digest,
            caref=caref,
            username=username,
            path_length=path_length,
            name_constraints_permitted=data.get('nameConstraintsPermitted'),
            name_constraints_excluded=data.get('nameConstraintsExcluded'),
            policy_constraints_require=data.get('policyConstraintsRequire'),
            policy_constraints_inhibit=data.get('policyConstraintsInhibit'),
            inhibit_any_policy=inhibit_any_policy,
            sia_urls=sia_urls_validated,
            key_usage=key_usage,
            extended_key_usage=extended_key_usage,
            hsm_provider_id=int(hsm_provider_id) if hsm_provider_id else None,
            hsm_key_id=int(hsm_key_id) if hsm_key_id else None,
            hsm_key_label=hsm_key_label,
            hsm_key_algorithm=hsm_key_algorithm,
        )

        # Single lifecycle event — bus fans out to webhook + email + WebSocket.
        # Snapshot before emit: subscribers may commit and expire the instance.
        ca_dict = ca.to_dict()
        from services.webhook_service import emit_ca_created
        emit_ca_created(ca_dict, actor=username)

        return created_response(
            data=ca_dict,
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

    # Track which fields actually changed for the audit log
    changed = []

    # Update allowed fields
    if 'name' in data:
        new_name = data['name']
        if new_name is not None and not isinstance(new_name, str):
            return error_response('name must be a string', 400)
        if new_name and len(new_name) > _MAX_DESCR_LEN:
            return error_response(f'name too long (max {_MAX_DESCR_LEN} chars)', 400)
        if new_name != ca.descr:
            ca.descr = new_name
            changed.append('name')
    if 'ocsp_enabled' in data:
        new_val = bool(data['ocsp_enabled'])
        if new_val != bool(ca.ocsp_enabled):
            changed.append('ocsp_enabled')
        ca.ocsp_enabled = new_val
        primary_ocsp = ca.get_primary_ocsp_url()
        if ca.ocsp_enabled and _needs_protocol_url(primary_ocsp):
            base_url = get_protocol_base_url()
            if not base_url:
                return error_response('Cannot auto-generate OCSP URL: configure a FQDN or Protocol Base URL in Settings first', 400)
            ca.set_ocsp_urls([f"{base_url}/ocsp"])
    for field, setter in (
        ('ocsp_url', ca.set_ocsp_urls),
        ('ocsp_urls', ca.set_ocsp_urls),
    ):
        if field in data:
            urls, err = _normalize_url_list(data[field], field)
            if err:
                return error_response(err, 400)
            setter(urls or [])
            changed.append(field)
    if 'cdp_enabled' in data:
        new_val = bool(data['cdp_enabled'])
        if new_val != bool(ca.cdp_enabled):
            changed.append('cdp_enabled')
        ca.cdp_enabled = new_val
        primary_cdp = ca.get_primary_cdp_url()
        if ca.cdp_enabled and _needs_protocol_url(primary_cdp):
            base_url = get_protocol_base_url()
            if not base_url:
                return error_response('Cannot auto-generate CDP URL: configure a FQDN or Protocol Base URL in Settings first', 400)
            ca.set_cdp_urls([f"{base_url}/cdp/{ca.refid}.crl"])
    for field, setter in (
        ('cdp_url', ca.set_cdp_urls),
        ('cdp_urls', ca.set_cdp_urls),
    ):
        if field in data:
            urls, err = _normalize_url_list(data[field], field)
            if err:
                return error_response(err, 400)
            setter(urls or [])
            changed.append(field)
    if 'aia_ca_issuers_enabled' in data:
        new_val = bool(data['aia_ca_issuers_enabled'])
        if new_val != bool(ca.aia_ca_issuers_enabled):
            changed.append('aia_ca_issuers_enabled')
        ca.aia_ca_issuers_enabled = new_val
        primary_aia = ca.get_primary_aia_url()
        if ca.aia_ca_issuers_enabled and _needs_protocol_url(primary_aia):
            base_url = get_protocol_base_url()
            if not base_url:
                return error_response('Cannot auto-generate AIA URL: configure a FQDN or Protocol Base URL in Settings first', 400)
            ca.set_aia_urls([f"{base_url}/ca/{ca.refid}.cer"])
    for field, setter in (
        ('aia_ca_issuers_url', ca.set_aia_urls),
        ('aia_ca_issuers_urls', ca.set_aia_urls),
    ):
        if field in data:
            urls, err = _normalize_url_list(data[field], field)
            if err:
                return error_response(err, 400)
            setter(urls or [])
            changed.append(field)
    # CPS fields
    if 'cps_enabled' in data:
        new_val = bool(data['cps_enabled'])
        if new_val != bool(ca.cps_enabled):
            changed.append('cps_enabled')
        ca.cps_enabled = new_val
    if 'cps_uri' in data:
        err = _validate_protocol_url(data['cps_uri'] or '', 'cps_uri')
        if err and data['cps_uri']:
            return error_response(err, 400)
        ca.cps_uri = data['cps_uri']
        changed.append('cps_uri')
    if 'cps_oid' in data:
        oid = (data['cps_oid'] or '').strip()
        if oid:
            if len(oid) > _MAX_OID_LEN or not _OID_RE.match(oid):
                return error_response('cps_oid must be a valid OID (e.g. 2.5.29.32.0)', 400)
        ca.cps_oid = oid or '2.5.29.32.0'
        changed.append('cps_oid')
    if 'is_active' in data:
        new_val = bool(data['is_active'])
        if new_val != bool(getattr(ca, 'is_active', None)):
            changed.append('is_active')
        ca.is_active = new_val
    # Offline state is mutated EXCLUSIVELY through the dedicated /offline and
    # /restore endpoints (they enforce password complexity + real key
    # encryption / decryption). Silently ignore any attempt to set
    # offline/offline_reason/offline_mode through the generic update path.
    for forbidden in ('offline', 'offline_reason', 'offline_mode'):
        if forbidden in data:
            logger.warning(
                "Ignoring attempt to mutate '%s' through PUT /api/v2/cas/%s "
                "(use /offline or /restore instead)",
                forbidden, ca_id
            )

    try:
        db.session.commit()

        # Audit log
        AuditService.log_action(
            action='ca_updated',
            resource_type='ca',
            resource_id=ca_id,
            resource_name=ca.descr,
            details=f'CA {ca.descr} updated: {", ".join(changed) if changed else "no changes"}',
            success=True
        )

        username = g.current_user.username if hasattr(g, 'current_user') else 'system'
        ca_dict = ca.to_dict()
        from services.webhook_service import emit_ca_updated
        emit_ca_updated(ca_dict, actor=username, changes={k: v for k, v in data.items()})

        return success_response(data=ca_dict, message='CA updated successfully')
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

    ca_snapshot = ca.to_dict()

    try:
        # Delete dependent records before deleting CA
        from models.crl import CRLMetadata
        from models.ocsp import OCSPResponse

        crl_count = CRLMetadata.query.filter_by(ca_id=ca_id).delete()
        ocsp_count = OCSPResponse.query.filter_by(ca_id=ca_id).delete()

        if crl_count or ocsp_count:
            logger.info(f"Deleted {crl_count} CRL(s) and {ocsp_count} OCSP response(s) for CA {ca_name}")

        db.session.delete(ca)
        ok, err = safe_commit(logger, "Failed to delete CA")
        if not ok:
            return err

        # Audit log
        AuditService.log_action(
            action='ca_deleted',
            resource_type='ca',
            resource_id=ca_id,
            resource_name=ca_name,
            details=f'Deleted CA: {ca_name} (cleaned {crl_count} CRLs, {ocsp_count} OCSP responses)',
            success=True
        )

        username = g.current_user.username if hasattr(g, 'current_user') else 'system'
        from services.webhook_service import emit_ca_deleted
        emit_ca_deleted(ca_snapshot, actor=username)

        return no_content_response()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete CA: {e}")
        return error_response('Failed to delete CA', 500)


@bp.route('/api/v2/cas/<int:ca_id>/offline', methods=['POST'])
@require_auth(['write:cas'])
def take_ca_offline(ca_id):
    """Take a CA offline by encrypting its private key with a user-supplied
    password.

    Two modes:

    - ``password_protected`` (default): the key is re-encrypted with the user
      password (PKCS#8 + ``BestAvailableEncryption``) and stored back in the
      DB under the master-key wrap. Restore needs the same password.
    - ``file_exported``: same key encryption is returned to the caller as a
      ``.key`` file download and **removed** from the DB. Restore needs the
      file uploaded back together with the password.

    Body (JSON): ``{password: str, mode: 'password_protected'|'file_exported'}``
    """
    from security.password_policy import validate_password
    from security.encryption import (
        decrypt_private_key, encrypt_private_key,
    )
    from utils.key_codec import load_pem_bytes, store_pem_bytes
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend
    from flask import Response

    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)

    if ca.offline:
        return error_response('CA is already offline', 409)

    if not ca.prv:
        return error_response(
            'CA has no in-DB private key to take offline (HSM-backed or '
            'externally-stored CAs cannot be taken offline through this flow)',
            400
        )

    # Accept JSON OR multipart (multipart unused for offline today, kept
    # symmetric with /restore which DOES need multipart for file_exported)
    data = request.get_json(silent=True) or {}
    password = (data.get('password') or '').strip()
    mode = data.get('mode', 'password_protected')

    if mode not in ('password_protected', 'file_exported'):
        return error_response(
            "Invalid mode: must be 'password_protected' or 'file_exported'", 400
        )

    # Password complexity (canonical UCM policy)
    ok, errs = validate_password(password)
    if not ok:
        # errs is now list of dicts with 'key' and 'message' fields
        msgs = [e.get('message', str(e)) if isinstance(e, dict) else str(e) for e in errs]
        return error_response(
            'Password does not meet complexity requirements: ' + '; '.join(msgs),
            400
        )

    # Load + re-encrypt the private key
    try:
        master_decrypted = decrypt_private_key(ca.prv)
        if not master_decrypted:
            raise ValueError('CA private key is empty after master decryption')
        pem_bytes = load_pem_bytes(master_decrypted.encode() if isinstance(master_decrypted, str) else master_decrypted,
                                   context=f"CA {ca_id}")
        priv = serialization.load_pem_private_key(
            pem_bytes, password=None, backend=default_backend()
        )
        encrypted_pem = priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.BestAvailableEncryption(password.encode('utf-8')),
        )
    except Exception as e:
        logger.error(f"take_ca_offline: failed to encrypt key for CA {ca_id}: {e}")
        return error_response('Failed to encrypt CA private key', 500)

    try:
        if mode == 'password_protected':
            # Store user-encrypted PEM under master-key wrap (defense-in-depth)
            ca.prv = encrypt_private_key(store_pem_bytes(encrypted_pem))
        else:  # file_exported
            # Wipe key from DB; caller receives the only copy as a download
            ca.prv = None

        ca.offline = True
        ca.offline_mode = mode
        ca.offline_reason = None  # legacy field, no longer collected
        ok, err = safe_commit(logger, "Failed to take CA offline")
        if not ok:
            return err

        AuditService.log_action(
            action='ca_offline',
            resource_type='ca',
            resource_id=ca_id,
            resource_name=ca.descr,
            details=f"CA taken offline: mode={mode}",
            success=True
        )

        if mode == 'file_exported':
            from utils.sanitize import sanitize_filename
            fname = f"{sanitize_filename(ca.descr or ca.refid or f'ca-{ca_id}')}-offline.key"
            return Response(
                encrypted_pem,
                mimetype='application/x-pem-file',
                headers={
                    'Content-Disposition': f'attachment; filename="{fname}"',
                    'X-UCM-Offline-Mode': 'file_exported',
                }
            )

        return success_response(data=ca.to_dict(), message='CA taken offline')
    except Exception as e:
        db.session.rollback()
        logger.error(f"take_ca_offline: DB write failed for CA {ca_id}: {e}")
        return error_response('Failed to take CA offline', 500)


@bp.route('/api/v2/cas/<int:ca_id>/restore', methods=['POST'])
@require_auth(['write:cas'])
def restore_ca(ca_id):
    """Restore an offline CA back to online state.

    - ``password_protected``: JSON ``{password}``. The DB-stored key is
      decrypted with the password; on success it is re-stored unencrypted
      (under the master-key wrap) and the CA is marked online.
    - ``file_exported``: multipart ``password`` field + ``key_file`` upload
      of the previously downloaded encrypted PEM. Same verification, same
      re-storage path.
    """
    from security.encryption import decrypt_private_key, encrypt_private_key
    from utils.key_codec import load_pem_bytes, store_pem_bytes
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend

    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)

    if not ca.offline:
        return error_response('CA is not offline', 409)

    mode = ca.offline_mode or 'password_protected'

    # Detect transport: multipart for file upload, JSON otherwise.
    if request.content_type and request.content_type.startswith('multipart/'):
        password = (request.form.get('password') or '').strip()
        upload = request.files.get('key_file')
    else:
        body = request.get_json(silent=True) or {}
        password = (body.get('password') or '').strip()
        upload = None

    if not password:
        return error_response('Password is required', 400)

    # Obtain the encrypted PEM bytes
    try:
        if mode == 'password_protected':
            if not ca.prv:
                return error_response(
                    'CA has no in-DB encrypted key — was it taken offline as '
                    'file_exported? Use the file upload flow.',
                    409
                )
            wrapped = decrypt_private_key(ca.prv)
            encrypted_pem = load_pem_bytes(
                wrapped.encode() if isinstance(wrapped, str) else wrapped,
                context=f"CA {ca_id}"
            )
        else:  # file_exported
            if upload is None:
                return error_response(
                    'Encrypted key file is required (field name: key_file)', 400
                )
            encrypted_pem = upload.read()
            if not encrypted_pem or len(encrypted_pem) > 256 * 1024:
                return error_response('Uploaded key file is empty or too large', 400)
    except Exception as e:
        logger.error(f"restore_ca: failed to load encrypted PEM for CA {ca_id}: {e}")
        return error_response('Failed to read encrypted CA key', 500)

    # Verify password by attempting decryption
    try:
        priv = serialization.load_pem_private_key(
            encrypted_pem, password=password.encode('utf-8'),
            backend=default_backend()
        )
    except (ValueError, TypeError) as e:
        # cryptography raises ValueError on bad password / malformed PEM
        logger.warning(f"restore_ca: password rejected for CA {ca_id}: {e}")
        return error_response('Invalid password or corrupted key file', 401)
    except Exception as e:
        logger.error(f"restore_ca: unexpected error decrypting key for CA {ca_id}: {e}")
        return error_response('Failed to decrypt CA key', 500)

    # Re-serialize unencrypted, re-wrap with master key, store
    try:
        plain_pem = priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        ca.prv = encrypt_private_key(store_pem_bytes(plain_pem))
        ca.offline = False
        ca.offline_mode = None
        ca.offline_reason = None
        db.session.commit()

        AuditService.log_action(
            action='ca_restored',
            resource_type='ca',
            resource_id=ca_id,
            resource_name=ca.descr,
            details=f"CA restored from offline (mode={mode})",
            success=True
        )
        return success_response(data=ca.to_dict(), message='CA restored to online state')
    except Exception as e:
        db.session.rollback()
        logger.error(f"restore_ca: DB write failed for CA {ca_id}: {e}")
        return error_response('Failed to restore CA', 500)

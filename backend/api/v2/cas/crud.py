"""
CAs CRUD Operations
"""

from . import bp
from flask import g, request
import base64
import ipaddress
import re
import logging
from datetime import datetime, timezone

from auth.unified import require_auth, has_permission
from utils.pagination import parse_request_pagination
from utils.response import success_response, error_response, created_response, no_content_response
from utils.pagination import paginate
from utils.dn_validation import validate_dn_field, validate_dn
from utils.protocol_url import get_protocol_base_url
from utils.decorators import require_json_body
from utils.validity import coerce_validity_days
from utils.db_transaction import safe_commit
import fips_mode
from fips_mode import FipsRestricted
from services.ca_service import CAService
from services.audit_service import AuditService
import compliance_profiles
from services.ca.signature_scheme import ca_pss_refusal, normalize_signature_scheme, pss_refusal
from services.deletion_blockers import ca_deletion_blockers, first_blocker
from services.notification_service import NotificationService
from utils.ca_profile import (
    default_digest_for_key_type,
    resolve_digest,
    validate_ca_key_usage,
    normalize_ca_eku,
    default_key_usage_for_ca,
)
from models import Certificate, CA, db
from models.hsm import HsmKey, HsmProvider
from services.hsm import HsmService
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import dsa
from utils import key_algorithms, notices as notices_mod
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
# Same ceiling as validityYears (50 years)
_MAX_CA_VALIDITY_DAYS = 50 * 365
# HSM key algorithm -> the key_type resolve_digest picks 'auto' from
_HSM_ALGORITHM_KEY_TYPE = {
    'RSA-2048': '2048', 'RSA-3072': '3072', 'RSA-4096': '4096',
    'EC-P256': 'prime256v1', 'EC-P384': 'secp384r1', 'EC-P521': 'secp521r1',
    'EC-BP256': 'brainpoolP256r1', 'EC-BP384': 'brainpoolP384r1', 'EC-BP512': 'brainpoolP512r1',
}
_MAX_OID_LEN = 100
_MAX_NAME_CONSTRAINTS = 32
_MAX_NAME_CONSTRAINT_LEN = 255
_MAX_SIA_URLS = 8
_MAX_PATH_LENGTH = 32
_OID_RE = re.compile(r'^[0-2](\.\d+)+$')


_CA_KEY_FAMILIES = {'rsa': 'RSA', 'ecdsa': 'EC', 'ec': 'EC', 'ml-dsa': 'ML-DSA', 'mldsa': 'ML-DSA'}


def _size_names(alg, size) -> bool:
    """Whether keySize *size* (bits, curve or level, int or text) names *alg*."""
    if isinstance(size, bool):
        return False
    text = str(size).strip()
    return (key_algorithms.get(text) is alg or text == alg.param
            or (alg.key_size is not None and text == str(alg.key_size)))


def _blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def _resolve_local_key_type(data):
    """(TrustStore key type, error) for a locally generated CA key.

    keyType is accepted as an alias of keyAlgo; a value that names no usable
    key is an error, only a request without any key field gets RSA-2048.
    """
    algo, alias, size = data.get('keyAlgo'), data.get('keyType'), data.get('keySize')
    if _blank(algo) and _blank(alias):
        if _blank(size):
            return '2048', None
        return None, 'keySize requires keyAlgo (RSA, ECDSA or ML-DSA)'
    names = [v for v in (algo, alias) if not _blank(v)]
    if not all(isinstance(v, str) for v in names):
        return None, 'keyAlgo must be a string (RSA, ECDSA or ML-DSA)'
    # A full label ('RSA-4096', 'EC-P384', '2048') names size and curve at once
    labels = {key_algorithms.get(v) for v in names}
    if len(labels) == 1 and None not in labels:
        alg = labels.pop()
        if alg.trust_store_id:
            if not _blank(size) and not _size_names(alg, size):
                return None, 'keyAlgo and keySize name different keys'
            return alg.trust_store_id, None
    families = {_CA_KEY_FAMILIES.get(v.strip().lower()) for v in names}
    if None in families:
        return None, f'Unsupported keyAlgo {names[0]!r}: a CA key is RSA, ECDSA (EC) or ML-DSA'
    if len(families) > 1:
        return None, 'keyAlgo and keyType name different algorithms'
    family = families.pop()
    choices = [a for a in key_algorithms.algorithms(family) if a.trust_store_id]
    if not choices:
        return None, f'{family} keys are not available on this build: they need OpenSSL 3.5 or later'
    if _blank(size) and family != 'ML-DSA':
        return choices[0].trust_store_id, None
    alg = None
    if isinstance(size, (int, str)) and not _blank(size):
        alg = next((a for a in choices if _size_names(a, size)), None)
    if alg is None:
        if family == 'RSA':
            return None, f'RSA key size must be one of {[a.key_size for a in choices]}'
        if family == 'ML-DSA':
            return None, f'ML-DSA key size must be one of {[int(a.param) for a in choices]}'
        return None, f'ECDSA curve must be one of {[a.trust_store_id for a in choices]}'
    return alg.trust_store_id, None


def _public_key_summary(public_key):
    """(keyAlgo, keySize) of a CA public key, as the detail view reports them."""
    family = key_algorithms.family_for_public_key(public_key)
    if family in ('RSA', 'EC'):
        return family, public_key.key_size
    alg = key_algorithms.get(key_algorithms.label_for_public_key(public_key))
    if alg is not None:
        return alg.display, alg.key_size
    if isinstance(public_key, dsa.DSAPublicKey):
        return 'DSA', public_key.key_size
    return 'Unknown', getattr(public_key, 'key_size', None)


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


_NAME_CONSTRAINT_TYPES = ('dns', 'ip', 'email')

# One or more LDH labels ("host", "host.example.com"); no leading/trailing dot,
# no empty labels, no scheme, path, space, underscore or wildcard.
_LDH_LABELS_RE = re.compile(
    r'^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?'
    r'(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$'
)

# RFC 5322 dot-atom local part: atext runs joined by single dots, no leading,
# trailing or doubled dot. Quoted local parts are deliberately unsupported.
_EMAIL_LOCAL_RE = re.compile(
    r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
    r"(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*$"
)


def _valid_dns_name_constraint(v):
    """RFC 5280 §4.2.1.10 dnsName constraint: plain LDH labels. A bare
    "example.com" already covers the host and every subdomain; RFC 5280 has no
    leading-dot form for dnsName (OpenSSL rejects it), so neither do we."""
    return _LDH_LABELS_RE.match(v) is not None


def _valid_email_name_constraint(v):
    """RFC 5280 §4.2.1.10 rfc822Name constraint: a full ``local@domain`` mailbox,
    a bare ``domain`` (mailboxes on that host), or ``.domain`` (the domain
    subtree). The leading dot IS valid here, unlike dnsName."""
    if '@' in v:
        local, _, domain = v.partition('@')
        if '@' in domain or len(local) > 64 or not _EMAIL_LOCAL_RE.match(local):
            return False
        return _LDH_LABELS_RE.match(domain) is not None
    return _LDH_LABELS_RE.match(v[1:] if v.startswith('.') else v) is not None


def _normalize_name_constraints(value, field):
    """Validate a NameConstraints subtree list for CA creation.

    Accepts a list of ``{"type": "dns|ip|email", "value": "..."}`` objects, the
    shape stored on the CA and consumed by
    ``ConstraintsMixin._build_general_subtrees``. Returns
    ``(list_or_none, error_str_or_none)``. Entries are rejected rather than
    silently skipped: a dropped entry would yield a CA with no NameConstraints
    extension at all, which is the opposite of what the caller asked for.
    """
    if value is None:
        return None, None
    if not isinstance(value, list):
        return None, f'{field} must be an array of {{type, value}} objects'
    if len(value) > _MAX_NAME_CONSTRAINTS:
        return None, f'{field} accepts at most {_MAX_NAME_CONSTRAINTS} entries'
    cleaned = []
    for item in value:
        if not isinstance(item, dict):
            return None, (
                f'{field} entries must be objects like '
                '{"type": "dns|ip|email", "value": "example.com"}'
            )
        ctype = str(item.get('type', '')).strip().lower()
        cval = item.get('value', '')
        if not isinstance(cval, str):
            return None, f'{field} entry value must be a string'
        cval = cval.strip()
        if ctype not in _NAME_CONSTRAINT_TYPES:
            return None, f'{field} entry type must be one of dns, ip, email'
        if not cval:
            return None, f'{field} entry value must not be empty'
        if len(cval) > _MAX_NAME_CONSTRAINT_LEN:
            return None, (
                f'{field} entry value too long (max {_MAX_NAME_CONSTRAINT_LEN} chars)'
            )
        if ctype == 'ip':
            try:
                # Same call the extension builder makes; a host with mask bits
                # set (e.g. 10.0.0.5/8) raises here rather than 500ing later.
                ipaddress.ip_network(cval)
            except ValueError:
                return None, (
                    f'{field} entry "{cval}" is not a valid IP network '
                    '(e.g. 10.0.0.0/8 or 2001:db8::/32)'
                )
        elif ctype in ('dns', 'email'):
            # These land verbatim in the critical, permanent extension. An
            # unvalidated value (URL, path, wildcard, non-ASCII) makes the CA
            # either unusable (permitted subtree nothing matches) or the
            # constraint inert (excluded subtree nothing matches).
            if not cval.isascii():
                return None, (
                    f'{field} entry "{cval}" must be ASCII '
                    '(IDNA-encode internationalized domains)'
                )
            ok = (_valid_dns_name_constraint(cval) if ctype == 'dns'
                  else _valid_email_name_constraint(cval))
            if not ok:
                return None, (
                    f'{field} entry "{cval}" is not a valid {ctype} name constraint'
                    + (' (e.g. example.com or .example.com)' if ctype == 'dns'
                       else ' (e.g. user@example.com, example.com, or .example.com)')
                )
        cleaned.append({'type': ctype, 'value': cval})
    return cleaned, None


@bp.route('/api/v2/cas', methods=['GET'])
@require_auth(['read:cas'])
def list_cas():
    """
    List CAs for current user
    Query: ?page=1&per_page=20&search=xxx&type=xxx
    """
    page, per_page = parse_request_pagination(default_per_page=20)
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

        # Registry sizes and curves only: no huge RSA keys, no unknown curves
        key_type, key_err = _resolve_local_key_type(data)
        if key_err:
            return error_response(key_err, 400)

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
        # A locally generated key FIPS mode excludes is refused as such, as on the issue path
        local_alg = None if modes else key_algorithms.get(key_type)
        if local_alg is not None and not local_alg.fips_approved:
            fips_mode.refuse(f'{local_alg.display} keys')

        # Resolve parent CA for intermediate CAs
        caref = None
        if data.get('type') == 'intermediate' and data.get('parentCAId'):
            parent_ca = db.session.get(CA, int(data['parentCAId']))
            if not parent_ca:
                return error_response('Parent CA not found', 400)
            if not parent_ca.has_private_key:
                return error_response('Parent CA has no private key', 400)
            if not parent_ca.crt:
                return error_response('Parent CA is awaiting its certificate', 400)
            if parent_ca.revoked_in_chain:
                return error_response('Parent CA is revoked and can no longer sign', 400)
            # The parent must be inside its own validity window
            parent_cert = x509.load_pem_x509_certificate(
                base64.b64decode(parent_ca.crt), default_backend()
            )
            from utils.ca_signing_window import check_issuer_window
            try:
                check_issuer_window(parent_cert)
            except ValueError as e:
                return error_response(str(e).replace('Issuing CA certificate', 'Parent CA certificate'), 400)
            caref = parent_ca.refid

        username = g.user.username if hasattr(g, 'user') else (g.current_user.username if hasattr(g, 'current_user') else 'system')

        # Validate validity period — cap at 50 years (CA/B Forum max for roots
        # is 25y; leave headroom for offline roots while preventing unbounded
        # values like 10000 years). Use explicit None check so 0 is rejected
        # (not silently replaced by the default).
        # validityDays, when given, takes precedence for a CA that does not
        # last a whole number of years (#378); same 50-year ceiling.
        raw_days = data.get('validityDays')
        if raw_days is not None and raw_days != '':
            validity_days = coerce_validity_days(raw_days)
            if validity_days is None or not 1 <= validity_days <= _MAX_CA_VALIDITY_DAYS:
                return error_response(
                    f'validityDays must be an integer between 1 and {_MAX_CA_VALIDITY_DAYS}', 400)
        else:
            raw_validity = data.get('validityYears')
            if raw_validity is None or raw_validity == '':
                validity_years = 10
            else:
                # A boolean or a fractional year is refused, as for validityDays
                validity_years = coerce_validity_days(raw_validity)
                if validity_years is None:
                    return error_response('Invalid validityYears', 400)
            if not 1 <= validity_years <= 50:
                return error_response('validityYears must be between 1 and 50', 400)
            validity_days = validity_years * 365

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

        # Validate NameConstraints subtree lists ({type, value} objects, the
        # shape stored on the CA and turned into the critical extension).
        nc_permitted, nc_err = _normalize_name_constraints(
            data.get('nameConstraintsPermitted'), 'nameConstraintsPermitted'
        )
        if nc_err:
            return error_response(nc_err, 400)
        nc_excluded, nc_err = _normalize_name_constraints(
            data.get('nameConstraintsExcluded'), 'nameConstraintsExcluded'
        )
        if nc_err:
            return error_response(nc_err, 400)
        if (nc_permitted or nc_excluded) and data.get('type') == 'external':
            return error_response(
                'Name constraints cannot be set on an external-CSR CA; they '
                'are applied by the signing CA when it issues the certificate',
                400,
            )

        # Validate SIA URLs (same rules as AIA/CDP/OCSP)
        sia_urls_validated, sia_err = _normalize_url_list(data.get('siaUrls'), 'siaUrls')
        if sia_err:
            return error_response(sia_err, 400)

        is_root = not caref
        raw_digest = data.get('digest') or data.get('hashAlgorithm')
        # 'auto' follows the key: for an HSM key that is the HSM algorithm,
        # not the local key_type default (#366).
        if hsm_key_id:
            hsm_key = db.session.get(HsmKey, int(hsm_key_id)) if str(hsm_key_id).isdigit() else None
            hsm_key_algorithm_for_digest = hsm_key.algorithm if hsm_key else None
        else:
            hsm_key_algorithm_for_digest = hsm_key_algorithm
        digest_key_type = _HSM_ALGORITHM_KEY_TYPE.get(hsm_key_algorithm_for_digest, key_type)
        if hsm_key_id or hsm_provider_id:
            if hsm_key_id:
                chosen_provider = hsm_key.provider if hsm_key else None
            else:
                chosen_provider = (db.session.get(HsmProvider, int(hsm_provider_id))
                                   if str(hsm_provider_id).isdigit() else None)
            brainpool_refusal = (HsmService.brainpool_refusal(chosen_provider.type, hsm_key_algorithm_for_digest)
                                 if chosen_provider else None)
            if brainpool_refusal:
                return error_response(brainpool_refusal, 400)
        # The parent signs an intermediate: its key decides whether a digest applies,
        # and 'auto' follows the child key only when both keys take one.
        signer_key_type = digest_key_type
        signer_default = None
        if caref and data.get('type') != 'external':
            parent_pub = parent_cert.public_key()
            if (not key_algorithms.needs_digest(parent_pub)
                    or default_digest_for_key_type(digest_key_type) is None):
                parent_alg = key_algorithms.get(key_algorithms.label_for_public_key(parent_pub))
                if parent_alg is not None:
                    signer_key_type = parent_alg.trust_store_id or parent_alg.label
                else:
                    # Outside the registry (RSA-8192, DSA): takes a digest, its own by default
                    signer_key_type = None
                    signer_default = key_algorithms.default_digest_for_key(parent_pub)
        if signer_key_type is None and str(raw_digest or 'auto').strip().lower() == 'auto':
            digest, digest_err = signer_default, None
        else:
            digest, digest_err = resolve_digest(raw_digest, signer_key_type)
        if digest_err:
            return error_response(digest_err, 400)
        digest_explicit = digest is not None and str(raw_digest or 'auto').strip().lower() != 'auto'
        notices = []
        if digest is None and str(raw_digest or 'auto').strip().lower() != 'auto':
            notices.append(notices_mod.digest_ignored(
                raw_digest, key_algorithms.normalize_label(signer_key_type) or signer_key_type))

        signature_scheme, scheme_err = normalize_signature_scheme(data.get('signatureScheme'))
        if scheme_err:
            return error_response(scheme_err, 400)
        if signature_scheme == 'pss':
            hsm_type = None
            if hsm_key_id:
                hsm_type = hsm_key.provider.type if hsm_key and hsm_key.provider else 'unknown'
            elif hsm_provider_id:
                provider = db.session.get(HsmProvider, int(hsm_provider_id))
                hsm_type = provider.type if provider else 'unknown'
            refusal = pss_refusal(str(digest_key_type).isdigit(), hsm_type)
            if refusal:
                return error_response(refusal, 400)

        # Absent means the instance default; an explicit null or '' means no profile
        if 'complianceProfile' in data or 'compliance_profile' in data:
            compliance_profile, profile_err = compliance_profiles.normalize(
                data.get('complianceProfile', data.get('compliance_profile')))
            if profile_err:
                return error_response(profile_err, 400)
        else:
            compliance_profile = compliance_profiles.default_profile()

        raw_ku = data.get('keyUsage')
        if raw_ku is None and data.get('key_usage') is not None:
            raw_ku = data.get('key_usage')
        if raw_ku is None:
            key_usage = default_key_usage_for_ca(is_root, digest_key_type)
        else:
            ku_err = validate_ca_key_usage(raw_ku)
            if ku_err:
                return error_response(ku_err, 400)
            key_usage = list(dict.fromkeys(s.strip() for s in raw_ku if isinstance(s, str)))

        # External-CSR mode (#298): generate the key pair + CA CSR now, the
        # certificate is installed later via POST /cas/<id>/certificate.
        # validityYears/parentCAId/EKU/constraints are decided by the external
        # signer and deliberately not consumed here.
        if data.get('type') == 'external':
            ca = CAService.create_external_ca(
                descr=description,
                dn=dn,
                key_type=key_type,
                digest=digest,
                username=username,
                path_length=path_length,
                key_usage=key_usage if raw_ku is not None else None,
                hsm_provider_id=int(hsm_provider_id) if hsm_provider_id else None,
                hsm_key_id=int(hsm_key_id) if hsm_key_id else None,
                hsm_key_label=hsm_key_label,
                hsm_key_algorithm=hsm_key_algorithm,
                named_urls=bool(data.get('namedUrls')),
                signature_scheme=signature_scheme,
                compliance_profile=compliance_profile,
            )
            ca_dict = ca.to_dict()
            from services.webhook_service import emit_ca_created
            emit_ca_created(ca_dict, actor=username)
            return created_response(
                data=ca_dict,
                message='CA created, awaiting certificate from external CA',
                meta=notices_mod.meta_with_notices(notices),
            )

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
            validity_days=validity_days,
            digest=digest,
            caref=caref,
            username=username,
            path_length=path_length,
            name_constraints_permitted=nc_permitted,
            name_constraints_excluded=nc_excluded,
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
            named_urls=bool(data.get('namedUrls')),
            # 'auto' (or nothing) is no choice: it yields to the policies
            digest_explicit=digest_explicit,
            signature_scheme=signature_scheme,
            compliance_profile=compliance_profile,
        )

        # Single lifecycle event — bus fans out to webhook + email + WebSocket.
        # Snapshot before emit: subscribers may commit and expire the instance.
        ca_dict = ca.to_dict()
        from services.webhook_service import emit_ca_created
        emit_ca_created(ca_dict, actor=username)

        return created_response(
            data=ca_dict,
            message='CA created successfully',
            meta=notices_mod.meta_with_notices(notices),
        )
    except FipsRestricted:
        raise
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
        fingerprints = details.get('fingerprints', {})
        key_algo, key_size = _public_key_summary(x509.load_pem_x509_certificate(
            base64.b64decode(ca.crt), default_backend()).public_key())
        # Merge details into response
        ca_data.update({
            'commonName': details.get('subject', {}).get('CN', ca.descr),
            'org': details.get('subject', {}).get('O', ''),
            'country': details.get('subject', {}).get('C', ''),
            'keyAlgo': key_algo,
            'keySize': key_size,
            'fingerprint': fingerprints.get('sha256', ''),
            'thumbprint_sha256': fingerprints.get('sha256', ''),
            'thumbprint_sha1': fingerprints.get('sha1', ''),
            'signature_algorithm': details.get('signature_algorithm'),
            'crlStatus': crl_status,
            'nextCrlUpdate': next_crl_update
        })
        from utils.serial_format import format_serial_colon
        serial_raw = details.get('serial_number')
        if serial_raw:
            ca_data['serial_number'] = format_serial_colon(serial_raw)
    except Exception:
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
    """

    ca = db.session.get(CA, ca_id)
    if not ca:
        return error_response('CA not found', 404)

    data = request.json or {}

    # A pending external-CSR CA has no certificate: CDP/OCSP would advertise
    # services it cannot serve.
    if ca.is_pending and (data.get('cdp_enabled') or data.get('ocsp_enabled')):
        return error_response(
            'Cannot enable CDP/OCSP on a CA awaiting its certificate', 400
        )

    # Checked before any field changes: a refused scheme leaves the CA as it was
    new_scheme = None
    if 'signatureScheme' in data or 'signature_scheme' in data:
        raw_scheme = data.get('signatureScheme', data.get('signature_scheme'))
        # A blank value names no scheme: it must not switch a PSS CA back to v1.5
        if raw_scheme in (None, ''):
            return error_response('signatureScheme must be pkcs1v15 or pss', 400)
        new_scheme, scheme_err = normalize_signature_scheme(raw_scheme)
        if scheme_err:
            return error_response(scheme_err, 400)
        if new_scheme == 'pss' and ca.signature_scheme != 'pss':
            refusal = ca_pss_refusal(ca)
            if refusal:
                return error_response(refusal, 400)

    # Same rule: validated before any mutation; null or '' removes the profile.
    # It binds future issuance only, nothing already issued is re-checked.
    new_profile, profile_changed = None, False
    if 'complianceProfile' in data or 'compliance_profile' in data:
        new_profile, profile_err = compliance_profiles.normalize(
            data.get('complianceProfile', data.get('compliance_profile')))
        if profile_err:
            return error_response(profile_err, 400)
        profile_changed = True

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
    if 'namedUrls' in data:
        want = bool(data['namedUrls'])
        if not want and ca.url_slug:
            return error_response('Named URLs cannot be disabled once enabled', 400)
        if want and not ca.url_slug:
            from services.ca.ca_creation import CACreationMixin
            slug = CACreationMixin._unique_url_slug(ca.descr)
            if not slug:
                return error_response('Cannot derive a URL slug from the CA name', 400)
            old_ref = ca.refid or ''
            ca.url_slug = slug
            # Re-materialize the auto-generated protocol URLs so new issuance
            # embeds the named form. Custom URLs are left untouched ({ca_refid}
            # templates resolve through url_ref at issuance and follow the slug).
            if old_ref:
                ca.set_cdp_urls([u.replace(f'/cdp/{old_ref}.crl', f'/cdp/{slug}.crl')
                                 for u in ca.get_cdp_urls()])
                ca.set_aia_urls([u.replace(f'/ca/{old_ref}.cer', f'/ca/{slug}.cer')
                                 for u in ca.get_aia_urls()])
            changed.append('namedUrls')
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
            ca.set_cdp_urls([f"{base_url}/cdp/{ca.url_ref}.crl"])
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
            ca.set_aia_urls([f"{base_url}/ca/{ca.url_ref}.cer"])
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
    # Offline state is mutated EXCLUSIVELY through the dedicated /offline and
    # /restore endpoints (they enforce password complexity + real key
    # encryption / decryption). Silently ignore any attempt to set
    # offline/offline_reason/offline_mode through the generic update path.
    # Only what the CA signs from now on: issued certificates keep their signature
    old_scheme = ca.signature_scheme or 'pkcs1v15'
    if new_scheme is not None and new_scheme != old_scheme:
        ca.signature_scheme = new_scheme
        changed.append(f'signature_scheme {old_scheme} -> {new_scheme}')
    if profile_changed and new_profile != ca.compliance_profile:
        changed.append(f'compliance_profile {ca.compliance_profile or "none"} -> '
                       f'{new_profile or "none"}')
        ca.compliance_profile = new_profile
    for forbidden in ('offline', 'offline_reason', 'offline_mode'):
        if forbidden in data:
            logger.warning(
                "Ignoring attempt to mutate '%s' through PUT /api/v2/cas/%s "
                "(use /offline or /restore instead)",
                forbidden, ca_id
            )

    try:
        db.session.commit()
        if any(c.startswith('signature_scheme ') for c in changed):
            # A cached OCSP answer would keep the previous scheme until it expires
            from services.ocsp_service import OCSPService
            OCSPService.invalidate_ca_cache(ca_id)

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

    ca = db.session.get(CA, ca_id)
    if not ca:
        return error_response('CA not found', 404)

    ca_name = ca.descr or f'CA #{ca_id}'

    blocker = first_blocker(ca_deletion_blockers(ca))
    if blocker:
        return error_response(blocker.message, blocker.status)

    try:
        username = g.current_user.username if hasattr(g, 'current_user') else 'system'
        # Delegate to the service so the CA cert/key files on disk are
        # unlinked and its dependent rows purged along with the DB row
        # instead of leaving them orphaned (audit log and webhook are
        # emitted by the service itself).
        CAService.delete_ca(ca_id=ca_id, username=username)

        return no_content_response()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete CA: {e}")
        return error_response('Failed to delete CA', 500)


def announce_ca_revoked(ca, username, reason):
    """Webhook and WebSocket notice of a CA revocation; returns the CA's
    snapshot, taken before the emit (subscribers may commit)."""
    ca_dict = ca.to_dict()
    from services.webhook_service import emit_ca_updated
    emit_ca_updated(ca_dict, actor=username, changes={'revoked': True, 'reason': reason})
    try:
        on_ca_updated(ca.id, ca_dict.get('descr'), {'revoked': True, 'reason': reason})
    except Exception:
        pass
    return ca_dict


@bp.route('/api/v2/cas/<int:ca_id>/revoke', methods=['POST'])
@require_auth(['write:cas'])
def revoke_ca(ca_id):
    """Revoke an intermediate CA from its parent (#343).

    Body (JSON): ``{reason: <RFC 5280 reason name>, invalidity_date?: ISO 8601}``.
    The serial is published on the parent's CRL and answered ``revoked`` by
    the parent's OCSP responder; the CA can no longer sign. Permanent.
    """
    from datetime import timedelta
    from utils.datetime_utils import utc_now, to_naive_utc
    from utils.revocation_reasons import normalize_revocation_reason, invalid_reason_message

    ca = db.session.get(CA, ca_id)
    if not ca:
        return error_response('CA not found', 404)
    if ca.revoked:
        return error_response('CA is already revoked', 409)

    # A malformed body must not become an "unspecified" revocation
    data = request.get_json(silent=True)
    if data is None:
        if request.get_data(cache=True).strip():
            return error_response('Invalid JSON body', 400)
        data = {}
    if not isinstance(data, dict):
        return error_response('JSON body must be an object', 400)
    reason = normalize_revocation_reason(data.get('reason', 'unspecified'))
    if reason is None:
        return error_response(invalid_reason_message(data.get('reason')), 400)

    invalidity_at = None
    invalidity_raw = data.get('invalidity_date') or data.get('invalidity_at')
    if invalidity_raw:
        try:
            raw = str(invalidity_raw).strip().replace('Z', '+00:00')
            invalidity_at = to_naive_utc(datetime.fromisoformat(raw))
        except (ValueError, TypeError, OverflowError) as e:
            return error_response(f'Invalid invalidity_date: {e}', 400)
        if invalidity_at > utc_now() + timedelta(minutes=5):
            return error_response('invalidity_date cannot be in the future', 400)

    # Refused at once when no revocation could honour it, then queued when a
    # policy requires approval for revocations under the parent (fail closed).
    # A CA the parent already revoked is left to revoke_ca (409, flag restored)
    if not ca.is_revoked:
        try:
            parent = CAService.revocation_issuer(ca, reason)
        except ValueError as e:
            return error_response(str(e), 400)
        try:
            from services.approval_gate import approval_payload, queue_ca_revocation
            policy, approval = queue_ca_revocation(
                g.current_user, ca, parent, reason=reason, invalidity_at=invalidity_at,
                comment=data.get('approval_comment'))
        except Exception as e:
            logger.error(f"Policy evaluation failed for revocation of CA {ca_id}: {e}", exc_info=True)
            return error_response('Policy evaluation failed; the CA was not revoked', 500)
        if approval is not None:
            return success_response(data=approval_payload(policy, approval),
                                    message='CA revocation submitted for approval')

    username = g.current_user.username if hasattr(g, 'current_user') else 'system'
    try:
        ca, warnings = CAService.revoke_ca(
            ca_id, reason=reason, username=username, invalidity_at=invalidity_at
        )
    except ValueError as e:
        db.session.rollback()
        # A CA already revoked, by its flag or by the parent's record, is a conflict, not a bad request
        return error_response(str(e), 409 if 'already revoked' in str(e) else 400)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to revoke CA {ca_id}: {e}", exc_info=True)
        return error_response('Failed to revoke CA', 500)

    ca_dict = announce_ca_revoked(ca, username, reason)
    message = 'CA revoked'
    if warnings:
        message = 'CA revoked, but not fully published: ' + ' '.join(warnings)
    return success_response(data={**ca_dict, 'warnings': warnings,
                                  'warning_codes': list(getattr(ca, 'revocation_warning_codes', []) or [])},
                            message=message)


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

    ca = db.session.get(CA, ca_id)
    if not ca:
        return error_response('CA not found', 404)

    if ca.offline:
        return error_response('CA is already offline', 409)

    if ca.is_revoked:
        # Offline would hide the revocation in the tree; a revoked CA has
        # nothing left to protect from use (review of #343)
        return error_response('A revoked CA is not taken offline: it stays visibly revoked', 409)

    if ca.is_pending:
        return error_response(
            'Cannot take a pending CA offline: install its certificate first', 409
        )

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
    # file_exported hands the key to the caller: same gate as a CA key export
    if mode == 'file_exported' and not has_permission('read:private_keys', g.permissions):
        return error_response(
            'Exporting the CA key to a file requires the read:private_keys permission', 403)

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

    ca = db.session.get(CA, ca_id)
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
                    'CA has no in-DB encrypted key. Was it taken offline as '
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

    # The uploaded key must be the CA certificate's own, as the import
    # route already requires: a foreign key would put the CA back online
    # signing certificates nothing can verify
    if ca.crt:
        from utils.cert_issuer import private_key_matches
        try:
            ca_cert_obj = x509.load_pem_x509_certificate(
                base64.b64decode(ca.crt), default_backend())
        except Exception:
            ca_cert_obj = None
        if ca_cert_obj is not None and not private_key_matches(priv, ca_cert_obj):
            return error_response('The key file is not the private key of this CA certificate', 400)

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

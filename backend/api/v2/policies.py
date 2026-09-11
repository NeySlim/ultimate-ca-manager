"""
Certificate Policy API - UCM
Manages certificate policies and approval workflows.
"""
from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from models import db, CA, Certificate
from models.policy import CertificatePolicy, ApprovalRequest
from models.certificate_template import CertificateTemplate
from datetime import datetime, timedelta
import json
import logging
import base64
import uuid
from utils.datetime_utils import cert_not_before, utc_now
from utils.leaf_key_usage import key_usage_for_key
from services.audit_service import AuditService
from security.encryption import encrypt_private_key
from services.template_service import compute_template_overrides
from utils.key_codec import private_key_to_pem
from utils.eku_validation import (add_ocsp_nocheck_if_responder, normalize_extra_ekus,
                                  to_object_identifiers, merge_eku_lists)
from utils.cert_profiles import profile_for

logger = logging.getLogger(__name__)

bp = Blueprint('policies_pro', __name__)


# Hard cap mirrored from utils.cert_validation.MAX_VALIDITY_DAYS
_MAX_VALIDITY_DAYS = 3650


from utils.signing_hash import signing_hash_for
from utils.x509_aki import authority_key_identifier_from_issuer


def _user_can_act_on_approval(user, approval):
    """RBAC + group-membership check for approve/reject.

    If the request's policy pins an approval_group_id, the acting user MUST
    be a member of that group (admins keep their override). Without this
    check, any user with write:approvals can vote on any request, defeating
    the whole point of approval_group_id.

    Returns (allowed: bool, reason: Optional[str]).
    """
    if user is None:
        return False, "Authentication required"
    # Admin can always act
    if getattr(user, 'role', None) == 'admin':
        return True, None
    policy = approval.policy
    if policy is None or not policy.approval_group_id:
        # No group restriction → write:approvals already enforced by decorator
        return True, None
    try:
        from models.group import GroupMember
        is_member = db.session.query(GroupMember.id).filter_by(
            group_id=policy.approval_group_id,
            user_id=user.id,
        ).first() is not None
    except Exception as e:
        logger.error(f"Group membership check failed for user={user.id} approval={approval.id}: {e}")
        return False, "Authorization check failed"
    if not is_member:
        return False, "You are not a member of the required approval group"
    return True, None


def _approval_is_expired(approval):
    """True if the request has an expires_at in the past."""
    if not approval.expires_at:
        return False
    exp = approval.expires_at
    if exp.tzinfo is not None:
        exp = exp.replace(tzinfo=None)
    return exp < utc_now().replace(tzinfo=None)


def _link_approval(approval, certificate_id):
    """Link the approval to the certificate it produced. Only the request
    that finds the sentinel still empty keeps its certificate."""
    claimed = db.session.query(ApprovalRequest).filter(
        ApprovalRequest.id == approval.id,
        ApprovalRequest.certificate_id.is_(None),
    ).update({ApprovalRequest.certificate_id: certificate_id}, synchronize_session=False)
    if claimed != 1:
        db.session.rollback()
        raise RuntimeError('A certificate was already issued for this approval')
    approval.certificate_id = certificate_id
    ok, _err = safe_commit(logger, "Failed to link approval to certificate")
    if not ok:
        raise RuntimeError('Failed to link approval to certificate')


def _close_duplicate_requests(approval, key, target_id):
    """The other pending requests for the same target (another operator
    queued the same signing or renewal) are approved along with this one,
    by this approver. They ride the issuance transaction, so a failed
    issuance leaves them pending, and are linked to the certificate by
    ``_link_duplicates`` once it exists. Returns their ids."""
    from services.approval_gate import resolve_moot_requests
    user = getattr(g, 'current_user', None)
    duplicates = resolve_moot_requests(
        approval.request_type, key, target_id, outcome='approved',
        username=getattr(user, 'username', None) or 'system', user_id=getattr(user, 'id', None),
        reason=f'Approved with request #{approval.id}', commit=False)
    return [dup.id for dup in duplicates]


def _link_duplicates(duplicate_ids, certificate_id):
    """Link the duplicate requests closed with an approval to the
    certificate it produced; committed with the approval's own link."""
    if not duplicate_ids:
        return
    db.session.query(ApprovalRequest).filter(
        ApprovalRequest.id.in_(duplicate_ids),
        ApprovalRequest.certificate_id.is_(None),
    ).update({ApprovalRequest.certificate_id: certificate_id}, synchronize_session=False)


def _issue_approved_csr(approval, data):
    """Sign the stored request an approved 'csr' request names, exactly as
    the Sign CSR route would have."""
    from services.cert_service import CertificateService
    from utils.datetime_utils import utc_isoformat
    cert = db.session.get(Certificate, data.get('csr_id'))
    if cert is None or not cert.csr:
        raise ValueError('The request to sign no longer exists')
    if cert.crt:
        # Signed meanwhile (directly, or through another approval): the
        # approval is closed on the certificate that exists
        _link_approval(approval, cert.id)
        return {'id': cert.id, 'cn': data.get('cn'), 'serial_number': cert.serial_number,
                'valid_from': utc_isoformat(cert.valid_from), 'valid_to': utc_isoformat(cert.valid_to),
                'already_issued': True}
    ca_ref = data.get('ca_id')
    ca = (db.session.get(CA, int(ca_ref)) if isinstance(ca_ref, int) or str(ca_ref).isdecimal()
          else CA.query.filter_by(refid=str(ca_ref)).first())
    if ca is None:
        raise ValueError('The signing CA no longer exists')
    duplicate_ids = _close_duplicate_requests(approval, 'csr_id', cert.id)
    signed = CertificateService.sign_csr(
        cert_id=cert.id, caref=ca.refid,
        validity_days=int(data.get('validity_days') or 365),
        cert_type=data.get('cert_type') or 'server_cert',
        extra_ekus=data.get('extra_ekus'),
        allow_sensitive_ekus=True,
        username=approval.requester.username if approval.requester else 'system',
    )
    if isinstance(signed, CA):
        # An intermediate CA request: the result lives in the CA table, the
        # approval keeps no certificate link
        logger.info(f"CSR {cert.id} signed as CA {signed.id} via approval #{approval.id}")
        return {'id': None, 'ca_id': signed.id, 'cn': data.get('cn'),
                'serial_number': signed.serial_number if hasattr(signed, 'serial_number') else None}
    _link_duplicates(duplicate_ids, signed.id)
    _link_approval(approval, signed.id)
    logger.info(f"CSR {cert.id} signed via approval #{approval.id}")
    return {
        'id': signed.id,
        'cn': data.get('cn'),
        'serial_number': signed.serial_number,
        'valid_from': utc_isoformat(signed.valid_from),
        'valid_to': utc_isoformat(signed.valid_to),
    }


def _issue_approved_renewal(approval, data):
    """Renew the certificate an approved 'renewal' request names, exactly as
    the renew route would have."""
    from services.cert.renewal import renew_certificate_in_place
    from utils.datetime_utils import utc_isoformat
    cert = db.session.get(Certificate, data.get('certificate_id'))
    if cert is None or not cert.crt:
        raise ValueError('The certificate to renew no longer exists')
    if cert.renewed_at and approval.created_at and cert.renewed_at > approval.created_at:
        # Renewed meanwhile: the approval is closed on the renewed certificate
        _link_approval(approval, cert.id)
        return {'id': cert.id, 'cn': data.get('cn'), 'serial_number': cert.serial_number,
                'valid_from': utc_isoformat(cert.valid_from), 'valid_to': utc_isoformat(cert.valid_to),
                'already_issued': True}
    duplicate_ids = _close_duplicate_requests(approval, 'certificate_id', cert.id)
    renew_certificate_in_place(
        cert,
        username=approval.requester.username if approval.requester else 'system',
        actor_user_id=approval.requester_id,
        rekey=True, regenerate_crl=True, trigger='manual',
    )
    _link_duplicates(duplicate_ids, cert.id)
    _link_approval(approval, cert.id)
    logger.info(f"Certificate {cert.id} renewed via approval #{approval.id}")
    return {
        'id': cert.id,
        'cn': data.get('cn'),
        'serial_number': cert.serial_number,
        'valid_from': utc_isoformat(cert.valid_from),
        'valid_to': utc_isoformat(cert.valid_to),
    }


def _issue_approved_certificate(approval):
    """Issue a certificate from an approved request's stored data.
    
    Re-invokes the certificate creation logic using the original request data.
    Returns the certificate dict on success, raises on failure.
    """
    from services.policy_service import PolicyEvaluationService
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, ec
    from cryptography.hazmat.backends import default_backend
    from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID, ExtensionOID
    from utils.datetime_utils import utc_now

    data = PolicyEvaluationService.get_request_data(approval)
    if not data:
        raise ValueError("No request data stored in approval")
    if approval.request_type == 'csr':
        return _issue_approved_csr(approval, data)
    if approval.request_type == 'renewal':
        return _issue_approved_renewal(approval, data)

    # Resolve the template the request was made against (issue #226 semantics:
    # templates govern issuance — KU/EKU, digest, and the defaults for key
    # type / validity). Without this, approved requests silently degraded to
    # the legacy hardcoded profile and produced certs that were NOT what the
    # template promised.
    template = None
    if data.get('template_id'):
        template = db.session.get(CertificateTemplate, data['template_id'])
        if not template:
            raise ValueError(f"Template {data['template_id']} not found")

    # Re-clamp validity at issuance time:
    #   0) template default when the request didn't pick one (digest behaves
    #      the same way — the template's digest is imposed at signing)
    requested_validity = int(data.get('validity_days')
                             or (template.validity_days if template and template.validity_days else 365))
    if requested_validity <= 0:
        requested_validity = 365
    effective_max = _MAX_VALIDITY_DAYS
    try:
        if approval.policy and approval.policy.is_active:
            policy_rules = approval.policy.get_rules() or {}
            policy_max = policy_rules.get('max_validity_days')
            if isinstance(policy_max, int) and policy_max > 0:
                effective_max = min(effective_max, policy_max)
    except Exception as e:
        logger.warning(f"Could not re-evaluate policy at issuance for approval {approval.id}: {e}")
    validity_days = min(requested_validity, effective_max)
    data['validity_days'] = validity_days  # propagate clamp to the rest of the function
    
    ca_ref = data['ca_id']
    ca = (db.session.get(CA, int(ca_ref)) if isinstance(ca_ref, int) or str(ca_ref).isdecimal()
          else CA.query.filter_by(refid=str(ca_ref)).first())
    if not ca:
        raise ValueError(f"CA {data['ca_id']} not found")
    if not ca.has_private_key:
        raise ValueError("CA private key not available")
    if not ca.crt:
        raise ValueError("CA is awaiting its certificate")
    if ca.offline:
        raise ValueError("CA is offline; restore it before issuing")
    if ca.revoked_in_chain:
        raise ValueError("CA is revoked and can no longer issue certificates")

    # Load CA cert and key
    ca_cert_pem = base64.b64decode(ca.crt)
    ca_cert = x509.load_pem_x509_certificate(ca_cert_pem, default_backend())
    from utils.ca_signing_window import check_issuer_window
    check_issuer_window(ca_cert)
    from services.hsm.ca_key_loader import get_ca_signing_key
    ca_key = get_ca_signing_key(ca)
    
    # Generate key pair. The stored request is the raw payload (the approval is
    # created before cert_create fills key params), so this path has to run the
    # same template fill and key parse the direct route does. Without it an EC
    # template with a blank key_size silently fell back to SECP256R1 via the old
    # curve_map default (#226, #318).
    from utils.key_type import parse_issue_key_type, fill_key_params_from_template

    key_type = data.get('key_type') or data.get('keyType')
    key_size = data.get('key_size') or data.get('keySize')
    if template:
        key_type, key_size = fill_key_params_from_template(
            key_type, key_size, template.key_type)
    key_type = key_type or 'RSA'
    key_size = key_size or '2048'

    normalized_key = parse_issue_key_type(key_type, key_size, curve=data.get('curve'))

    # Policy Rules (#335), re-checked at issuance time against every policy in
    # scope (the approving policy included): key type, DNS SAN cap, validity cap.
    from services.policy_service import PolicyViolation
    from utils.san_parse import auto_san_buckets_from_cn as _implicit_sans
    _requested_dns = list(data.get('san_dns') or [])
    _implicit_dns = _implicit_sans(
        data.get('cn') or '', data.get('cert_type', 'server'),
        subject_email=data.get('email'),
    ).get('san_dns') or []
    _policies = PolicyEvaluationService.applicable_policies(
        data['ca_id'], data.get('template_id'), data.get('cn'), _requested_dns)
    _violations, validity_days = PolicyEvaluationService.enforce_rules(
        _policies, key_type=normalized_key,
        dns_name_count=len(set(_requested_dns) | set(_implicit_dns)),
        validity_days=validity_days,
    )
    if _violations:
        raise PolicyViolation('; '.join(_violations))
    data['validity_days'] = validity_days
    EC_CURVES = {
        'prime256v1': ec.SECP256R1(),
        'secp384r1': ec.SECP384R1(),
        'secp521r1': ec.SECP521R1(),
    }
    if normalized_key in EC_CURVES:
        new_key = ec.generate_private_key(EC_CURVES[normalized_key], default_backend())
    else:
        new_key = rsa.generate_private_key(65537, int(normalized_key), default_backend())
    
    # Build subject
    subject_attrs = [x509.NameAttribute(NameOID.COMMON_NAME, data['cn'])]
    for field, oid in [('organization', NameOID.ORGANIZATION_NAME), ('organizational_unit', NameOID.ORGANIZATIONAL_UNIT_NAME),
                       ('country', NameOID.COUNTRY_NAME), ('state', NameOID.STATE_OR_PROVINCE_NAME), ('locality', NameOID.LOCALITY_NAME),
                       ('email', NameOID.EMAIL_ADDRESS)]:
        if data.get(field):
            val = data[field].upper() if field == 'country' else data[field]
            subject_attrs.append(x509.NameAttribute(oid, val))
    
    subject = x509.Name(subject_attrs)
    # validity_days already clamped + propagated above
    validity_days = data['validity_days']
    now = utc_now()

    # CA-chain sanity: validity must not extend past the CA's own certificate
    ca_not_after = ca_cert.not_valid_after_utc.replace(tzinfo=None)
    if now + timedelta(days=validity_days) > ca_not_after:
        raise ValueError(
            f"validity_days exceeds CA expiration ({ca_not_after.isoformat()})")
    
    builder = x509.CertificateBuilder()
    builder = builder.subject_name(subject)
    builder = builder.issuer_name(ca_cert.subject)
    builder = builder.public_key(new_key.public_key())
    builder = builder.serial_number(x509.random_serial_number())
    builder = builder.not_valid_before(cert_not_before())
    builder = builder.not_valid_after(now + timedelta(days=validity_days))
    
    builder = builder.add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    
    # Key Usage / Extended Key Usage.
    # A template's extensions_template is the source of truth for KU/EKU
    # (issue #226); without a template the legacy cert_type profile applies.
    cert_type = data.get('cert_type', 'server')
    tpl_ext = {}
    if template and template.extensions_template:
        try:
            tpl_ext = template.extensions_template
            # tolerate double-encoded JSON from older/import payloads
            for _ in range(2):
                if isinstance(tpl_ext, str):
                    tpl_ext = json.loads(tpl_ext)
            if not isinstance(tpl_ext, dict):
                tpl_ext = {}
        except (ValueError, TypeError):
            tpl_ext = {}

    ku_name_to_flag = {
        'digitalsignature': 'digital_signature',
        'keyencipherment': 'key_encipherment',
        'contentcommitment': 'content_commitment',
        'nonrepudiation': 'content_commitment',
        'dataencipherment': 'data_encipherment',
        'keyagreement': 'key_agreement',
        # keyCertSign / cRLSign are CA bits: never taken from a template
        # onto a leaf (the CSR trunk and SCEP never did)
    }

    # The same profiles as the direct issue path, so an approved request
    # yields the certificate the requester asked for (self-review of #347)
    profile = profile_for(cert_type)
    ku_flags = profile['ku']
    base_ekus = profile['eku']

    tpl_ku = tpl_ext.get('key_usage')
    if isinstance(tpl_ku, list) and tpl_ku:
        mapped = dict.fromkeys(ku_flags, False)
        for name in tpl_ku:
            flag = ku_name_to_flag.get(str(name).lower())
            if flag:
                mapped[flag] = True
        if any(mapped.values()):
            ku_flags = mapped

    tpl_eku = tpl_ext.get('extended_key_usage')
    if isinstance(tpl_eku, list) and tpl_eku:
        tpl_oid_strs, tpl_err = normalize_extra_ekus(tpl_eku)
        if tpl_err:
            raise ValueError(f'Invalid template EKUs: {tpl_err}')
        base_ekus = to_object_identifiers(tpl_oid_strs)

    # extra_ekus of the request, merged on top like the direct path does
    extra_oid_strs, extra_err = normalize_extra_ekus(data.get('extra_ekus'))
    if extra_err:
        raise ValueError(f'Invalid extra_ekus: {extra_err}')
    base_ekus = merge_eku_lists(base_ekus, to_object_identifiers(extra_oid_strs))

    # Same key-type clamp as the direct issue path (#327): no keyEncipherment
    # on an EC key, keyAgreement instead for an S/MIME one.
    builder = builder.add_extension(
        key_usage_for_key(new_key.public_key(), x509.KeyUsage(**ku_flags), base_ekus),
        critical=True,
    )
    if base_ekus:
        builder = builder.add_extension(x509.ExtendedKeyUsage(base_ekus), critical=False)
        builder = add_ocsp_nocheck_if_responder(builder, base_ekus)
    
    # SANs
    from ipaddress import ip_address
    san_list = []
    for dns in data.get('san_dns', []):
        san_list.append(x509.DNSName(dns))
    for ip in data.get('san_ip', []):
        san_list.append(x509.IPAddress(ip_address(ip)))
    for email in data.get('san_email', []):
        san_list.append(x509.RFC822Name(email))
    for uri in data.get('san_uri', []) or []:
        san_list.append(x509.UniformResourceIdentifier(uri))
    if data.get('san_upn'):
        from utils.upn_san import build_upn_other_name, is_valid_upn
        for upn in data['san_upn']:
            if not is_valid_upn(upn):
                raise ValueError(f'Invalid UPN format: {upn}')
            san_list.append(build_upn_other_name(upn))
    
    cn = data['cn']
    from utils.san_parse import auto_san_buckets_from_cn

    implicit = auto_san_buckets_from_cn(cn, cert_type, subject_email=data.get('email'))
    for dns in implicit.get('san_dns') or []:
        if dns not in data.get('san_dns', []):
            san_list.insert(0, x509.DNSName(dns))
    for ip in implicit.get('san_ip') or []:
        if ip not in data.get('san_ip', []):
            san_list.insert(0, x509.IPAddress(ip_address(ip)))
    for email in implicit.get('san_email') or []:
        if email not in data.get('san_email', []):
            san_list.insert(0, x509.RFC822Name(email))
    
    if san_list:
        builder = builder.add_extension(x509.SubjectAlternativeName(san_list), critical=False)
    if data.get('ocsp_must_staple'):
        builder = builder.add_extension(
            x509.TLSFeature([x509.TLSFeatureType.status_request]), critical=False,
        )

    # Enforce the CA chain's NameConstraints (RFC 5280 §4.2.1.10) on the
    # approved subject + SANs before signing.
    from services.trust_store.constraints_mixin import validate_name_constraints
    validate_name_constraints(ca_cert, subject, san_list or None)

    # SKI/AKI
    builder = builder.add_extension(x509.SubjectKeyIdentifier.from_public_key(new_key.public_key()), critical=False)
    builder = builder.add_extension(authority_key_identifier_from_issuer(ca_cert), critical=False)
    
    # CDP/OCSP/CPS
    if ca.cdp_enabled:
        cdp_urls = [url.replace('{ca_refid}', ca.url_ref) for url in ca.get_cdp_urls()]
        if cdp_urls:
            builder = builder.add_extension(x509.CRLDistributionPoints([
                x509.DistributionPoint(full_name=[x509.UniformResourceIdentifier(url)], relative_name=None, reasons=None, crl_issuer=None)
                for url in cdp_urls
            ]), critical=False)
    aia_descs = []
    if ca.ocsp_enabled:
        for uri in ca.get_ocsp_urls():
            aia_descs.append(x509.AccessDescription(x509.oid.AuthorityInformationAccessOID.OCSP, x509.UniformResourceIdentifier(uri)))
    if ca.aia_ca_issuers_enabled:
        for url in ca.get_aia_urls():
            aia_descs.append(x509.AccessDescription(x509.oid.AuthorityInformationAccessOID.CA_ISSUERS, x509.UniformResourceIdentifier(url.replace('{ca_refid}', ca.url_ref))))
    if aia_descs:
        builder = builder.add_extension(x509.AuthorityInformationAccess(aia_descs), critical=False)
    if ca.cps_enabled and ca.cps_uri:
        builder = builder.add_extension(x509.CertificatePolicies([
            x509.PolicyInformation(policy_identifier=x509.ObjectIdentifier(ca.cps_oid or '2.5.29.32.0'), policy_qualifiers=[ca.cps_uri])
        ]), critical=False)
    
    # Sign — honor the template digest when one is used
    from services.trust_store.constants import HASH_ALGORITHMS
    sign_hash = hashes.SHA256()
    if template and template.digest:
        sign_hash = HASH_ALGORITHMS.get(template.digest.lower().strip(), hashes.SHA256())
    new_cert = builder.sign(ca_key, signing_hash_for(ca_key, sign_hash), default_backend())
    # Same CT policy as the direct issue form (raises ValueError when
    # ct_required cannot be met: the approval stays pending with the reason)
    from utils.ct_client import apply_ct_policy
    new_cert, _ = apply_ct_policy(new_cert, ca_cert, ca_key)
    cert_pem = new_cert.public_bytes(serialization.Encoding.PEM).decode('utf-8')
    key_pem = private_key_to_pem(new_key).decode('utf-8')
    
    # Extract SKI/AKI
    cert_ski, cert_aki = None, None
    try:
        ext = new_cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_KEY_IDENTIFIER)
        cert_ski = ext.value.key_identifier.hex(':').upper()
    except Exception:
        pass
    try:
        ext = new_cert.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_KEY_IDENTIFIER)
        if ext.value.key_identifier:
            cert_aki = ext.value.key_identifier.hex(':').upper()
    except Exception:
        pass
    
    # Save to DB — encrypt private key at rest (matches CertificateService.sign_csr), keep the
    # template link and record the issued divergences from its defaults (#258).
    prv_encoded = encrypt_private_key(base64.b64encode(key_pem.encode()).decode())

    # normalized_key is what was actually generated (RSA size or OpenSSL curve
    # name), so it reflects a `curve` override too; compute_template_overrides
    # normalizes it to the template's label form for the divergence check.
    template_overrides = compute_template_overrides(
        template, key_type=normalized_key, validity_days=validity_days,
        digest=template.digest if template else None,
    ) if template else None
    db_cert = Certificate(
        refid=str(uuid.uuid4())[:8],
        descr=data.get('description', data['cn']),
        caref=ca.refid,
        crt=base64.b64encode(cert_pem.encode()).decode(),
        prv=prv_encoded,
        cert_type=cert_type,
        subject=new_cert.subject.rfc4514_string(),
        issuer=new_cert.issuer.rfc4514_string(),
        serial_number=format(new_cert.serial_number, 'x'),
        aki=cert_aki,
        ski=cert_ski,
        valid_from=now,
        valid_to=now + timedelta(days=validity_days),
        san_dns=json.dumps(data.get('san_dns', [])),
        san_ip=json.dumps(data.get('san_ip', [])),
        san_email=json.dumps(data.get('san_email', [])),
        san_uri=json.dumps(data.get('san_uri', []) or []),
        san_upn=json.dumps(data.get('san_upn', []) or []),
        ocsp_must_staple=bool(data.get('ocsp_must_staple')),
        source='approval',
        template_id=template.id if template else None,
        template_overrides=template_overrides,
        created_by=approval.requester.username if approval.requester else 'system'
    )
    db.session.add(db_cert)
    
    # Link approval to issued cert: the id exists only once flushed. Only the
    # request that finds the sentinel still empty may link (and keep) its
    # certificate: two approvers racing on SQLite, which serialises writes
    # but not read-check-write, would otherwise both issue
    db.session.flush()
    claimed = db.session.query(ApprovalRequest).filter(
        ApprovalRequest.id == approval.id,
        ApprovalRequest.certificate_id.is_(None),
    ).update({ApprovalRequest.certificate_id: db_cert.id}, synchronize_session=False)
    if claimed != 1:
        db.session.rollback()
        raise RuntimeError('A certificate was already issued for this approval')
    approval.certificate_id = db_cert.id
    ok, _err = safe_commit(logger, "Failed to link approval to certificate")
    if not ok:
        # The caller (approve_request) treats any exception as a failed
        # issuance; returning the Flask error tuple here used to land it in
        # the JSON response as `certificate`
        raise RuntimeError('Failed to link approval to certificate')
    
    logger.info(f"Certificate CN={data['cn']} issued via approval #{approval.id}")
    
    return {
        'id': db_cert.id,
        'cn': data['cn'],
        'serial_number': db_cert.serial_number,
        'valid_from': now.isoformat(),
        'valid_to': (now + timedelta(days=validity_days)).isoformat(),
    }


# ============ Policy Management ============

@bp.route('/api/v2/policies', methods=['GET'])
@require_auth(['read:policies'])
def list_policies():
    """List all certificate policies"""
    policies = CertificatePolicy.query.order_by(CertificatePolicy.priority).all()
    return success_response(data=[p.to_dict() for p in policies])


@bp.route('/api/v2/policies/<int:policy_id>', methods=['GET'])
@require_auth(['read:policies'])
def get_policy(policy_id):
    """Get policy details"""
    policy = db.get_or_404(CertificatePolicy, policy_id)
    return success_response(data=policy.to_dict())


@bp.route('/api/v2/policies', methods=['POST'])
@require_auth(['write:policies'])
def create_policy():
    """Create new certificate policy"""
    data = request.get_json()
    
    if not data.get('name'):
        return error_response("Policy name is required", 400)
    
    # Check uniqueness
    if CertificatePolicy.query.filter_by(name=data['name']).first():
        return error_response("Policy name already exists", 400)
    
    policy = CertificatePolicy(
        name=data['name'],
        description=data.get('description'),
        policy_type=data.get('policy_type', 'issuance'),
        ca_id=data.get('ca_id'),
        template_id=data.get('template_id'),
        requires_approval=data.get('requires_approval', False),
        approval_group_id=data.get('approval_group_id'),
        min_approvers=data.get('min_approvers', 1),
        notify_on_violation=data.get('notify_on_violation', True),
        is_active=data.get('is_active', True),
        priority=data.get('priority', 100),
        created_by=g.current_user.username if hasattr(g, 'current_user') and g.current_user else None
    )
    
    if data.get('rules'):
        policy.set_rules(data['rules'])
    
    if data.get('notification_emails'):
        policy.notification_emails = json.dumps(data['notification_emails'])
    
    db.session.add(policy)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to create policy: {e}")
        return error_response('Failed to create policy', 500)
    
    AuditService.log_action(
        action='create',
        resource_type='policy',
        resource_id=policy.id,
        resource_name=policy.name,
        details=f'Created policy: {policy.name}',
        success=True
    )
    
    return success_response(data=policy.to_dict(), message="Policy created")


@bp.route('/api/v2/policies/<int:policy_id>', methods=['PUT'])
@require_auth(['write:policies'])
def update_policy(policy_id):
    """Update certificate policy"""
    policy = db.get_or_404(CertificatePolicy, policy_id)
    data = request.get_json()
    
    # Update fields
    if 'name' in data:
        existing = CertificatePolicy.query.filter_by(name=data['name']).first()
        if existing and existing.id != policy_id:
            return error_response("Policy name already exists", 400)
        policy.name = data['name']
    
    if 'description' in data:
        policy.description = data['description']
    if 'policy_type' in data:
        policy.policy_type = data['policy_type']
    if 'ca_id' in data:
        policy.ca_id = data['ca_id']
    if 'template_id' in data:
        policy.template_id = data['template_id']
    if 'requires_approval' in data:
        policy.requires_approval = data['requires_approval']
    if 'approval_group_id' in data:
        policy.approval_group_id = data['approval_group_id']
    if 'min_approvers' in data:
        policy.min_approvers = data['min_approvers']
    if 'notify_on_violation' in data:
        policy.notify_on_violation = data['notify_on_violation']
    if 'is_active' in data:
        policy.is_active = data['is_active']
    if 'priority' in data:
        policy.priority = data['priority']
    if 'rules' in data:
        policy.set_rules(data['rules'])
    if 'notification_emails' in data:
        policy.notification_emails = json.dumps(data['notification_emails'])
    
    ok, _err = safe_commit(logger, "Failed to update policy")
    if not ok:
        return _err
    
    AuditService.log_action(
        action='update',
        resource_type='policy',
        resource_id=policy.id,
        resource_name=policy.name,
        details=f'Updated policy: {policy.name}',
        success=True
    )
    
    return success_response(data=policy.to_dict(), message="Policy updated")


@bp.route('/api/v2/policies/<int:policy_id>', methods=['DELETE'])
@require_auth(['delete:policies'])
def delete_policy(policy_id):
    """Delete certificate policy"""
    policy = db.get_or_404(CertificatePolicy, policy_id)
    
    # Check for pending requests
    pending = ApprovalRequest.query.filter_by(
        policy_id=policy_id,
        status='pending'
    ).count()
    
    if pending > 0:
        return error_response(f"Cannot delete policy with {pending} pending approval requests", 400)
    
    try:
        # Clean up completed/rejected approval requests
        ApprovalRequest.query.filter_by(policy_id=policy_id).delete()
        
        policy_name = policy.name
        db.session.delete(policy)
        db.session.commit()
        
        AuditService.log_action(
            action='delete',
            resource_type='policy',
            resource_id=policy_id,
            resource_name=policy_name,
            details=f'Deleted policy: {policy_name}',
            success=True
        )
        
        return success_response(message="Policy deleted")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete policy {policy_id}: {e}")
        return error_response('Failed to delete policy', 500)


@bp.route('/api/v2/policies/<int:policy_id>/toggle', methods=['POST'])
@require_auth(['write:policies'])
def toggle_policy(policy_id):
    """Enable/disable policy"""
    policy = db.get_or_404(CertificatePolicy, policy_id)
    policy.is_active = not policy.is_active
    try:
        db.session.commit()
        status = "enabled" if policy.is_active else "disabled"
        return success_response(data=policy.to_dict(), message=f"Policy {status}")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to toggle policy {policy_id}: {e}")
        return error_response('Failed to update policy', 500)


# ============ Approval Requests ============

@bp.route('/api/v2/approvals', methods=['GET'])
@require_auth(['read:approvals'])
def list_approvals():
    """List approval requests"""
    status = request.args.get('status', 'pending')
    
    query = ApprovalRequest.query
    if status != 'all':
        query = query.filter_by(status=status)
    
    requests = query.order_by(ApprovalRequest.created_at.desc()).all()
    return success_response(data=[r.to_dict() for r in requests])


@bp.route('/api/v2/approvals/<int:request_id>', methods=['GET'])
@require_auth(['read:approvals'])
def get_approval(request_id):
    """Get approval request details"""
    approval = db.get_or_404(ApprovalRequest, request_id)
    return success_response(data=approval.to_dict())


@bp.route('/api/v2/approvals/<int:request_id>/approve', methods=['POST'])
@require_auth(['write:approvals'])
def approve_request(request_id):
    """Approve a request — triggers certificate issuance if fully approved.

    Race-safe: takes a row-level lock on the approval (Postgres SELECT
    ... FOR UPDATE; harmless no-op on SQLite which serialises writes
    anyway) so concurrent reviewers cannot both flip status='approved'
    and trigger duplicate certificate issuance. Also enforces:
      * one vote per user (idempotency for double-clicks / multiple tabs)
      * single issuance via approval.certificate_id sentinel
    """
    data = request.get_json() or {}
    user = g.current_user if hasattr(g, 'current_user') else None
    user_id = getattr(user, 'id', None)
    username = getattr(user, 'username', None) or 'system'

    # Drop any stale identity-map copy so with_for_update actually
    # re-reads the row inside the lock.
    db.session.expire_all()
    approval = (
        ApprovalRequest.query
        .with_for_update()
        .filter_by(id=request_id)
        .first()
    )
    if approval is None:
        return error_response('Approval request not found', 404)

    if approval.status != 'pending':
        return error_response(f"Request is already {approval.status}", 400)

    # Auto-expire if past expiry
    if _approval_is_expired(approval):
        approval.status = 'expired'
        approval.resolved_at = utc_now()
        safe_commit(logger, "Failed to expire request")
        return error_response("Request has expired", 410)

    # Group-membership gate: enforce policy.approval_group_id
    allowed, reason = _user_can_act_on_approval(user, approval)
    if not allowed:
        return error_response(reason or "Not authorized to act on this request", 403)

    # Prevent self-approval
    if user_id and approval.requester_id == user_id:
        return error_response("Cannot approve your own request", 403)

    # Idempotency: same user must not vote twice (covers double-click,
    # multiple tabs, replay). Anonymous/system votes (user_id is None)
    # bypass this check — these only happen for backfill/automation.
    if user_id is not None:
        existing_votes = approval.get_approvals()
        if any(v.get('user_id') == user_id for v in existing_votes):
            return error_response('You have already voted on this request', 409)

    approval.add_approval(
        user_id=user_id,
        username=username,
        action='approve',
        comment=data.get('comment'),
    )

    # Issue the certificate inside the SAME transaction so the row
    # lock is held until certificate_id is set. A concurrent approver
    # blocked on the lock will re-read status='approved' and bail.
    issued_cert = None
    issue_error = None
    if approval.status == 'approved' and approval.request_data and approval.certificate_id is None:
        try:
            issued_cert = _issue_approved_certificate(approval)
            if issued_cert:
                logger.info(f"Certificate issued for approval #{approval.id}")
        except Exception as e:
            logger.error(f"Failed to issue certificate for approval #{approval.id}: {e}",
                         exc_info=True)
            from services.policy_service import PolicyViolation
            from services.cert.renewal import RenewalError
            if isinstance(e, PolicyViolation):
                issue_error = f'Policy violation: {e}'
            elif isinstance(e, RenewalError):
                issue_error = e.message
            elif isinstance(e, RuntimeError) and 'already issued' in str(e):
                issue_error = 'A certificate was already issued for this request by another approver; reload it'
            elif isinstance(e, ValueError) and not any(
                marker in str(e) for marker in ('signing key', 'KEY_ENCRYPTION_KEY', 'HSM')
            ):
                # The issuance service's own refusals (CA offline, validity
                # past the CA, template gone...): the approver needs the
                # reason to know what to fix before retrying. Key-material
                # failures stay generic, as on the direct route.
                issue_error = str(e)
            else:
                issue_error = 'Certificate issuance failed. Check server logs.'
            db.session.rollback()
            # The rollback discarded the vote along with the failed
            # issuance, and that is the point: the request stays pending so
            # the approver can approve again once the cause (CA offline, HSM
            # unreachable, policy rule) is dealt with. Re-recording the vote
            # used to flip the request to `approved` with no certificate and
            # no way to ever issue it.
            approval = ApprovalRequest.query.filter_by(id=request_id).first()
            if approval is None:
                return error_response('Approval request not found', 404)

    ok, _err = safe_commit(logger, "Failed to approve request")
    if not ok:
        return _err

    AuditService.log_action(
        action='approval_issue_failed' if issue_error else 'approval_approved',
        resource_type='approval',
        resource_id=str(request_id),
        resource_name=f'Approval #{request_id}',
        details=(f'Approval vote by {username} not kept: {issue_error}' if issue_error
                 else f'Approved by {username} (status: {approval.status})'),
        success=not issue_error,
    )

    # Snapshot before emitting: bus subscribers may commit and expire the
    # ORM instance, so re-reading approval afterwards could raise.
    result = approval.to_dict()
    if approval.status == 'approved' and not issue_error:
        from services.webhook_service import emit_csr_approved
        emit_csr_approved(result)

    if issued_cert is not None:
        result['certificate'] = issued_cert
        result['certificate_issued'] = True
        if issued_cert.get('already_issued'):
            # Closed on a certificate that already existed (signed or
            # renewed directly meanwhile)
            result['already_issued'] = True
    elif issue_error is not None:
        result['certificate_issued'] = False
        result['issue_error'] = issue_error

    return success_response(data=result, message="Approval recorded")


@bp.route('/api/v2/approvals/<int:request_id>/reject', methods=['POST'])
@require_auth(['write:approvals'])
def reject_request(request_id):
    """Reject a request (race-safe, single vote per user)"""
    data = request.get_json() or {}
    user = g.current_user if hasattr(g, 'current_user') else None
    user_id = getattr(user, 'id', None)
    username = getattr(user, 'username', None) or 'system'

    if not data.get('comment'):
        return error_response("Rejection reason is required", 400)

    db.session.expire_all()
    approval = (
        ApprovalRequest.query
        .with_for_update()
        .filter_by(id=request_id)
        .first()
    )
    if approval is None:
        return error_response('Approval request not found', 404)

    if approval.status != 'pending':
        return error_response(f"Request is already {approval.status}", 400)

    if _approval_is_expired(approval):
        approval.status = 'expired'
        approval.resolved_at = utc_now()
        safe_commit(logger, "Failed to expire request")
        return error_response("Request has expired", 410)

    allowed, reason = _user_can_act_on_approval(user, approval)
    if not allowed:
        return error_response(reason or "Not authorized to act on this request", 403)

    if user_id is not None:
        existing_votes = approval.get_approvals()
        if any(v.get('user_id') == user_id for v in existing_votes):
            return error_response('You have already voted on this request', 409)

    approval.add_approval(
        user_id=user_id,
        username=username,
        action='reject',
        comment=data.get('comment'),
    )

    ok, _err = safe_commit(logger, "Failed to reject request")
    if not ok:
        return _err

    result = approval.to_dict()
    if approval.status == 'rejected':
        from services.webhook_service import emit_csr_rejected
        emit_csr_rejected(result, reason=data.get('comment'))

    return success_response(data=result, message="Request rejected")


@bp.route('/api/v2/approvals/stats', methods=['GET'])
@require_auth(['read:approvals'])
def approval_stats():
    """Get approval statistics"""
    pending = ApprovalRequest.query.filter_by(status='pending').count()
    approved = ApprovalRequest.query.filter_by(status='approved').count()
    rejected = ApprovalRequest.query.filter_by(status='rejected').count()
    
    return success_response(data={
        'pending': pending,
        'approved': approved,
        'rejected': rejected,
        'total': pending + approved + rejected
    })

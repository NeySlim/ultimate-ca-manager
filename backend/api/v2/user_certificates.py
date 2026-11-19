"""
User Certificates API - Manage user/client certificates (mTLS)
Provides list, detail, export, revoke, delete for certificates linked to users via auth_certificates.
"""

import base64
import logging
from datetime import datetime, timedelta

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from utils.pkcs12_export import legacy_flag, pkcs12_encryption
from utils.algorithm_refusal import refuse_unexportable_key
import fips_mode
from fips_mode import FipsRestricted
from flask import Blueprint, Response, g, request

from auth.unified import require_auth, has_permission
from models import CA, AuthCertificate, Certificate, User, db
from utils.key_codec import load_pem_bytes
from services.audit_service import AuditService
from services.key_export_audit import encrypt_key_pem
from services.cert_service import CertificateService
from services.approval_gate import PairApprovalConflict, approval_payload, queue_revocation
from services.cert.related_pair import revocation_partner
from services.mtls_enrollment import remove_enrolment
from services.acme.upstream_revocation import (
    propagate_acme_revocation, revocation_answer, with_related_answer)
from utils.pagination import parse_request_pagination
from utils.days_remaining import days_remaining as compute_days_remaining
from utils.export_password import validate_export_password
from utils.cert_status import (USER_CERTIFICATE_STATUS_FILTERS,
                               normalize_status_filters,
                               unknown_status_message)
from utils.response import error_response, no_content_response, success_response
from utils.db_transaction import safe_commit
from utils.sanitize import content_disposition, sanitize_filename
from utils.datetime_utils import utc_now, utc_isoformat
from utils.revocation_reasons import normalize_revocation_reason, invalid_reason_message, revocable
from utils.export_options import json_boolean, query_boolean

logger = logging.getLogger(__name__)

bp = Blueprint('user_certificates', __name__, url_prefix='/api/v2/user-certificates')


# Formats that carry no key or no chain default those options off, so a plain
# DER or P7B request is not refused for an option nobody ticked.
def _key_by_default(export_format):
    return export_format not in ('der', 'pkcs7', 'p7b')


def _chain_by_default(export_format):
    return export_format not in ('der', 'key')


_EXPORT_FORMATS = ('pem', 'der', 'pkcs7', 'p7b', 'key', 'pkcs12', 'p12', 'pfx', 'jks')


def _is_admin_or_operator(user):
    """Check if user has admin or operator role."""
    return getattr(user, 'role', '') in ('admin', 'operator')


def _is_auditor(user):
    """Check if user has auditor role."""
    return getattr(user, 'role', '') == 'auditor'


def _can_access_cert(user, auth_cert):
    """Check if user can access a specific certificate."""
    if _is_admin_or_operator(user) or _is_auditor(user):
        return True
    return auth_cert.user_id == user.id


def _get_certificate_for_auth_cert(auth_cert):
    """The Certificate record an enrolment is bound to (never merely one
    sharing its serial number: see services.mtls_enrollment)."""
    from services.mtls_enrollment import certificate_row_for
    return certificate_row_for(auth_cert)


def _cert_status(certificate, now):
    """The status a listing row shows and the status filter matches."""
    if certificate is None:
        return 'orphan'
    if certificate.revoked:
        return 'revoked'
    if certificate.valid_to and certificate.valid_to <= now:
        return 'expired'
    if certificate.valid_to and certificate.valid_to <= now + timedelta(days=30):
        return 'expiring'
    return 'valid'


def _build_cert_response(auth_cert, certificate, owner_user=None):
    """Build a combined response dict from auth_cert + certificate."""
    result = auth_cert.to_dict()
    if certificate:
        result['cert_id'] = certificate.id
        result['refid'] = certificate.refid
        result['description'] = certificate.descr
        result['subject'] = certificate.subject
        result['issuer'] = certificate.issuer
        result['serial_number'] = certificate.serial_number
        result['valid_from'] = utc_isoformat(certificate.valid_from)
        result['valid_to'] = utc_isoformat(certificate.valid_to)
        result['cert_type'] = certificate.cert_type
        result['revoked'] = certificate.revoked or False
        result['revoke_reason'] = certificate.revoke_reason if certificate.revoked else None
        result['has_private_key'] = bool(certificate.prv)
        result['caref'] = certificate.caref
        # Extract CN from subject for CertificateDetails compatibility
        from utils.dn_parse import stored_dn_common_name
        cn = stored_dn_common_name(certificate.subject)
        result['common_name'] = cn or auth_cert.name or certificate.descr or ''
        result['cn'] = result['common_name']
        # Key info (parse from cert if available)
        result['key_algorithm'] = getattr(certificate, 'key_algorithm', None) or 'RSA'
        result['key_size'] = getattr(certificate, 'key_size', None)
        result['signature_algorithm'] = getattr(certificate, 'signature_algorithm', None)
        # Compute status + days_remaining
        now = utc_now()
        result['status'] = _cert_status(certificate, now)
        if certificate.valid_to:
            result['days_remaining'] = compute_days_remaining(
                certificate.valid_to, now)
    else:
        result['status'] = 'orphan'
        result['has_private_key'] = False
        result['common_name'] = auth_cert.name or ''
        result['cn'] = result['common_name']

    if owner_user:
        result['owner'] = owner_user.username
        result['owner_id'] = owner_user.id
    return result


@bp.route('', methods=['GET'])
@require_auth(['read:user_certificates'])
def list_user_certificates():
    """List user certificates with ownership-aware access control."""
    user = g.current_user

    # Pagination
    page, per_page = parse_request_pagination(default_per_page=25)

    # Filters
    status_filters, unknown_status = normalize_status_filters(
        request.args.getlist('status'), USER_CERTIFICATE_STATUS_FILTERS)
    if unknown_status:
        return error_response(
            unknown_status_message(
                unknown_status, USER_CERTIFICATE_STATUS_FILTERS), 400)
    user_filter = request.args.get('user_id', type=int)
    search = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', 'created_at')
    sort_order = request.args.get('sort_order', 'desc')

    # Base query
    query = AuthCertificate.query

    # Access control: viewers see only own certs
    if not _is_admin_or_operator(user) and not _is_auditor(user):
        query = query.filter(AuthCertificate.user_id == user.id)
    elif user_filter:
        query = query.filter(AuthCertificate.user_id == user_filter)

    # Search
    if search:
        safe_search = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        search_pattern = f'%{safe_search}%'
        query = query.filter(
            db.or_(
                AuthCertificate.name.ilike(search_pattern, escape='\\'),
                AuthCertificate.cert_subject.ilike(search_pattern, escape='\\'),
                AuthCertificate.cert_serial.ilike(search_pattern, escape='\\'),
            )
        )

    # Sorting
    sort_col_map = {
        'created_at': AuthCertificate.created_at,
        'name': AuthCertificate.name,
        'valid_until': AuthCertificate.valid_until,
        'last_used_at': AuthCertificate.last_used_at,
    }
    sort_col = sort_col_map.get(sort_by, AuthCertificate.created_at)
    # Absent values last in both directions, whichever engine; the primary key
    # breaks ties so the page boundary does not depend on the plan.
    if sort_order == 'asc':
        query = query.order_by(sort_col.asc().nulls_last(), AuthCertificate.id.asc())
    else:
        query = query.order_by(sort_col.desc().nulls_last(), AuthCertificate.id.desc())

    if status_filters:
        # The status is computed from the bound certificate, so the filter
        # runs before the page is cut: total and pages are those of the match.
        now = utc_now()
        matched = []
        for ac in query.all():
            cert = _get_certificate_for_auth_cert(ac)
            if _cert_status(cert, now) in status_filters:
                matched.append((ac, cert))
        total = len(matched)
        pages = (total + per_page - 1) // per_page
        window = matched[(page - 1) * per_page:page * per_page]
    else:
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        total, pages = pagination.total, pagination.pages
        window = [(ac, _get_certificate_for_auth_cert(ac)) for ac in pagination.items]

    results = []
    user_cache = {}
    for ac, cert in window:
        if ac.user_id not in user_cache:
            user_cache[ac.user_id] = db.session.get(User, ac.user_id)
        results.append(_build_cert_response(ac, cert, user_cache[ac.user_id]))

    return success_response(data={
        'items': results,
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': pages,
    })


@bp.route('/stats', methods=['GET'])
@require_auth(['read:user_certificates'])
def get_user_certificate_stats():
    """Get user certificate statistics."""
    user = g.current_user
    now = utc_now()
    expiry_threshold = now + timedelta(days=30)

    # Base query with access control
    query = AuthCertificate.query
    if not _is_admin_or_operator(user) and not _is_auditor(user):
        query = query.filter(AuthCertificate.user_id == user.id)

    auth_certs = query.all()
    stats = {'total': len(auth_certs), 'valid': 0, 'expiring': 0, 'expired': 0, 'revoked': 0}

    for ac in auth_certs:
        cert = _get_certificate_for_auth_cert(ac)
        if not cert:
            continue
        if cert.revoked:
            stats['revoked'] += 1
        elif cert.valid_to and cert.valid_to <= now:
            stats['expired'] += 1
        elif cert.valid_to and cert.valid_to <= expiry_threshold:
            stats['expiring'] += 1
        else:
            stats['valid'] += 1

    # User count (admins/operators only)
    if _is_admin_or_operator(user) or _is_auditor(user):
        stats['users'] = db.session.query(
            db.func.count(db.distinct(AuthCertificate.user_id))
        ).scalar() or 0

    return success_response(data=stats)


@bp.route('/<int:cert_id>', methods=['GET'])
@require_auth(['read:user_certificates'])
def get_user_certificate(cert_id):
    """Get a single user certificate by auth_certificate ID."""
    user = g.current_user

    auth_cert = db.session.get(AuthCertificate, cert_id)
    if not auth_cert:
        return error_response('Certificate not found', 404)

    if not _can_access_cert(user, auth_cert):
        return error_response('Certificate not found', 404)

    cert = _get_certificate_for_auth_cert(auth_cert)
    owner = db.session.get(User, auth_cert.user_id)

    return success_response(data=_build_cert_response(auth_cert, cert, owner))


@bp.route('/<int:cert_id>/export', methods=['GET', 'POST'])
@require_auth(['read:user_certificates'])
def export_user_certificate(cert_id):
    """Export a user certificate as PEM, DER, P7B, the key alone, PKCS#12 or JKS. Auditors cannot export."""
    user = g.current_user

    if _is_auditor(user):
        return error_response('Auditors cannot export certificates', 403)

    auth_cert = db.session.get(AuthCertificate, cert_id)
    if not auth_cert:
        return error_response('Certificate not found', 404)

    if not _can_access_cert(user, auth_cert):
        return error_response('Certificate not found', 404)

    cert = _get_certificate_for_auth_cert(auth_cert)
    if not cert:
        return error_response('Certificate data not found', 404)

    if request.method == 'POST' and request.is_json:
        data = request.get_json()
        export_format = data.get('format', 'pem').lower()
        password = data.get('password', '')
        try:
            include_key = json_boolean(data, 'include_key', _key_by_default(export_format))
            include_chain = json_boolean(data, 'include_chain', _chain_by_default(export_format))
            include_root = json_boolean(data, 'include_root', False)
            legacy_value = json_boolean(data, 'legacy', False)
        except ValueError as exc:
            return error_response(str(exc), 400)
        legacy = legacy_flag(legacy_value)  # 3DES/SHA-1 profile (#331)
    else:
        export_format = request.args.get('format', 'pem').lower()
        password = request.args.get('password', '')
        legacy = False
        try:
            include_key = query_boolean(request.args, 'include_key', False)
            include_chain = query_boolean(request.args, 'include_chain', _chain_by_default(export_format))
            include_root = query_boolean(request.args, 'include_root', False)
        except ValueError as exc:
            return error_response(str(exc), 400)
        # Outside a JSON body no password is read, so no key is served: a GET
        # carries the certificate alone unless it asks for a key (400).
        if password or include_key or export_format in ('pkcs12', 'p12', 'pfx', 'jks', 'key'):
            if password:
                logger.warning(
                    "Rejected user-certificate export with password in query string "
                    "(cert_id=%s): client must POST with JSON body",
                    cert_id,
                )
            return error_response(
                'Password and private key exports must use POST with a JSON body, '
                'not the query string', 400)

    if export_format not in _EXPORT_FORMATS:
        return error_response(f'Unsupported format: {export_format}', 400)
    from api.v2.certificates.export import inapplicable_option, requested_chain_variant
    option_err = inapplicable_option(export_format, include_key, include_chain)
    if option_err:
        return error_response(option_err, 400)
    variant, variant_err = requested_chain_variant(
        data if request.method == 'POST' and request.is_json else request.args, cert)
    if variant_err:
        return variant_err

    # Somebody else's key needs `read:private_keys`, as on the certificate
    # route, or the approval-gated Key Recovery flow is bypassable (#232).
    # Your own key stays: that is what the account page is for.
    wants_key = include_key or export_format in ('pkcs12', 'p12', 'pfx', 'jks', 'key')
    if wants_key and auth_cert.user_id != user.id:
        if not has_permission('read:private_keys', g.permissions):
            return error_response(
                "Exporting another user's private key requires the "
                'read:private_keys permission; roles without it must use the '
                'Key Recovery approval flow', 403)

    try:
        cert_pem = base64.b64decode(cert.crt)
        # The raw name goes to content_disposition(), which falls back to the refid.
        raw_name = auth_cert.name or cert.descr or cert.refid
        filename_base = sanitize_filename(raw_name)

        if export_format == 'key':
            pw_err = validate_export_password(password, allow_empty=True)
            if pw_err:
                return error_response(pw_err, 400)
            from api.v2.certificates.export import key_only_response
            answer = key_only_response(cert, password, 'user_certificate', filename_base, raw_name)
            if answer.status_code == 200:
                AuditService.log_action(
                    action='user_certificate_exported',
                    resource_type='user_certificate',
                    resource_id=cert_id,
                    resource_name=filename_base,
                    details=f'Exported private key only for user cert: {filename_base}',
                    success=True
                )
            return answer

        if export_format in ('der', 'pkcs7', 'p7b'):
            from api.v2.certificates.export import (
                _build_ca_chain, _split_pem_certs, der_response, p7b_response)
            if export_format == 'der':
                answer = der_response(cert_pem, raw_name, cert.refid)
            else:
                leaf = _split_pem_certs(cert_pem)
                pems = [leaf[0].public_bytes(serialization.Encoding.PEM) if leaf else cert_pem]
                if include_chain:
                    pems += [c.public_bytes(serialization.Encoding.PEM) for c in _build_ca_chain(
                        cert, cert_pem, include_root=include_root, variant=variant)]
                answer = p7b_response(pems, raw_name, cert.refid)
            AuditService.log_action(
                action='user_certificate_exported',
                resource_type='user_certificate',
                resource_id=cert_id,
                resource_name=filename_base,
                details=f'Exported {export_format.upper()} for user cert: {filename_base}',
                success=True
            )
            return answer

        if export_format in ('pkcs12', 'p12', 'pfx'):
            pw_err = validate_export_password(password)
            if pw_err:
                return error_response(pw_err, 400)
            if not cert.prv:
                return error_response('Certificate has no private key for PKCS12 export', 400)

            x509_cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            key_pem = load_pem_bytes(cert.prv, context=f"certificate {cert.id}")
            private_key = serialization.load_pem_private_key(key_pem, password=None, backend=default_backend())
            refuse_unexportable_key(private_key, export_format)

            from api.v2.certificates.export import _build_ca_chain
            ca_certs = (
                _build_ca_chain(cert, cert_pem, include_root=include_root, variant=variant)
                if include_chain else []
            )

            p12_bytes = pkcs12.serialize_key_and_certificates(
                name=filename_base.encode(),
                key=private_key,
                cert=x509_cert,
                cas=ca_certs if ca_certs else None,
                encryption_algorithm=pkcs12_encryption(password, legacy, caref=cert.caref),
            )

            AuditService.log_action(
                action='user_certificate_exported',
                resource_type='user_certificate',
                resource_id=cert_id,
                resource_name=filename_base,
                details=f'Exported PKCS12 with private key for user cert: {filename_base}',
                success=True
            )

            return Response(
                p12_bytes,
                mimetype='application/x-pkcs12',
                headers={'Content-Disposition': content_disposition(raw_name, '.p12', fallback=cert.refid)}
            )

        elif export_format == 'jks':
            pw_err = validate_export_password(password)
            if pw_err:
                return error_response(pw_err, 400)
            if not cert.prv:
                return error_response('Certificate has no private key for JKS export', 400)
            fips_mode.refuse('JKS export')

            import jks as pyjks
            import time as _time

            x509_cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            key_pem_data = load_pem_bytes(cert.prv, context=f"certificate {cert.id}")
            private_key = serialization.load_pem_private_key(key_pem_data, password=None, backend=default_backend())
            refuse_unexportable_key(private_key, 'jks')

            cert_der = x509_cert.public_bytes(serialization.Encoding.DER)
            key_pkcs8 = private_key.private_bytes(
                serialization.Encoding.DER,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption()
            )

            cert_chain = [("X.509", cert_der)]
            if include_chain:
                from api.v2.certificates.export import _build_ca_chain
                for ca_cert_obj in _build_ca_chain(
                    cert, cert_pem, include_root=include_root, variant=variant
                ):
                    cert_chain.append((
                        "X.509", ca_cert_obj.public_bytes(serialization.Encoding.DER)
                    ))

            ts = int(_time.time() * 1000)
            pke = pyjks.PrivateKeyEntry(
                alias=(filename_base).lower().replace(' ', '-'),
                cert_chain=cert_chain,
                pkey_pkcs8=key_pkcs8,
                timestamp=ts,
            )

            keystore = pyjks.KeyStore.new("jks", [pke])
            jks_bytes = keystore.saves(password)

            AuditService.log_action(
                action='user_certificate_exported',
                resource_type='user_certificate',
                resource_id=cert_id,
                resource_name=filename_base,
                details=f'Exported JKS with private key for user cert: {filename_base}',
                success=True
            )

            return Response(
                jks_bytes,
                mimetype='application/x-java-keystore',
                headers={'Content-Disposition': content_disposition(raw_name, '.jks', fallback=cert.refid)}
            )

        # PEM export (default)
        from api.v2.certificates.export import _build_ca_chain, _split_pem_certs
        stored_certs = _split_pem_certs(cert_pem)
        result = (
            stored_certs[0].public_bytes(serialization.Encoding.PEM)
            if stored_certs else cert_pem
        )
        suffix = '.crt'

        if include_key and cert.prv:
            pw_err = validate_export_password(password, allow_empty=True)
            if pw_err:
                return error_response(pw_err, 400)
            key_pem = encrypt_key_pem(
                load_pem_bytes(cert.prv, context=f"certificate {cert.id}"), password)
            if not result.endswith(b'\n'):
                result += b'\n'
            result += key_pem
            suffix = '.pem'

        if include_chain:
            for ca_cert in _build_ca_chain(cert, cert_pem, include_root=include_root, variant=variant):
                if not result.endswith(b'\n'):
                    result += b'\n'
                result += ca_cert.public_bytes(serialization.Encoding.PEM)

        AuditService.log_action(
            action='user_certificate_exported',
            resource_type='user_certificate',
            resource_id=cert_id,
            resource_name=filename_base,
            details=(f'Exported PEM with private key ({"password-protected" if password else "unencrypted"}) for user cert: {filename_base}'
                     if include_key and cert.prv else f'Exported PEM for user cert: {filename_base}'),
            success=True
        )

        return Response(
            result,
            mimetype='application/x-pem-file',
            headers={'Content-Disposition': content_disposition(raw_name, suffix, fallback=cert.refid)}
        )

    except FipsRestricted:
        raise  # the app handler answers 400 with the FIPS problem type
    except Exception as e:
        logger.error(f"Failed to export user certificate {cert_id}: {e}")
        return error_response('Failed to export certificate', 500)


@bp.route('/<int:cert_id>/revoke', methods=['POST'])
@require_auth(['write:user_certificates'])
def revoke_user_certificate(cert_id):
    """Revoke a user certificate. Operators and admins only."""
    user = g.current_user

    auth_cert = db.session.get(AuthCertificate, cert_id)
    if not auth_cert:
        return error_response('Certificate not found', 404)
    # Ownership first: a 404 reveals nothing, and no policy is evaluated for strangers
    if not _can_access_cert(user, auth_cert):
        return error_response('Certificate not found', 404)
    cert = _get_certificate_for_auth_cert(auth_cert)
    if not cert:
        return error_response('Certificate data not found', 404)

    data = request.json or {}
    reason = normalize_revocation_reason(data.get('reason', 'unspecified'))
    if reason is None:
        return error_response(invalid_reason_message(data.get('reason')), 400)

    if not revocable(cert, reason):
        return error_response('Certificate already revoked', 400)

    partner = revocation_partner(cert)
    try:
        policy, approval = queue_revocation(user, cert, reason=reason,
                                            comment=data.get('approval_comment'),
                                            auth_certificate_id=auth_cert.id,
                                            partner=partner if partner is not None and revocable(partner, reason) else None)
    except PairApprovalConflict as e:
        return error_response(str(e), 409)
    except Exception as e:
        logger.error(f"Policy evaluation failed for revocation of user certificate {cert_id}: {e}",
                     exc_info=True)
        return error_response('Policy evaluation failed; the certificate was not revoked', 500)
    if approval is not None:
        return success_response(data=approval_payload(policy, approval),
                                message='Certificate revocation submitted for approval')

    try:
        related_acme = []
        cert = CertificateService.revoke_certificate(
            cert_id=cert.id,
            reason=reason,
            username=user.username,
            related_acme=related_acme,
        )

        # Disable auth certificate
        auth_cert.enabled = False
        db.session.commit()

        AuditService.log_action(
            action='user_certificate_revoked',
            resource_type='user_certificate',
            resource_id=cert_id,
            resource_name=auth_cert.name or cert.descr,
            details=f'Revoked user certificate: {auth_cert.name or cert.descr} (reason: {reason})',
            success=True
        )

        # After the commit: a failed lookup rolls back, which must not re-enable the enrolment
        acme_outcome, acme_detail = propagate_acme_revocation(cert, reason)
        owner = db.session.get(User, auth_cert.user_id)
        return success_response(
            data=_build_cert_response(auth_cert, cert, owner),
            **with_related_answer(revocation_answer(acme_outcome, acme_detail), related_acme))
    except ValueError as e:
        logger.error(f'User certificate revocation validation error: {e}')
        return error_response('Invalid revocation request', 400)
    except Exception as e:
        logger.error(f"Failed to revoke user certificate {cert_id}: {e}")
        return error_response('Failed to revoke certificate', 500)


@bp.route('/<int:cert_id>', methods=['DELETE'])
@require_auth(['delete:user_certificates'])
def delete_user_certificate(cert_id):
    """Delete a user certificate. Operators and admins only."""
    user = g.current_user

    auth_cert = db.session.get(AuthCertificate, cert_id)
    if not auth_cert:
        return error_response('Certificate not found', 404)
    # Ownership first: a 404 reveals nothing, and no policy is evaluated for strangers
    if not _can_access_cert(user, auth_cert):
        return error_response('Certificate not found', 404)
    cert_name = auth_cert.name or f'User Certificate #{cert_id}'

    # Refused while a policy requires approval to revoke its certificate,
    # whoever holds it (administrators bypass)
    removed, answer = remove_enrolment(auth_cert, username=user.username, actor=user)
    if not removed:
        return answer

    AuditService.log_action(
        action='user_certificate_deleted',
        resource_type='user_certificate',
        resource_id=cert_id,
        resource_name=cert_name,
        details=f'Deleted user certificate: {cert_name} (by: {user.username})',
        success=True
    )

    return success_response(**answer) if answer else no_content_response()

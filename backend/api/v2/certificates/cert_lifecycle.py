"""Certificate lifecycle routes (delete, revoke, unhold)"""
import logging
from datetime import datetime, timedelta
from flask import request, g
from auth.unified import require_auth
from utils.datetime_utils import to_naive_utc, utc_now
from utils.serial_format import canonical_serial, serial_to_hex
from utils.response import success_response, error_response, no_content_response
from models import Certificate, CA, db
from utils.revocation_reasons import normalize_revocation_reason, invalid_reason_message, revocable, HOLD_REASONS
from services.cert_service import CertificateService
from services.approval_gate import (PairApprovalConflict, approval_payload, queue_revocation,
                                    revocation_policy_for)
from services.cert.related_pair import revocation_partner, unhold_partner
from utils.export_options import json_boolean
from services.deletion_blockers import certificate_deletion_blockers, first_blocker
from services.ocsp_service import OCSPService
from services.acme.upstream_revocation import (
    REVOKED_MESSAGE, propagate_acme_revocation, revocation_answer, with_related_answer)
from services.audit_service import AuditService
from services.notification_service import NotificationService
from websocket.emitters import on_certificate_revoked, on_certificate_deleted
from . import bp

logger = logging.getLogger(__name__)


@bp.route('/api/v2/certificates/<int:cert_id>', methods=['DELETE'])
@require_auth(['delete:certificates'])
def delete_certificate(cert_id):
    """Delete certificate"""

    cert = db.session.get(Certificate, cert_id)
    if not cert:
        return error_response('Certificate not found', 404)

    cert_name = cert.descr or f'Certificate #{cert_id}'

    blocker = first_blocker(certificate_deletion_blockers(cert))
    if blocker:
        return error_response(blocker.message, blocker.status)
    try:
        username = g.current_user.username if hasattr(g, 'current_user') else 'system'
        # Delegate to the service so cert/key/csr files on disk are unlinked
        # along with the DB row instead of leaving them orphaned (audit log
        # and webhook are emitted by the service itself).
        if not CertificateService.delete_certificate(cert_id=cert_id, username=username):
            return error_response('Failed to delete certificate', 500)

        return no_content_response()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete certificate {cert_name}: {e}")
        return error_response('Failed to delete certificate', 500)


@bp.route('/api/v2/certificates/<int:cert_id>/revoke', methods=['POST'])
@require_auth(['write:certificates'])
def revoke_certificate(cert_id):
    """Revoke certificate"""

    data = request.json
    if data is not None and not isinstance(data, dict):
        return error_response('Request body must be a JSON object', 400)
    reason = data.get('reason', 'unspecified') if data else 'unspecified'
    # RFC 5280 reason names only, stored in canonical spelling (#334)
    canonical = normalize_revocation_reason(reason)
    if canonical is None:
        return error_response(invalid_reason_message(reason), 400)
    reason = canonical
    invalidity_raw = None
    if data:
        invalidity_raw = data.get('invalidity_date') or data.get('invalidity_at')

    invalidity_at = None
    if invalidity_raw:
        try:
            raw = str(invalidity_raw).strip().replace('Z', '+00:00')
            invalidity_at = to_naive_utc(datetime.fromisoformat(raw))
        except (ValueError, TypeError, OverflowError) as e:
            return error_response(f'Invalid invalidity_date: {e}', 400)
        # RFC 5280 §5.3.2 — invalidityDate is a past compromise/invalidity
        # time; a future date is always a client error (allow 5 min skew).
        if invalidity_at > utc_now() + timedelta(minutes=5):
            return error_response('invalidity_date cannot be in the future', 400)

    cert = db.session.get(Certificate, cert_id)
    if not cert:
        return error_response('Certificate not found', 404)

    if not revocable(cert, reason):
        return error_response('Certificate already revoked', 400)

    # The other member of a related pair falls with it unless the request says otherwise
    try:
        revoke_related = json_boolean(data or {}, 'revoke_related', True)
    except ValueError as e:
        return error_response(str(e), 400)
    partner = revocation_partner(cert)
    partner_id = partner.id if partner is not None and revocable(partner, reason) else None
    refusal = _related_choice_refusal(cert, partner_id, revoke_related)
    if refusal:
        return error_response(*refusal)

    # A policy that requires approval for revoking either member queues the
    # request (administrators bypass); fail closed on any evaluation error
    try:
        policy, approval = queue_revocation(
            g.current_user, cert, reason=reason, invalidity_at=invalidity_at,
            comment=(data or {}).get('approval_comment'),
            partner=partner if revoke_related and partner_id else None)
    except PairApprovalConflict as e:
        return error_response(str(e), 409)
    except Exception as e:
        logger.error(f"Policy evaluation failed for revocation of {cert_id}: {e}", exc_info=True)
        return error_response('Policy evaluation failed; the certificate was not revoked', 500)
    if approval is not None:
        return success_response(data=approval_payload(policy, approval),
                                message='Certificate revocation submitted for approval')

    try:
        username = g.current_user.username if hasattr(g, 'current_user') else 'system'

        # Revoke using service — the service emits a single lifecycle event
        # that the bus fans out to webhook + email + WebSocket subscribers.
        related_acme = []
        cert = CertificateService.revoke_certificate(
            cert_id=cert_id,
            reason=reason,
            username=username,
            invalidity_at=invalidity_at,
            revoke_related=revoke_related,
            related_acme=related_acme,
        )

        # A cert issued through a Microsoft CA connection: try to propagate the
        # revocation to the Windows CA via the WinRM admin channel if one is
        # configured. Web Enrollment (/certsrv) itself has no revocation
        # endpoint, so without the admin channel the revocation stays local.
        if cert.source == 'msca':
            return _revoke_msca_on_ca(cert, reason)

        # Obtained over ACME: only the issuing CA's answer reaches relying parties
        acme_outcome, acme_detail = propagate_acme_revocation(cert, reason)
        cert_dict = cert.to_dict()
        partner = db.session.get(Certificate, partner_id) if revoke_related and partner_id else None
        message = REVOKED_MESSAGE
        if partner is not None and not revocable(partner, reason):
            cert_dict['related_revoked'] = partner_id
        elif partner is not None:
            # This one stays revoked; the other member's failure is said, not hidden
            cert_dict['related_not_revoked'] = partner_id
            message = (f'Certificate revoked; its related certificate #{partner_id} was not '
                       'revoked, revoke it separately')
        answer = revocation_answer(acme_outcome, acme_detail, message)
        return success_response(data=cert_dict, **with_related_answer(answer, related_acme))
    except ValueError as e:
        logger.error(f"Certificate revocation validation error: {e}")
        return error_response('Validation failed', 400)
    except Exception as e:
        logger.error(f"Failed to revoke certificate: {e}")
        return error_response('Failed to revoke certificate', 500)


def _related_choice_refusal(cert, partner_id, revoke_related):
    """``(message, status)`` when keeping the other member cannot be honoured: an
    approved revocation takes the pair with it, so such a request is refused, not queued."""
    if revoke_related or not partner_id:
        return None
    if getattr(getattr(g, 'current_user', None), 'role', None) == 'admin':
        return None
    try:
        policy = revocation_policy_for(cert)
    except Exception as e:
        logger.error(f"Policy evaluation failed for revocation of {cert.id}: {e}", exc_info=True)
        return 'Policy evaluation failed; the certificate was not revoked', 500
    if policy is None:
        return None
    return (f'Policy "{policy.name}" requires approval, which revokes both certificates of a '
            'related pair; request it with revoke_related left on', 400)


def _revoke_msca_on_ca(cert, reason):
    """After a local msca revocation, propagate to the Windows CA if possible.

    The propagation itself is shared with the bulk route
    (``services/msca/propagation.py``); what stays here is turning its
    outcome into the response clients already read.
    """
    from services.msca.propagation import (
        propagate_revocation, PROPAGATED, CHANNEL_FAILED,
    )

    # Snapshotted before the propagation audits: that call commits the
    # session, which expires this instance (the bus/audit rule).
    cert_dict = cert.to_dict()
    outcome, detail = propagate_revocation(cert, reason)

    if outcome == CHANNEL_FAILED:
        return success_response(
            data=cert_dict,
            message=(
                'Certificate revoked in UCM, but propagating the revocation to '
                f'the Windows CA failed: {detail}. Revoke it on the CA manually.'
            ),
            meta={'msca_local_only': True, 'msca_ca_error': str(detail)[:300]}
        )

    if outcome != PROPAGATED:
        return success_response(
            data=cert_dict,
            message=(
                'Certificate revoked in UCM only, no Microsoft CA admin channel '
                'is configured, so the Windows CA was not notified. Enable the '
                'WinRM admin channel on the connection, or revoke it on the CA.'
            ),
            meta={'msca_local_only': True}
        )

    return success_response(
        data=cert_dict,
        message='Certificate revoked in UCM and on the Microsoft CA',
        meta={'msca_ca_revoked': True}
    )


@bp.route('/api/v2/certificates/<int:cert_id>/unhold', methods=['POST'])
@require_auth(['write:certificates'])
def unhold_certificate(cert_id):
    """Remove certificate hold (temporary revocation) and restore to valid status"""

    cert = db.session.get(Certificate, cert_id)
    if not cert:
        return error_response('Certificate not found', 404)

    if not cert.revoked:
        return error_response('Certificate is not revoked', 400)

    # Only certificateHold can be unheld
    if cert.revoke_reason not in HOLD_REASONS:
        return error_response(
            'Only certificates with reason "certificateHold" can be unheld', 400
        )

    # A body that is present is read strictly (400/415): an unreadable refusal must not lift the pair
    body = request.get_json() if request.get_data(cache=True) else None
    if body is not None and not isinstance(body, dict):
        return error_response('Request body must be a JSON object', 400)
    try:
        unhold_related = json_boolean(body or {}, 'unhold_related', True)
    except ValueError as e:
        return error_response(str(e), 400)

    try:
        username = g.current_user.username if hasattr(g, 'current_user') else 'system'

        # The other member of a related pair comes off hold with it unless the request says otherwise
        partner = unhold_partner(cert) if unhold_related else None
        members = [cert] + ([partner] if partner is not None else [])
        cas = {m.id: (CA.query.filter_by(refid=m.caref).first() if m.caref else None)
               for m in members}

        # Each hold as it stands, before the removeFromCRL staging below
        helds = {m.id: ({field: getattr(m, field)
                         for field in ('revoked', 'revoked_at', 'revoke_reason', 'invalidity_at')},
                        m.serial_number, m.caref) for m in members}

        # RFC 5280 §5.3.1: stage removeFromCRL on every member, commit once, then
        # emit one delta per distinct CA so relying parties drop the entries.
        staged_cas = {}
        for member in members:
            member_ca = cas[member.id]
            if not (member_ca and member_ca.delta_crl_enabled and member_ca.cdp_enabled):
                continue
            member.revoke_reason = 'removeFromCRL'
            member.revoked_at = utc_now()
            staged_cas[member_ca.id] = member_ca
        if staged_cas:
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.error(f"Failed to stage removeFromCRL before unhold: {e}")
                _restore_holds(helds)
                return error_response('Failed to remove certificate hold', 500)
            from services.crl_service import CRLService
            for staged_ca in staged_cas.values():
                try:
                    CRLService.generate_delta_crl(staged_ca.id, username=username)
                except Exception as e:
                    # The full CRL regenerated below no longer lists the certificates
                    logger.warning(f"Failed to emit removeFromCRL delta before unhold: {e}")
            members = [db.session.get(Certificate, m.id) for m in members]
            cert = members[0]

        # The lifted holds and their revocation records go together or not at all
        try:
            from models import RevokedSerial
            for member in members:
                member.revoked = False
                member.revoked_at = None
                member.revoke_reason = None
                member.invalidity_at = None
                _, serial, caref = helds[member.id]
                if caref and serial:
                    RevokedSerial.query.filter_by(caref=caref, serial_number=canonical_serial(serial)).delete(
                        synchronize_session='fetch')
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to remove hold on certificate {cert_id}: {e}", exc_info=True)
            _restore_holds(helds)
            return error_response('Failed to remove certificate hold', 500)

        # Audit log
        for member in members:
            AuditService.log_action(
                action='certificate_unheld',
                resource_type='certificate',
                resource_id=str(member.id),
                resource_name=member.descr or member.refid,
                details='Certificate hold removed, restored to valid status',
                success=True
            )

        # Regenerate CRL for each issuing CA
        for member_ca in {c.id: c for c in cas.values() if c}.values():
            try:
                from services.crl_service import CRLService
                CRLService.generate_crl(member_ca.id, username=username)
                logger.info(f"Regenerated CRL for CA {member_ca.id} after unhold")
            except Exception as e:
                logger.warning(f"Failed to regenerate CRL after unhold: {e}")

        # Invalidate all per-algorithm OCSP cache entries (RFC 6960 §2.2).
        for member in members:
            member_ca = cas[member.id]
            if member.serial_number:
                OCSPService.invalidate_cached_responses(
                    member.serial_number, ca_id=member_ca.id if member_ca else None)
            # A delegated responder coming off hold signs again: the answers the
            # CA signed meanwhile carry the wrong identity (#347 review)
            for responder_ca_id in OCSPService.responder_cas_for_certificate(member.id):
                OCSPService.invalidate_ca_cache(responder_ca_id)

        # Snapshots first, the bus after the commit
        from services.webhook_service import emit_cert_unheld
        snapshots = [(m.to_dict(), m.caref) for m in members]
        for snapshot, caref in snapshots:
            emit_cert_unheld(snapshot, ca_refid=caref, actor=username)

        # Propagate the unhold to the Windows CA if this cert came from an MS CA
        # with an admin channel (certutil unrevoke only lifts a certificateHold).
        if cert.source == 'msca':
            from services.msca_service import MicrosoftCAService, MSCAAdminChannelError
            from services.msca.propagation import find_msca_for_cert
            msca = find_msca_for_cert(cert)
            if msca and MicrosoftCAService.admin_channel_available(msca):
                try:
                    MicrosoftCAService.unrevoke_on_ca(msca, serial_to_hex(cert.serial_number))  # certutil reads hex
                    AuditService.log_action(
                        action='msca.unrevoke_on_ca',
                        resource_type='certificate',
                        resource_id=str(cert.id),
                        resource_name=cert.subject or cert.refid,
                        details=f"Hold lifted on Microsoft CA '{msca.name}'",
                        success=True,
                    )
                    return success_response(
                        data=_unhold_data(cert, partner),
                        message='Certificate hold removed in UCM and on the Microsoft CA',
                        meta={'msca_ca_unrevoked': True}
                    )
                except MSCAAdminChannelError as e:
                    logger.error(f"MS CA admin-channel unrevoke failed for cert {cert.id}: {e}")
                    return success_response(
                        data=_unhold_data(cert, partner),
                        message=(
                            'Certificate hold removed in UCM, but lifting it on the '
                            f'Windows CA failed: {e}. Unrevoke it on the CA manually.'
                        ),
                        meta={'msca_local_only': True, 'msca_ca_error': str(e)[:300]}
                    )

        return success_response(
            data=_unhold_data(cert, partner),
            message='Certificate hold removed successfully'
        )
    except Exception as e:
        logger.error(f"Failed to unhold certificate: {e}")
        return error_response('Failed to remove certificate hold', 500)


def _unhold_data(cert, partner):
    data = cert.to_dict()
    if partner is not None:
        data['related_unheld'] = partner.id
    return data


def _restore_holds(helds):
    """Put the holds back as they were before a failed unhold (the delta staging
    may have committed removeFromCRL)."""
    for cert_id, (held, _serial, _caref) in helds.items():
        try:
            cert = db.session.get(Certificate, cert_id)
            if cert is None:
                continue
            for field, value in held.items():
                setattr(cert, field, value)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Certificate {cert_id}: hold not restored after a failed unhold: {e}")

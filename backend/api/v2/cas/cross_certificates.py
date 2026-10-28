"""Cross-certificates of a CA (#400): /api/v2/cas/<id>/cross-certificates."""
import logging
from datetime import datetime, timedelta

from flask import Response, g, request

from auth.unified import require_auth
from models import CA, db
from models.ca_cross_certificate import CACrossCertificate
from services.audit_service import AuditService
from services.ca import cross_certs
from services.ca.cross_certs import CrossCertError
from utils.response import created_response, error_response, no_content_response, success_response
from utils.sanitize import sanitize_filename

from . import bp

logger = logging.getLogger(__name__)


def _username():
    return getattr(getattr(g, 'current_user', None), 'username', None) or 'system'


def _ca_and_row(ca_id, xid=None):
    ca = db.session.get(CA, ca_id)
    if not ca:
        return None, None, error_response('CA not found', 404)
    if xid is None:
        return ca, None, None
    row = db.session.get(CACrossCertificate, xid)
    if not row or row.ca_id != ca.id:
        return ca, None, error_response('Cross-certificate not found', 404)
    return ca, row, None


@bp.route('/api/v2/cas/<int:ca_id>/cross-certificates', methods=['GET'])
@require_auth(['read:cas'])
def list_cross_certificates(ca_id):
    ca, _, err = _ca_and_row(ca_id)
    if err:
        return err
    return success_response(data=[row.to_dict() for row in cross_certs.list_for(ca)])


@bp.route('/api/v2/cas/<int:ca_id>/cross-certificates', methods=['POST'])
@require_auth(['write:cas'])
def attach_cross_certificate(ca_id):
    """Body (JSON): ``{certificate: PEM, served?: bool}``. Not served unless asked."""
    ca, _, err = _ca_and_row(ca_id)
    if err:
        return err
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response('JSON body must be an object', 400)
    served = data.get('served', False)
    if not isinstance(served, bool):
        return error_response('served must be true or false', 400)
    try:
        cert = cross_certs.parse_certificate(data.get('certificate') or data.get('pem') or '')
        row, warnings = cross_certs.attach_certificate(ca, cert, _username(), served=served)
    except CrossCertError as e:
        db.session.rollback()
        return error_response(e.message, e.status, details={'code': e.code})
    cross_certs.announce(ca, 'attached', row, _username())
    return created_response({**row.to_dict(), 'warnings': warnings}, 'Cross-certificate attached')


@bp.route('/api/v2/cas/<int:ca_id>/cross-certificates/<int:xid>', methods=['GET'])
@require_auth(['read:cas'])
def get_cross_certificate(ca_id, xid):
    _, row, err = _ca_and_row(ca_id, xid)
    if err:
        return err
    return success_response(data=row.to_dict())


@bp.route('/api/v2/cas/<int:ca_id>/cross-certificates/<int:xid>', methods=['PATCH'])
@require_auth(['write:cas'])
def update_cross_certificate(ca_id, xid):
    """Body (JSON): ``{served: bool}``. At most one cross-certificate per CA is served."""
    ca, row, err = _ca_and_row(ca_id, xid)
    if err:
        return err
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('served'), bool):
        return error_response('served must be true or false', 400)
    try:
        cross_certs.set_served(ca, row, data['served'])
    except CrossCertError as e:
        db.session.rollback()
        return error_response(e.message, e.status, details={'code': e.code})
    cross_certs.announce(ca, 'served' if row.served else 'unserved', row, _username())
    return success_response(data=row.to_dict())


@bp.route('/api/v2/cas/<int:ca_id>/cross-certificates/<int:xid>', methods=['DELETE'])
@require_auth(['write:cas'])
def detach_cross_certificate(ca_id, xid):
    ca, row, err = _ca_and_row(ca_id, xid)
    if err:
        return err
    snapshot = row.to_dict()
    cross_certs.detach(row)
    AuditService.log_ca('ca_cross_certificate_detached', ca,
                        f'Cross-certificate detached from CA {ca.descr}: {snapshot["subject"]} by {snapshot["issuer"]}',
                        username=_username())
    from services.webhook_service import emit_ca_updated
    emit_ca_updated(ca.to_dict(), actor=_username(),
                    changes={'cross_certificate': 'detached', 'cross_certificate_id': snapshot['id']})
    return no_content_response()


@bp.route('/api/v2/cas/<int:ca_id>/cross-certificates/<int:xid>/revoke', methods=['POST'])
@require_auth(['write:cas'])
def revoke_cross_certificate(ca_id, xid):
    """Revoke the cross-certificate at its issuer; the CA it certifies is not revoked."""
    from utils.datetime_utils import to_naive_utc
    from utils.revocation_reasons import invalid_reason_message, normalize_revocation_reason
    ca, row, err = _ca_and_row(ca_id, xid)
    if err:
        return err
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
    if data.get('invalidity_date'):
        try:
            raw = str(data['invalidity_date']).strip().replace('Z', '+00:00')
            invalidity_at = to_naive_utc(datetime.fromisoformat(raw))
        except (ValueError, TypeError, OverflowError) as e:
            return error_response(f'Invalid invalidity_date: {e}', 400)
        from utils.datetime_utils import utc_now
        if invalidity_at > utc_now() + timedelta(minutes=5):
            return error_response('invalidity_date cannot be in the future', 400)
    if reason in ('certificateHold', 'certificate_hold'):
        return error_response('A cross-certificate cannot be put on hold: revocation is permanent', 400)
    if not row.revoked:
        issuer = cross_certs.issuer_of(row)
        # A serial the issuer already publishes needs no approval: only the row is brought in line
        if issuer is not None and not cross_certs.published_record(row, issuer):
            try:
                from services.approval_gate import approval_payload, queue_cross_revocation
                policy, approval = queue_cross_revocation(
                    g.current_user, row, issuer, reason=reason, invalidity_at=invalidity_at,
                    comment=data.get('approval_comment'))
            except Exception as e:
                logger.error(f"Policy evaluation failed for cross-certificate {xid}: {e}", exc_info=True)
                return error_response('Policy evaluation failed; the cross-certificate was not revoked', 500)
            if approval is not None:
                return success_response(data=approval_payload(policy, approval),
                                        message='Cross-certificate revocation submitted for approval')
    try:
        warnings = cross_certs.revoke(row, reason, _username(), invalidity_at)
        db.session.commit()
    except CrossCertError as e:
        db.session.rollback()
        return error_response(e.message, e.status, details={'code': e.code})
    cross_certs.announce(ca, 'revoked', row, _username(), {'reason': reason})
    return success_response(data={**row.to_dict(), 'warnings': warnings}, message='Cross-certificate revoked')


@bp.route('/api/v2/cas/<int:ca_id>/cross-certificates/<int:xid>/export', methods=['GET'])
@require_auth(['read:cas'])
def export_cross_certificate(ca_id, xid):
    """The certificate alone, whatever its state: ``?format=pem|der``."""
    from cryptography.hazmat.primitives import serialization
    ca, row, err = _ca_and_row(ca_id, xid)
    if err:
        return err
    fmt = (request.args.get('format') or 'pem').lower()
    if fmt not in ('pem', 'der'):
        return error_response('format must be pem or der', 400)
    try:
        cert = cross_certs.certificate_of(row)
    except CrossCertError as e:
        return error_response(e.message, e.status)
    name = f'{sanitize_filename(ca.descr or ca.refid)}-cross-{row.id}'
    if fmt == 'der':
        return Response(cert.public_bytes(serialization.Encoding.DER), mimetype='application/pkix-cert',
                        headers={'Content-Disposition': f'attachment; filename="{name}.cer"'})
    return Response(cert.public_bytes(serialization.Encoding.PEM), mimetype='application/x-pem-file',
                    headers={'Content-Disposition': f'attachment; filename="{name}.pem"'})

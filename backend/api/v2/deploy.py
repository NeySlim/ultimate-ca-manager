"""
Deploy Hooks Routes v2.0 (#299)

Admin-only: deploy targets hold SSH credentials that can run a command on
remote hosts, so every route sits behind the admin-only 'deploy' resource
and every mutation is audited.
"""

from flask import Blueprint, request, g
import logging

from sqlalchemy.exc import IntegrityError

from auth.unified import require_auth
from utils.response import success_response, error_response, created_response
from utils.pagination import parse_request_limit
from utils.db_transaction import safe_commit
from models import (
    db, CA, Certificate, DeployTarget, DeployBinding, CRLDeployBinding,
    DeployDelivery,
)
from services.deploy import DeployService
from fips_mode import FipsRestricted
from services.deploy.ssh import DeploySSHError, HostKeyMismatch
from services.audit_service import AuditService

logger = logging.getLogger(__name__)

bp = Blueprint('deploy_v2', __name__)


def _actor():
    for attr in ('current_user', 'user'):
        obj = getattr(g, attr, None)
        if obj is not None:
            username = getattr(obj, 'username', None) or (obj.get('username') if isinstance(obj, dict) else None)
            if username:
                return username
    return 'admin'


# ================================================================== targets

@bp.route('/api/v2/deploy/targets', methods=['GET'])
@require_auth(['read:deploy'])
def list_targets():
    targets = DeployTarget.query.order_by(DeployTarget.name.asc()).all()
    return success_response(data=[t.to_dict() for t in targets])


@bp.route('/api/v2/deploy/targets', methods=['POST'])
@require_auth(['write:deploy'])
def create_target():
    data = request.get_json() or {}
    name = str(data.get('name') or '').strip()
    if name and DeployTarget.query.filter_by(name=name).count():
        return error_response('A deploy target with this name already exists', 409)
    try:
        target = DeployService.create_target(data, username=_actor())
    except (ValueError, DeploySSHError) as e:
        db.session.rollback()
        return error_response(str(e), 400)

    ok, err = safe_commit(logger, 'Failed to create deploy target')
    if not ok:
        return err

    # Audit AFTER the business commit, for the reason written at
    # `create_binding` below (R-03): `log_action` commits the session it is
    # given and rolls all of it back when its own entry cannot be written, so
    # called first it decided whether the target survived. An audit failure
    # undid the target, the commit that followed committed an empty session
    # and reported success, and the route answered 201 with an identifier the
    # flush had handed out for a row that is not there.
    result = target.to_dict()
    AuditService.log_action(
        action='deploy_target_create', resource_type='deploy_target',
        resource_id=str(target.id), resource_name=target.name,
        details=f"Created deploy target {target.name} ({target.username}@{target.host}:{target.port})",
        success=True)
    return created_response(data=result, message='Deploy target created')


@bp.route('/api/v2/deploy/targets/<int:target_id>', methods=['GET'])
@require_auth(['read:deploy'])
def get_target(target_id):
    target = db.session.get(DeployTarget, target_id)
    if not target:
        return error_response('Deploy target not found', 404)
    data = target.to_dict()
    data['bindings'] = [b.to_dict(include_target=False) for b in target.bindings]
    data['crl_bindings'] = [b.to_dict(include_target=False) for b in target.crl_bindings]
    return success_response(data=data)


@bp.route('/api/v2/deploy/targets/<int:target_id>', methods=['PATCH'])
@require_auth(['write:deploy'])
def update_target(target_id):
    target = db.session.get(DeployTarget, target_id)
    if not target:
        return error_response('Deploy target not found', 404)
    data = request.get_json() or {}
    try:
        DeployService.update_target(target, data)
    except (ValueError, DeploySSHError) as e:
        db.session.rollback()
        return error_response(str(e), 400)

    ok, err = safe_commit(logger, 'Failed to update deploy target')
    if not ok:
        return err

    # Audit after the commit, as above: called first, its rollback undid the
    # change and the route answered 200 for an update that did not happen.
    AuditService.log_action(
        action='deploy_target_update', resource_type='deploy_target',
        resource_id=str(target.id), resource_name=target.name,
        details=f"Updated deploy target {target.name}", success=True)
    return success_response(data=target.to_dict(), message='Deploy target updated')


@bp.route('/api/v2/deploy/targets/<int:target_id>', methods=['DELETE'])
@require_auth(['delete:deploy'])
def delete_target(target_id):
    target = db.session.get(DeployTarget, target_id)
    if not target:
        return error_response('Deploy target not found', 404)
    name = target.name
    try:
        binding_ids = [b.id for b in target.bindings]
        crl_binding_ids = [b.id for b in target.crl_bindings]
        if binding_ids:
            DeployDelivery.query.filter(
                DeployDelivery.binding_type == DeployDelivery.BINDING_CERTIFICATE,
                DeployDelivery.binding_id.in_(binding_ids)).delete(synchronize_session=False)
            DeployBinding.query.filter(
                DeployBinding.id.in_(binding_ids)).delete(synchronize_session=False)
        if crl_binding_ids:
            DeployDelivery.query.filter(
                DeployDelivery.binding_type == DeployDelivery.BINDING_CRL,
                DeployDelivery.binding_id.in_(crl_binding_ids)).delete(synchronize_session=False)
            CRLDeployBinding.query.filter(
                CRLDeployBinding.id.in_(crl_binding_ids)).delete(synchronize_session=False)
        db.session.delete(target)
        ok, err = safe_commit(logger, 'Failed to delete deploy target')
        if not ok:
            return err
        # Audit after the commit, as everywhere else on this page: written
        # first, its own rollback put the target back and the route still
        # answered that it had been deleted.
        AuditService.log_action(
            action='deploy_target_delete', resource_type='deploy_target',
            resource_id=str(target_id), resource_name=name,
            details=(f"Deleted deploy target {name} and "
                     f"{len(binding_ids) + len(crl_binding_ids)} binding(s)"),
            success=True)
        return success_response(message='Deploy target deleted')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Failed to delete deploy target {target_id}: {e}')
        return error_response('Failed to delete deploy target', 500)


@bp.route('/api/v2/deploy/targets/<int:target_id>/test', methods=['POST'])
@require_auth(['write:deploy'])
def test_target(target_id):
    target = db.session.get(DeployTarget, target_id)
    if not target:
        return error_response('Deploy target not found', 404)
    try:
        result = DeployService.test_target(target)
    except HostKeyMismatch as e:
        db.session.rollback()
        return error_response(str(e), 409)
    except FipsRestricted:
        db.session.rollback()
        raise  # the app handler answers 400 with the FIPS problem type
    except DeploySSHError as e:
        db.session.rollback()
        return error_response(str(e), 502)
    except Exception as e:
        db.session.rollback()
        logger.error(f'Deploy target test failed unexpectedly: {e}', exc_info=True)
        return error_response('Connection test failed', 500)

    ok, err = safe_commit(logger, 'Failed to persist host key pin')
    if not ok:
        return err
    # Audit after the commit: the host key pin this test records is the point
    # of the call, and an audit failure used to undo it while the answer said
    # the connection was fine.
    AuditService.log_action(
        action='deploy_target_test', resource_type='deploy_target',
        resource_id=str(target.id), resource_name=target.name,
        details=f"Connection test succeeded for {target.name}", success=True)
    return success_response(data=result, message='Connection and SFTP OK')


# ================================================================= bindings

@bp.route('/api/v2/deploy/bindings', methods=['GET'])
@require_auth(['read:deploy'])
def list_bindings():
    query = DeployBinding.query
    cert_id = request.args.get('certificate_id', type=int)
    target_id = request.args.get('target_id', type=int)
    if cert_id:
        query = query.filter_by(certificate_id=cert_id)
    if target_id:
        query = query.filter_by(target_id=target_id)
    bindings = query.order_by(DeployBinding.id.asc()).all()

    # Attach the latest delivery per binding for status display
    result = []
    for b in bindings:
        data = b.to_dict()
        last = (DeployDelivery.query.filter_by(
                    binding_id=b.id,
                    binding_type=DeployDelivery.BINDING_CERTIFICATE)
                .order_by(DeployDelivery.id.desc()).first())
        data['last_delivery'] = last.to_dict() if last else None
        result.append(data)
    return success_response(data=result)


@bp.route('/api/v2/deploy/bindings', methods=['POST'])
@require_auth(['write:deploy'])
def create_binding():
    data = request.get_json() or {}
    target = db.session.get(DeployTarget, data.get('target_id') or 0)
    if not target:
        return error_response('Deploy target not found', 404)
    certificate = db.session.get(Certificate, data.get('certificate_id') or 0)
    if not certificate:
        return error_response('Certificate not found', 404)
    if not certificate.crt:
        return error_response('Certificate has no certificate data (CSR-only record)', 400)

    try:
        fields = DeployService.validate_binding_paths(data)
        DeployService.check_chain_variant(certificate, fields.get('chain_variant', 'auto'))
        DeployService.ensure_distinct_paths(
            fields.get('cert_path'), fields.get('key_path'), fields.get('fullchain_path'))
    except ValueError as e:
        return error_response(str(e), 400)
    if not any(fields.get(f) for f in ('cert_path', 'key_path', 'fullchain_path')):
        return error_response('At least one destination path is required', 400)
    if fields.get('key_path') and not certificate.prv:
        return error_response(
            'This certificate has no private key in UCM: remove the key path', 400)

    if DeployBinding.query.filter_by(
            target_id=target.id, certificate_id=certificate.id).first():
        return error_response('This certificate is already bound to this target', 409)

    binding = DeployBinding(
        target_id=target.id,
        certificate_id=certificate.id,
        created_by=_actor(),
        **fields,
    )
    cert_label = certificate.descr or certificate.refid
    db.session.add(binding)
    delivery = None
    # Binding + initial delivery commit in ONE transaction, flush protected:
    # a concurrent create races past the pre-check and must yield 409 (unique
    # constraint), never an unhandled 500 (review R-03).
    try:
        db.session.flush()
        # First push queued right away (drained by the scheduler with
        # retries) — the issued event can never match a binding created
        # after issuance. None when the binding or target is disabled.
        delivery = DeployService.enqueue_initial_push(binding, actor=_actor())
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error_response('This certificate is already bound to this target', 409)
    except Exception as e:
        db.session.rollback()
        logger.error(f'Failed to create deploy binding: {e}', exc_info=True)
        return error_response('Failed to create deploy binding', 500)

    queued = delivery is not None
    result = binding.to_dict()
    # Audit AFTER the business commit — its internal commit/rollback can no
    # longer undo the binding (R-03); wording reflects whether a delivery was
    # actually queued (R-04: a disabled binding/target is a valid state, not
    # an error, but must not be announced as queued).
    AuditService.log_action(
        action='deploy_binding_create', resource_type='deploy_target',
        resource_id=str(target.id), resource_name=target.name,
        details=(f"Bound certificate {cert_label} to {target.name}; "
                 + ('initial deployment queued' if queued else
                    'initial deployment not queued (binding or target disabled)')),
        success=True)
    message = ('Deploy binding created: initial deployment queued' if queued
               else 'Deploy binding created, no deployment queued (binding or target disabled)')
    return created_response(data=result, message=message)


@bp.route('/api/v2/deploy/bindings/<int:binding_id>', methods=['PATCH'])
@require_auth(['write:deploy'])
def update_binding(binding_id):
    binding = db.session.get(DeployBinding, binding_id)
    if not binding:
        return error_response('Deploy binding not found', 404)
    data = request.get_json() or {}
    try:
        fields = DeployService.validate_binding_paths(data, partial=True)
        if 'chain_variant' in fields:
            DeployService.check_chain_variant(binding.certificate, fields['chain_variant'])
    except ValueError as e:
        return error_response(str(e), 400)
    changed_fields = [key for key, value in fields.items()
                      if getattr(binding, key) != value]
    for key, value in fields.items():
        setattr(binding, key, value)
    if not any((binding.cert_path, binding.key_path, binding.fullchain_path)):
        db.session.rollback()
        return error_response('At least one destination path is required', 400)
    try:
        # Collision check on the FINAL state (a partial PATCH can collide
        # with a path that was already stored)
        DeployService.ensure_distinct_paths(
            binding.cert_path, binding.key_path, binding.fullchain_path)
    except ValueError as e:
        db.session.rollback()
        return error_response(str(e), 400)
    if binding.key_path and binding.certificate and not binding.certificate.prv:
        db.session.rollback()
        return error_response(
            'This certificate has no private key in UCM: remove the key path', 400)

    delivery = DeployService.deploy_binding_update_now(
        binding, DeployDelivery.BINDING_CERTIFICATE, actor=_actor())
    ok, err = safe_commit(logger, 'Failed to update deploy binding')
    if not ok:
        return err
    AuditService.log_action(
        action='deploy_binding_update', resource_type='deploy_target',
        resource_id=str(binding.target_id),
        resource_name=binding.target.name if binding.target else '?',
        details=(f"Updated certificate deploy binding {binding.id}; changed fields: "
                 f"{', '.join(changed_fields) if changed_fields else 'none'}"),
        success=True)
    if not delivery:
        message = 'Deploy binding updated, no deployment queued'
    elif delivery.status == DeployDelivery.STATUS_DELIVERED:
        message = 'Deploy binding updated and deployed successfully'
    elif delivery.status == DeployDelivery.STATUS_PENDING:
        message = 'Deploy binding updated; immediate deployment failed, retry queued'
    else:
        message = 'Deploy binding updated; deployment failed'
    return success_response(data=binding.to_dict(), message=message)


@bp.route('/api/v2/deploy/bindings/<int:binding_id>', methods=['DELETE'])
@require_auth(['delete:deploy'])
def delete_binding(binding_id):
    binding = db.session.get(DeployBinding, binding_id)
    if not binding:
        return error_response('Deploy binding not found', 404)
    target_name = binding.target.name if binding.target else '?'
    try:
        # Same helper as the webhook route, which had no such line at all.
        from services.delivery_retention import delete_binding_deliveries
        delete_binding_deliveries(binding.id)
        target_id = binding.target_id
        db.session.delete(binding)
        ok, err = safe_commit(logger, 'Failed to delete deploy binding')
        if not ok:
            return err
        # Audit after the commit, as its sibling above already did.
        AuditService.log_action(
            action='deploy_binding_delete', resource_type='deploy_target',
            resource_id=str(target_id), resource_name=target_name,
            details=f"Removed deploy binding {binding_id} from {target_name}",
            success=True)
        return success_response(message='Deploy binding deleted')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Failed to delete deploy binding {binding_id}: {e}')
        return error_response('Failed to delete deploy binding', 500)


@bp.route('/api/v2/deploy/bindings/<int:binding_id>/deploy', methods=['POST'])
@require_auth(['write:deploy'])
def deploy_now(binding_id):
    """Manual push — runs synchronously for immediate operator feedback."""
    binding = db.session.get(DeployBinding, binding_id)
    if not binding:
        return error_response('Deploy binding not found', 404)

    delivery = DeployDelivery(
        binding_id=binding.id,
        binding_type=DeployDelivery.BINDING_CERTIFICATE,
        event_type='manual',
        status=DeployDelivery.STATUS_PENDING,
        attempts=1,
        max_attempts=1,  # manual runs don't retry in the background
        triggered_by=_actor(),
    )
    db.session.add(delivery)
    ok = DeployService.execute_delivery(delivery)
    ok_commit, err = safe_commit(logger, 'Failed to record deploy delivery')
    if not ok_commit:
        return err
    if ok:
        return success_response(data=delivery.to_dict(), message='Deployed successfully')
    return error_response(delivery.last_error or 'Deploy failed', 502)


# =========================================================== CRL bindings

@bp.route('/api/v2/deploy/crl-bindings', methods=['GET'])
@require_auth(['read:deploy'])
def list_crl_bindings():
    query = CRLDeployBinding.query
    ca_id = request.args.get('ca_id', type=int)
    target_id = request.args.get('target_id', type=int)
    if ca_id:
        query = query.filter_by(ca_id=ca_id)
    if target_id:
        query = query.filter_by(target_id=target_id)
    bindings = query.order_by(CRLDeployBinding.id.asc()).all()
    result = []
    for binding in bindings:
        data = binding.to_dict()
        last = (DeployDelivery.query.filter_by(
                    binding_id=binding.id,
                    binding_type=DeployDelivery.BINDING_CRL)
                .order_by(DeployDelivery.id.desc()).first())
        data['last_delivery'] = last.to_dict() if last else None
        result.append(data)
    return success_response(data=result)


@bp.route('/api/v2/deploy/crl-bindings', methods=['POST'])
@require_auth(['write:deploy'])
def create_crl_binding():
    data = request.get_json() or {}
    target = db.session.get(DeployTarget, data.get('target_id') or 0)
    if not target:
        return error_response('Deploy target not found', 404)
    ca = db.session.get(CA, data.get('ca_id') or 0)
    if not ca:
        return error_response('CA not found', 404)
    if CRLDeployBinding.query.filter_by(target_id=target.id, ca_id=ca.id).first():
        return error_response('This CA CRL is already bound to this target', 409)
    try:
        fields = DeployService.validate_crl_binding(data)
        DeployService._latest_complete_crl(ca.id)
    except ValueError as e:
        return error_response(str(e), 400)

    binding = CRLDeployBinding(
        target_id=target.id, ca_id=ca.id, created_by=_actor(), **fields)
    db.session.add(binding)
    delivery = None
    try:
        db.session.flush()
        delivery = DeployService.enqueue_initial_crl_push(binding, actor=_actor())
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error_response('This CA CRL is already bound to this target', 409)
    except Exception as e:
        db.session.rollback()
        logger.error(f'Failed to create CRL deploy binding: {e}', exc_info=True)
        return error_response('Failed to create CRL deploy binding', 500)

    queued = delivery is not None
    result = binding.to_dict()
    AuditService.log_action(
        action='crl_deploy_binding_create', resource_type='deploy_target',
        resource_id=str(target.id), resource_name=target.name,
        details=(f"Bound CRL for {ca.descr} to {target.name}; "
                 + ('initial deployment queued' if queued else
                    'initial deployment not queued (binding or target disabled)')),
        success=True)
    message = ('CRL deploy binding created: initial deployment queued' if queued
               else 'CRL deploy binding created, no deployment queued')
    return created_response(data=result, message=message)


@bp.route('/api/v2/deploy/crl-bindings/<int:binding_id>', methods=['PATCH'])
@require_auth(['write:deploy'])
def update_crl_binding(binding_id):
    binding = db.session.get(CRLDeployBinding, binding_id)
    if not binding:
        return error_response('CRL deploy binding not found', 404)
    data = dict(request.get_json() or {})
    data['current_format'] = binding.format
    data['current_include_parent_crls'] = binding.include_parent_crls
    try:
        fields = DeployService.validate_crl_binding(data, partial=True)
    except ValueError as e:
        return error_response(str(e), 400)
    changed_fields = [key for key, value in fields.items()
                      if getattr(binding, key) != value]
    for key, value in fields.items():
        setattr(binding, key, value)
    delivery = DeployService.deploy_binding_update_now(
        binding, DeployDelivery.BINDING_CRL, actor=_actor())
    ok, err = safe_commit(logger, 'Failed to update CRL deploy binding')
    if not ok:
        return err
    AuditService.log_action(
        action='crl_deploy_binding_update', resource_type='deploy_target',
        resource_id=str(binding.target_id),
        resource_name=binding.target.name if binding.target else '?',
        details=(f"Updated CRL deploy binding {binding.id}; changed fields: "
                 f"{', '.join(changed_fields) if changed_fields else 'none'}"),
        success=True)
    if not delivery:
        message = 'CRL deploy binding updated, no deployment queued'
    elif delivery.status == DeployDelivery.STATUS_DELIVERED:
        message = 'CRL deploy binding updated and deployed successfully'
    elif delivery.status == DeployDelivery.STATUS_PENDING:
        message = 'CRL deploy binding updated; immediate deployment failed, retry queued'
    else:
        message = 'CRL deploy binding updated; deployment failed'
    return success_response(data=binding.to_dict(), message=message)


@bp.route('/api/v2/deploy/crl-bindings/<int:binding_id>', methods=['DELETE'])
@require_auth(['delete:deploy'])
def delete_crl_binding(binding_id):
    binding = db.session.get(CRLDeployBinding, binding_id)
    if not binding:
        return error_response('CRL deploy binding not found', 404)
    target_id = binding.target_id
    target_name = binding.target.name if binding.target else '?'
    try:
        from services.delivery_retention import delete_binding_deliveries
        delete_binding_deliveries(binding.id, DeployDelivery.BINDING_CRL)
        db.session.delete(binding)
        ok, err = safe_commit(logger, 'Failed to delete CRL deploy binding')
        if not ok:
            return err
        AuditService.log_action(
            action='crl_deploy_binding_delete', resource_type='deploy_target',
            resource_id=str(target_id), resource_name=target_name,
            details=f"Removed CRL deploy binding {binding_id} from {target_name}",
            success=True)
        return success_response(message='CRL deploy binding deleted')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Failed to delete CRL deploy binding {binding_id}: {e}')
        return error_response('Failed to delete CRL deploy binding', 500)


@bp.route('/api/v2/deploy/crl-bindings/<int:binding_id>/deploy', methods=['POST'])
@require_auth(['write:deploy'])
def deploy_crl_now(binding_id):
    binding = db.session.get(CRLDeployBinding, binding_id)
    if not binding:
        return error_response('CRL deploy binding not found', 404)
    delivery = DeployDelivery(
        binding_id=binding.id,
        binding_type=DeployDelivery.BINDING_CRL,
        event_type='manual',
        status=DeployDelivery.STATUS_PENDING,
        attempts=1,
        max_attempts=1,
        triggered_by=_actor(),
    )
    db.session.add(delivery)
    ok = DeployService.execute_delivery(delivery)
    ok_commit, err = safe_commit(logger, 'Failed to record CRL deploy delivery')
    if not ok_commit:
        return err
    if ok:
        return success_response(data=delivery.to_dict(), message='CRL deployed successfully')
    return error_response(delivery.last_error or 'CRL deploy failed', 502)


# =============================================================== deliveries

@bp.route('/api/v2/deploy/deliveries', methods=['GET'])
@require_auth(['read:deploy'])
def list_deliveries():
    query = DeployDelivery.query
    binding_id = request.args.get('binding_id', type=int)
    cert_id = request.args.get('certificate_id', type=int)
    if binding_id:
        binding_type = request.args.get('binding_type', 'certificate')
        if binding_type not in ('certificate', 'crl'):
            return error_response('binding_type must be certificate or crl', 400)
        query = query.filter_by(binding_id=binding_id, binding_type=binding_type)
    elif cert_id:
        binding_ids = [b.id for b in DeployBinding.query.filter_by(certificate_id=cert_id)]
        if not binding_ids:
            return success_response(data=[])
        query = query.filter(
            DeployDelivery.binding_type == DeployDelivery.BINDING_CERTIFICATE,
            DeployDelivery.binding_id.in_(binding_ids))
    limit = parse_request_limit(50, 200)
    deliveries = query.order_by(DeployDelivery.id.desc()).limit(limit).all()
    return success_response(data=[d.to_dict() for d in deliveries])


@bp.route('/api/v2/deploy/deliveries/<int:delivery_id>/retry', methods=['POST'])
@require_auth(['write:deploy'])
def retry_delivery(delivery_id):
    delivery = db.session.get(DeployDelivery, delivery_id)
    if not delivery:
        return error_response('Delivery not found', 404)
    if delivery.status != DeployDelivery.STATUS_FAILED:
        return error_response('Only failed deliveries can be retried', 400)
    from utils.datetime_utils import utc_now
    delivery.status = DeployDelivery.STATUS_PENDING
    delivery.attempts = 0
    delivery.max_attempts = DeployService.DEFAULT_MAX_ATTEMPTS
    delivery.next_attempt_at = utc_now()
    delivery.last_error = None
    delivery.triggered_by = _actor()
    ok, err = safe_commit(logger, 'Failed to requeue delivery')
    if not ok:
        return err
    return success_response(data=delivery.to_dict(), message='Delivery requeued')

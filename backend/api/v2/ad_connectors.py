"""
Active Directory connectors collection
/api/v2/ad-connectors/* -- one stored LDAP connection per directory (forest or
domain). Secrets are never returned: the bind password reads back as ``***``.
"""
import logging

from flask import Blueprint, g, request
from sqlalchemy.exc import IntegrityError

from auth.unified import require_auth
from api.v2.ad_connector import (
    _ad_retarget_error, apply_fields, refresh_domain_sid, run_saved_test, run_unsaved_test,
)
from models import db, ADConnectorConfig
from services.ad_connector import lookup
from services.audit_service import AuditService
from services.deletion_blockers import connector_deletion_blockers, first_blocker
from utils.datetime_utils import utc_now
from utils.db_transaction import safe_commit
from utils.response import success_response, error_response, no_content_response

logger = logging.getLogger(__name__)

bp = Blueprint('ad_connectors_v2', __name__)

MAX_NAME_LEN = 100


def _audit(action, config, details):
    AuditService.log_action(
        action=action, resource_type='ad_connector', resource_id=str(config.id),
        resource_name=config.name, details=details, success=True,
    )


def _name_error(data, current=None):
    """(name, error): the submitted name, free and within bounds."""
    name = data.get('name')
    if not isinstance(name, str) or not name.strip():
        return None, error_response('name is required', 400)
    name = name.strip()
    if len(name) > MAX_NAME_LEN:
        return None, error_response('name is too long', 400)
    taken = ADConnectorConfig.query.filter(ADConnectorConfig.name == name)
    if current is not None:
        taken = taken.filter(ADConnectorConfig.id != current.id)
    if taken.count():
        return None, error_response(f"A connector named '{name}' already exists", 409)
    return name, None


def _serve_default_profile(config):
    """A default profile with no connector is served by the first one created, as the
    single-connector route does, so the protocols use what the screen shows."""
    from services import windows_profiles
    profile = windows_profiles.default_profile()
    if profile is not None:
        db.session.flush()
        if profile.connector_id is None:
            profile.connector_id = config.id
        windows_profiles.fill_realm(profile)


def _save(config, creating):
    config.updated_at = utc_now()
    try:
        refresh_domain_sid(config)
        if creating:
            _serve_default_profile(config)
        # A name a concurrent save took is refused here: safe_commit would answer 500
        db.session.flush()
        ok, err = safe_commit(logger, 'Failed to save the AD connector')
        if not ok:
            return err
    except IntegrityError:
        db.session.rollback()
        return error_response('A connector with this name already exists', 409)
    except Exception as e:
        # A failed flush or profile update stores nothing; the password setter ran before
        db.session.rollback()
        logger.error('Failed to save the AD connector: %s', e)
        return error_response('Failed to save configuration (encryption unavailable?)', 500)
    return None


def _requires_realm(config):
    if not config.base_dn or not lookup.realm_of_base_dn(config.base_dn):
        return error_response('base_dn must name the domain with DC components, '
                              'such as DC=corp,DC=example', 400)
    return None


@bp.route('/api/v2/ad-connectors', methods=['GET'])
@require_auth(['read:ad_connector'])
def list_connectors():
    rows = ADConnectorConfig.query.order_by(ADConnectorConfig.id).all()
    return success_response(data=[row.to_dict() for row in rows])


@bp.route('/api/v2/ad-connectors/<int:connector_id>', methods=['GET'])
@require_auth(['read:ad_connector'])
def get_connector(connector_id):
    config = db.session.get(ADConnectorConfig, connector_id)
    if config is None:
        return error_response('Connector not found', 404)
    return success_response(data=config.to_dict())


@bp.route('/api/v2/ad-connectors', methods=['POST'])
@require_auth(['write:ad_connector'])
def create_connector():
    data = request.json or {}
    name, err = _name_error(data)
    if err:
        return err
    config = ADConnectorConfig(name=name, created_by=g.user.username if getattr(g, 'user', None) else None)
    db.session.add(config)
    err = apply_fields(config, data) or _requires_realm(config)
    if err:
        db.session.rollback()
        return err
    err = _save(config, True)
    if err:
        return err
    _audit('ad_connector_create', config, f'Created AD connector {config.name}')
    return success_response(data=config.to_dict(), message='AD connector created', status=201)


@bp.route('/api/v2/ad-connectors/<int:connector_id>', methods=['PUT'])
@require_auth(['write:ad_connector'])
def update_connector(connector_id):
    config = db.session.get(ADConnectorConfig, connector_id)
    if config is None:
        return error_response('Connector not found', 404)
    data = request.json or {}
    err = _ad_retarget_error(config, data)
    if err:
        return err
    if 'name' in data:
        name, err = _name_error(data, config)
        if err:
            return err
        config.name = name
    err = apply_fields(config, data) or _requires_realm(config)
    if err:
        db.session.rollback()
        return err
    err = _save(config, False)
    if err:
        return err
    _audit('ad_connector_update', config, f'Updated AD connector {config.name}')
    return success_response(data=config.to_dict(), message='AD connector saved')


@bp.route('/api/v2/ad-connectors/<int:connector_id>', methods=['DELETE'])
@require_auth(['write:ad_connector'])
def delete_connector(connector_id):
    config = db.session.get(ADConnectorConfig, connector_id)
    if config is None:
        return error_response('Connector not found', 404)
    blocker = first_blocker(connector_deletion_blockers(config))
    if blocker:
        return error_response(blocker.message, blocker.status)
    name = config.name
    db.session.delete(config)
    ok, err = safe_commit(logger, 'Failed to delete the AD connector')
    if not ok:
        return err
    AuditService.log_action(
        action='ad_connector_delete', resource_type='ad_connector', resource_id=str(connector_id),
        resource_name=name, details=f'Deleted AD connector {name}', success=True,
    )
    return no_content_response()


@bp.route('/api/v2/ad-connectors/<int:connector_id>/test', methods=['POST'])
@require_auth(['write:ad_connector'])
def test_connector(connector_id):
    """Test the saved connector; the verdict and the domain SID are stored on its row."""
    config = db.session.get(ADConnectorConfig, connector_id)
    if config is None:
        return error_response('Connector not found', 404)
    return run_saved_test(config)


@bp.route('/api/v2/ad-connectors/test', methods=['POST'])
@require_auth(['write:ad_connector'])
def test_values():
    """Test values not saved yet. A blank password falls back to connector ``id``'s saved one,
    for the target it was saved for only."""
    data = request.json or {}
    saved = None
    if data.get('id') is not None:
        saved = db.session.get(ADConnectorConfig, data['id']) if isinstance(data['id'], int) else None
        if saved is None:
            return error_response('Connector not found', 404)
    return run_unsaved_test(data, saved)

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
from models import db, ADConnectorConfig, WindowsEnrollmentProfile
from services import windows_profiles
from services.ad_connector import lookup
from services.audit_service import AuditService
from services.deletion_blockers import connector_deletion_blockers, first_blocker
from utils.datetime_utils import utc_now
from utils.db_transaction import safe_commit
from utils.response import success_response, error_response, no_content_response

logger = logging.getLogger(__name__)

bp = Blueprint('ad_connectors_v2', __name__)

MAX_NAME_LEN = 100
MAX_LISTED_PROFILES = 50


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


def _stage(config, creating, followed=()):
    """Everything of a save but its commit, which the route does before it audits."""
    config.updated_at = utc_now()
    moved = (followed[0].realm, [p.id for p in followed]) if followed else None
    try:
        refresh_domain_sid(config)
        if creating:
            _serve_default_profile(config)
        # A name a concurrent save took is refused here: safe_commit would answer 500
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        # A concurrent save gave another profile the realm the followers were moving to
        if moved and WindowsEnrollmentProfile.query.filter(
                WindowsEnrollmentProfile.realm == moved[0], ~WindowsEnrollmentProfile.id.in_(moved[1])).first():
            return error_response(f'{moved[0]} is already served by another profile', 409)
        return error_response('A connector with this name already exists', 409)
    except Exception as e:
        # A failed flush or profile update stores nothing; the password setter ran before
        db.session.rollback()
        logger.error('Failed to save the AD connector: %s', e)
        return error_response('Failed to save configuration (encryption unavailable?)', 500)
    return None


KEYTAB_FIXES_REALM = 'its keytab fixes its realm'


def _follow_realm(config, old_realm):
    """Move the realm of the profiles of *config* to its new domain, in the caller's transaction.
    Returns (error response, followed profiles): a profile with a keytab, or whose realm was not
    the old domain, or a realm another profile holds, refuses the whole save."""
    new_realm = lookup.realm_of_base_dn(config.base_dn)
    if not old_realm or new_realm == old_realm:
        return None, []
    # No autoflush: the connector UPDATE must not reach the database before the DC bind
    with db.session.no_autoflush:
        using = WindowsEnrollmentProfile.query.filter_by(connector_id=config.id).order_by(
            WindowsEnrollmentProfile.name).all()
        follow, refused = [], []
        for profile in using:
            if profile.realm is None or profile.realm == new_realm:
                continue
            if profile.keytab:
                refused.append((profile, KEYTAB_FIXES_REALM))
            elif profile.realm != old_realm:
                refused.append((profile, f'its realm is {profile.realm}, not {old_realm}'))
            elif windows_profiles.realm_problem(new_realm, profile):
                refused.append((profile, f'{new_realm} is already served by another profile'))
            else:
                follow.append(profile)
    if refused:
        db.session.rollback()
        listed = '; '.join(f'profile {p.name}: {why}' for p, why in refused[:5])
        more = f' (and {len(refused) - 5} more)' if len(refused) > 5 else ''
        # A keytab holds the realm of its profile: only another connector (or none) is left to it
        exits = []
        if any(why == KEYTAB_FIXES_REALM for _p, why in refused):
            exits.append('give a profile with a keytab another connector, or none')
        if any(why != KEYTAB_FIXES_REALM for _p, why in refused):
            exits.append('change the realm of the other profiles, or give them another connector')
        return error_response(
            f'Cannot move connector {config.name} from {old_realm} to {new_realm}: {listed}{more}. '
            f'First {" and ".join(exits)}.', 409,
            details={'profiles': [{'id': p.id, 'name': p.name, 'reason': why}
                                  for p, why in refused[:MAX_LISTED_PROFILES]],
                     'total': len(refused)}), []
    for profile in follow:
        profile.realm = new_realm
    return None, follow


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
    err = _stage(config, True)
    if err:
        return err
    ok, err = safe_commit(logger, 'Failed to save the AD connector')
    if not ok:
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
    old_realm = lookup.realm_of_base_dn(config.base_dn)
    if 'name' in data:
        name, err = _name_error(data, config)
        if err:
            return err
        config.name = name
    err = apply_fields(config, data) or _requires_realm(config)
    if err:
        db.session.rollback()
        return err
    err, followed = _follow_realm(config, old_realm)
    if err:
        return err
    err = _stage(config, False, followed)
    if err:
        return err
    ok, err = safe_commit(logger, 'Failed to save the AD connector')
    if not ok:
        return err
    details = f'Updated AD connector {config.name}'
    if followed:
        details += f'; realm {old_realm} -> {lookup.realm_of_base_dn(config.base_dn)} of profile ' + ', '.join(p.name for p in followed)
    _audit('ad_connector_update', config, details)
    return success_response(data=config.to_dict(), message='AD connector saved')


@bp.route('/api/v2/ad-connectors/<int:connector_id>', methods=['DELETE'])
@require_auth(['write:ad_connector'])
def delete_connector(connector_id):
    config = db.session.get(ADConnectorConfig, connector_id)
    if config is None:
        return error_response('Connector not found', 404)
    blocker = first_blocker(connector_deletion_blockers(config))
    if blocker:
        # The profiles that use it ride along, so the screen can name them
        query = WindowsEnrollmentProfile.query.filter_by(connector_id=config.id)
        using = query.order_by(WindowsEnrollmentProfile.name).limit(MAX_LISTED_PROFILES).all()
        return error_response(blocker.message, blocker.status, details={
            'profiles': [{'id': p.id, 'name': p.name} for p in using], 'total': query.count()})
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
        saved = db.session.get(ADConnectorConfig, data['id']) if type(data['id']) is int else None
        if saved is None:
            return error_response('Connector not found', 404)
    return run_unsaved_test(data, saved)

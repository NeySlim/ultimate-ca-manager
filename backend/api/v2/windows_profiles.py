"""
Windows enrollment profiles v2.0
/api/v2/windows-profiles - one realm each, served by XCEP, WSTEP and Kerberos
"""
import json
import logging

from flask import Blueprint, g, request

from auth.unified import require_auth
from models import CA, ADConnectorConfig, Certificate, WindowsEnrollmentProfile, WindowsProfileTemplate, db
from services import windows_profiles
from services.audit_service import AuditService
from services.ad_connector import lookup
from services.deletion_blockers import first_blocker, windows_profile_deletion_blockers
from utils.db_transaction import safe_commit
from utils.pagination import parse_request_pagination
from utils.response import error_response, success_response
from utils.signing_ca import signing_ca_problem, xcep_ca_problem
from utils.validity import (MAX_VALIDITY_DAYS, MIN_VALIDITY_DAYS, coerce_validity_days,
                            validity_days_in_range)

logger = logging.getLogger(__name__)

bp = Blueprint('windows_profiles_v2', __name__)

MAX_PER_PAGE = 200
# Spelled apart from the column names: the 2.x setting keys are not named in code (tested)
SERVICES = ('xcep', 'wstep')
WRITABLE = ('name', 'realm', 'enabled', 'is_default', 'connector_id', 'issuing_ca_refid',
            'policy_ca_refid', 'validity_days', 'allowed_ad_group', 'pinned_subject_fields',
            *(f'{svc}_{part}' for svc in SERVICES for part in ('username', 'password')))


def _actor():
    return getattr(getattr(g, 'current_user', None), 'username', None)


def _render(profile, ca_names):
    """The profile as the API shows it: passwords and keytab only as set/unset flags."""
    return {
        'id': profile.id,
        'name': profile.name,
        'realm': profile.realm,
        'is_default': bool(profile.is_default),
        'enabled': bool(profile.enabled),
        'connector_id': profile.connector_id,
        'issuing_ca_refid': profile.issuing_ca_refid,
        'issuing_ca_name': ca_names.get(profile.issuing_ca_refid),
        'policy_ca_refid': profile.policy_ca_refid,
        'policy_ca_name': ca_names.get(profile.policy_ca_refid),
        'validity_days': profile.validity_days,
        **{f'{svc}_username': getattr(profile, f'{svc}_username') or '' for svc in SERVICES},
        **{f'{svc}_password_set': bool(getattr(profile, f'{svc}_password')) for svc in SERVICES},
        'allowed_ad_group': profile.allowed_ad_group,
        'pinned_subject_fields': profile.pinned_subject_fields,
        'keytab_set': bool(profile.keytab),
        'created_at': profile.created_at.isoformat() if profile.created_at else None,
        'updated_at': profile.updated_at.isoformat() if profile.updated_at else None,
    }


def _ca_names(profiles):
    refids = {r for p in profiles for r in (p.issuing_ca_refid, p.policy_ca_refid) if r}
    if not refids:
        return {}
    return {c.refid: (c.descr or c.common_name)
            for c in CA.query.filter(CA.refid.in_(refids)).all()}


def _escape_like(text):
    return text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def _apply(profile, data):
    """Validate *data* and set it on *profile*; an (message, status) pair when refused."""
    if 'name' in data:
        name = data['name']
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
            return 'name must be a non-empty string of 100 characters at most', 400
        name = name.strip()
        other = WindowsEnrollmentProfile.query.filter(WindowsEnrollmentProfile.name == name)
        if profile.id is not None:
            other = other.filter(WindowsEnrollmentProfile.id != profile.id)
        if other.first() is not None:
            return f'a profile named {name} already exists', 409
        profile.name = name
    elif profile.id is None:
        return 'name is required', 400

    if 'realm' in data:
        realm = data['realm']
        # Only an explicit null clears the realm; a blank string is a mistake
        if isinstance(realm, str) and realm.strip():
            realm = realm.strip().upper()
        if realm is not None:
            problem = windows_profiles.realm_problem(realm, profile)
            if problem:
                return problem
        profile.realm = realm

    for flag in ('is_default', 'enabled'):
        if flag in data and type(data[flag]) is not bool:
            return f'{flag} must be a JSON boolean', 400

    if 'is_default' in data:
        wanted = data['is_default']
        if profile.id is None and wanted:
            if windows_profiles.default_profile() is not None:
                return 'there is already a default profile', 409
            profile.is_default = True
        elif wanted != bool(profile.is_default):
            return 'the default profile cannot be changed here', 409
    if 'enabled' in data:
        profile.enabled = data['enabled']

    for field, check in (('issuing_ca_refid', signing_ca_problem), ('policy_ca_refid', xcep_ca_problem)):
        if field not in data:
            continue
        if data[field] is not None and not isinstance(data[field], str):
            return f'{field} must be a string', 400
        refid = data[field] or None
        if refid:
            ca = CA.query.filter_by(refid=refid).first()
            if ca is None:
                return 'CA not found', 404
            # Checked when chosen only: a CA already saved stays saveable
            if refid != getattr(profile, field) and check(ca):
                return check(ca), 400
        setattr(profile, field, refid)

    if 'validity_days' in data:
        days = coerce_validity_days(data['validity_days'])
        if days is None:
            return 'validity_days must be an integer', 400
        if not validity_days_in_range(days):
            return f'validity_days must be between {MIN_VALIDITY_DAYS} and {MAX_VALIDITY_DAYS}', 400
        profile.validity_days = days

    if 'pinned_subject_fields' in data:
        pinned, err = _pinned_subject_fields(data['pinned_subject_fields'])
        if err:
            return err, 400
        profile.pinned_subject_fields = pinned
    for field in ('allowed_ad_group', *(f'{svc}_username' for svc in SERVICES)):
        if field in data:
            value = data[field]
            if value is not None and not isinstance(value, str):
                return f'{field} must be a string', 400
            setattr(profile, field, value or None)
    for field in (f'{svc}_password' for svc in SERVICES):
        if data.get(field):
            from utils.password_hash import hash_password
            setattr(profile, field, hash_password(str(data[field])))

    if data.get('connector_id') is not None and type(data['connector_id']) is not int:
        return 'connector_id must be an integer', 400
    if 'connector_id' in data and data['connector_id'] is not None:
        if db.session.get(ADConnectorConfig, data['connector_id']) is None:
            return 'connector not found', 404
        profile.connector_id = data['connector_id']
    elif 'connector_id' in data:
        profile.connector_id = None
    # Checked when chosen only, as the CAs: a pair saved elsewhere stays saveable
    if 'realm' in data or 'connector_id' in data:
        return _connector_problem(profile)
    return None


def _pinned_subject_fields(value):
    """(stored JSON or None, error): an object or its JSON text, checked as a template's pins."""
    from api.v2.templates import _clean_pinned_subject_fields
    if isinstance(value, str):
        try:
            value = json.loads(value) if value.strip() else None
        except ValueError:
            return None, 'pinned_subject_fields must be a JSON object'
    if value is not None and not isinstance(value, dict):
        return None, 'pinned_subject_fields must be an object'
    try:
        cleaned, err = _clean_pinned_subject_fields(value)
    except AttributeError:
        return None, 'pinned_subject_fields values must be strings'
    if err:
        return None, err
    return (json.dumps(cleaned) if cleaned else None), None


def _connector_problem(profile):
    """The connector's domain must be the profile's realm (A1): the DN realm is compared exactly."""
    if not profile.connector_id or not profile.realm:
        return None
    connector = db.session.get(ADConnectorConfig, profile.connector_id)
    realm = lookup.realm_of_base_dn(connector.base_dn) if connector is not None else None
    if realm and realm != profile.realm:
        return (f'the connector serves the domain {realm}, not the realm {profile.realm} '
                'of this profile'), 400
    return None


def _recompose_keytab():
    """Recompose the served keytab from the profiles, in the caller's transaction;
    an (message, status) pair when a keytab cannot be decrypted here."""
    from sqlalchemy.exc import SQLAlchemyError
    from services import cluster_commands
    try:
        windows_profiles.publish_keytab(actor=_actor())
    except ValueError as e:
        db.session.rollback()
        return f'Keytab not composed: {e}', 409
    except SQLAlchemyError:
        # The composition flushes the profile: a write the database refuses ends as a commit would
        db.session.rollback()
        logger.error('Windows enrollment profile not saved with its keytab', exc_info=True)
        return 'Failed to save the Windows enrollment profile', 500
    cluster_commands.emit(cluster_commands.RELOAD_KEYTAB)
    return None


def _write_keytab_file():
    """This node's file follows the stored keytab; a failure is left to the next reload."""
    from services.kerberos import negotiate_auth
    try:
        negotiate_auth.write_stored_keytab()
    except (OSError, ValueError) as e:
        logger.error('Failed to write the Kerberos keytab file: %s', e)


def _audit(action, profile, details):
    AuditService.log_action(action=action, resource_type='windows_profile',
                            resource_id=str(profile.id), resource_name=profile.name,
                            details=details, success=True)


@bp.route('/api/v2/windows-profiles', methods=['GET'])
@require_auth(['read:xcep'])
def list_windows_profiles():
    """Profiles, paginated; ``q`` matches the name or the realm."""
    page, per_page = parse_request_pagination(default_per_page=25, max_per_page=MAX_PER_PAGE)
    query = WindowsEnrollmentProfile.query
    q = (request.args.get('q') or '').strip()
    if q:
        like = f'%{_escape_like(q)}%'
        query = query.filter(db.or_(WindowsEnrollmentProfile.name.ilike(like, escape='\\'),
                                    WindowsEnrollmentProfile.realm.ilike(like, escape='\\')))
    query = query.order_by(WindowsEnrollmentProfile.name, WindowsEnrollmentProfile.id)
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    names = _ca_names(pagination.items)
    return success_response(
        data=[_render(p, names) for p in pagination.items],
        meta={'total': pagination.total, 'page': page, 'per_page': per_page,
              'total_pages': pagination.pages})


@bp.route('/api/v2/windows-profiles/<int:profile_id>', methods=['GET'])
@require_auth(['read:xcep'])
def get_windows_profile(profile_id):
    profile = db.session.get(WindowsEnrollmentProfile, profile_id)
    if profile is None:
        return error_response('Profile not found', 404)
    return success_response(data=_render(profile, _ca_names([profile])))


@bp.route('/api/v2/windows-profiles', methods=['POST'])
@require_auth(['write:xcep'])
def create_windows_profile():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response('A JSON object is required', 400)
    profile = WindowsEnrollmentProfile(enabled=True, is_default=False, created_by=_actor(),
                                       updated_by=_actor())
    problem = _apply(profile, {k: v for k, v in data.items() if k in WRITABLE})
    if problem:
        db.session.rollback()
        return error_response(problem[0], problem[1])
    db.session.add(profile)
    ok, err = safe_commit(logger, 'Failed to create the Windows enrollment profile')
    if not ok:
        return err
    _audit('windows_profile_create', profile, f'Created Windows enrollment profile {profile.name}')
    return success_response(data=_render(profile, _ca_names([profile])),
                            message='Profile created', status=201)


@bp.route('/api/v2/windows-profiles/<int:profile_id>', methods=['PUT', 'PATCH'])
@require_auth(['write:xcep'])
def update_windows_profile(profile_id):
    profile = db.session.get(WindowsEnrollmentProfile, profile_id)
    if profile is None:
        return error_response('Profile not found', 404)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response('A JSON object is required', 400)
    changed = sorted(k for k in data if k in WRITABLE)
    problem = _apply(profile, {k: v for k, v in data.items() if k in WRITABLE})
    if problem:
        db.session.rollback()
        return error_response(problem[0], problem[1])
    profile.updated_by = _actor()
    ok, err = safe_commit(logger, 'Failed to update the Windows enrollment profile')
    if not ok:
        return err
    _audit('windows_profile_update', profile,
           f"Updated Windows enrollment profile {profile.name}; fields: {', '.join(changed) or 'none'}")
    return success_response(data=_render(profile, _ca_names([profile])), message='Profile updated')


@bp.route('/api/v2/windows-profiles/<int:profile_id>', methods=['DELETE'])
@require_auth(['write:xcep'])
def delete_windows_profile(profile_id):
    profile = db.session.get(WindowsEnrollmentProfile, profile_id)
    if profile is None:
        return error_response('Profile not found', 404)
    blocker = first_blocker(windows_profile_deletion_blockers(profile))
    if blocker:
        return error_response(blocker.message, blocker.status)
    name = profile.name
    held_keytab = bool(profile.keytab)
    # SQLite enforces no key: the template links go with their profile explicitly
    WindowsProfileTemplate.query.filter_by(profile_id=profile.id).delete()
    # No key either: a dangling id would be inherited by a later profile reusing it
    Certificate.query.filter_by(windows_profile_id=profile.id).update(
        {'windows_profile_id': None}, synchronize_session=False)
    db.session.delete(profile)
    if held_keytab:
        problem = _recompose_keytab()
        if problem:
            return error_response(problem[0], problem[1])
    ok, err = safe_commit(logger, 'Failed to delete the Windows enrollment profile')
    if not ok:
        return err
    if held_keytab:
        _write_keytab_file()
    AuditService.log_action(action='windows_profile_delete', resource_type='windows_profile',
                            resource_id=str(profile_id), resource_name=name,
                            details=f'Deleted Windows enrollment profile {name}', success=True)
    return success_response(message='Profile deleted')

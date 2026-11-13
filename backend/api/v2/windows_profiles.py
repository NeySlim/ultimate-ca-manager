"""
Windows enrollment profiles v2.0
/api/v2/windows-profiles - one realm each, served by XCEP, WSTEP and Kerberos
"""
import json
import logging

import os
import tempfile

from flask import Blueprint, g, request

from auth.unified import has_permission, require_auth
from models import (CA, ADConnectorConfig, Certificate, SystemConfig, WindowsEnrollmentProfile,
                    WindowsProfileTemplate, db)
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
            'template_ids',
            *(f'{svc}_{part}' for svc in SERVICES for part in ('username', 'password')))


def _actor():
    return getattr(getattr(g, 'current_user', None), 'username', None)


STATES = ('complete', 'keytab_missing', 'connector_failing', 'disabled')
KEYTAB_EXTENSIONS = {'.keytab', '.kt'}
# A keytab is a few dozen bytes per key entry; the composed file has no cap
MAX_KEYTAB_SIZE = 256 * 1024


def _failing_connector_ids():
    """The connectors whose last probe says down (at most a few hundred rows, read once)."""
    from services.ad_connector import health
    return {c.id for c in ADConnectorConfig.query.all() if health.state_of(c.health) == health.STATE_DOWN}


def _state(profile, failing):
    """One state per profile; a disabled profile is shown as such whatever else is missing."""
    if not profile.enabled:
        return 'disabled'
    if not profile.keytab:
        return 'keytab_missing'
    if profile.connector_id in failing:
        return 'connector_failing'
    return 'complete'


def _connectors(profiles):
    ids = {p.connector_id for p in profiles if p.connector_id}
    if not ids:
        return {}
    return {c.id: c for c in ADConnectorConfig.query.filter(ADConnectorConfig.id.in_(ids)).all()}


def _template_ids(profiles):
    ids = [p.id for p in profiles]
    found = {i: [] for i in ids}
    if ids:
        rows = WindowsProfileTemplate.query.filter(WindowsProfileTemplate.profile_id.in_(ids)).all()
        for row in rows:
            found[row.profile_id].append(row.template_id)
    return {i: sorted(v) for i, v in found.items()}


def keytab_entries(profile):
    """``(entries, error)``: the key entries of the profile's keytab, each with its realm."""
    from services.kerberos.keytab_format import read_entries
    try:
        raw = profile.keytab_bytes()
    except ValueError:
        return [], 'the keytab cannot be decrypted here'
    if raw is None:
        return [], None
    entries = read_entries(raw)
    if entries is None:
        return [], 'the entries of the keytab cannot be read'
    return [{'principal': e.principal, 'realm': e.realm, 'kvno': e.kvno, 'enctype': e.enctype}
            for e in entries], None


def _render(profile, ca_names, connectors=None, failing=None, templates=None, detail=False,
            binding_reason=False, key_realms=False):
    """The profile as the API shows it: passwords and keytab only as set/unset flags.
    ``detail`` adds the keytab entries, which cost a decryption per profile."""
    connectors = connectors if connectors is not None else _connectors([profile])
    failing = failing if failing is not None else _failing_connector_ids()
    if templates is None:
        templates = _template_ids([profile]) if profile.id else {}
    connector = connectors.get(profile.connector_id)
    from services.ad_connector import health
    connector_realm = lookup.realm_of_base_dn(connector.base_dn) if connector is not None else None
    data = {
        'id': profile.id,
        'name': profile.name,
        'realm': profile.realm,
        'is_default': bool(profile.is_default),
        'enabled': bool(profile.enabled),
        'state': _state(profile, failing),
        'connector_id': profile.connector_id,
        'connector_name': connector.name if connector is not None else None,
        'connector_enabled': bool(connector.enabled) if connector is not None else None,
        'connector_health': health.state_of(connector.health) if connector is not None else None,
        'connector_realm': connector_realm,
        # Served all the same; the screen warns that the realm and the domain disagree
        'connector_domain_mismatch': bool(profile.realm and connector_realm
                                          and profile.realm != connector_realm),
        'issuing_ca_refid': profile.issuing_ca_refid,
        'issuing_ca_name': ca_names.get(profile.issuing_ca_refid),
        'policy_ca_refid': profile.policy_ca_refid,
        'policy_ca_name': ca_names.get(profile.policy_ca_refid),
        'validity_days': profile.validity_days,
        **{f'{svc}_username': getattr(profile, f'{svc}_username') or '' for svc in SERVICES},
        **{f'{svc}_password_set': bool(getattr(profile, f'{svc}_password')) for svc in SERVICES},
        'allowed_ad_group': profile.allowed_ad_group,
        'pinned_subject_fields': profile.pinned_subject_fields,
        'template_ids': templates.get(profile.id, []),
        'keytab_set': bool(profile.keytab),
        'kerberos_refusal': windows_profiles.kerberos_unserved_reason(profile, binding_reason, key_realms),
        'created_at': profile.created_at.isoformat() if profile.created_at else None,
        'updated_at': profile.updated_at.isoformat() if profile.updated_at else None,
    }
    if detail:
        data['keytab_entries'], data['keytab_error'] = keytab_entries(profile)
    return data


def _binding_reason_for_caller():
    """The binding's reason only for a caller who may read the Kerberos state (as GET /settings);
    None otherwise, so only the profile's own refusal shows."""
    if not has_permission('read:kerberos', getattr(g, 'permissions', None) or []):
        return None
    return windows_profiles.kerberos_binding_reason()


def _render_one(profile, detail=False):
    return _render(profile, _ca_names([profile]), detail=detail,
                   binding_reason=_binding_reason_for_caller())


def _render_page(profiles):
    names, connectors = _ca_names(profiles), _connectors(profiles)
    failing, templates = _failing_connector_ids(), _template_ids(profiles)
    binding_reason, key_realms = _binding_reason_for_caller(), windows_profiles.served_key_realms()
    return [_render(p, names, connectors, failing, templates, binding_reason=binding_reason,
                    key_realms=key_realms) for p in profiles]


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

    if 'template_ids' in data:
        ids, err = _template_id_list(data['template_ids'])
        if err:
            return err, 400
        profile._wanted_templates = ids
    if 'pinned_subject_fields' in data:
        pinned, err = _pinned_subject_fields(data['pinned_subject_fields'])
        if err:
            return err, 400
        profile.pinned_subject_fields = pinned
    # Only the default profile's binding reads the shared accounts: elsewhere they would never be used
    if not profile.is_default:
        for field in (f'{svc}_{part}' for svc in SERVICES for part in ('username', 'password')):
            if data.get(field):
                return (f'{field} is read for the default profile only: this profile is not the default one, '
                        'so the account would never be used'), 400
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


def _template_id_list(value):
    """(ids, error): a list of existing template ids; empty: the templates of the CA."""
    from models import CertificateTemplate
    if not isinstance(value, list) or any(type(i) is not int for i in value):
        return None, 'template_ids must be a list of template ids'
    ids = sorted(set(value))
    found = {t.id for t in CertificateTemplate.query.filter(CertificateTemplate.id.in_(ids)).all()} if ids else set()
    if found != set(ids):
        return None, f'template not found: {sorted(set(ids) - found)}'
    return ids, None


def _store_templates(profile):
    """Replace the profile's template links by the ones validated by _apply, if it got any."""
    wanted = getattr(profile, '_wanted_templates', None)
    if wanted is None:
        return
    db.session.flush()
    WindowsProfileTemplate.query.filter_by(profile_id=profile.id).delete()
    for template_id in wanted:
        db.session.add(WindowsProfileTemplate(profile_id=profile.id, template_id=template_id))


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
    """Profiles, paginated; ``q`` matches the name or the realm, ``ca`` (a refid) the issuing or
    policy CA, ``state`` one of complete, keytab_missing, connector_failing, disabled."""
    page, per_page = parse_request_pagination(default_per_page=25, max_per_page=MAX_PER_PAGE)
    P = WindowsEnrollmentProfile
    query = P.query
    q = (request.args.get('q') or '').strip()
    if q:
        like = f'%{_escape_like(q)}%'
        query = query.filter(db.or_(P.name.ilike(like, escape='\\'), P.realm.ilike(like, escape='\\')))
    ca = (request.args.get('ca') or '').strip()
    if ca:
        query = query.filter(db.or_(P.issuing_ca_refid == ca, P.policy_ca_refid == ca))
    state = (request.args.get('state') or '').strip()
    if state:
        if state not in STATES:
            return error_response(f"state must be one of {', '.join(STATES)}", 400)
        failing = _failing_connector_ids()
        if state == 'disabled':
            query = query.filter(P.enabled.is_(False))
        elif state == 'keytab_missing':
            query = query.filter(P.enabled.is_(True), P.keytab.is_(None))
        elif state == 'connector_failing':
            query = query.filter(P.enabled.is_(True), P.keytab.is_not(None), P.connector_id.in_(failing or [0]))
        else:
            query = query.filter(P.enabled.is_(True), P.keytab.is_not(None))
            if failing:
                query = query.filter(db.or_(P.connector_id.is_(None), P.connector_id.not_in(failing)))
    query = query.order_by(P.name, P.id)
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return success_response(
        data=_render_page(pagination.items),
        meta={'total': pagination.total, 'page': page, 'per_page': per_page,
              'total_pages': pagination.pages})


@bp.route('/api/v2/windows-profiles/<int:profile_id>', methods=['GET'])
@require_auth(['read:xcep'])
def get_windows_profile(profile_id):
    profile = db.session.get(WindowsEnrollmentProfile, profile_id)
    if profile is None:
        return error_response('Profile not found', 404)
    return success_response(data=_render_one(profile, detail=True))


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
    _store_templates(profile)
    ok, err = safe_commit(logger, 'Failed to create the Windows enrollment profile')
    if not ok:
        return err
    _audit('windows_profile_create', profile, f'Created Windows enrollment profile {profile.name}')
    return success_response(data=_render_one(profile),
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
    _store_templates(profile)
    ok, err = safe_commit(logger, 'Failed to update the Windows enrollment profile')
    if not ok:
        return err
    _audit('windows_profile_update', profile,
           f"Updated Windows enrollment profile {profile.name}; fields: {', '.join(changed) or 'none'}")
    return success_response(data=_render_one(profile, detail=True), message='Profile updated')


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


def _read_keytab_upload():
    """``(content, entries, error_response)`` for the multipart ``file`` field: a keytab GSSAPI
    loads and that holds at least one entry."""
    from services.kerberos import negotiate_auth
    from services.kerberos.keytab_format import read_entries
    from utils.file_validation import validate_upload
    if 'file' not in request.files:
        return None, None, error_response('No file provided', 400)
    try:
        content, _name = validate_upload(request.files['file'], KEYTAB_EXTENSIONS,
                                         max_size=MAX_KEYTAB_SIZE)
    except ValueError as e:
        return None, None, error_response(str(e), 400)
    fd, tmp_path = tempfile.mkstemp(prefix='.kerberos-keytab-check-')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(content)
        inspection = negotiate_auth.inspect_keytab(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    if not inspection['valid']:
        return None, None, error_response(
            f"Keytab is not a valid krb5 keytab: {inspection['error']}", 400)
    entries = read_entries(content)
    if not entries:
        return None, None, error_response('Keytab holds no entry', 400)
    return content, entries, None


def _foreign_entries(entries, realm):
    """The principals of *entries* that are not ``<service>/<SPN host>@<realm>``: the unnamed
    acceptor takes a ticket for any entry, so a stray one widens what UCM accepts."""
    from services.kerberos import negotiate_auth
    parsed = negotiate_auth._parse_spn(negotiate_auth.get_spn())
    service, host = parsed if parsed else ('HTTP', None)
    hosts = {e.components[1].lower() for e in entries if len(e.components) == 2}
    if host is None and len(hosts) == 1:
        host = next(iter(hosts))
    return [e.principal for e in entries
            if e.realm != realm or len(e.components) != 2 or e.components[0] != service
            or e.components[1].lower() != (host or '').lower()]


@bp.route('/api/v2/windows-profiles/<int:profile_id>/keytab', methods=['POST'])
@require_auth(['write:xcep'])
def upload_profile_keytab(profile_id):
    """Replace the keytab of a profile (multipart ``file``). Loaded with GSSAPI before it is
    stored; every entry must be ``<SPN service>/<SPN host>@<realm of the profile>``, else 400.
    With ``dry_run`` the entries are listed, per realm, and nothing is stored."""
    from services import cluster_commands
    from services.kerberos import negotiate_auth
    # The route replaces the retired keytab upload, which answered to write:kerberos
    if not has_permission('write:kerberos', g.permissions):
        return error_response('Insufficient permissions', 403)
    profile = db.session.get(WindowsEnrollmentProfile, profile_id)
    if profile is None:
        return error_response('Profile not found', 404)
    content, entries, err = _read_keytab_upload()
    if err:
        return err
    listed = [{'principal': e.principal, 'realm': e.realm, 'kvno': e.kvno, 'enctype': e.enctype}
              for e in entries]
    if request.form.get('dry_run') in ('1', 'true'):
        realms = sorted({e.realm for e in entries})
        return success_response(data={
            'keytab_entries': listed, 'realms': realms, 'profile_realm': profile.realm,
            'foreign_entries': sorted(set(_foreign_entries(entries, profile.realm)))
            if profile.realm else [],
        })
    profile.updated_by = _actor()
    profile.set_keytab(content)
    windows_profiles.fill_realm(profile)
    if profile.realm is None:
        db.session.rollback()
        return error_response('the profile has no realm: set it, then upload its keytab', 400)
    foreign = _foreign_entries(entries, profile.realm)
    if foreign:
        db.session.rollback()
        return error_response(f"Keytab entries outside HTTP/<host>@{profile.realm}: "
                              f"{', '.join(sorted(set(foreign)))}", 400)
    try:
        windows_profiles.publish_keytab(actor=_actor())
    except ValueError as e:
        db.session.rollback()
        return error_response(f'Keytab not composed: {e}', 409)
    cluster_commands.emit(cluster_commands.RELOAD_KEYTAB)
    ok, err = safe_commit(logger, 'Failed to store the Windows profile keytab')
    if not ok:
        return err
    try:
        negotiate_auth.write_stored_keytab()
    except (OSError, ValueError) as e:
        logger.error('Failed to write the Kerberos keytab: %s', e)
        return error_response('Failed to save keytab', 500)
    AuditService.log_action(
        action='kerberos_keytab_upload', resource_type='windows_profile',
        resource_id=str(profile.id), resource_name=profile.name,
        details=f"Uploaded a Kerberos keytab for profile {profile.name} (principals: "
                f"{', '.join(sorted({e.principal for e in entries}))})",
        success=True)
    return success_response(message='Keytab uploaded', data=_render_one(profile, detail=True))


def _flag(key):
    row = SystemConfig.query.filter_by(key=key).first()
    return bool(row and (row.value or '').lower() == 'true')


def _put_setting(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if row is None:
        db.session.add(SystemConfig(key=key, value=value))
    else:
        row.value = value


@bp.route('/api/v2/windows-profiles/settings', methods=['GET'])
@require_auth(['read:xcep'])
def get_windows_settings():
    """The switches and the SPN shared by every profile, and the state of the composed keytab.
    The WSTEP and Kerberos parts need their own read scope."""
    from services.kerberos import negotiate_auth
    perms = getattr(g, 'permissions', None) or []
    default = windows_profiles.default_profile()
    data = {
        'xcep_enabled': _flag('xcep_enabled'),
        # Kerberos is refused until the default profile names a realm (A1): the screen says so
        'default_profile': ({'id': default.id, 'name': default.name, 'realm': default.realm,
                             'enabled': bool(default.enabled)} if default is not None else None),
    }
    if has_permission('read:wstep', perms):
        data['wstep_enabled'] = _flag('wstep_enabled')
    if has_permission('read:kerberos', perms):
        inspection = negotiate_auth.inspect_keytab()
        data.update({
            'kerberos_enabled': negotiate_auth.is_enabled(),
            'kerberos_spn': negotiate_auth.get_spn(),
            'library_available': negotiate_auth.is_library_available(),
            'keytab_set': negotiate_auth.KEYTAB_PATH.exists(),
            'keytab_valid': inspection['valid'],
            'keytab_error': inspection['error'],
            'keytab_entries': inspection['entries'],
        })
    return success_response(data=data)


@bp.route('/api/v2/windows-profiles/settings', methods=['PATCH'])
@require_auth(['write:xcep'])
def update_windows_settings():
    """Set the XCEP, WSTEP and Kerberos switches and the SPN. WSTEP and Kerberos need their own
    write scope; a change of the WSTEP switch restarts the service (TLS cap read at startup)."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response('A JSON object is required', 400)
    perms = getattr(g, 'permissions', None) or []
    for key in ('xcep_enabled', 'wstep_enabled', 'kerberos_enabled'):
        if key in data and type(data[key]) is not bool:
            return error_response(f'{key} must be a JSON boolean', 400)
    if 'kerberos_spn' in data and not isinstance(data['kerberos_spn'], str):
        return error_response('kerberos_spn must be a string', 400)
    if 'wstep_enabled' in data and not has_permission('write:wstep', perms):
        return error_response('Insufficient permissions', 403)
    if ({'kerberos_enabled', 'kerberos_spn'} & set(data)) and not has_permission('write:kerberos', perms):
        return error_response('Insufficient permissions', 403)

    enabled_changed = 'wstep_enabled' in data and _flag('wstep_enabled') != data['wstep_enabled']
    for key in ('xcep_enabled', 'wstep_enabled', 'kerberos_enabled'):
        if key in data:
            _put_setting(key, 'true' if data[key] else 'false')
    if 'kerberos_spn' in data:
        _put_setting('kerberos_spn', data['kerberos_spn'].strip())
        default = windows_profiles.default_profile()
        if default is not None:
            db.session.flush()
            windows_profiles.fill_realm(default)

    from utils.ha import ha_enabled
    rolling = enabled_changed and ha_enabled()
    if rolling:
        from services.cluster_commands import RESTART, emit
        emit(RESTART)
    ok, err = safe_commit(logger, 'Failed to save the Windows enrollment settings')
    if not ok:
        return err
    AuditService.log_action(action='windows_settings_update', resource_type='windows_profile',
                            resource_name='Windows enrollment settings',
                            details=f"Updated Windows enrollment settings: {', '.join(sorted(data))}",
                            success=True)
    if rolling:
        return success_response(message='Settings saved. Rolling restart requested: '
                                        'the nodes restart one at a time.')
    if enabled_changed:
        from config.settings import is_docker
        if is_docker():
            return success_response(
                message='Settings saved. Restart the container to apply the TLS behavior change.',
                data={'requires_container_restart': True})
        from utils.service_manager import restart_service
        success, msg = restart_service()
        if not success:
            logger.warning('Settings saved but service restart failed: %s', msg)
            return success_response(
                message='Settings saved, but the automatic restart failed: restart UCM manually '
                        'for the TLS behavior change to take effect.',
                data={'restart_failed': True})
        return success_response(message='Settings saved. Service restarting...')
    return success_response(message='Settings saved')

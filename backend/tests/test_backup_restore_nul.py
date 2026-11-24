"""A NUL character in an archived text: kept on SQLite, restored as the two characters \\0 on PostgreSQL.

SQLite stores U+0000 in a text (an API call can write one) and keeps it at a restore, so an
archive restores onto the installation that wrote it with every row under its own identity.
PostgreSQL stores none: the restore rewrites every such text there the way the audit log writes
one, before anything compares or follows identities, and names each section.field once.
"""
import io
import json
import os

import pytest

from models import db

from tests.fresh_app import fresh_app_fixtures
from tests.restore_support import post_to_the_end
from tests.test_restore_sso_one_per_type import target  # noqa: F401  (SQLite and PostgreSQL)

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

PASSWORD = 'Correct-Horse-Battery-9'
RESTORE_URL = '/api/v2/system/restore'
MODES = ['merge', 'replace']
ESCAPED = '\\0'


def _service():
    from services.backup_service import BackupService
    return BackupService()


def _restore(payload, mode):
    return _service()._restore_payload(payload, os.urandom(32), mode)


def _nul_warnings(results):
    return [w for w in results.get('warnings', []) if 'NUL character' in w]


def _stored(target, text):
    """``text`` as the target's database holds it once restored."""
    return text.replace('\x00', ESCAPED) if target == 'postgresql' else text


def _fields(results):
    return sorted(w.split(':')[0] for w in _nul_warnings(results))


def _target(name, **fields):
    return {'name': name, 'host': 'deploy.test', 'port': 22, 'username': 'ucm',
            'private_key': 'k', **fields}


def _postgresql_only(target):
    if target != 'postgresql':
        pytest.skip('SQLite rewrites nothing')


# --- Each place a text can hold one --------------------------------------------------------------

@pytest.mark.parametrize('mode', MODES)
def test_a_column_value_is_kept_or_rewritten_and_named_once(target, mode):
    from models.deploy import DeployTarget
    results = _restore({'deploy_targets': [_target('nul-a', host='deploy\x00a.test'),
                                           _target('nul-b', host='deploy\x00b.test')]}, mode)
    db.session.expire_all()
    assert sorted(t.host for t in DeployTarget.query) == [
        _stored(target, 'deploy\x00a.test'), _stored(target, 'deploy\x00b.test')]
    warnings = _nul_warnings(results)
    if target == 'sqlite':
        assert warnings == []
        return
    assert len(warnings) == 1 and warnings[0].startswith('deploy_targets.host:'), warnings
    assert '\x00' not in warnings[0] and 'deploy' not in warnings[0].split(':', 1)[1]


@pytest.mark.parametrize('mode', MODES)
def test_a_nested_json_value_and_a_json_key(target, mode):
    from models.rbac import CustomRole
    results = _restore({'custom_roles': [
        {'name': 'nul-role-value', 'permissions': ['read:cas', 'read:x\x00y']},
        {'name': 'nul-role-key', 'permissions': [{'k\x00ey': ['v\x00']}]},
    ]}, mode)
    db.session.expire_all()
    roles = {r.name: r.permissions for r in CustomRole.query.filter(
        CustomRole.name.like('nul-role-%'))}
    assert roles['nul-role-value'] == ['read:cas', _stored(target, 'read:x\x00y')]
    assert roles['nul-role-key'] == [{_stored(target, 'k\x00ey'): [_stored(target, 'v\x00')]}]
    assert _fields(results) == ([] if target == 'sqlite' else ['custom_roles.permissions'])


@pytest.mark.parametrize('mode', MODES)
def test_a_key_and_a_value_of_the_configuration(target, mode):
    from models import SystemConfig
    results = _restore({'configuration': {'settings': {'nul_value': 'a\x00b', 'nul\x00key': 'c'}}},
                       mode)
    db.session.expire_all()
    assert SystemConfig.query.filter_by(key='nul_value').one().value == _stored(target, 'a\x00b')
    assert SystemConfig.query.filter_by(key=_stored(target, 'nul\x00key')).one().value == 'c'
    assert _fields(results) == ([] if target == 'sqlite' else [
        f'configuration.settings.nul{ESCAPED}key', 'configuration.settings.nul_value'])


@pytest.mark.parametrize('mode', MODES)
def test_a_reference_by_an_identity_holding_one_still_names_its_row(target, mode):
    """The role an archived role inherits from is named by its name, which holds a NUL: kept or
    rewritten, the identity and the reference stay alike, so the link holds."""
    from models.rbac import CustomRole
    _restore({'custom_roles': [
        {'name': 'child-role', 'permissions': [], 'inherits_from': 77,
         'inherits_from_ref': {'name': 'base\x00role'}},
        {'name': 'base\x00role', 'permissions': []},
    ]}, mode)
    db.session.expire_all()
    base = CustomRole.query.filter_by(name=_stored(target, 'base\x00role')).one()
    assert CustomRole.query.filter_by(name='child-role').one().inherits_from == base.id


def test_an_archive_restored_twice_finds_its_rows_again(target):
    """Guard: the second merge matches the names already here, one role each."""
    from models.rbac import CustomRole
    archive = lambda: {'custom_roles': [  # noqa: E731  (each restore may rewrite its own copy)
        {'name': 'child-role', 'permissions': [], 'inherits_from': 77,
         'inherits_from_ref': {'name': 'base\x00role'}},
        {'name': 'base\x00role', 'permissions': []}]}
    for _ in range(2):
        _restore(archive(), 'merge')
        db.session.expire_all()
    base = CustomRole.query.filter_by(name=_stored(target, 'base\x00role')).one()
    assert CustomRole.query.filter_by(name='child-role').one().inherits_from == base.id


@pytest.mark.parametrize('mode', MODES)
def test_an_sso_provider_restored_again_is_the_one_here(target, mode):
    """One provider per type compares names: the archive's is compared as stored, so the
    provider a first restore wrote is this one, neither replaced nor left out."""
    from models.sso import SSOProvider
    row = {'name': 'corp\x00idp', 'provider_type': 'oauth2', 'enabled': True,
           'default_role': 'viewer', 'oauth2_issuer': 'https://corp.example'}
    _restore({'sso_providers': [dict(row)]}, 'merge')
    db.session.commit()
    first = SSOProvider.query.filter_by(name=_stored(target, 'corp\x00idp')).one().id
    results = _restore({'sso_providers': [dict(row)]}, mode)
    db.session.expire_all()
    assert [(p.id, p.name) for p in SSOProvider.query] == [(first, _stored(target, 'corp\x00idp'))]
    assert not [w for w in results['warnings'] if w.startswith('sso_providers:')], results


@pytest.mark.parametrize('mode', MODES)
def test_a_pem_still_fails_its_own_check(target, mode):
    """Kept or rewritten, a field of the wrong type is refused by its own check."""
    from services.backup.restore import RestoreValidationError
    with pytest.raises(RestoreValidationError) as refused:
        _restore({'certificates': [{'refid': 'nul-cert', 'descr': 'nul-cert',
                                    'certificate_pem': ['-----BEGIN\x00']}]}, mode)
    db.session.rollback()
    assert 'certificates.certificate_pem' in str(refused.value)


# --- What the report says on PostgreSQL ----------------------------------------------------------

@pytest.mark.parametrize('mode', MODES)
def test_a_field_name_holding_one_is_named_as_ignored(target, mode):
    """No column name holds a NUL: such a field is never written, and the report says so."""
    _postgresql_only(target)
    results = _restore({'deploy_targets': [_target('nul-field', **{'no\x00column': 'x'})]}, mode)
    warning, = _nul_warnings(results)
    assert warning.startswith(f'deploy_targets.no{ESCAPED}column: a field no column takes, ignored')


@pytest.mark.parametrize('mode', MODES)
def test_two_rows_that_become_one_are_named(target, mode):
    """``a\\x00`` and the text ``a\\0`` are one name once rewritten: the report says so."""
    _postgresql_only(target)
    results = _restore({'custom_roles': [{'name': 'twin\x00', 'permissions': []},
                                         {'name': f'twin{ESCAPED}', 'permissions': []}]}, mode)
    merged = [w for w in results['warnings'] if 'restored as one' in w]
    assert [w.split(':')[0] for w in merged] == ['custom_roles.name'], results['warnings']


def test_rows_already_alike_are_not_named_as_merged(target):
    _postgresql_only(target)
    results = _restore({'custom_roles': [{'name': 'same\x00a', 'permissions': []},
                                         {'name': 'same\x00b', 'permissions': []}]}, 'merge')
    assert not [w for w in results['warnings'] if 'restored as one' in w]


def test_the_report_names_a_bounded_number_of_fields(target):
    from services.backup.restore.apply import NUL_WARNING_FIELDS
    _postgresql_only(target)
    many = NUL_WARNING_FIELDS + 5
    results = _restore({'configuration': {'settings': {
        f'nul_{i:02d}': 'x\x00' for i in range(many)}}}, 'merge')
    warnings = _nul_warnings(results)
    assert len(warnings) == NUL_WARNING_FIELDS + 1, warnings
    assert warnings[-1].startswith('5 more fields'), warnings[-1]


# --- The audit log -------------------------------------------------------------------------------

def _sealed_entries():
    """Three entries sealed as before the audit log escaped NUL, the second over a NUL."""
    from datetime import datetime
    from models.audit_log import AuditLog
    rows, prev = [], None
    for i, details in enumerate(['clean one', 'with\x00nul', 'clean two']):
        row = AuditLog(id=1000 + i, timestamp=datetime(2025, 1, 1, 0, 0, i), username='u',
                       action='nul-probe', resource_type='t', resource_id=str(i),
                       details=details, success=True, prev_hash=prev)
        row.entry_hash = row.compute_hash(prev)
        prev = row.entry_hash
        rows.append(row)
    return rows


def _probe_details():
    from models.audit_log import AuditLog
    return [r.details for r in AuditLog.query.filter_by(action='nul-probe').order_by(AuditLog.id)]


@pytest.mark.parametrize('mode', MODES)
def test_an_audit_entry_holding_a_nul_keeps_its_seal_on_sqlite(target, mode):
    """SQLite stores the NUL: the entry comes back as sealed, the chain checks, no warning."""
    from models.audit_log import AuditLog
    from services.audit.chain import verify_chain
    from services.backup import manifest
    if target != 'sqlite':
        pytest.skip('PostgreSQL never held such an entry')
    for row in _sealed_entries():
        db.session.add(row)
    db.session.commit()
    svc = _service()
    blob = svc.create_backup(PASSWORD, include={n: n == 'audit_logs' for n in manifest.SECTIONS})
    results = svc.restore_backup(blob, PASSWORD, mode=mode)
    db.session.expire_all()
    assert _probe_details() == ['clean one', 'with\x00nul', 'clean two']
    assert verify_chain(AuditLog.query.order_by(AuditLog.id).all(), True)['errors'] == []
    assert _nul_warnings(results) == []


@pytest.mark.parametrize('mode', MODES)
def test_an_archived_audit_entry_holding_a_nul_is_rewritten_on_postgresql(target, mode):
    """An archive from SQLite, presented by hand: PostgreSQL cannot store the NUL."""
    from models.audit_log import AuditLog
    _postgresql_only(target)
    columns = [c.name for c in AuditLog.__table__.columns]
    payload = {'audit_logs': [
        {name: (getattr(row, name).isoformat() if name == 'timestamp' else getattr(row, name))
         for name in columns} for row in _sealed_entries()]}
    results = _restore(payload, mode)
    db.session.expire_all()
    assert _probe_details() == ['clean one', f'with{ESCAPED}nul', 'clean two']
    assert _fields(results) == ['audit_logs.details']


# --- Through the route: an archive this product wrote, and one presented to PostgreSQL ---------

def _sqlite_app_only(app):
    with app.app_context():
        if db.engine.dialect.name != 'sqlite':
            pytest.skip('only SQLite stores the NUL a request writes')


def _post_restore(auth_client, blob, mode):
    return post_to_the_end(auth_client, RESTORE_URL, content_type='multipart/form-data', data={
        'password': PASSWORD, 'mode': mode, 'file': (io.BytesIO(blob), 'nul.ucmbkp')})


def _created(response):
    assert response.status_code in (200, 201), response.data
    return response.get_json()['data']


@pytest.mark.parametrize('mode', MODES)
def test_an_installation_restores_its_own_backup_unchanged(app, auth_client, create_cert, mode):
    """A group and a description written with a NUL through the API, and an inherited role, on
    SQLite: the backup restores onto the same installation with one row each, links intact."""
    from models import Certificate, User
    from models.group import Group, GroupMember
    from models.rbac import CustomRole
    _sqlite_app_only(app)
    tag = f'nul-{mode}'
    cert_id = create_cert().get('id')
    assert auth_client.patch(f'/api/v2/certificates/{cert_id}', content_type='application/json',
                             data=json.dumps({'descr': f'web\u0000{tag}'})).status_code == 200
    group = _created(auth_client.post('/api/v2/groups', content_type='application/json',
                                      data=json.dumps({'name': f'ops\u0000{tag}'})))
    with app.app_context():
        admin_id = User.query.filter_by(username='admin').one().id
    _created(auth_client.post(f"/api/v2/groups/{group['id']}/members",
                              content_type='application/json',
                              data=json.dumps({'user_id': admin_id})))
    with app.app_context():
        # The role API refuses a NUL in a name; an older release or a direct edit did not
        base = CustomRole(name=f'base\x00{tag}', permissions=['read:cas'])
        db.session.add(base)
        db.session.flush()
        db.session.add(CustomRole(name=f'child-{tag}', permissions=[], inherits_from=base.id))
        db.session.commit()
        refid = db.session.get(Certificate, cert_id).refid
        blob = _service().create_backup(PASSWORD)
    response = _post_restore(auth_client, blob, mode)
    assert response.status_code == 200, response.data
    with app.app_context():
        assert Certificate.query.filter_by(refid=refid).one().descr == f'web\x00{tag}'
        # SQLite's LIKE stops at a NUL: matched here instead
        groups = [g for g in Group.query if g.name.startswith('ops') and g.name.endswith(tag)]
        assert [g.name for g in groups] == [f'ops\x00{tag}']
        assert GroupMember.query.filter_by(group_id=groups[0].id).count() == 1
        roles = [r for r in CustomRole.query if r.name.startswith('base') and r.name.endswith(tag)]
        assert [r.name for r in roles] == [f'base\x00{tag}']
        assert CustomRole.query.filter_by(name=f'child-{tag}').one().inherits_from == roles[0].id


def test_the_route_restores_a_nul_onto_postgresql(app, auth_client):
    """A v4 archive read as a stream, holding a NUL nothing on PostgreSQL could have written."""
    from models.deploy import DeployTarget
    from tests.test_backup_hostile_corpus import _forged
    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            pytest.skip('the application runs on SQLite')
        blob = _forged(['deploy_targets'], deploy_targets=[_target('nul-route', host='a\x00b')])
    try:
        response = _post_restore(auth_client, blob, 'merge')
        assert response.status_code == 200, response.data
        with app.app_context():
            assert DeployTarget.query.filter_by(name='nul-route').one().host == f'a{ESCAPED}b'
    finally:
        with app.app_context():
            DeployTarget.query.filter_by(name='nul-route').delete()
            db.session.commit()


# --- The rewrite itself, whatever the engine underneath -------------------------------------------

def _rewritten(payload):
    from services.backup.manifest import SECTIONS
    from services.backup.restore_core import RESTORED_SECTIONS
    from services.backup.restore.apply import escape_nul_in_archive
    return escape_nul_in_archive(payload, set(SECTIONS) | RESTORED_SECTIONS)


def test_the_rewrite_names_two_rows_that_become_one():
    payload = {'custom_roles': [{'name': 'twin\x00'}, {'name': f'twin{ESCAPED}'}]}
    merged = [w for w in _rewritten(payload) if 'restored as one' in w]
    assert [w.split(':')[0] for w in merged] == ['custom_roles.name']
    assert [r['name'] for r in payload['custom_roles']] == [f'twin{ESCAPED}'] * 2


def test_the_rewrite_does_not_name_rows_that_stay_apart():
    payload = {'custom_roles': [{'name': 'same\x00a'}, {'name': 'same\x00b'}, {'name': 'plain'},
                                {'name': 'plain'}]}
    assert not [w for w in _rewritten(payload) if 'restored as one' in w]


def test_the_rewrite_escapes_and_bounds_a_name_from_the_archive():
    from services.backup.restore.apply import NAME_SHOWN
    warnings = _rewritten({'configuration': {'settings': {'line\nbreak': 'a\x00',
                                                          'x' * 5000: 'b\x00'}}})
    assert len(warnings) == 2 and not any('\n' in w for w in warnings), warnings
    assert any(w.startswith('configuration.settings.line\\x0abreak:') for w in warnings)
    long_one, = [w for w in warnings if 'xxx' in w]
    assert long_one.startswith('configuration.settings.' + 'x' * NAME_SHOWN + '...:')


def test_the_rewrite_names_a_field_no_column_takes_as_ignored():
    warnings = _rewritten({'deploy_targets': [_target('n', **{'no\x00col\numn': 'x'},
                                                      host='h\x00')]})
    assert sorted(warnings) == sorted([
        'deploy_targets.host: a NUL character, which PostgreSQL cannot store in text, was '
        'restored as the two characters \\0',
        f'deploy_targets.no{ESCAPED}col\\x0aumn: a field no column takes, ignored, holding a '
        'NUL character'])


@pytest.mark.parametrize('mode', MODES)
def test_a_list_in_an_identity_beside_a_nul_is_named_not_a_server_error(target, mode):
    """The shape of a field is checked before the rewrite: 400 naming it, on both engines."""
    from models.rbac import CustomRole
    from services.backup.restore import RestoreValidationError
    with pytest.raises(RestoreValidationError) as refused:
        _restore({'custom_roles': [{'name': ['x'], 'description': 'a\x00', 'permissions': []}]},
                 mode)
    db.session.rollback()
    assert 'custom_roles.name' in str(refused.value)
    assert CustomRole.query.count() == 0


def test_the_rewrite_never_fails_on_an_identity_that_is_a_list():
    payload = {'custom_roles': [{'name': ['x'], 'description': 'a\x00'},
                                {'name': ['x'], 'description': 'b'}]}
    assert _rewritten(payload)


def test_the_rewrite_names_two_mapping_keys_that_become_one():
    payload = {'configuration': {'settings': {'k\x00': 'one', f'k{ESCAPED}': 'two'}}}
    merged = [w for w in _rewritten(payload) if 'restored as one' in w]
    assert [w.split(':')[0] for w in merged] == ['configuration.settings'], merged


def test_the_rewrite_names_two_json_keys_of_a_column_that_become_one():
    payload = {'custom_roles': [{'name': 'r', 'permissions': [{'k\x00': 1, f'k{ESCAPED}': 2}]}]}
    merged = [w for w in _rewritten(payload) if 'restored as one' in w]
    assert [w.split(':')[0] for w in merged] == ['custom_roles.permissions'], merged


def test_the_rewrite_does_not_blame_the_nul_for_rows_already_alike():
    payload = {'custom_roles': [{'name': 'g\x00'}, {'name': 'g\x00'}]}
    assert not [w for w in _rewritten(payload) if 'restored as one' in w]


_NO_COLUMN = ('a field no column takes held a NUL character; where the restore reads it, it '
              'is restored as the two characters \\0')


def test_the_rewrite_does_not_say_where_a_value_no_column_takes_went():
    """A readable name with no column: the restore may read it itself, or drop it."""
    warnings = _rewritten({'deploy_targets': [_target('n', no_column='x\x00')]})
    assert warnings == [f'deploy_targets.no_column: {_NO_COLUMN}'], warnings


def test_a_field_an_older_archive_carries_is_not_said_ignored():
    """An archive of the previous major names the SSO identity on the account itself."""
    warnings = _rewritten({'users': [{'username': 'u', 'sso_external_id': 'a\x00b'}]})
    assert warnings == [f'users.sso_external_id: {_NO_COLUMN}'], warnings


@pytest.mark.parametrize('mode', MODES)
def test_a_text_pem_holding_a_nul_is_stored_as_it_reads(target, mode):
    """What happens today, not a promise: the restore does not parse an archived certificate
    PEM, so one holding a NUL is written, the NUL kept (SQLite) or as \\0 (PostgreSQL)."""
    import base64
    from models import Certificate
    pem = '-----BEGIN CERTIFICATE-----\nMII\x00\n-----END CERTIFICATE-----\n'
    _restore({'certificates': [{'refid': 'nul-pem', 'descr': 'nul-pem', 'certificate_pem': pem}]},
             mode)
    db.session.expire_all()
    stored = Certificate.query.filter_by(refid='nul-pem').one().crt
    assert base64.b64decode(stored).decode() == _stored(target, pem)


def test_the_rewrite_names_two_keys_of_a_mapping_section_that_become_one():
    payload = {'configuration': {'a\x00': 'one', f'a{ESCAPED}': 'two'}}
    merged = [w for w in _rewritten(payload) if 'restored as one' in w]
    assert [w.split(':')[0] for w in merged] == ['configuration'], merged

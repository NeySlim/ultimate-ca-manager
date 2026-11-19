"""A NUL character in an archived text is restored as the two characters \\0, never refused.

SQLite stores U+0000 in a text (an API call can write one), PostgreSQL stores none. The restore
rewrites every such text the way the audit log writes one, on both backends, before anything
compares or follows identities, and names each section.field once in its report.
"""
import io
import json
import os

import pytest

from models import db

from tests.fresh_app import fresh_app_fixtures
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


def _target(name, **fields):
    return {'name': name, 'host': 'deploy.test', 'port': 22, 'username': 'ucm',
            'private_key': 'k', **fields}


# --- Each place a text can hold one --------------------------------------------------------------

@pytest.mark.parametrize('mode', MODES)
def test_a_column_value_is_rewritten_and_named_once(target, mode):
    from models.deploy import DeployTarget
    results = _restore({'deploy_targets': [_target('nul-a', host='deploy\x00a.test'),
                                           _target('nul-b', host='deploy\x00b.test')]}, mode)
    db.session.expire_all()
    assert sorted(t.host for t in DeployTarget.query) == [
        f'deploy{ESCAPED}a.test', f'deploy{ESCAPED}b.test']
    warnings = _nul_warnings(results)
    assert len(warnings) == 1 and warnings[0].startswith('deploy_targets.host:'), warnings
    assert '\x00' not in warnings[0] and 'deploy' not in warnings[0].split(':', 1)[1]


@pytest.mark.parametrize('mode', MODES)
def test_a_nested_json_value_and_a_json_key_are_rewritten(target, mode):
    from models.rbac import CustomRole
    results = _restore({'custom_roles': [
        {'name': 'nul-role-value', 'permissions': ['read:cas', 'read:x\x00y']},
        {'name': 'nul-role-key', 'permissions': [{'k\x00ey': ['v\x00']}]},
    ]}, mode)
    db.session.expire_all()
    roles = {r.name: r.permissions for r in CustomRole.query.filter(
        CustomRole.name.like('nul-role-%'))}
    assert roles['nul-role-value'] == ['read:cas', f'read:x{ESCAPED}y']
    assert roles['nul-role-key'] == [{f'k{ESCAPED}ey': [f'v{ESCAPED}']}]
    assert [w.split(':')[0] for w in _nul_warnings(results)] == ['custom_roles.permissions']


@pytest.mark.parametrize('mode', MODES)
def test_a_field_name_of_a_row_is_rewritten(target, mode):
    """A key of the row itself: no column bears it, so nothing is written for it, and the
    report names it rewritten."""
    results = _restore({'deploy_targets': [_target('nul-field', **{'no\x00column': 'x'})]}, mode)
    assert [w.split(':')[0] for w in _nul_warnings(results)] == [f'deploy_targets.no{ESCAPED}column']


@pytest.mark.parametrize('mode', MODES)
def test_a_key_and_a_value_of_the_configuration_are_rewritten(target, mode):
    from models import SystemConfig
    results = _restore({'configuration': {'settings': {'nul_value': 'a\x00b', 'nul\x00key': 'c'}}},
                       mode)
    db.session.expire_all()
    assert SystemConfig.query.filter_by(key='nul_value').one().value == f'a{ESCAPED}b'
    assert SystemConfig.query.filter_by(key=f'nul{ESCAPED}key').one().value == 'c'
    assert sorted(w.split(':')[0] for w in _nul_warnings(results)) == [
        f'configuration.settings.nul{ESCAPED}key', 'configuration.settings.nul_value']


@pytest.mark.parametrize('mode', MODES)
def test_a_reference_by_an_identity_holding_one_still_names_its_row(target, mode):
    """The role an archived role inherits from is named by its name, which holds a NUL: the
    identity and the reference are rewritten alike, so the link holds."""
    from models.rbac import CustomRole
    _restore({'custom_roles': [
        {'name': 'child-role', 'permissions': [], 'inherits_from': 77,
         'inherits_from_ref': {'name': 'base\x00role'}},
        {'name': 'base\x00role', 'permissions': []},
    ]}, mode)
    db.session.expire_all()
    base = CustomRole.query.filter_by(name=f'base{ESCAPED}role').one()
    assert CustomRole.query.filter_by(name='child-role').one().inherits_from == base.id


def test_an_archive_restored_twice_finds_its_rows_again(target):
    """Guard: the second merge matches the rewritten names already here, one role each."""
    from models.rbac import CustomRole
    archive = lambda: {'custom_roles': [  # noqa: E731  (each restore rewrites its own copy)
        {'name': 'child-role', 'permissions': [], 'inherits_from': 77,
         'inherits_from_ref': {'name': 'base\x00role'}},
        {'name': 'base\x00role', 'permissions': []}]}
    for _ in range(2):
        _restore(archive(), 'merge')
        db.session.expire_all()
    base = CustomRole.query.filter_by(name=f'base{ESCAPED}role').one()
    assert CustomRole.query.filter_by(name='child-role').one().inherits_from == base.id


@pytest.mark.parametrize('mode', MODES)
def test_an_sso_provider_restored_again_is_the_one_here(target, mode):
    """One provider per type compares names: the archive's is compared rewritten, so the
    provider a first restore wrote is this one, neither replaced nor left out."""
    from models.sso import SSOProvider
    row = {'name': 'corp\x00idp', 'provider_type': 'oauth2', 'enabled': True,
           'default_role': 'viewer', 'oauth2_issuer': 'https://corp.example'}
    _restore({'sso_providers': [dict(row)]}, 'merge')
    db.session.commit()
    first = SSOProvider.query.filter_by(name=f'corp{ESCAPED}idp').one().id
    results = _restore({'sso_providers': [dict(row)]}, mode)
    db.session.expire_all()
    assert [(p.id, p.name) for p in SSOProvider.query] == [(first, f'corp{ESCAPED}idp')]
    assert not [w for w in results['warnings'] if w.startswith('sso_providers:')], results


@pytest.mark.parametrize('mode', MODES)
def test_a_pem_still_fails_its_own_check(target, mode):
    """The rewrite does not turn a field of the wrong type into one of the right type."""
    from services.backup.restore import RestoreValidationError
    with pytest.raises(RestoreValidationError) as refused:
        _restore({'certificates': [{'refid': 'nul-cert', 'descr': 'nul-cert',
                                    'certificate_pem': ['-----BEGIN\x00']}]}, mode)
    db.session.rollback()
    assert 'certificates.certificate_pem' in str(refused.value)


def test_the_report_names_a_bounded_number_of_fields(target):
    from services.backup.restore.apply import NUL_WARNING_FIELDS
    many = NUL_WARNING_FIELDS + 5
    results = _restore({'configuration': {'settings': {
        f'nul_{i:02d}': 'x\x00' for i in range(many)}}}, 'merge')
    warnings = _nul_warnings(results)
    assert len(warnings) == NUL_WARNING_FIELDS + 1, warnings
    assert warnings[-1].startswith('5 more fields'), warnings[-1]


# --- An archive this product wrote ---------------------------------------------------------------

def test_a_description_written_through_the_api_restores_in_both_modes(app, auth_client,
                                                                      create_cert):
    """SQLite keeps the NUL a PATCH writes; its backup restores, merged then replacing."""
    from models import Certificate
    cert = create_cert()
    cert_id = cert.get('id') or cert.get('cert_id')
    response = auth_client.patch(f'/api/v2/certificates/{cert_id}',
                                 data=json.dumps({'descr': 'web\u0000prod'}),
                                 content_type='application/json')
    assert response.status_code == 200, response.data
    with app.app_context():
        refid = db.session.get(Certificate, cert_id).refid
        blob = _service().create_backup(PASSWORD)
    for mode in MODES:
        response = auth_client.post(RESTORE_URL, content_type='multipart/form-data', data={
            'password': PASSWORD, 'mode': mode, 'file': (io.BytesIO(blob), 'nul.ucmbkp')})
        assert response.status_code == 200, (mode, response.data)
        with app.app_context():
            assert Certificate.query.filter_by(refid=refid).one().descr == f'web{ESCAPED}prod'


# --- The audit log -------------------------------------------------------------------------------

@pytest.mark.parametrize('mode', MODES)
def test_an_audit_entry_older_than_the_escaping_is_restored_and_flagged(target, mode):
    """An entry written before the audit log escaped NUL, sealed over the NUL: restored
    rewritten, it fails the chain check alone, and the report says the check will say so."""
    from datetime import datetime
    from models.audit_log import AuditLog
    from services.audit.chain import verify_chain
    from services.backup import manifest
    if target == 'postgresql':
        pytest.skip('PostgreSQL never held such an entry: the archive comes from SQLite')
    prev = None
    for i, details in enumerate(['clean one', 'with\x00nul', 'clean two']):
        row = AuditLog(id=1000 + i, timestamp=datetime(2025, 1, 1, 0, 0, i), username='u',
                       action='nul-probe', resource_type='t', resource_id=str(i),
                       details=details, success=True, prev_hash=prev)
        row.entry_hash = row.compute_hash(prev)
        prev = row.entry_hash
        db.session.add(row)
    db.session.commit()
    assert verify_chain(AuditLog.query.order_by(AuditLog.id).all(), True)['valid']
    svc = _service()
    blob = svc.create_backup(PASSWORD, include={n: n == 'audit_logs' for n in manifest.SECTIONS})
    results = svc.restore_backup(blob, PASSWORD, mode=mode)
    db.session.expire_all()
    rows = AuditLog.query.filter_by(action='nul-probe').order_by(AuditLog.id).all()
    assert [r.details for r in rows] == ['clean one', f'with{ESCAPED}nul', 'clean two']
    checked = verify_chain(AuditLog.query.order_by(AuditLog.id).all(), True)
    assert [(e['id'], e['code']) for e in checked['errors']] == [(rows[1].id, 'tampered')]
    warning, = _nul_warnings(results)
    assert warning.startswith('audit_logs.details:') and 'integrity check' in warning

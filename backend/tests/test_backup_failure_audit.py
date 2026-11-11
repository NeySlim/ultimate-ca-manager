"""A failed manual backup or restore leaves an audit line on both route families."""
import io
import json

import pytest

from services.audit_service import AuditService

CREATE = ('/api/v2/system/backup', '/api/v2/settings/backup/create')
RESTORE = ('/api/v2/system/restore', '/api/v2/settings/backup/restore')
SECRET = 'hunter2-secret-password-value'
LEAKY = '/srv/private/path/' + SECRET


@pytest.fixture
def audit(monkeypatch):
    calls = []
    monkeypatch.setattr(AuditService, 'log_action',
                        staticmethod(lambda **kw: calls.append(kw)))
    return calls


def _assert_failure(calls, action):
    assert [(c['action'], c['success']) for c in calls] == [(action, False)]
    text = json.dumps(calls[0], default=str)
    assert SECRET not in text and '/srv/' not in text
    assert calls[0]['details']


@pytest.mark.parametrize('route', CREATE)
@pytest.mark.parametrize('error', ['export', 'validation', 'busy', 'generic'])
def test_failed_backup_is_audited(auth_client, audit, monkeypatch, route, error):
    from services.backup import storage
    from services.backup.locking import BackupBusyError
    from services.backup_service import BackupExportError, BackupValidationError
    exc = {'export': BackupExportError(LEAKY), 'validation': BackupValidationError(LEAKY),
           'busy': BackupBusyError(LEAKY), 'generic': RuntimeError(LEAKY)}[error]

    def boom(*a, **k):
        raise exc
    monkeypatch.setattr(storage, 'export_archive', boom)

    response = auth_client.post(route, data=json.dumps({'password': SECRET + 'xx'}),
                                content_type='application/json')

    assert response.status_code in (409, 500)
    _assert_failure(audit, 'system_backup')


def _upload(client, route):
    return client.post(
        route, data={'file': (io.BytesIO(b'x'), 'r.ucmbkp'), 'password': SECRET + 'xx'},
        content_type='multipart/form-data')


@pytest.mark.parametrize('route', RESTORE)
@pytest.mark.parametrize('error', ['decrypt', 'value', 'generic', 'pending'])
def test_failed_restore_is_audited(auth_client, audit, monkeypatch, route, error):
    import importlib
    from services.backup.decrypt_mixin import BackupDecryptionError
    from services.backup_service import BackupService
    exc = {'decrypt': BackupDecryptionError(LEAKY), 'value': ValueError(LEAKY),
           'generic': RuntimeError(LEAKY), 'pending': None}[error]

    if error == 'pending':
        for module in ('api.v2.system.backup', 'api.v2.settings.backup'):
            monkeypatch.setattr(importlib.import_module(module),
                                'pending_switch_refusal', lambda: LEAKY)
    else:
        def boom(self, *a, **k):
            raise exc
        monkeypatch.setattr(BackupService, 'restore_backup_from_stream', boom)

    response = _upload(auth_client, route)

    assert response.status_code in (400, 409, 500)
    _assert_failure(audit, 'system_restore')


def _post_create(client, route, body):
    return client.post(route, data=json.dumps(body), content_type='application/json')


def _single_refusal(calls, action):
    _assert_failure(calls, action)
    assert 'refused' in calls[0]['details']


@pytest.mark.parametrize('route', CREATE)
def test_a_password_the_rules_refuse_is_audited(auth_client, audit, route):
    response = _post_create(auth_client, route, {'password': 'short'})
    assert response.status_code == 400
    _single_refusal(audit, 'system_backup')


@pytest.mark.parametrize('route', CREATE)
def test_a_refused_kdf_is_audited(auth_client, audit, route):
    response = _post_create(auth_client, route, {'password': SECRET + 'xx', 'kdf': LEAKY})
    assert response.status_code == 400
    _single_refusal(audit, 'system_backup')


def test_a_missing_backup_password_is_audited(auth_client, audit):
    response = _post_create(auth_client, CREATE[0], {})
    assert response.status_code == 400
    _single_refusal(audit, 'system_backup')


@pytest.mark.parametrize('route', CREATE)
def test_a_fips_refused_kdf_is_audited(auth_client, audit, monkeypatch, route):
    import importlib
    from fips_mode import FipsRestricted
    module = importlib.import_module('api.v2.system.backup' if route == CREATE[0] else 'api.v2.settings.backup')

    def refuse(kdf):
        raise FipsRestricted(LEAKY)
    monkeypatch.setattr(module, 'check_backup_kdf', refuse)
    _post_create(auth_client, route, {'password': SECRET + 'xx', 'kdf': 'argon2id'})
    _single_refusal(audit, 'system_backup')


def _restore(client, route, data):
    return client.post(route, data=data, content_type='multipart/form-data')


def _form(filename='r.ucmbkp', **extra):
    data = {'password': SECRET + 'xx', **extra}
    if filename is not None:
        data['file'] = (io.BytesIO(b'x'), filename)
    return data


@pytest.mark.parametrize('route', RESTORE)
@pytest.mark.parametrize('case', ['no_file', 'no_name', 'no_password', 'bad_mode', 'bad_extension', 'too_large'])
def test_a_restore_refused_before_it_starts_is_audited(auth_client, audit, monkeypatch, route, case):
    from services.backup import storage
    data = {
        'no_file': _form(None),
        'no_name': _form(''),
        'no_password': {'file': (io.BytesIO(b'x'), 'r.ucmbkp')},
        'bad_mode': _form(mode=LEAKY),
        'bad_extension': _form('r.exe'),
        'too_large': _form(),
    }[case]
    if case == 'too_large':
        monkeypatch.setattr(storage, 'restore_size_refusal', lambda stream: (413, LEAKY))

    response = _restore(auth_client, route, data)

    assert response.status_code in (400, 413)
    _single_refusal(audit, 'system_restore')


@pytest.mark.parametrize('route', RESTORE)
def test_a_fips_refused_restore_is_audited(auth_client, audit, monkeypatch, route):
    from fips_mode import FipsRestricted
    from services.backup_service import BackupService

    def refuse(self, *a, **k):
        raise FipsRestricted(LEAKY)
    monkeypatch.setattr(BackupService, 'restore_backup_from_stream', refuse)
    _restore(auth_client, route, _form())
    _single_refusal(audit, 'system_restore')


@pytest.mark.parametrize('route', RESTORE)
def test_a_failure_after_the_restore_committed_leaves_no_failure_line(auth_client, audit, monkeypatch, route):
    import importlib
    from services.backup.restore import invalidate
    from services.backup_service import BackupService
    module = importlib.import_module('api.v2.system.backup' if route == RESTORE[0] else 'api.v2.settings.backup')

    monkeypatch.setattr(BackupService, 'restore_backup_from_stream',
                        lambda self, *a, **k: {'sections_carried': ['users']})
    monkeypatch.setattr(invalidate, 'invalidate_after_restore', lambda: 0)
    monkeypatch.setattr(module, '_request_restart_after_restore' if route == RESTORE[0] else 'request_restart',
                        lambda: (False, 'no'))

    def boom(results):
        raise RuntimeError(LEAKY)
    monkeypatch.setattr(module, 'restore_message', boom)

    response = _restore(auth_client, route, _form())

    assert response.status_code == 500
    assert [(c['action'], c['success']) for c in audit] == [('system_restore', True)]


@pytest.mark.parametrize('route', RESTORE)
def test_a_committed_restore_is_audited_even_when_its_details_cannot_be_built(auth_client, audit, monkeypatch, route):
    from services.backup import restore_report
    from services.backup.restore import invalidate
    from services.backup_service import BackupService
    import importlib
    module = importlib.import_module('api.v2.system.backup' if route == RESTORE[0] else 'api.v2.settings.backup')

    monkeypatch.setattr(BackupService, 'restore_backup_from_stream',
                        lambda self, *a, **k: {'sections_carried': ['users']})
    monkeypatch.setattr(invalidate, 'invalidate_after_restore', lambda: 0)
    monkeypatch.setattr(module, '_request_restart_after_restore' if route == RESTORE[0] else 'request_restart',
                        lambda: (False, 'no'))

    def boom(filename, results):
        raise RuntimeError(LEAKY)
    monkeypatch.setattr(restore_report, 'restore_audit_details', boom)

    _restore(auth_client, route, _form())

    assert [(c['action'], c['success']) for c in audit] == [('system_restore', True)]
    assert LEAKY not in str(audit)


def _raw_restore(client, route, filename, **fields):
    """A multipart restore whose file name travels as RFC 2231 filename*, CR and LF included."""
    from urllib.parse import quote
    parts = [f'--B\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'
             for k, v in {'password': SECRET + 'xx', **fields}.items()]
    parts.append("--B\r\nContent-Disposition: form-data; name=\"file\"; "
                 f"filename*=UTF-8''{quote(filename, safe='')}\r\n"
                 "Content-Type: application/octet-stream\r\n\r\nx\r\n--B--\r\n")
    return client.post(route, data=''.join(parts).encode(),
                       content_type='multipart/form-data; boundary=B')


@pytest.mark.parametrize('route', RESTORE)
@pytest.mark.parametrize('outcome', ['restored', 'refused'])
def test_the_audited_file_name_is_its_base_name_on_one_line(auth_client, audit, monkeypatch,
                                                           route, outcome):
    import importlib
    from services.backup.restore import invalidate
    from services.backup_service import BackupService
    module = importlib.import_module('api.v2.system.backup' if route == RESTORE[0] else 'api.v2.settings.backup')
    if outcome == 'restored':
        monkeypatch.setattr(BackupService, 'restore_backup_from_stream',
                            lambda self, *a, **k: {'sections_carried': ['users']})
        monkeypatch.setattr(invalidate, 'invalidate_after_restore', lambda: 0)
        monkeypatch.setattr(module, '_request_restart_after_restore' if route == RESTORE[0]
                            else 'request_restart', lambda: (False, 'no'))
        _raw_restore(auth_client, route, '../../x\r\nforged.ucmbkp')
        audited = 'xforged.ucmbkp'
    else:
        _raw_restore(auth_client, route, '../../x\r\nforged', mode=LEAKY)
        audited = 'xforged'
    assert [(c['action'], c['success'], c['resource_name']) for c in audit] == [
        ('system_restore', outcome == 'restored', audited)]
    assert not any(ch in audit[0]['details'] for ch in '\r\n/') and '..' not in audit[0]['details']


@pytest.mark.parametrize('raw, audited', [
    ('../../x\r\nforged', 'xforged'), ('C:\\dir\\b.ucmbkp', 'b.ucmbkp'),
    ('a\x00\x1b\x7f\x85\u2028b', 'ab'), ('n' * 300, 'n' * 255), ('../\r\n', 'upload'),
    ('evil\u202egpj.exe', 'evilgpj.exe'), ('a\u200bb\ufeff', 'ab'), ('  ', 'upload'),
    (' . x.ucmbkp. ', 'x.ucmbkp')])
def test_client_filename(raw, audited):
    from utils.sanitize import client_filename
    assert client_filename(raw) == audited

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

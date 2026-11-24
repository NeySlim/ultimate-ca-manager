"""The restore answer lists, one line per element, what the operator still has to do."""
import io

import pytest

from config.settings import Config
from services.backup import storage
from services.backup.restore_report import restore_todo_lines
from tests.fresh_app import fresh_app_fixtures
from tests.restore_support import post_to_the_end

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

DEGRADED = {
    'sections_carried': ['cas'],
    'sections_not_restored': ['hsm_providers', 'future_thing'],
    'key_mismatches': ['issuing-ca'],
    'invalidated': {'crls_failed': ['Root CA'], 'crls_delta_failed': ['Sub CA']},
    'dropped_secrets': ['smtp password'],
}


class TestTodoLines:
    def test_one_line_per_element_naming_it(self):
        lines = restore_todo_lines(DEGRADED)
        assert len(lines) == 6
        for name in ('hsm_providers', 'future_thing', 'issuing-ca', 'Root CA', 'Sub CA', 'smtp password'):
            assert sum(name in line for line in lines) == 1, (name, lines)

    def test_a_clean_restore_has_nothing_to_do(self):
        assert restore_todo_lines({'sections_carried': ['cas'], 'invalidated': {}}) == []

    def test_a_crl_pass_that_failed_as_a_whole_is_said(self):
        lines = restore_todo_lines({'invalidated': {'crls_not_regenerated': True}})
        assert len(lines) == 1 and 'CRL' in lines[0]


class TestRoutesAnswerWithTheLines:
    @pytest.mark.parametrize('route', ('/api/v2/system/restore', '/api/v2/settings/backup/restore'))
    def test_data_carries_todo(self, app, auth_client, monkeypatch, route):
        import services.backup.restore.invalidate as invalidate
        from services.backup_service import BackupService

        monkeypatch.setattr(BackupService, 'restore_backup_from_stream',
                            lambda self, *a, **k: {k_: v for k_, v in DEGRADED.items() if k_ != 'invalidated'})
        monkeypatch.setattr(BackupService, 'check_archive_opens', lambda self, *a, **k: None)
        monkeypatch.setattr(invalidate, 'invalidate_after_restore',
                            lambda *a, **k: DEGRADED['invalidated'])
        from tests.restore_job_support import sessions_kept
        sessions_kept(monkeypatch)  # the restore job's own sessions step
        # The restore job's CRL step reports what the degraded aftermath says
        monkeypatch.setattr(invalidate, 'regenerate_crls_summary',
                            lambda: dict(DEGRADED['invalidated']))
        # At its source, read at call time by the restore job: no restart file is written
        monkeypatch.setattr('services.backup.restore_completion.request_restart', lambda: (True, 'ok'))

        response = post_to_the_end(
            auth_client, route, data={'file': (io.BytesIO(b'x'), 'x.ucmbkp'),
                                      'password': 'a-password-that-is-long-enough'},
            content_type='multipart/form-data')

        assert response.status_code == 200, response.data
        todo = response.get_json()['data']['todo']
        assert len(todo) == 6 and any('Root CA' in line for line in todo)


class TestListingAnnouncesTheRestoreLimits:
    def test_meta_carries_both_ceilings(self, app, auth_client, tmp_path, monkeypatch):
        monkeypatch.setattr(Config, 'BACKUP_DIR', tmp_path, raising=False)
        monkeypatch.setattr(Config, 'BACKUP_MAX_UPLOAD_MB', 512, raising=False)
        monkeypatch.setattr(Config, 'BACKUP_MAX_ARCHIVE_MB', 2048, raising=False)
        meta = auth_client.get('/api/v2/system/backups').get_json()['data']['meta']
        assert meta['restore_limits'] == {
            'upload_bytes': storage.restore_upload_limit(),
            'archive_bytes': storage.restore_archive_limit(),
        }
        assert meta['restore_limits']['archive_bytes'] == 2048 * 1024 * 1024


class TestArchiveWithoutSection:
    @pytest.mark.parametrize('route', ('/api/v2/system/restore', '/api/v2/settings/backup/restore'))
    def test_early_answer_still_lists_what_was_not_restored(self, app, auth_client, monkeypatch, route):
        from services.backup_service import BackupService

        monkeypatch.setattr(BackupService, 'restore_backup_from_stream',
                            lambda self, *a, **k: {'sections_carried': [],
                                                   'sections_not_restored': ['future_thing']})
        monkeypatch.setattr(BackupService, 'check_archive_opens', lambda self, *a, **k: None)

        response = post_to_the_end(
            auth_client, route, data={'file': (io.BytesIO(b'x'), 'x.ucmbkp'),
                                      'password': 'a-password-that-is-long-enough'},
            content_type='multipart/form-data')

        assert response.status_code == 200, response.data
        data = response.get_json()['data']
        assert len(data['todo']) == 1 and 'future_thing' in data['todo'][0]
        assert 'restart_requested' not in data

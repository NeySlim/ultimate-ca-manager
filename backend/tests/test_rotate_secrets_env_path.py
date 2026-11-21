"""The secret rotation writes the sandboxed env file, never the machine's."""
import pytest

from tests.conftest import UCM_TEST_ENV_FILE

SECRET = 'x' * 40


def test_rotation_targets_the_sandbox_env_file_pos(auth_client, monkeypatch):
    seen = []

    def guarded(path, *a, **k):
        # raises before any write when the path is not the sandbox
        seen.append(path)
        assert str(path) == str(UCM_TEST_ENV_FILE), f'unsandboxed env path {path}'
        return True, 'ok', None

    monkeypatch.setattr('api.v2.system.security.update_env_file', guarded)
    monkeypatch.setattr('utils.service_manager.restart_service', lambda *a, **k: True)
    r = auth_client.post('/api/v2/system/security/rotate-secrets',
                         json={'new_secret': SECRET})
    assert r.status_code == 200, r.data
    assert seen

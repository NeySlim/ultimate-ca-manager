"""`hostname -f` is resolved once per process; env overrides stay live."""
import subprocess

import pytest

from config import settings


@pytest.fixture
def native(monkeypatch):
    """Simulated native install: spy on subprocess.run, no FQDN env."""
    monkeypatch.setattr(settings, 'is_docker', lambda: False)
    monkeypatch.delenv('FQDN', raising=False)
    monkeypatch.delenv('UCM_FQDN', raising=False)
    calls = []

    def make(stdout='', returncode=0, exc=None):
        def fake_run(cmd, *a, **kw):
            calls.append(cmd)
            if exc:
                raise exc
            return subprocess.CompletedProcess(cmd, returncode, stdout, '')
        monkeypatch.setattr(settings.subprocess, 'run', fake_run)
        settings._system_hostname_fqdn.cache_clear()
        return calls
    yield make
    settings._system_hostname_fqdn.cache_clear()


def test_api_requests_spawn_hostname_once(native, auth_client):
    calls = native(stdout='pi.example.net\n')
    for _ in range(3):
        assert auth_client.get('/api/v2/webhooks').status_code == 200
        assert auth_client.get('/api/v2/dashboard/stats').status_code == 200
    assert len(calls) <= 1


@pytest.mark.parametrize('kw', [
    dict(stdout='nodot\n'),
    dict(stdout=''),
    dict(stdout='localhost\n'),
    dict(stdout='a.b\n', returncode=1),
    dict(exc=FileNotFoundError()),
    dict(exc=subprocess.TimeoutExpired('hostname', 2)),
    dict(exc=subprocess.SubprocessError()),
])
def test_failed_or_invalid_hostname_runs_once(native, kw):
    calls = native(**kw)
    for _ in range(4):
        assert settings.get_system_fqdn() is None
    assert len(calls) == 1


def test_fqdn_env_set_after_first_call_is_honoured(native, monkeypatch):
    calls = native(stdout='nodot\n')
    assert settings.get_system_fqdn() is None
    monkeypatch.setenv('FQDN', 'late.example.org')
    assert settings.get_system_fqdn() == 'late.example.org'
    assert len(calls) == 1

"""UCM_FIPS=1 stops the process unless both libraries run on a FIPS provider
and the self-tests pass; the API shows the module without /health naming
versions."""
import logging

import _hashlib
import pytest
from cryptography.hazmat.bindings._rust import openssl as rust_openssl

import fips_mode

LOG = logging.getLogger('test-fips-startup')


@pytest.fixture
def providers(monkeypatch):
    """Set what each library reports: providers(pyca=True, hashlib=False)."""
    def set_state(pyca, hashlib):
        monkeypatch.setattr(rust_openssl, 'is_fips_enabled', lambda: pyca)
        monkeypatch.setattr(_hashlib, 'get_fips_mode', lambda: int(hashlib), raising=False)
    return set_state


class TestEnforceAtStartup:
    @pytest.mark.parametrize('pyca, hashlib, named', [
        (False, False, 'cryptography is not running on a FIPS provider'),
        (False, True, 'cryptography is not running on a FIPS provider'),
        (True, False, 'hashlib is not running on a FIPS provider'),
    ])
    def test_a_missing_provider_stops_the_process(self, monkeypatch, providers, caplog,
                                                  pyca, hashlib, named):
        monkeypatch.setenv('UCM_FIPS', '1')
        providers(pyca, hashlib)
        monkeypatch.setattr(fips_mode, 'self_tests', lambda: None)
        with caplog.at_level(logging.ERROR), pytest.raises(SystemExit) as exc:
            fips_mode.enforce_at_startup(LOG)
        assert exc.value.code == 1
        assert named in caplog.text

    def test_a_failed_self_test_stops_the_process(self, monkeypatch, providers, caplog):
        monkeypatch.setenv('UCM_FIPS', '1')
        providers(True, True)

        def failing():
            raise RuntimeError('MD5 in cryptography still works')
        monkeypatch.setattr(fips_mode, 'self_tests', failing)
        with caplog.at_level(logging.ERROR), pytest.raises(SystemExit):
            fips_mode.enforce_at_startup(LOG)
        assert 'FIPS self-test failed: MD5 in cryptography still works' in caplog.text

    def test_an_active_provider_names_the_module(self, monkeypatch, providers, caplog):
        monkeypatch.setenv('UCM_FIPS', '1')
        providers(True, True)
        monkeypatch.setattr(fips_mode, 'self_tests', lambda: None)
        monkeypatch.setattr(fips_mode, 'provider_info', lambda: {
            'name': 'OpenSSL FIPS Provider', 'version': '3.1.2', 'buildinfo': '3.1.2'})
        with caplog.at_level(logging.INFO):
            fips_mode.enforce_at_startup(LOG)
        assert 'FIPS mode active: OpenSSL FIPS Provider 3.1.2' in caplog.text

    def test_without_ucm_fips_nothing_is_checked(self, monkeypatch, providers):
        monkeypatch.delenv('UCM_FIPS', raising=False)
        providers(False, False)

        def must_not_run():
            raise AssertionError('self-tests ran without UCM_FIPS')
        monkeypatch.setattr(fips_mode, 'self_tests', must_not_run)
        fips_mode.enforce_at_startup(LOG)


class _Stopped(Exception):
    pass


def test_create_app_runs_the_check_before_anything_else(monkeypatch):
    def stop(log):
        raise _Stopped
    monkeypatch.setattr(fips_mode, 'enforce_at_startup', stop)
    from app import create_app
    with pytest.raises(_Stopped):
        create_app('testing')


@pytest.mark.skipif(fips_mode.provider_active(), reason='runs on a FIPS provider')
class TestSelfTestsWithoutProvider:
    def test_they_fail_on_the_default_provider(self):
        # The test environment runs without a FIPS provider: MD5 still works
        with pytest.raises(RuntimeError, match='still works'):
            fips_mode.self_tests()

    def test_no_fips_provider_is_reported_here(self):
        assert fips_mode.provider_info() is None


class TestApi:
    def test_status_carries_the_crypto_block(self, auth_client, monkeypatch, providers):
        monkeypatch.setenv('UCM_FIPS', '1')
        providers(True, True)
        monkeypatch.setattr(fips_mode, 'provider_info', lambda: {
            'name': 'OpenSSL FIPS Provider', 'version': '3.1.2', 'buildinfo': '3.1.2'})
        crypto = auth_client.get('/api/v2/system/service/status').get_json()['data']['crypto']
        assert crypto['fips_requested'] and crypto['fips_active'] and crypto['provider_active']
        assert crypto['provider']['version'] == '3.1.2'
        assert crypto['library'] == fips_mode.library_version()

    def test_status_outside_fips(self, auth_client, monkeypatch):
        monkeypatch.delenv('UCM_FIPS', raising=False)
        crypto = auth_client.get('/api/v2/system/service/status').get_json()['data']['crypto']
        assert crypto == {'fips_requested': False, 'fips_active': False, 'provider_active': False,
                          'library': fips_mode.library_version(), 'provider': None}

    @pytest.mark.parametrize('active', [True, False])
    def test_health_says_whether_fips_is_on_without_versions(self, client, monkeypatch, active):
        monkeypatch.setattr(fips_mode, 'enabled', lambda: active)
        body = client.get('/api/v2/health').get_json()
        assert body['fips_active'] is active
        assert 'library' not in body and 'provider' not in body

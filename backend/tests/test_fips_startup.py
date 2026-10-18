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
        monkeypatch.setattr(fips_mode, 'module_settings',
                            lambda: dict.fromkeys(fips_mode.APPROVED_MODE_SETTINGS, 1))
        with caplog.at_level(logging.INFO):
            fips_mode.enforce_at_startup(LOG)
        assert 'FIPS mode active: OpenSSL FIPS Provider 3.1.2' in caplog.text

    @pytest.mark.parametrize('url', [
        'postgresql://ucm@db.example/ucm',
        'postgresql://ucm@db.example/ucm?sslmode=prefer',
    ])
    def test_postgres_without_tls_stops_the_process(self, monkeypatch, providers, caplog, url):
        monkeypatch.setenv('UCM_FIPS', '1')
        monkeypatch.delenv('PGSSLMODE', raising=False)
        providers(True, True)
        monkeypatch.setattr(fips_mode, 'self_tests', lambda: None)
        with caplog.at_level(logging.ERROR), pytest.raises(SystemExit):
            fips_mode.enforce_at_startup(LOG, url)
        assert 'DATABASE_URL reaches PostgreSQL over TCP with sslmode=' in caplog.text

    @pytest.mark.parametrize('url', [
        'postgresql://ucm@db.example/ucm?sslmode=require',
        'postgresql://ucm@db.example/ucm?sslmode=verify-full',
        'postgresql://ucm@/ucm?host=/run/postgresql',
        'sqlite:////var/lib/ucm/ucm.db',
        '',
    ])
    def test_tls_socket_or_sqlite_starts(self, monkeypatch, providers, url):
        monkeypatch.setenv('UCM_FIPS', '1')
        monkeypatch.delenv('PGSSLMODE', raising=False)
        monkeypatch.delenv('PGHOST', raising=False)
        providers(True, True)
        monkeypatch.setattr(fips_mode, 'self_tests', lambda: None)
        monkeypatch.setattr(fips_mode, 'provider_info', lambda: None)
        fips_mode.enforce_at_startup(LOG, url)

    def test_create_app_passes_the_database_url(self, monkeypatch):
        seen = {}

        def capture(log, database_url=''):
            seen['url'] = database_url
            raise _Stopped
        monkeypatch.setattr(fips_mode, 'enforce_at_startup', capture)
        from app import create_app
        with pytest.raises(_Stopped):
            create_app('testing')
        assert seen['url'].startswith('sqlite:')

    def test_without_ucm_fips_nothing_is_checked(self, monkeypatch, providers):
        monkeypatch.delenv('UCM_FIPS', raising=False)
        providers(False, False)

        def must_not_run():
            raise AssertionError('self-tests ran without UCM_FIPS')
        monkeypatch.setattr(fips_mode, 'self_tests', must_not_run)
        fips_mode.enforce_at_startup(LOG)


class _Stopped(Exception):
    pass


UPSTREAM = {'name': 'OpenSSL FIPS Provider', 'version': '3.1.2', 'buildinfo': '3.1.2'}
ALL_ON = dict.fromkeys(fips_mode.APPROVED_MODE_SETTINGS, 1)


class TestApprovedModeSettings:
    """The upstream provider must run with every setting of its security
    policy's approved mode at 1; a distribution module is not judged."""

    @pytest.fixture
    def active(self, monkeypatch, providers):
        monkeypatch.setenv('UCM_FIPS', '1')
        providers(True, True)
        monkeypatch.setattr(fips_mode, 'self_tests', lambda: None)

        def set_module(info, settings):
            monkeypatch.setattr(fips_mode, 'provider_info', lambda: info)
            monkeypatch.setattr(fips_mode, 'module_settings', lambda: settings)
        return set_module

    @pytest.mark.parametrize('setting', fips_mode.APPROVED_MODE_SETTINGS)
    @pytest.mark.parametrize('value', [0, None])
    def test_a_setting_off_or_unreported_stops_the_process(self, active, caplog, setting, value):
        active(UPSTREAM, {**ALL_ON, setting: value})
        with caplog.at_level(logging.ERROR), pytest.raises(SystemExit):
            fips_mode.enforce_at_startup(LOG)
        assert f'runs with {setting} not at 1' in caplog.text

    def test_unreadable_settings_stop_the_process(self, active, caplog):
        active(UPSTREAM, None)
        with caplog.at_level(logging.ERROR), pytest.raises(SystemExit):
            fips_mode.enforce_at_startup(LOG)
        assert 'security-checks, tls1-prf-ems-check, drbg-no-trunc-md not at 1' in caplog.text

    def test_all_settings_on_starts(self, active, caplog):
        active(UPSTREAM, ALL_ON)
        with caplog.at_level(logging.INFO):
            fips_mode.enforce_at_startup(LOG)
        assert 'FIPS mode active: OpenSSL FIPS Provider 3.1.2' in caplog.text

    def test_a_distribution_module_follows_its_own_policy(self, active, caplog):
        # Measured on a RHEL-family host: drbg-no-trunc-md = 0, Ubuntu reports none
        active({'name': 'Red Hat Enterprise Linux OpenSSL FIPS Provider', 'version': '3.5.8'},
               {**ALL_ON, 'drbg-no-trunc-md': 0})
        with caplog.at_level(logging.INFO):
            fips_mode.enforce_at_startup(LOG)
        assert 'FIPS mode active: Red Hat Enterprise Linux OpenSSL FIPS Provider' in caplog.text


@pytest.mark.skipif(fips_mode.provider_active(), reason='runs on a FIPS provider')
def test_no_settings_are_reported_without_a_fips_provider():
    assert fips_mode.module_settings() is None


def test_create_app_runs_the_check_before_anything_else(monkeypatch):
    def stop(log, database_url=''):
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
        monkeypatch.setattr(fips_mode, 'module_settings',
                            lambda: dict.fromkeys(fips_mode.APPROVED_MODE_SETTINGS, 1))
        monkeypatch.setattr(fips_mode, 'provider_info', lambda: {
            'name': 'OpenSSL FIPS Provider', 'version': '3.1.2', 'buildinfo': '3.1.2'})
        crypto = auth_client.get('/api/v2/system/service/status').get_json()['data']['crypto']
        assert crypto['fips_requested'] and crypto['fips_active'] and crypto['provider_active']
        assert crypto['provider']['version'] == '3.1.2'
        assert crypto['module_settings'] == dict.fromkeys(fips_mode.APPROVED_MODE_SETTINGS, 1)
        assert crypto['library'] == fips_mode.library_version()

    def test_status_outside_fips(self, auth_client, monkeypatch):
        monkeypatch.delenv('UCM_FIPS', raising=False)
        crypto = auth_client.get('/api/v2/system/service/status').get_json()['data']['crypto']
        assert crypto == {'fips_requested': False, 'fips_active': False, 'provider_active': False,
                          'library': fips_mode.library_version(), 'provider': None,
                          'module_settings': None}

    @pytest.mark.parametrize('active', [True, False])
    def test_health_says_whether_fips_is_on_without_versions(self, client, monkeypatch, active):
        monkeypatch.setattr(fips_mode, 'enabled', lambda: active)
        body = client.get('/api/v2/health').get_json()
        assert body['fips_active'] is active
        assert 'library' not in body and 'provider' not in body

"""UCM_FIPS=1 stops the process unless both libraries run on a FIPS provider
and the self-tests pass; the API shows the module without /health naming
versions."""
import logging

import _hashlib
import pytest
from cryptography.hazmat.bindings._rust import openssl as rust_openssl

import fips_mode

LOG = logging.getLogger('test-fips-startup')
REAL_TLS_SELF_TEST = fips_mode.tls_self_test


@pytest.fixture(autouse=True)
def pg_environment_restored(monkeypatch):
    """enforce_at_startup sets PGGSSENCMODE: undo it after each test."""
    monkeypatch.setenv('PGGSSENCMODE', 'unset')
    monkeypatch.delenv('PGGSSENCMODE')


@pytest.fixture(autouse=True)
def tls_checked_elsewhere(monkeypatch):
    """The test process negotiates X25519: TestTlsGroups runs the TLS check for real."""
    monkeypatch.setattr(fips_mode, 'tls_self_test', lambda: None)


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


def _libpq_default(keyword):
    """What libpq itself would use for ``keyword`` with no value in the connection string."""
    import ctypes
    import ctypes.util

    class Option(ctypes.Structure):
        _fields_ = [('keyword', ctypes.c_char_p), ('envvar', ctypes.c_char_p),
                    ('compiled', ctypes.c_char_p), ('val', ctypes.c_char_p),
                    ('label', ctypes.c_char_p), ('dispchar', ctypes.c_char_p),
                    ('dispsize', ctypes.c_int)]
    try:
        lib = ctypes.CDLL(ctypes.util.find_library('pq') or 'libpq.so.5')
    except OSError:
        pytest.skip('libpq is not installed')
    lib.PQconndefaults.restype = ctypes.POINTER(Option)
    lib.PQconninfoFree.argtypes = [ctypes.POINTER(Option)]
    options = lib.PQconndefaults()
    try:
        i = 0
        while options[i].keyword:
            if options[i].keyword.decode() == keyword:
                value = options[i].val or options[i].compiled
                return value.decode() if value else None
            i += 1
    finally:
        lib.PQconninfoFree(options)
    pytest.skip(f'this libpq has no {keyword}')


class TestPostgresGssapiEncryption:
    """libpq prefers GSSAPI encryption (Kerberos library, outside the module) to
    TLS when a ticket is present: FIPS mode turns it off or refuses to start."""

    @pytest.fixture
    def active(self, monkeypatch, providers):
        monkeypatch.setenv('UCM_FIPS', '1')
        monkeypatch.delenv('PGSSLMODE', raising=False)
        monkeypatch.delenv('PGHOST', raising=False)
        providers(True, True)
        monkeypatch.setattr(fips_mode, 'self_tests', lambda: None)
        monkeypatch.setattr(fips_mode, 'provider_info', lambda: None)

    @pytest.mark.parametrize('url, env', [
        ('postgresql://ucm@db.example/ucm?sslmode=require&gssencmode=prefer', None),
        ('postgresql://ucm@db.example/ucm?sslmode=require&gssencmode=require', None),
        ('postgresql://ucm@db.example/ucm?sslmode=require', 'prefer'),
    ])
    def test_gssapi_encryption_asked_for_stops_the_process(self, monkeypatch, active, caplog,
                                                           url, env):
        if env:
            monkeypatch.setenv('PGGSSENCMODE', env)
        with caplog.at_level(logging.ERROR), pytest.raises(SystemExit):
            fips_mode.enforce_at_startup(LOG, url)
        assert 'PostgreSQL is set to gssencmode=' in caplog.text

    @pytest.mark.parametrize('url', [
        'postgresql://ucm@db.example/ucm?sslmode=require',
        'postgresql://ucm@db.example/ucm?sslmode=require&gssencmode=disable',
        'postgresql://ucm@/ucm?host=/run/postgresql&gssencmode=prefer',
        'sqlite:////var/lib/ucm/ucm.db',
    ])
    def test_otherwise_libpq_is_told_to_disable_it(self, active, url):
        assert _libpq_default('gssencmode') == 'prefer'
        fips_mode.enforce_at_startup(LOG, url)
        assert _libpq_default('gssencmode') == 'disable'

    def test_standard_mode_leaves_libpq_alone(self, monkeypatch, providers):
        monkeypatch.delenv('UCM_FIPS', raising=False)
        fips_mode.enforce_at_startup(LOG, 'postgresql://ucm@db.example/ucm?sslmode=require')
        assert _libpq_default('gssencmode') == 'prefer'


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


GROUPS_CNF = """openssl_conf = openssl_init

[openssl_init]
ssl_conf = ssl_sect

[ssl_sect]
system_default = system_default_sect

[system_default_sect]
Groups = P-256:P-384:P-521:ffdhe2048:ffdhe3072:ffdhe4096
"""


def _tls_self_test_in(tmp_path, groups):
    """Run tls_self_test() in a fresh interpreter, with or without the Groups section."""
    import os
    import subprocess
    import sys
    env = {k: v for k, v in os.environ.items() if k != 'OPENSSL_CONF'}
    if groups:
        (tmp_path / 'groups.cnf').write_text(GROUPS_CNF)
        env['OPENSSL_CONF'] = str(tmp_path / 'groups.cnf')
    code = 'import fips_mode; fips_mode.tls_self_test(); print("passed")'
    return subprocess.run([sys.executable, '-c', code], cwd=os.path.dirname(fips_mode.__file__),
                          env=env, capture_output=True, text=True, timeout=60)


class TestTlsGroups:
    def test_x25519_offered_by_default_fails_the_check(self, tmp_path):
        result = _tls_self_test_in(tmp_path, groups=False)
        assert result.returncode != 0
        assert 'TLS still negotiates X25519' in result.stderr

    def test_the_groups_section_passes_it(self, tmp_path):
        result = _tls_self_test_in(tmp_path, groups=True)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == 'passed'

    def test_this_process_negotiates_every_group(self):
        for group in ('X25519', 'X448', 'prime256v1', 'secp384r1'):
            assert fips_mode.tls_negotiates(group) is True, group

    @pytest.mark.parametrize('narrowed', ['clients', 'servers'])
    def test_either_side_accepting_x25519_is_seen(self, monkeypatch, narrowed):
        import ssl
        real = ssl.create_default_context
        purpose = ssl.Purpose.SERVER_AUTH if narrowed == 'clients' else ssl.Purpose.CLIENT_AUTH

        def factory(which=ssl.Purpose.SERVER_AUTH, **kwargs):
            ctx = real(which, **kwargs)
            if which == purpose:
                ctx.set_ecdh_curve('prime256v1')
            return ctx
        monkeypatch.setattr(ssl, 'create_default_context', factory)
        assert fips_mode.tls_negotiates('X25519') is True

    @pytest.mark.parametrize('group', ['X25519', 'X448'])
    def test_each_refused_group_is_checked(self, monkeypatch, group):
        monkeypatch.setattr(fips_mode, 'tls_negotiates', lambda g: g in (group, 'prime256v1'))
        with pytest.raises(RuntimeError, match=f'TLS still negotiates {group}'):
            REAL_TLS_SELF_TEST()

    def test_tls_that_fails_on_p256_fails_the_check(self, monkeypatch):
        monkeypatch.setattr(fips_mode, 'tls_negotiates', lambda group: False)
        with pytest.raises(RuntimeError, match='TLS fails on P-256'):
            REAL_TLS_SELF_TEST()

    def test_a_failure_stops_the_process(self, monkeypatch, providers, caplog):
        monkeypatch.setenv('UCM_FIPS', '1')
        providers(True, True)
        monkeypatch.setattr(fips_mode, 'self_tests', lambda: None)
        monkeypatch.setattr(fips_mode, 'tls_self_test', REAL_TLS_SELF_TEST)
        monkeypatch.setattr(fips_mode, 'tls_negotiates', lambda group: True)
        with caplog.at_level(logging.ERROR), pytest.raises(SystemExit):
            fips_mode.enforce_at_startup(LOG)
        assert 'FIPS self-test failed: TLS still negotiates X25519' in caplog.text

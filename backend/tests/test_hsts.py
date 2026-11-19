"""Tests for operator-configurable HSTS header (issue #154)."""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.hsts import build_hsts_header, hsts_enabled, hsts_include_subdomains, hsts_max_age, hsts_env_locked
from models import SystemConfig, db


def _set_cfg(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if row is None:
        row = SystemConfig(key=key, value=str(value))
        db.session.add(row)
    else:
        row.value = str(value)
    db.session.commit()


def _clear_cfg(key):
    row = SystemConfig.query.filter_by(key=key).first()
    if row is not None:
        db.session.delete(row)
        db.session.commit()


@pytest.fixture(autouse=True)
def _clean_hsts_env(monkeypatch, app):
    # Disable env overrides so DB / defaults are exercised.
    for var in ('UCM_HSTS_ENABLED', 'UCM_HSTS_INCLUDE_SUBDOMAINS',
               'UCM_HSTS_MAX_AGE', 'ucm_hsts_enabled',
               'ucm_hsts_include_subdomains', 'ucm_hsts_max_age'):
        monkeypatch.delenv(var, raising=False)
    yield
    with app.app_context():
        for key in ('hsts_enabled', 'hsts_include_subdomains', 'hsts_max_age'):
            _clear_cfg(key)


class TestHstsDefaults:
    def test_defaults_to_legacy_header(self, app):
        with app.app_context():
            assert hsts_enabled() is True
            assert hsts_include_subdomains() is True
            assert hsts_max_age() == 31536000
            assert build_hsts_header() == 'max-age=31536000; includeSubDomains'


class TestHstsDisabled:
    def test_disabled_via_db(self, app):
        with app.app_context():
            _set_cfg('hsts_enabled', 'false')
            assert hsts_enabled() is False
            assert build_hsts_header() is None

    def test_disabled_via_env(self, app, monkeypatch):
        monkeypatch.setenv('UCM_HSTS_ENABLED', '0')
        with app.app_context():
            assert hsts_enabled() is False
            assert build_hsts_header() is None

    def test_env_override_wins_over_db(self, app, monkeypatch):
        monkeypatch.setenv('UCM_HSTS_ENABLED', 'true')
        with app.app_context():
            _set_cfg('hsts_enabled', 'false')
            assert hsts_enabled() is True


class TestHstsOptions:
    def test_drop_include_subdomains(self, app):
        with app.app_context():
            _set_cfg('hsts_include_subdomains', 'false')
            assert hsts_include_subdomains() is False
            assert build_hsts_header() == 'max-age=31536000'

    def test_custom_max_age(self, app):
        with app.app_context():
            _set_cfg('hsts_max_age', '86400')
            assert hsts_max_age() == 86400
            assert build_hsts_header() == 'max-age=86400; includeSubDomains'

    def test_invalid_max_age_falls_back(self, app):
        with app.app_context():
            _set_cfg('hsts_max_age', 'not-a-number')
            assert hsts_max_age() == 31536000

    def test_negative_max_age_clamped(self, app):
        with app.app_context():
            _set_cfg('hsts_max_age', '-5')
            assert hsts_max_age() == 0


class TestHstsEnvLocked:
    def test_no_env_returns_empty(self, app):
        with app.app_context():
            assert hsts_env_locked() == []

    def test_detects_each_var(self, app, monkeypatch):
        with app.app_context():
            monkeypatch.setenv('UCM_HSTS_ENABLED', '0')
            assert hsts_env_locked() == ['hsts_enabled']
            monkeypatch.setenv('UCM_HSTS_INCLUDE_SUBDOMAINS', 'true')
            assert hsts_env_locked() == ['hsts_enabled', 'hsts_include_subdomains']
            monkeypatch.setenv('UCM_HSTS_MAX_AGE', '3600')
            assert hsts_env_locked() == ['hsts_enabled', 'hsts_include_subdomains', 'hsts_max_age']

    def test_lower_case_env_also_detected(self, app, monkeypatch):
        # /etc/ucm/ucm.env is sourced as-is; canonical UPPER + lower both honored
        monkeypatch.setenv('ucm_hsts_enabled', '1')
        with app.app_context():
            assert hsts_env_locked() == ['hsts_enabled']


class TestHstsHeaderInResponse:
    def test_header_present_by_default(self, client):
        r = client.get('/api/v2/health')
        assert 'Strict-Transport-Security' in r.headers
        assert r.headers['Strict-Transport-Security'] == 'max-age=31536000; includeSubDomains'

    def test_header_absent_when_disabled(self, app, client):
        with app.app_context():
            _set_cfg('hsts_enabled', 'false')
        r = client.get('/api/v2/health')
        assert 'Strict-Transport-Security' not in r.headers

    def test_header_reflects_custom_max_age(self, app, client):
        with app.app_context():
            _set_cfg('hsts_max_age', '3600')
            _set_cfg('hsts_include_subdomains', 'false')
        r = client.get('/api/v2/health')
        assert r.headers['Strict-Transport-Security'] == 'max-age=3600'



class _Unreadable:
    """SystemConfig.query on a database that cannot answer."""
    def __get__(self, obj, owner):
        raise RuntimeError('database is locked')


@pytest.fixture
def unreadable():
    SystemConfig.query = _Unreadable()
    try:
        yield
    finally:
        del SystemConfig.query


class TestHstsUnreadableSetting:
    def test_no_header_when_the_setting_cannot_be_read(self, app, unreadable):
        """A database that cannot answer may hold hsts_enabled=false: no header then."""
        with app.app_context():
            assert build_hsts_header() is None

    def test_the_environment_still_decides_when_it_sets_all_three(self, app, monkeypatch, unreadable):
        monkeypatch.setenv('UCM_HSTS_ENABLED', '1')
        monkeypatch.setenv('UCM_HSTS_INCLUDE_SUBDOMAINS', '0')
        monkeypatch.setenv('UCM_HSTS_MAX_AGE', '600')
        with app.app_context():
            assert build_hsts_header() == 'max-age=600'

    def test_enabled_by_the_environment_is_not_enough(self, app, monkeypatch, unreadable):
        """The duration and scope the database may hold are unknown: no header."""
        monkeypatch.setenv('UCM_HSTS_ENABLED', '1')
        with app.app_context():
            assert build_hsts_header() is None


class _OneKeyUnreadable:
    """SystemConfig.query that cannot answer for one key only."""
    def __init__(self, key):
        self.key = key

    def __get__(self, obj, owner):
        real = db.session.query(owner)
        key = self.key

        class _Query:
            def filter_by(self, **kw):
                if kw.get('key') == key:
                    raise RuntimeError('database is locked')
                return real.filter_by(**kw)
        return _Query()


@pytest.fixture
def unreadable_key():
    def make(key):
        SystemConfig.query = _OneKeyUnreadable(key)
    try:
        yield make
    finally:
        if isinstance(SystemConfig.__dict__.get('query'), _OneKeyUnreadable):
            del SystemConfig.query


@pytest.mark.parametrize('key', ['hsts_enabled', 'hsts_include_subdomains', 'hsts_max_age'])
def test_any_unreadable_setting_emits_no_header(app, unreadable_key, key):
    unreadable_key(key)
    with app.app_context():
        assert build_hsts_header() is None


@pytest.mark.parametrize('key, env, value', [
    ('hsts_include_subdomains', 'UCM_HSTS_INCLUDE_SUBDOMAINS', '1'),
    ('hsts_max_age', 'UCM_HSTS_MAX_AGE', '31536000'),
])
def test_a_setting_the_environment_fixes_is_never_unreadable(app, monkeypatch, unreadable_key,
                                                            key, env, value):
    monkeypatch.setenv(env, value)
    unreadable_key(key)
    with app.app_context():
        assert build_hsts_header() == 'max-age=31536000; includeSubDomains'

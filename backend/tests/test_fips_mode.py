"""FIPS mode is in force only when asked for and backed by an active provider,
and its refusals reach API clients as a 400 with a stable problem type."""
import _hashlib

import pytest
from cryptography.hazmat.bindings._rust import openssl as rust_openssl

import fips_mode
from fips_mode import FipsRestricted


@pytest.mark.parametrize('value, expected', [
    (None, False), ('', False), ('0', False), ('no', False),
    ('1', True), ('true', True), (' YES ', True), ('on', True),
])
def test_requested_reads_ucm_fips(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv('UCM_FIPS', raising=False)
    else:
        monkeypatch.setenv('UCM_FIPS', value)
    assert fips_mode.requested() is expected


@pytest.mark.parametrize('pyca, hashlib_mode, expected', [
    (True, 1, True), (True, 0, False), (False, 1, False), (False, 0, False),
])
def test_provider_active_needs_both_libraries(monkeypatch, pyca, hashlib_mode, expected):
    monkeypatch.setattr(rust_openssl, 'is_fips_enabled', lambda: pyca)
    monkeypatch.setattr(_hashlib, 'get_fips_mode', lambda: hashlib_mode, raising=False)
    assert fips_mode.provider_active() is expected


@pytest.mark.parametrize('asked, active, expected', [
    (True, True, True), (True, False, False), (False, True, False), (False, False, False),
])
def test_enabled_needs_the_request_and_the_provider(monkeypatch, asked, active, expected):
    monkeypatch.setattr(fips_mode, 'requested', lambda: asked)
    monkeypatch.setattr(fips_mode, 'provider_active', lambda: active)
    assert fips_mode.enabled() is expected


def test_refuse_raises_only_in_fips_mode(monkeypatch):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: False)
    fips_mode.refuse('Ed25519 keys')
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    with pytest.raises(FipsRestricted, match='Ed25519 keys not available in FIPS mode'):
        fips_mode.refuse('Ed25519 keys')


def test_a_refusal_is_a_400_with_its_problem_type(app):
    with app.test_request_context('/api/v2/certificates/1/export'):
        response = app.make_response(app.handle_user_exception(
            FipsRestricted('JKS export not available in FIPS mode')))
    body = response.get_json()
    assert response.status_code == 400
    assert body['type'] == fips_mode.PROBLEM_TYPE
    assert body['message'] == 'JKS export not available in FIPS mode'


def test_other_value_errors_keep_the_generic_message(app):
    with app.test_request_context('/api/v2/certificates/1/export'):
        response = app.make_response(app.handle_user_exception(ValueError('internal detail')))
    body = response.get_json()
    assert response.status_code == 400
    assert body['type'] == 'about:blank' and body['message'] == 'Invalid parameter value'

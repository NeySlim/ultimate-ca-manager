"""A non-string key_type and a non-string ca_bundle are refused (400) without leaving files behind."""
import glob
import os
import tempfile

import pytest

from services.acme.acme_client_service import cert_key_type_refusal


@pytest.mark.parametrize('value', [['EC-P256'], {'a': 1}, 5, True])
def test_a_non_string_key_type_is_refused_not_a_crash(value):
    assert cert_key_type_refusal(value)


def test_a_non_string_key_type_is_a_400_on_preflight(auth_client):
    r = auth_client.post('/api/v2/acme/client/preflight', json={
        'domains': ['preflight.example.com'], 'email': 'admin@example.com',
        'challenge_type': 'http-01', 'mode': 'validate_only', 'key_type': ['EC-P256']})
    assert r.status_code == 400, r.data[:300]


def _leftovers():
    return set(glob.glob(os.path.join(tempfile.gettempdir(), 'ucm_sso_ca_*')))


@pytest.mark.parametrize('bundle', [['pem'], {'a': 1}, 12])
def test_a_non_string_ca_bundle_is_a_400_and_leaves_no_file(auth_client, bundle):
    before = _leftovers()
    r = auth_client.post('/api/v2/sso/saml/metadata/fetch', json={
        'metadata_url': 'https://idp.example.com/metadata', 'ca_bundle': bundle})
    assert r.status_code == 400
    assert 'ca_bundle' in r.get_json()['message']
    assert _leftovers() == before


def test_a_failed_write_removes_the_temporary_bundle(monkeypatch):
    from api.v2.sso import sessions
    before = _leftovers()

    def boom(fd, data):
        raise OSError('disk full')

    monkeypatch.setattr(sessions.os, 'write', boom)
    with pytest.raises(OSError):
        sessions._typed_ssl_verify(True, 'PEM')
    assert _leftovers() == before

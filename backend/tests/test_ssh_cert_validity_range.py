"""A validity range typed for an SSH certificate is applied or refused, never ignored."""
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_ssh import _generate_test_ssh_key, post_json
from tests.ssh_cleanup import ssh_rows_stay_in_their_module  # noqa: F401


def _iso(delta):
    return (datetime.now(timezone.utc) + delta).strftime('%Y-%m-%dT%H:%M:%SZ')


def _parse(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def _ca(auth_client, **extra):
    r = post_json(auth_client, '/api/v2/ssh/cas', {
        'descr': 'Range CA', 'ca_type': 'user', 'key_type': 'ed25519',
        'allow_any_principal': True, **extra})
    assert r.status_code == 201, r.data
    return r.get_json()['data']


def _sign(auth_client, ca_id, **extra):
    return post_json(auth_client, '/api/v2/ssh/certificates', {
        'ca_id': ca_id, 'public_key': _generate_test_ssh_key(),
        'cert_type': 'user', 'principals': ['alice'], **extra})


def _generate(auth_client, ca_id, **extra):
    return post_json(auth_client, '/api/v2/ssh/certificates/generate', {
        'ca_id': ca_id, 'key_type': 'ecdsa-p256',
        'cert_type': 'user', 'principals': ['alice'], **extra})


def _certificate(response):
    return response.get_json()['data']


@pytest.mark.parametrize('issue', [_sign, _generate])
def test_the_typed_range_is_the_validity(auth_client, issue):
    ca = _ca(auth_client)
    start, end = _iso(timedelta(hours=1)), _iso(timedelta(hours=3))
    r = issue(auth_client, ca['id'], valid_from=start, valid_to=end)
    assert r.status_code == 201, r.data
    cert = _certificate(r)
    assert _parse(cert['valid_from']) == _parse(start)
    assert _parse(cert['valid_to']) == _parse(end)


def test_an_end_alone_starts_now(auth_client):
    ca = _ca(auth_client)
    end = _iso(timedelta(hours=2))
    r = _sign(auth_client, ca['id'], valid_to=end)
    assert r.status_code == 201, r.data
    cert = _certificate(r)
    assert _parse(cert['valid_to']) == _parse(end)
    assert abs((_parse(cert['valid_from']) - datetime.now(timezone.utc)).total_seconds()) < 600


@pytest.mark.parametrize('issue', [_sign, _generate])
@pytest.mark.parametrize('fields, field', [
    ({'valid_from': 'tomorrow', 'valid_to': '2099-01-01T00:00:00Z'}, 'valid_from'),
    ({'valid_to': 'soon'}, 'valid_to'),
    ({'valid_from': '2099-01-01T00:00:00Z'}, 'valid_to'),
    ({'valid_from': '2098-01-01T00:00:00Z', 'valid_to': '2097-01-01T00:00:00Z'}, 'valid_to'),
    ({'valid_to': '2001-01-01T00:00:00Z'}, 'valid_to'),
    ({'valid_from': '2001-01-01T00:00:00Z', 'valid_to': '2099-01-01T00:00:00Z'}, 'valid_from'),
    ({'valid_to': 12345}, 'valid_to'),
])
def test_a_bad_range_is_a_400_naming_the_field(auth_client, issue, fields, field):
    ca = _ca(auth_client)
    r = issue(auth_client, ca['id'], **fields)
    assert r.status_code == 400, r.data
    assert field in r.get_json()['message']


def test_a_range_and_a_duration_together_are_refused(auth_client):
    ca = _ca(auth_client)
    r = _sign(auth_client, ca['id'], validity_seconds=3600, valid_to=_iso(timedelta(hours=2)))
    assert r.status_code == 400
    assert 'validity_seconds' in r.get_json()['message']


def test_a_range_beyond_the_ca_maximum_is_refused_not_truncated(auth_client):
    ca = _ca(auth_client, max_ttl=3600)
    r = _sign(auth_client, ca['id'], valid_from=_iso(timedelta(hours=1)),
              valid_to=_iso(timedelta(hours=4)))
    assert r.status_code == 400
    assert 'max_ttl' in r.get_json()['message']
    ok = _sign(auth_client, ca['id'], valid_from=_iso(timedelta(hours=1)),
               valid_to=_iso(timedelta(minutes=110)))
    assert ok.status_code == 201, ok.data


def test_a_duration_beyond_the_maximum_is_still_capped(auth_client):
    ca = _ca(auth_client, max_ttl=3600)
    r = _sign(auth_client, ca['id'], validity_seconds=86400)
    assert r.status_code == 201, r.data
    cert = _certificate(r)
    span = (_parse(cert['valid_to']) - _parse(cert['valid_from'])).total_seconds()
    assert span <= 3600 + 300 + 1

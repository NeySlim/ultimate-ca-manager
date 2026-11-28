"""GET system/updates/check serves the last answer with its age; force=true always asks GitHub."""
import time

import pytest
import requests

import services.updates as updates


class _Answer:
    def __init__(self, rows):
        self.rows = rows

    def raise_for_status(self):
        return None

    def json(self):
        return self.rows


@pytest.fixture
def github(monkeypatch):
    """Counts the requests sent to GitHub; `state['fail']` makes them fail."""
    state = {'calls': 0, 'fail': False}
    major = updates.major_of(updates.get_current_version())
    rows = [{'tag_name': f'v{major}.999', 'draft': False, 'prerelease': False, 'assets': []}]

    def fake_get(url, **kwargs):
        state['calls'] += 1
        if state['fail']:
            raise requests.exceptions.ConnectionError('offline')
        return _Answer(rows)

    monkeypatch.setattr(updates.requests, 'get', fake_get)
    for key, value in (('data', None), ('ts', 0), ('error', None), ('error_ts', 0)):
        monkeypatch.setitem(updates._releases_cache, key, value)
    return state


def _check(client, query=''):
    r = client.get('/api/v2/system/updates/check' + query)
    assert r.status_code == 200, r.data
    return r.get_json()['data']


def test_second_check_is_served_without_network(auth_client, github):
    first = _check(auth_client)
    second = _check(auth_client)
    assert github['calls'] == 1
    assert first['latest_version'] == second['latest_version']
    assert first['checked_at'] and second['checked_at'] == first['checked_at']


def test_an_hour_old_answer_is_still_served_to_the_screen_but_not_to_install(auth_client, github):
    _check(auth_client)
    updates._releases_cache['ts'] = time.time() - 3600
    _check(auth_client)
    assert github['calls'] == 1
    updates.check_for_updates()
    assert github['calls'] == 2


def test_an_answer_older_than_the_refresh_age_asks_again(auth_client, github):
    _check(auth_client)
    updates._releases_cache['ts'] = time.time() - updates.UI_CHECK_MAX_AGE - 5
    _check(auth_client)
    assert github['calls'] == 2


def test_a_failure_is_remembered_with_its_age(auth_client, github):
    github['fail'] = True
    first = _check(auth_client)
    second = _check(auth_client)
    assert github['calls'] == 1
    assert first['error'] and second['error'] == first['error']
    assert second['checked_at'] == first['checked_at']


def test_a_remembered_failure_expires_and_does_not_block_install(auth_client, github):
    github['fail'] = True
    _check(auth_client)
    github['fail'] = False
    assert updates.check_for_updates().get('error') is None  # install and the automatic check ask again
    assert github['calls'] == 2
    github['fail'] = True
    updates._releases_cache['data'] = None
    updates._releases_cache['error_ts'] = time.time() - updates.FAILURE_MEMO_TTL - 5
    updates._releases_cache['error'] = 'old'
    assert _check(auth_client)['error'] != 'old'
    assert github['calls'] == 3


def test_force_always_asks_github(auth_client, github):
    _check(auth_client)
    _check(auth_client, '?force=true')
    _check(auth_client, '?force=true')
    assert github['calls'] == 3
    github['fail'] = True
    _check(auth_client)  # a fresh answer is served: nothing is asked
    assert github['calls'] == 3
    assert 'error' in _check(auth_client, '?force=true')
    assert github['calls'] == 4


def _install(client, **body):
    return client.post('/api/v2/system/updates/install', json=body)


def test_install_refuses_a_version_other_than_the_one_confirmed(auth_client, github, monkeypatch):
    monkeypatch.setattr('services.updates.download_update', lambda *a, **k: pytest.fail('downloaded'))
    major = updates.major_of(updates.get_current_version())
    r = _install(auth_client, version=f'{major}.998')
    assert r.status_code == 409, r.data
    assert f'{major}.999' in r.get_json()['message']
    # The confirmed version goes on to the next step (no package for this platform here)
    r = _install(auth_client, version=f'{major}.999')
    assert r.status_code == 400 and 'download URL' in r.get_json()['message'], r.data
    # A client that names no version keeps the former behaviour
    r = _install(auth_client)
    assert r.status_code == 400 and 'download URL' in r.get_json()['message'], r.data

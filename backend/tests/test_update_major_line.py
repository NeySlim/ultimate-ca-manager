"""An installed version updates within its own major version; a later major
version is offered as an explicit, recommended upgrade and never installed
unattended; the update check carries the security-maintenance notice.

Releases are simulated through the releases cache: no network request.
"""
import time
from datetime import datetime

import pytest

import services.updates as updates
import services.webhook_service as wh


def _release(tag, prerelease=None, notes=''):
    v = tag.lstrip('v')
    fv = v.replace('-', '.')
    deb = f'ucm_{fv}_all.deb'
    return {
        'tag_name': f'v{v}', 'draft': False,
        'prerelease': ('-' in v) if prerelease is None else prerelease,
        'body': notes, 'published_at': '2027-01-01T00:00:00Z',
        'html_url': f'https://example.invalid/releases/v{v}',
        'assets': [
            {'name': deb, 'browser_download_url': f'http://x/{deb}'},
            {'name': f'{deb}.sha256', 'browser_download_url': f'http://x/{deb}.sha256'},
        ],
    }


MIXED = ['3.0', '2.254.2', '2.254.3-rc1', '3.1-rc1']


def _clear(app):
    from models import db, SystemConfig
    with app.app_context():
        for key in (
            updates.UPDATE_CHANNEL_KEY, updates.AUTO_UPDATE_ENABLED_KEY,
            updates.AUTO_UPDATE_HOUR_KEY, updates._LAST_CHECK_TS_KEY,
            updates._NOTIFIED_VERSION_KEY, updates._ATTEMPTED_VERSION_KEY,
            updates._NOTIFIED_MAJOR_KEY,
        ):
            SystemConfig.query.filter_by(key=key).delete()
        db.session.commit()


@pytest.fixture
def clean(app):
    _clear(app)
    yield
    _clear(app)


@pytest.fixture
def instance(monkeypatch):
    def setup(current, tags, docker=False):
        monkeypatch.setattr(updates, 'get_current_version', lambda: current)
        monkeypatch.setitem(updates._releases_cache, 'data', [_release(t) for t in tags])
        monkeypatch.setitem(updates._releases_cache, 'ts', time.time())
        monkeypatch.setattr(updates.os.path, 'exists', lambda p: p == '/usr/bin/dpkg')
        if docker:
            monkeypatch.setenv('UCM_DOCKER', '1')
        else:
            monkeypatch.delenv('UCM_DOCKER', raising=False)
    return setup


# ---- version parsing -------------------------------------------------------------------------

@pytest.mark.parametrize('low,high', [
    ('2.254.2', '3.0'), ('2.254.3-rc1', '3.0'), ('3.0-rc1', '3.0'), ('2.254', '2.254.1'),
    ('2.254.1', '2.254.2'), ('2.254.2-rc1', '2.254.2'), ('2.254.2-dev', '2.254.2-rc1'),
    ('3.0', '3.1-rc1'), ('3.0', '3.0.1'),
])
def test_versions_of_two_and_three_segments_compare(low, high):
    assert updates.compare_versions(low, high) == -1
    assert updates.compare_versions(high, low) == 1


def test_major_of_a_version():
    assert updates.major_of('2.254.2') == 2
    assert updates.major_of('v3.0-rc1') == 3


# ---- the update stays within the installed major -------------------------------------------

def test_stable_channel_updates_within_the_installed_major(instance):
    instance('2.254.1', MIXED)
    result = updates.check_for_updates(channel='stable')
    assert (result['update_available'], result['latest_version']) == (True, '2.254.2')
    assert result['package_name'] == 'ucm_2.254.2_all.deb'
    assert result['checksum_url'] == 'http://x/ucm_2.254.2_all.deb.sha256'
    assert result['major_upgrade']['version'] == '3.0'


def test_rc_channel_updates_within_the_installed_major(instance):
    instance('2.254.1', MIXED)
    result = updates.check_for_updates(channel='rc')
    assert (result['update_available'], result['latest_version']) == (True, '2.254.3-rc1')
    # never the RC of the later major, whatever the channel
    assert result['major_upgrade']['version'] == '3.0'


def test_manual_check_with_prereleases_stays_within_the_major(instance):
    instance('2.254.1', MIXED)
    result = updates.check_for_updates(include_prereleases=True, include_dev=True)
    assert result['latest_version'] == '2.254.3-rc1'
    assert result['major_upgrade']['version'] == '3.0'


def test_major_upgrade_carries_the_platform_package(instance):
    instance('2.254.1', MIXED)
    upgrade = updates.check_for_updates(channel='stable')['major_upgrade']
    assert upgrade == {
        'version': '3.0',
        'published_at': '2027-01-01T00:00:00Z',
        'release_notes': '',
        'html_url': 'https://example.invalid/releases/v3.0',
        'download_url': 'http://x/ucm_3.0_all.deb',
        'package_name': 'ucm_3.0_all.deb',
        'checksum_url': 'http://x/ucm_3.0_all.deb.sha256',
    }


def test_major_upgrade_under_docker_names_the_image(instance):
    instance('2.254.1', MIXED, docker=True)
    upgrade = updates.check_for_updates(channel='stable')['major_upgrade']
    assert upgrade['download_url'] == 'ghcr.io/neyslim/ultimate-ca-manager:3.0'


def test_no_higher_fix_but_a_later_major(instance):
    instance('2.254.1', ['2.254.1', '2.254', '3.0'])
    result = updates.check_for_updates(channel='stable')
    assert result['update_available'] is False
    assert result['latest_version'] == '2.254.1'
    assert result['major_upgrade']['version'] == '3.0'


def test_the_highest_stable_later_major_is_offered(instance):
    instance('2.254.1', ['3.0', '3.2', '4.0-rc1', '3.1'])
    assert updates.check_for_updates(channel='rc')['major_upgrade']['version'] == '3.2'


def test_a_later_major_rc_alone_is_never_offered(instance):
    instance('2.254.1', ['2.254.2', '3.0-rc1', '3.0-rc2'])
    for channel in ('stable', 'rc'):
        assert updates.check_for_updates(channel=channel)['major_upgrade'] is None


def test_a_later_major_rc_not_flagged_prerelease_is_never_offered(monkeypatch, instance):
    instance('2.254.1', ['2.254.2'])
    monkeypatch.setitem(updates._releases_cache, 'data',
                        updates._releases_cache['data'] + [_release('3.0-rc1', prerelease=False)])
    assert updates.check_for_updates(channel='rc')['major_upgrade'] is None


def test_a_later_major_flagged_prerelease_is_never_offered(monkeypatch, instance):
    instance('2.254.1', ['2.254.2'])
    monkeypatch.setitem(updates._releases_cache, 'data',
                        updates._releases_cache['data'] + [_release('3.0', prerelease=True)])
    assert updates.check_for_updates(channel='rc')['major_upgrade'] is None


def test_without_a_later_major_the_notice_stays(instance):
    instance('2.254.1', ['2.254.2', '2.254.1'])
    result = updates.check_for_updates(channel='stable')
    assert result['major_upgrade'] is None
    assert result['security_maintenance'] is True


def test_notice_and_empty_major_on_a_failed_check(monkeypatch):
    monkeypatch.setitem(updates._releases_cache, 'data', None)

    def _down(*a, **k):
        raise updates.requests.ConnectionError('no egress')
    monkeypatch.setattr(updates.requests, 'get', _down)
    result = updates.check_for_updates(force=True)
    assert result['error']
    assert result['major_upgrade'] is None
    assert result['security_maintenance'] is True


def test_releases_are_requested_100_per_page(monkeypatch):
    seen = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return [_release('2.254.2')]

    def _get(url, **kwargs):
        seen['url'], seen['params'] = url, kwargs.get('params')
        return _Resp()
    monkeypatch.setattr(updates.requests, 'get', _get)
    monkeypatch.setattr(updates, 'get_current_version', lambda: '2.254.1')
    updates.check_for_updates(force=True)
    updates.invalidate_update_cache()
    assert seen['params'] == {'per_page': 100}


def test_check_route_returns_the_major_upgrade_and_notice(auth_client, instance):
    instance('2.254.1', MIXED)
    data = auth_client.get('/api/v2/system/updates/check').get_json()['data']
    assert data['latest_version'] == '2.254.2'
    assert data['major_upgrade']['version'] == '3.0'
    assert data['security_maintenance'] is True


# ---- unattended install ---------------------------------------------------------------------

def _enable_auto(app):
    with app.app_context():
        updates._cfg_set(updates.AUTO_UPDATE_ENABLED_KEY, 'true')
        updates._cfg_set(updates.AUTO_UPDATE_HOUR_KEY, str(datetime.now().hour))


def _capture_install(monkeypatch):
    calls = []
    monkeypatch.setattr(updates, 'fetch_expected_sha256', lambda url, name: 'e' * 64)
    monkeypatch.setattr(updates, 'download_update',
                        lambda url, name, expected_sha256=None: calls.append(('download', name))
                        or f'/x/{name}')
    monkeypatch.setattr(updates, 'install_update',
                        lambda p, to_version=None, **k: calls.append(('install', to_version)))
    monkeypatch.setattr(wh, 'emit_update_available', lambda update: None)
    monkeypatch.setattr(wh, 'emit_update_initiated', lambda *a, **k: None)
    return calls


def test_scheduled_install_takes_the_fix_never_the_later_major(app, clean, instance, monkeypatch):
    instance('2.254.1', MIXED)
    calls = _capture_install(monkeypatch)
    _enable_auto(app)
    with app.app_context():
        updates.scheduled_update_check()
    assert calls == [('download', 'ucm_2.254.2_all.deb'), ('install', '2.254.2')]


def test_scheduled_install_with_only_a_later_major_installs_nothing(app, clean, instance, monkeypatch):
    instance('2.254.1', ['2.254.1', '3.0'])
    calls = _capture_install(monkeypatch)
    _enable_auto(app)
    with app.app_context():
        updates.scheduled_update_check()
    assert calls == []


def test_auto_install_refuses_another_major_even_when_handed_one(app, clean, monkeypatch):
    monkeypatch.setattr(updates, 'get_current_version', lambda: '2.254.1')
    monkeypatch.delenv('UCM_DOCKER', raising=False)
    calls = _capture_install(monkeypatch)
    audits = []
    from services.audit_service import AuditService
    monkeypatch.setattr(AuditService, 'log_action', lambda **k: audits.append(k))
    with app.app_context():
        updates._auto_install({
            'update_available': True, 'current_version': '2.254.1', 'latest_version': '3.0',
            'download_url': 'http://x/ucm_3.0_all.deb', 'package_name': 'ucm_3.0_all.deb',
            'checksum_url': 'http://x/ucm_3.0_all.deb.sha256',
        })
    assert calls == []
    assert len(audits) == 1 and audits[0]['success'] is False
    assert '3.0' in audits[0]['details']


# ---- install route --------------------------------------------------------------------------

def _route_install(monkeypatch):
    import api.v2.system.updates as route
    calls = []
    monkeypatch.setattr(updates, 'fetch_expected_sha256', lambda url, name: 'e' * 64)
    monkeypatch.setattr(updates, 'download_update',
                        lambda url, name, expected_sha256=None: calls.append(('download', name))
                        or f'/x/{name}')
    monkeypatch.setattr(updates, 'install_update',
                        lambda p, to_version=None, **k: calls.append(('install', to_version)))
    monkeypatch.setattr(wh, 'emit_update_initiated', lambda *a, **k: None)
    return route, calls


URL = '/api/v2/system/updates/install'


def test_install_route_installs_the_fix(auth_client, instance, monkeypatch):
    instance('2.254.1', MIXED)
    _, calls = _route_install(monkeypatch)
    r = auth_client.post(URL, json={})
    assert r.status_code == 200, r.data[:300]
    assert calls == [('download', 'ucm_2.254.2_all.deb'), ('install', '2.254.2')]


def test_install_route_refuses_another_major_without_the_explicit_parameter(
        auth_client, monkeypatch):
    monkeypatch.delenv('UCM_DOCKER', raising=False)
    monkeypatch.setattr(updates, 'get_current_version', lambda: '2.254.1')
    _, calls = _route_install(monkeypatch)
    monkeypatch.setattr(updates, 'check_for_updates', lambda **k: {
        'update_available': True, 'current_version': '2.254.1', 'latest_version': '3.0',
        'download_url': 'http://x/ucm_3.0_all.deb', 'package_name': 'ucm_3.0_all.deb',
        'checksum_url': 'http://x/ucm_3.0_all.deb.sha256', 'major_upgrade': None,
    })
    r = auth_client.post(URL, json={})
    assert r.status_code == 400
    assert calls == []


def test_install_route_upgrades_to_the_later_major_on_request(auth_client, instance, monkeypatch):
    instance('2.254.1', ['2.254.1', '3.0'])
    _, calls = _route_install(monkeypatch)
    r = auth_client.post(URL, json={'major_upgrade': True, 'version': '3.0'})
    assert r.status_code == 200, r.data[:300]
    assert calls == [('download', 'ucm_3.0_all.deb'), ('install', '3.0')]


def test_install_route_major_upgrade_needs_the_confirmed_version(auth_client, instance, monkeypatch):
    instance('2.254.1', ['2.254.1', '3.1'])
    _, calls = _route_install(monkeypatch)
    assert auth_client.post(URL, json={'major_upgrade': True}).status_code == 400
    assert auth_client.post(URL, json={'major_upgrade': True, 'version': '3.0'}).status_code == 409
    assert calls == []


def test_install_route_major_upgrade_without_one_available(auth_client, instance, monkeypatch):
    instance('2.254.1', ['2.254.1', '2.254.2'])
    _, calls = _route_install(monkeypatch)
    r = auth_client.post(URL, json={'major_upgrade': True, 'version': '2.254.2'})
    assert r.status_code == 400
    assert calls == []


def test_install_route_ignores_a_major_upgrade_that_is_not_true(auth_client, instance, monkeypatch):
    instance('2.254.1', ['2.254.1', '3.0'])
    _, calls = _route_install(monkeypatch)
    r = auth_client.post(URL, json={'major_upgrade': 'yes', 'version': '3.0'})
    assert r.status_code == 400
    assert calls == []


# ---- end-of-life notification ---------------------------------------------------------------

def _capture_notices(monkeypatch):
    events = []
    monkeypatch.setattr(wh, 'emit_update_available', lambda update: events.append(update))
    return events


def _tick(app):
    with app.app_context():
        updates._cfg_set(updates._LAST_CHECK_TS_KEY, '0')
        updates.scheduled_update_check()


def test_a_later_major_is_notified_once_per_major(app, clean, instance, monkeypatch):
    events = _capture_notices(monkeypatch)
    instance('2.254.1', ['2.254.1', '3.0'])
    _tick(app)
    _tick(app)
    majors = [e for e in events if e.get('major_upgrade')]
    assert len(majors) == 1
    assert majors[0]['latest_version'] == '3.0'
    assert majors[0]['current_version'] == '2.254.1'
    # a later build of the same major does not notify again
    instance('2.254.1', ['2.254.1', '3.0', '3.1'])
    _tick(app)
    assert len([e for e in events if e.get('major_upgrade')]) == 1
    # a new major notifies once
    instance('2.254.1', ['2.254.1', '3.1', '4.0'])
    _tick(app)
    _tick(app)
    majors = [e for e in events if e.get('major_upgrade')]
    assert [e['latest_version'] for e in majors] == ['3.0', '4.0']


def test_the_fix_and_the_later_major_are_two_notifications(app, clean, instance, monkeypatch):
    events = _capture_notices(monkeypatch)
    instance('2.254.1', MIXED)
    _tick(app)
    assert sorted((bool(e.get('major_upgrade')), e['latest_version']) for e in events) == [
        (False, '2.254.2'), (True, '3.0')]


def test_no_later_major_no_notice_event(app, clean, instance, monkeypatch):
    events = _capture_notices(monkeypatch)
    instance('2.254.1', ['2.254.1', '3.0-rc1'])
    _tick(app)
    assert events == []


# ---- review follow-ups -----------------------------------------------------------------------

def test_an_unreadable_installed_version_offers_no_major_upgrade(instance):
    """Without a readable version nothing says which major is installed."""
    instance('unknown', ['2.254.2', '2.254.1'])
    assert updates.check_for_updates(channel='stable')['major_upgrade'] is None


def test_an_earlier_major_is_never_offered(instance):
    instance('2.254.1', ['1.7.0', '2.254.1'])
    result = updates.check_for_updates(channel='stable')
    assert result['major_upgrade'] is None and result['update_available'] is False


@pytest.mark.parametrize('body', [[1], 'text', 7])
def test_install_route_refuses_a_json_body_that_is_not_an_object(auth_client, instance, monkeypatch, body):
    instance('2.254.1', ['2.254.2', '3.0'])
    _, calls = _route_install(monkeypatch)
    r = auth_client.post(URL, json=body)
    assert r.status_code == 400, r.data
    assert calls == []


@pytest.mark.parametrize('fips,suffix', [('1', '-fips'), ('', '')])
def test_docker_image_names_the_variant_in_use(instance, monkeypatch, fips, suffix):
    """A FIPS deployment is pointed at the -fips image, the standard one at the standard image."""
    instance('2.254.1', MIXED, docker=True)
    monkeypatch.setenv('UCM_FIPS', fips)
    result = updates.check_for_updates(channel='stable')
    assert result['download_url'] == f'ghcr.io/neyslim/ultimate-ca-manager:2.254.2{suffix}'
    assert result['major_upgrade']['download_url'] == f'ghcr.io/neyslim/ultimate-ca-manager:3.0{suffix}'


def test_an_ordinary_update_event_says_it_is_not_a_major_upgrade(app, clean, instance, monkeypatch):
    instance('2.254.1', ['2.254.2'])
    events = _capture_notices(monkeypatch)
    _tick(app)
    with app.app_context():
        updates.scheduled_update_check()
    assert [e['major_upgrade'] for e in events] == [False]

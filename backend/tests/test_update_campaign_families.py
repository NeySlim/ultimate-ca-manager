"""HA rolling update in a mixed cluster: each node installs the package of its own family,
whose SHA-256 the campaign froze at the start. No test installs anything: the download
and the local install are witnesses."""
import json
import os
from datetime import timedelta

import pytest

import services.update_campaign as uc
import services.updates as updates
from config.settings import Config

PREFIX = 'ucf-test-'
DEB, EL9, FC = 'ucm_3.1_all.deb', 'ucm-el9-3.1-1.el9.noarch.rpm', 'ucm-3.1-1.fc43.noarch.rpm'
EL10 = 'ucm-el10-3.1-1.el10.noarch.rpm'
SHAS = {DEB: 'a1' * 32, EL9: 'b2' * 32, FC: 'c3' * 32, EL10: 'd4' * 32}


def _asset(name):
    return {'name': name, 'browser_download_url': f'https://x/{name}'}


ASSETS = ([_asset(n) for n in (DEB, EL9, EL10, FC)] + [_asset(f'{n}.sha256') for n in (DEB, EL9, EL10, FC)]
          + [_asset('full-stop-migrations.json')])


def _clean(app):
    from models import ClusterCommand, ClusterNode, SystemConfig, db
    with app.app_context():
        SystemConfig.query.filter_by(key=uc.CAMPAIGN_KEY).delete()
        ClusterNode.query.filter(ClusterNode.node_id.like(PREFIX + '%')).delete(synchronize_session=False)
        ClusterCommand.query.filter(ClusterCommand.kind == 'update').delete()
        db.session.commit()


@pytest.fixture
def ha(app, monkeypatch, tmp_path):
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr(updates, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(updates, 'fetch_expected_sha256', lambda url, name: SHAS.get(name))
    monkeypatch.setattr(updates, 'fetch_full_stop_marks', lambda url: {})
    _clean(app)
    yield
    _clean(app)


def _rows(app, **families):
    from models import ClusterNode, db
    from utils.datetime_utils import utc_now
    now = utc_now()
    with app.app_context():
        for name, family in families.items():
            db.session.add(ClusterNode(node_id=PREFIX + name, started_at=now - timedelta(minutes=10),
                                       heartbeat_at=now, is_leader=False, pid=1, version='3.0',
                                       package_family=family))
        db.session.commit()


def _back(app, name, version='3.1'):
    from models import ClusterNode, db
    from utils.datetime_utils import utc_now
    with app.app_context():
        node = db.session.get(ClusterNode, PREFIX + name)
        node.started_at = node.heartbeat_at = utc_now() + timedelta(seconds=1)
        node.version = version
        db.session.commit()


def _commands(app):
    from models import ClusterCommand
    with app.app_context():
        return [(c.node_id, json.loads(c.payload)) for c in
                ClusterCommand.query.filter_by(kind='update').order_by(ClusterCommand.id).all()]


def _state(app):
    with app.app_context():
        return uc.read_campaign()[1]


def _start(app, assets=ASSETS):
    with app.app_context():
        return uc.start_campaign('3.1', assets, 'admin')


def _witnesses(monkeypatch, calls, install_error=None):
    def download(url, name, expected_sha256=None):
        calls.append(('download', url, expected_sha256))
        path = os.path.join(str(updates.DATA_DIR), 'updates', name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(b'pkg')
        return path

    def install(path, **kw):
        calls.append(('install', os.path.basename(path).split('-', 1)[1]))
        if install_error:
            raise Exception(install_error)
    monkeypatch.setattr(updates, 'download_update', download)
    monkeypatch.setattr(updates, 'install_update', install)


def _turn(app, monkeypatch, name, family):
    monkeypatch.setattr(updates, 'package_family', lambda: family)
    with app.app_context():
        uc.run_local_turn(_commands(app)[-1][1], node_id=PREFIX + name, version='3.0')


# ------------------------------------------------------------------ family of this host


@pytest.mark.parametrize('docker, files, el, expected', [
    ('1', {'/usr/bin/dpkg'}, None, 'container'),
    (None, {'/usr/bin/dpkg', '/usr/bin/rpm'}, None, 'deb'),
    (None, {'/usr/bin/rpm'}, '9', 'rpm-el9'),
    (None, {'/usr/bin/rpm'}, '10', 'rpm-el10'),
    (None, {'/usr/bin/rpm'}, None, 'rpm-fedora'),
    (None, set(), None, 'unknown'),
])
def test_the_package_family_follows_the_update_detection(monkeypatch, docker, files, el, expected):
    if docker:
        monkeypatch.setenv('UCM_DOCKER', docker)
    else:
        monkeypatch.delenv('UCM_DOCKER', raising=False)
    monkeypatch.setattr(updates.os.path, 'exists', lambda p: p in files)
    monkeypatch.setattr(updates, '_el_release', lambda: el)
    assert updates.package_family() == expected


@pytest.mark.parametrize('family, name', [('deb', DEB), ('rpm-el9', EL9), ('rpm-fedora', FC),
                                          ('rpm-el10', EL10), ('rpm-el8', FC)])
def test_each_family_takes_its_package_and_checksum(family, name):
    assert updates.family_package(ASSETS, family) == {
        'download_url': f'https://x/{name}', 'package_name': name,
        'checksum_url': f'https://x/{name}.sha256'}


@pytest.mark.parametrize('family', ['container', 'unknown', None])
def test_a_family_without_package_has_none(family):
    assert updates.family_package(ASSETS, family) is None


def test_the_heartbeat_publishes_the_family_in_the_node_list(app, monkeypatch):
    from models import ClusterNode, db
    from services import scheduler_leader
    from utils.datetime_utils import utc_now
    monkeypatch.setattr(updates, 'package_family', lambda: 'rpm-el9')
    with app.app_context():
        try:
            scheduler_leader.write_heartbeat(PREFIX + 'hb', False, utc_now())
            assert db.session.get(ClusterNode, PREFIX + 'hb').package_family == 'rpm-el9'
            detail = {n['node_id']: n for n in scheduler_leader.cluster_nodes_detail(60)}
            assert detail[PREFIX + 'hb']['package_family'] == 'rpm-el9'
        finally:
            ClusterNode.query.filter_by(node_id=PREFIX + 'hb').delete()
            db.session.commit()


# ------------------------------------------------------------------ catalog at the start


def test_a_mixed_cluster_freezes_one_package_per_present_family(app, ha):
    _rows(app, a='deb', b='rpm-el9')
    ok, message, campaign = _start(app)
    assert ok, message
    assert campaign['packages'] == {
        'deb': {'download_url': f'https://x/{DEB}', 'package_name': DEB, 'sha256': SHAS[DEB]},
        'rpm-el9': {'download_url': f'https://x/{EL9}', 'package_name': EL9, 'sha256': SHAS[EL9]}}
    assert campaign['families'] == {PREFIX + 'a': 'deb', PREFIX + 'b': 'rpm-el9'}
    assert uc.public_view(campaign)['families'] == campaign['families']


def test_a_present_family_without_checksum_refuses_the_start(app, ha):
    _rows(app, a='deb', b='rpm-el9')
    ok, message, _ = _start(app, assets=[a for a in ASSETS if a['name'] != f'{EL9}.sha256'])
    assert not ok
    assert PREFIX + 'b' in message and 'SHA-256' in message
    assert _state(app) is None


def test_a_checksum_file_that_misses_a_family_refuses_the_start(app, ha, monkeypatch):
    monkeypatch.setattr(updates, 'fetch_expected_sha256', lambda url, name: None if name == FC else SHAS[name])
    _rows(app, a='deb', c='rpm-fedora')
    ok, message, _ = _start(app)
    assert not ok and PREFIX + 'c' in message and 'SHA-256' in message
    assert _state(app) is None


@pytest.mark.parametrize('family', ['container', 'unknown', None])
def test_a_node_whose_family_has_no_package_refuses_the_start(app, ha, family):
    _rows(app, a='deb', b=family)
    ok, message, _ = _start(app)
    assert not ok
    assert PREFIX + 'b' in message
    # A container node is updated by its orchestrator, not by a missing package
    if family == 'container':
        assert updates.CONTAINER_HA_REFUSAL in message and 'no package' not in message
    else:
        assert 'no package' in message
    assert _state(app) is None


def test_a_release_without_the_package_of_a_present_family_refuses_the_start(app, ha):
    _rows(app, a='deb', b='rpm-el9')
    ok, message, _ = _start(app, assets=[a for a in ASSETS if not a['name'].startswith('ucm-')])
    assert not ok and PREFIX + 'b' in message
    assert _state(app) is None


# ------------------------------------------------------------------ each node's turn


def test_each_node_installs_the_package_of_its_own_family(app, ha, monkeypatch):
    calls = []
    _witnesses(monkeypatch, calls)
    _rows(app, a='deb', b='rpm-el9', c='rpm-fedora')
    assert _start(app)[0]
    for name, family, package in (('a', 'deb', DEB), ('b', 'rpm-el9', EL9), ('c', 'rpm-fedora', FC)):
        with app.app_context():
            assert uc.campaign_tick() == ('dispatch', PREFIX + name, None)
        _turn(app, monkeypatch, name, family)
        assert calls[-2:] == [('download', f'https://x/{package}', SHAS[package]), ('install', package)]
        _back(app, name)
        with app.app_context():
            assert uc.campaign_tick()[0] == 'node_done'
    with app.app_context():
        assert uc.campaign_tick()[0] == 'finished'


def test_a_node_whose_local_family_is_not_in_the_campaign_stops_it(app, ha, monkeypatch):
    """The turn trusts the local detection, not the column: a node reinstalled on another
    distribution after the start finds no package of its own and installs nothing."""
    calls = []
    _witnesses(monkeypatch, calls)
    _rows(app, a='deb', b='deb')
    assert _start(app)[0]
    with app.app_context():
        uc.campaign_tick()
    _turn(app, monkeypatch, 'a', 'rpm-el9')
    assert calls == []
    state = _state(app)
    assert state['status'] == uc.STOPPED and state['failed']['node'] == PREFIX + 'a'
    assert 'rpm-el9' in state['failed']['reason'] and 'no package' in state['failed']['reason']


def test_a_forged_checksum_in_the_command_installs_nothing(app, ha, monkeypatch):
    calls = []
    _witnesses(monkeypatch, calls)
    _rows(app, a='deb', b='rpm-el9')
    assert _start(app)[0]
    with app.app_context():
        uc.campaign_tick()
    payload = _commands(app)[-1][1]
    # The entry of another family carries the right digest: only this node's own entry counts
    payload['packages']['deb'] = dict(payload['packages']['rpm-el9'])
    monkeypatch.setattr(updates, 'package_family', lambda: 'deb')
    with app.app_context():
        uc.run_local_turn(payload, node_id=PREFIX + 'a', version='3.0')
    assert calls == []
    state = _state(app)
    assert state['status'] == uc.STOPPED and 'SHA-256' in state['failed']['reason']


def test_the_download_is_verified_against_the_campaign_digest(app, ha, monkeypatch):
    """A command whose URL points elsewhere still downloads under the campaign's frozen digest."""
    calls = []
    _witnesses(monkeypatch, calls)
    _rows(app, a='deb')
    assert _start(app)[0]
    with app.app_context():
        uc.campaign_tick()
    payload = _commands(app)[-1][1]
    payload['packages']['deb']['download_url'] = 'https://evil/p.deb'
    monkeypatch.setattr(updates, 'package_family', lambda: 'deb')
    with app.app_context():
        uc.run_local_turn(payload, node_id=PREFIX + 'a', version='3.0')
    assert calls[0][2] == SHAS[DEB]


@pytest.mark.parametrize('family', ['rpm-el9', 'container'])
def test_a_node_joining_after_the_start_without_its_package_stops_the_campaign(app, ha, monkeypatch, family):
    _rows(app, a='deb')
    assert _start(app)[0]
    _rows(app, z=family)
    with app.app_context():
        event = uc.campaign_tick()
    assert event[0] == 'stopped' and event[1] == PREFIX + 'z'
    reason = _state(app)['failed']['reason']
    assert 'after the start' in reason
    assert (updates.CONTAINER_HA_REFUSAL if family == 'container' else 'rpm-el9') in reason
    assert _commands(app) == []



def test_a_node_joining_already_on_the_target_counts_as_done(app, ha, monkeypatch):
    # Its family has no package (a container), but it has nothing to install
    calls = []
    _witnesses(monkeypatch, calls)
    _rows(app, a='deb')
    assert _start(app)[0]
    _rows(app, z='container')
    _back(app, 'z')
    with app.app_context():
        assert uc.campaign_tick() == ('dispatch', PREFIX + 'a', None)
    state = _state(app)
    assert state['status'] == uc.RUNNING and PREFIX + 'z' in state['done']

def test_a_node_joining_after_the_start_with_its_package_gets_its_turn(app, ha, monkeypatch):
    calls = []
    _witnesses(monkeypatch, calls)
    _rows(app, a='deb')
    assert _start(app)[0]
    _rows(app, z='deb')
    with app.app_context():
        assert uc.campaign_tick() == ('dispatch', PREFIX + 'a', None)
    _back(app, 'a')
    with app.app_context():
        assert uc.campaign_tick()[0] == 'node_done'
        assert uc.campaign_tick() == ('dispatch', PREFIX + 'z', None)
    assert _state(app)['order'] == [PREFIX + 'a', PREFIX + 'z']


def test_a_node_whose_family_changed_since_the_start_stops_at_its_dispatch(app, ha):
    from models import ClusterNode, db
    _rows(app, a='deb')
    assert _start(app)[0]
    with app.app_context():
        db.session.get(ClusterNode, PREFIX + 'a').package_family = 'rpm-fedora'
        db.session.commit()
        event = uc.campaign_tick()
    assert event[0] == 'stopped' and 'rpm-fedora' in _state(app)['failed']['reason']
    assert _commands(app) == []


# ------------------------------------------------------------------ B-05b review leftovers


def test_a_failed_install_request_drops_the_package(app, ha, monkeypatch):
    calls = []
    _witnesses(monkeypatch, calls, install_error='An update operation is already pending')
    _rows(app, a='deb')
    assert _start(app)[0]
    with app.app_context():
        uc.campaign_tick()
    _turn(app, monkeypatch, 'a', 'deb')
    assert calls[-1] == ('install', DEB)
    assert os.listdir(os.path.join(str(updates.DATA_DIR), 'updates')) == []
    assert _state(app)['status'] == uc.STOPPED


def test_a_new_turn_purges_the_packages_of_earlier_turns_only(app, ha, monkeypatch):
    calls = []
    _witnesses(monkeypatch, calls)
    folder = os.path.join(str(updates.DATA_DIR), 'updates')
    os.makedirs(folder)
    for name in ('0123456789ab-old.deb', 'abcdef012345-pending.rpm', 'manual.deb', 'notes.txt'):
        with open(os.path.join(folder, name), 'wb') as f:
            f.write(b'x')
    with open(os.path.join(str(updates.DATA_DIR), '.update_pending'), 'w') as f:
        f.write(os.path.join(folder, 'abcdef012345-pending.rpm'))
    _rows(app, a='deb')
    assert _start(app)[0]
    with app.app_context():
        uc.campaign_tick()
    _turn(app, monkeypatch, 'a', 'deb')
    left = sorted(os.listdir(folder))
    assert 'abcdef012345-pending.rpm' in left and 'manual.deb' in left and 'notes.txt' in left
    assert '0123456789ab-old.deb' not in left
    assert len([n for n in left if n.endswith('-' + DEB)]) == 1  # this turn's own package stays



def test_the_package_the_watcher_is_installing_is_not_purged(app, ha, monkeypatch):
    # The watcher deletes .update_pending before dpkg or dnf runs; its claimed manifest names the package
    import json
    calls = []
    _witnesses(monkeypatch, calls)
    folder = os.path.join(str(updates.DATA_DIR), 'updates')
    os.makedirs(folder)
    installing = os.path.join(folder, 'abcdef012345-installing.rpm')
    for path in (installing, os.path.join(folder, '0123456789ab-old.deb')):
        with open(path, 'wb') as f:
            f.write(b'x')
    with open(os.path.join(str(updates.DATA_DIR), '.update_manifest.processing'), 'w') as f:
        json.dump({'package_path': installing, 'to_version': '3.0'}, f)
    _rows(app, a='deb')
    assert _start(app)[0]
    with app.app_context():
        uc.campaign_tick()
    _turn(app, monkeypatch, 'a', 'deb')
    left = sorted(os.listdir(folder))
    assert 'abcdef012345-installing.rpm' in left and '0123456789ab-old.deb' not in left

def test_the_end_message_names_the_nodes_left_out(app, ha, monkeypatch):
    from models import ClusterNode, db
    from utils.datetime_utils import utc_now
    alerts = []
    import websocket.emitters as ws
    monkeypatch.setattr(ws, 'on_system_alert', lambda kind, message, severity, details: alerts.append(message))
    _rows(app, a='deb', s='deb')
    with app.app_context():
        db.session.get(ClusterNode, PREFIX + 's').heartbeat_at = utc_now() - timedelta(hours=1)
        db.session.commit()
    assert _start(app)[0]
    _back(app, 'a')
    with app.app_context():
        assert uc.campaign_tick()[0] == 'node_done'
        assert uc.campaign_tick()[0] == 'finished'
    assert 'every node' not in alerts[-1] and PREFIX + 's' in alerts[-1]


def test_the_end_message_of_a_full_roll_says_every_node(app, ha, monkeypatch):
    alerts = []
    import websocket.emitters as ws
    monkeypatch.setattr(ws, 'on_system_alert', lambda kind, message, severity, details: alerts.append(message))
    _rows(app, a='deb')
    assert _start(app)[0]
    _back(app, 'a')
    with app.app_context():
        uc.campaign_tick()
        assert uc.campaign_tick()[0] == 'finished'
    assert 'every node' in alerts[-1]


# ------------------------------------------------------------------ entry points


def test_the_install_route_builds_the_catalog_of_a_mixed_cluster(app, auth_client, ha, monkeypatch):
    monkeypatch.delenv('UCM_DOCKER', raising=False)
    monkeypatch.setattr(updates, 'check_for_updates', lambda **k: {
        'update_available': True, 'current_version': '3.0', 'latest_version': '3.1',
        'download_url': None, 'package_name': None, 'checksum_url': None, 'assets': ASSETS})
    _rows(app, a='deb', b='rpm-fedora')
    r = auth_client.post('/api/v2/system/updates/install', json={})
    assert r.status_code == 200, r.data
    campaign = r.get_json()['data']['campaign']
    assert sorted(campaign['packages']) == ['deb', 'rpm-fedora']
    assert campaign['packages']['rpm-fedora']['sha256'] == SHAS[FC]


def test_scheduled_auto_install_in_ha_gives_each_family_its_package(app, ha, monkeypatch):
    from models import SystemConfig, db
    monkeypatch.delenv('UCM_DOCKER', raising=False)
    _rows(app, a='deb', b='rpm-el9')
    with app.app_context():
        SystemConfig.query.filter_by(key=updates._ATTEMPTED_VERSION_KEY).delete()
        db.session.commit()
        try:
            updates._auto_install({'latest_version': '3.1', 'current_version': '3.0',
                                   'download_url': f'https://x/{DEB}', 'package_name': DEB,
                                   'checksum_url': f'https://x/{DEB}.sha256', 'assets': ASSETS})
        finally:
            SystemConfig.query.filter_by(key=updates._ATTEMPTED_VERSION_KEY).delete()
            db.session.commit()
    state = _state(app)
    assert state['initiated_by'] == 'scheduler'
    assert {f: p['sha256'] for f, p in state['packages'].items()} == {'deb': SHAS[DEB], 'rpm-el9': SHAS[EL9]}
    assert [c[0] for c in _commands(app)] == [PREFIX + 'a']



@pytest.mark.parametrize('assets', [[], [_asset(DEB), _asset(DEB + '.sha256')],
                                    [a for a in ASSETS if a['name'] != 'full-stop-migrations.json']],
                         ids=['nothing', 'one family', 'no manifest'])
def test_scheduled_auto_install_in_ha_waits_for_every_asset_it_reads(app, ha, monkeypatch, assets):
    # A release still uploading its packages or its full-stop manifest is tried again at the next
    # check, not marked as attempted
    from models import SystemConfig, db
    monkeypatch.delenv('UCM_DOCKER', raising=False)
    _rows(app, a='deb', b='rpm-el9')
    with app.app_context():
        SystemConfig.query.filter_by(key=updates._ATTEMPTED_VERSION_KEY).delete()
        db.session.commit()
        try:
            updates._auto_install({'latest_version': '3.1', 'current_version': '3.0', 'assets': assets})
            assert updates._cfg_get(updates._ATTEMPTED_VERSION_KEY) in (None, '')
        finally:
            SystemConfig.query.filter_by(key=updates._ATTEMPTED_VERSION_KEY).delete()
            db.session.commit()
    assert _state(app) is None

def test_scheduled_auto_install_in_ha_refuses_a_cluster_with_a_family_without_checksum(app, ha, monkeypatch):
    from models import SystemConfig, db
    from services.audit_service import AuditService
    audits = []
    monkeypatch.delenv('UCM_DOCKER', raising=False)
    monkeypatch.setattr(AuditService, 'log_action', staticmethod(lambda **kw: audits.append(kw)))
    monkeypatch.setattr(updates, 'fetch_expected_sha256', lambda url, name: SHAS[name] if name == DEB else None)
    _rows(app, a='deb', b='rpm-el9')
    with app.app_context():
        SystemConfig.query.filter_by(key=updates._ATTEMPTED_VERSION_KEY).delete()
        db.session.commit()
        try:
            updates._auto_install({'latest_version': '3.1', 'current_version': '3.0',
                                   'download_url': f'https://x/{DEB}', 'package_name': DEB,
                                   'checksum_url': f'https://x/{DEB}.sha256', 'assets': ASSETS})
        finally:
            SystemConfig.query.filter_by(key=updates._ATTEMPTED_VERSION_KEY).delete()
            db.session.commit()
    assert _state(app) is None
    assert audits and audits[-1]['success'] is False and PREFIX + 'b' in audits[-1]['details']

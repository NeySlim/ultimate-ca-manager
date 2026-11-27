"""An update from the interface or from the scheduler to a real 2.254.N, or the major upgrade to
3.0, goes through the backend (check, digest, download, trigger) and then through the root
watcher, which checks the download again and installs it. GitHub is a directory both read: the
backend through a stubbed requests.get, the watcher through UCM_WATCHER_RELEASES.
"""
import hashlib
import os
import time

import pytest

import services.updates as updates
import services.webhook_service as wh
from tests.test_update_major_line import clean  # noqa: F401 (fixture)
from tests.test_update_watcher_claim import Host

INSTALLED = '2.254.7'
ASSETS = {
    'deb': lambda v: f'ucm_{v.replace("-", ".")}_all.deb',
    'el9': lambda v: f'ucm-el9-{v.replace("-", ".")}-1.el9.noarch.rpm',
    'fc43': lambda v: f'ucm-{v.replace("-", ".")}-1.fc43.noarch.rpm',
}


def _release(v):
    names = [make(v) for make in ASSETS.values()]
    return {
        'tag_name': f'v{v}', 'draft': False, 'prerelease': '-' in v, 'body': '',
        'published_at': '2027-01-01T00:00:00Z', 'html_url': f'https://example.invalid/v{v}',
        'assets': [{'name': n + ext, 'browser_download_url': f'https://dl.invalid/v{v}/{n}{ext}'}
                   for n in names for ext in ('', '.sha256')],
    }


class _Response:
    def __init__(self, body):
        self.content = body
        self.text = body.decode()

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size=8192):
        yield self.content


@pytest.fixture
def site(tmp_path, monkeypatch):
    """A 2.254.7 host whose GitHub serves 2.254.8 and 3.0, every asset with its .sha256."""
    def setup(target, family):
        host = Host(tmp_path, installed=INSTALLED, target=target)
        if family != 'deb':
            host.tool('dnf')
        bodies = {}
        for v in ('2.254.8', '3.0'):
            for make in ASSETS.values():
                name = make(v)
                bodies[f'v{v}/{name}'] = body = f'release package {name}'.encode()
                (host.releases / f'v{v}').mkdir(parents=True, exist_ok=True)
                (host.releases / f'v{v}' / f'{name}.sha256').write_text(
                    f'{hashlib.sha256(body).hexdigest()}  {name}\n')

        def get(url, **kwargs):
            key = url.split('https://dl.invalid/', 1)[1]
            if key.endswith('.sha256'):
                return _Response((host.releases / key).read_bytes())
            return _Response(bodies[key])

        real_exists = os.path.exists
        tools = {'/usr/bin/dpkg': family == 'deb', '/usr/bin/rpm': family != 'deb'}
        monkeypatch.setattr(updates.os.path, 'exists', lambda p: tools.get(p, real_exists(p)))
        monkeypatch.setattr(updates, '_el_release', lambda: '9' if family == 'el9' else None)
        monkeypatch.setattr(updates.requests, 'get', get)
        monkeypatch.setattr(updates, 'DATA_DIR', str(host.data))
        monkeypatch.setattr(updates, 'get_current_version', lambda: INSTALLED)
        monkeypatch.setitem(updates._releases_cache, 'data', [_release(v) for v in ('2.254.8', INSTALLED, '3.0')])
        monkeypatch.setitem(updates._releases_cache, 'ts', time.time())
        monkeypatch.delenv('UCM_DOCKER', raising=False)
        monkeypatch.setattr(wh, 'emit_update_initiated', lambda *a, **k: None)
        host.installed = []
        monkeypatch.setattr(wh, 'emit_update_installed', lambda payload, **k: host.installed.append(payload))
        return host
    return setup


def _watch(host, family, target, app):
    """Runs the watcher on what the backend left, then the backend's next start consumes the result."""
    pending = host.data / '.update_pending'
    assert pending.read_text() == str(host.data / 'updates' / ASSETS[family](target))
    result, calls = host.run(None, to_version=target, manifest=False)
    assert result['status'] == 'installed' and result['installed_version'] == target, result
    verb = 'dpkg -i ' if family == 'deb' else 'dnf install -y '
    assert calls[0].startswith(verb), calls
    assert os.path.basename(calls[0][len(verb):]) == ASSETS[family](target)
    assert calls[-1] == 'systemctl restart ucm', calls
    assert not pending.exists() and not list((host.data / 'updates').iterdir())
    with app.app_context():
        updates.consume_update_result()
    assert [p['installed_version'] for p in host.installed] == [target]


@pytest.mark.parametrize('family', list(ASSETS))
def test_an_update_from_the_interface_is_installed(auth_client, app, clean, site, family):  # noqa: F811
    host = site('2.254.8', family)
    r = auth_client.post('/api/v2/system/updates/install', json={})
    assert r.status_code == 200, r.data[:300]
    _watch(host, family, '2.254.8', app)


@pytest.mark.parametrize('family', ['deb', 'el9'])
def test_the_major_upgrade_from_the_interface_is_installed(auth_client, app, clean, site, family):  # noqa: F811
    host = site('3.0', family)
    r = auth_client.post('/api/v2/system/updates/install', json={'major_upgrade': True, 'version': '3.0'})
    assert r.status_code == 200, r.data[:300]
    _watch(host, family, '3.0', app)


@pytest.mark.parametrize('family', ['deb', 'el9'])
def test_an_unattended_update_is_installed(app, clean, site, family):  # noqa: F811
    host = site('2.254.8', family)
    with app.app_context():
        updates._auto_install(updates.check_for_updates(channel='stable'))
    _watch(host, family, '2.254.8', app)

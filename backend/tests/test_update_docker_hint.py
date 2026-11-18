"""The Docker refusal of the install route never points an ordinary update at the latest tag."""
import services.updates as updates


def test_the_docker_refusal_names_the_tag_of_the_new_version(app, auth_client, monkeypatch):
    monkeypatch.setattr(updates, 'is_container_install', lambda: True)
    r = auth_client.post('/api/v2/system/updates/install', json={})
    assert r.status_code == 400
    message = r.get_json()['message']
    assert 'ultimate-ca-manager:<version>' in message
    assert ':latest' not in message


def _container_check(monkeypatch, fips):
    import time
    monkeypatch.setattr(updates, 'package_family', lambda: updates.CONTAINER_FAMILY)
    monkeypatch.setattr(updates, 'get_current_version', lambda: '3.1')
    monkeypatch.setenv('UCM_FIPS', '1' if fips else '')
    release = {'tag_name': 'v3.2', 'draft': False, 'prerelease': False, 'body': '',
               'published_at': '2027-01-01T00:00:00Z', 'html_url': 'https://example.invalid/v3.2',
               'assets': [{'name': 'ucm_3.2_all.deb', 'browser_download_url': 'http://x/ucm_3.2_all.deb'}]}
    monkeypatch.setitem(updates._releases_cache, 'data', [release])
    monkeypatch.setitem(updates._releases_cache, 'ts', time.time())
    return updates.check_for_updates(channel='stable')


def test_a_container_is_pointed_at_the_image_of_the_new_version(monkeypatch):
    assert _container_check(monkeypatch, fips=False)['download_url'] == 'ghcr.io/neyslim/ultimate-ca-manager:3.2'


def test_a_fips_container_is_pointed_at_the_fips_image(monkeypatch):
    """The FIPS image is published under <version>-fips: the standard one has no FIPS module."""
    assert _container_check(monkeypatch, fips=True)['download_url'] == 'ghcr.io/neyslim/ultimate-ca-manager:3.2-fips'


def test_the_docker_refusal_names_the_fips_tag_on_a_fips_container(app, auth_client, monkeypatch):
    monkeypatch.setattr(updates, 'is_container_install', lambda: True)
    monkeypatch.setenv('UCM_FIPS', '1')
    message = auth_client.post('/api/v2/system/updates/install', json={}).get_json()['message']
    assert 'ultimate-ca-manager:<version>-fips' in message

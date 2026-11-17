"""The Docker refusal of the install route never points an ordinary update at the latest tag."""
import services.updates as updates


def test_the_docker_refusal_names_the_tag_of_the_new_version(app, auth_client, monkeypatch):
    monkeypatch.setattr(updates, 'is_container_install', lambda: True)
    r = auth_client.post('/api/v2/system/updates/install', json={})
    assert r.status_code == 400
    message = r.get_json()['message']
    assert 'ultimate-ca-manager:<version>' in message
    assert ':latest' not in message

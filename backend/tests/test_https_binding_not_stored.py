"""Outside HA, an HTTPS apply or regenerate whose binding is not stored restarts nothing.

The next start writes the pair the database names: restarting would serve the previous
certificate again over the one just written.
"""
import pytest


@pytest.fixture
def broken_binding(monkeypatch, tmp_path):
    import api.v2.system.https as route
    from config.settings import Config
    monkeypatch.setenv('HTTPS_CERT_PATH', str(tmp_path / 'https_cert.pem'))
    monkeypatch.setenv('HTTPS_KEY_PATH', str(tmp_path / 'https_key.pem'))
    monkeypatch.setattr(Config, 'HA_MODE', False)

    def fail(*a, **k):
        raise RuntimeError('commit failed')
    monkeypatch.setattr('services.https_binding.set_bound_refid', fail)
    restarts = []
    monkeypatch.setattr(route, 'restart_to_serve', lambda: restarts.append(1) or (True, ''))
    return restarts


@pytest.fixture
def own_cert(app, create_ca, create_cert):
    """A certificate under a CA of its own, both deleted after the test."""
    ca = create_ca(cn='HTTPS unstored binding CA')
    yield create_cert(cn='https-unstored.example.test', ca_id=ca['id'])
    from models import CA, db
    from tests.seeded_rows import delete_cas
    with app.app_context():
        delete_cas(CA.query.filter_by(id=ca['id']))
        db.session.commit()


def test_apply_without_a_stored_binding_does_not_restart(auth_client, own_cert, broken_binding):
    cert = own_cert
    r = auth_client.post('/api/v2/system/https/apply', json={'cert_id': cert['id']})
    assert r.status_code == 500, r.data
    assert broken_binding == []


def test_regenerate_without_a_stored_binding_does_not_restart(auth_client, broken_binding):
    r = auth_client.post('/api/v2/system/https/regenerate', json={'common_name': 'unstored.test'})
    assert r.status_code == 500, r.data
    assert broken_binding == []


@pytest.fixture
def prior(app):
    """Sets what the database served before the request: nothing, a binding, or a
    regenerated pair; the rows found before are put back after."""
    from models import SharedFile, SystemConfig, db
    from services import shared_files
    from services.https_binding import BOUND_REFID_KEY
    with app.app_context():
        row = SystemConfig.query.filter_by(key=BOUND_REFID_KEY).first()
        saved_bound = row.value if row else None
        generated = db.session.get(SharedFile, shared_files.HTTPS_GENERATED)
        saved_generated = generated.content if generated else None

    def _set(state):
        from services.https_binding import _set_config
        with app.app_context():
            _set_config(BOUND_REFID_KEY, 'earlier-https-refid' if state == 'bound' else '', 'test')
            shared_files.drop_file(shared_files.HTTPS_GENERATED)
            if state == 'generated':
                shared_files.store_file(shared_files.HTTPS_GENERATED, b'{"crt": "", "key": ""}')
            db.session.commit()
    yield _set
    with app.app_context():
        from services.https_binding import _set_config
        _set_config(BOUND_REFID_KEY, saved_bound or '', 'test')
        shared_files.drop_file(shared_files.HTTPS_GENERATED)
        db.session.flush()
        if saved_generated is not None:
            db.session.add(SharedFile(name=shared_files.HTTPS_GENERATED, content=saved_generated))
        db.session.commit()


def _post(auth_client, route, own_cert):
    if route == 'apply':
        return auth_client.post('/api/v2/system/https/apply', json={'cert_id': own_cert['id']})
    return auth_client.post('/api/v2/system/https/regenerate', json={'common_name': 'unstored.test'})


@pytest.mark.parametrize('route', ['apply', 'regenerate'])
@pytest.mark.parametrize('state, served', [
    ('none', 'this certificate'), ('bound', 'the previous certificate'),
    ('generated', 'the previous certificate')])
def test_the_500_names_the_certificate_the_next_start_serves(
        auth_client, own_cert, broken_binding, prior, route, state, served):
    # No binding and no stored pair: the next start leaves the files just written
    prior(state)
    r = _post(auth_client, route, own_cert)
    assert r.status_code == 500, r.data
    assert r.get_json()['message'].endswith(f'its next start serves {served}'), r.data


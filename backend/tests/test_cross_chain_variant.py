"""chain_variant on exports, deploy bindings and bulk exports; an unknown value is a 400 (#400)."""

import pytest

from models import Certificate, DeployBinding, db
from tests.fixtures.cross_world import admin_enrolment, build_world, set_served
from tests.test_cross_chain_paths import _der, _loads

BAD = ['bogus', 'cross:999999', 'cross:', 'CROSS:1']


@pytest.fixture
def world(app, auth_client):
    return build_world(app, auth_client)


def _roots(certs, w):
    return [{_der(w.pki.root_b): 'B', _der(w.pki.cross_b): 'cross', _der(w.pki.root_a): 'A',
             _der(w.pki.int_b): 'int'}[_der(c)] for c in certs]


def _cert_export(client, w, method, variant):
    url = f'/api/v2/certificates/{w.leaf_id}/export'
    if method == 'get':
        return client.get(f'{url}?format=pem&include_chain=true&include_root=true&chain_variant={variant}')
    return client.post(url, json={'format': 'pem', 'include_chain': True, 'include_root': True,
                                  'chain_variant': variant})


@pytest.mark.parametrize('method', ['get', 'post'])
def test_a_certificate_export_honours_an_explicit_variant_over_the_served_flag(auth_client, world, method):
    set_served(auth_client, world, True)
    r = _cert_export(auth_client, world, method, 'primary')
    assert _roots(_loads(r.data)[1:], world) == ['int', 'B']
    set_served(auth_client, world, False)
    r = _cert_export(auth_client, world, method, f'cross:{world.xid}')
    assert _roots(_loads(r.data)[1:], world) == ['int', 'cross', 'A']
    r = _cert_export(auth_client, world, method, 'auto')
    assert _roots(_loads(r.data)[1:], world) == ['int', 'B']


@pytest.mark.parametrize('method', ['get', 'post'])
@pytest.mark.parametrize('bad', BAD)
def test_a_certificate_export_refuses_an_unknown_variant(auth_client, world, method, bad):
    assert _cert_export(auth_client, world, method, bad).status_code == 400


def test_a_pkcs12_export_refuses_an_unknown_variant_before_building_anything(auth_client, world):
    r = auth_client.post(f'/api/v2/certificates/{world.leaf_id}/export',
                         json={'format': 'pkcs12', 'password': 'Sup3r-secret-pw!', 'chain_variant': 'bogus'})
    assert r.status_code == 400


def test_a_ca_export_swaps_the_ca_certificate_for_its_cross_certificate(auth_client, world):
    r = auth_client.post(f'/api/v2/cas/{world.b_id}/export', json={'format': 'pem', 'include_chain': True})
    assert _roots(_loads(r.data), world) == ['B']
    r = auth_client.post(f'/api/v2/cas/{world.b_id}/export',
                         json={'format': 'pem', 'include_chain': True, 'chain_variant': f'cross:{world.xid}'})
    assert _roots(_loads(r.data), world) == ['cross', 'A']
    set_served(auth_client, world, True)
    r = auth_client.post(f'/api/v2/cas/{world.b_id}/export', json={'format': 'pem', 'include_chain': True})
    assert _roots(_loads(r.data), world) == ['B']
    r = auth_client.post(f'/api/v2/cas/{world.b_id}/export',
                         json={'format': 'pem', 'include_chain': True, 'chain_variant': 'auto'})
    assert _roots(_loads(r.data), world) == ['cross', 'A']
    r = auth_client.post(f'/api/v2/cas/{world.b_id}/export',
                         json={'format': 'pem', 'include_chain': True, 'chain_variant': 'primary'})
    assert _roots(_loads(r.data), world) == ['B']
    # without a chain the CA exports its own certificate whatever is served
    r = auth_client.post(f'/api/v2/cas/{world.b_id}/export', json={'format': 'pem'})
    assert _roots(_loads(r.data), world) == ['B']


@pytest.mark.parametrize('bad', BAD)
def test_a_ca_export_refuses_an_unknown_variant(auth_client, world, bad):
    r = auth_client.post(f'/api/v2/cas/{world.b_id}/export',
                         json={'format': 'pem', 'include_chain': True, 'chain_variant': bad})
    assert r.status_code == 400
    assert auth_client.get(f'/api/v2/cas/{world.b_id}/export?chain_variant={bad}').status_code == 400


def test_a_variant_of_another_ca_is_not_valid_for_this_one(auth_client, world):
    r = auth_client.post(f'/api/v2/cas/{world.a_id}/export',
                         json={'format': 'pem', 'include_chain': True, 'chain_variant': f'cross:{world.xid}'})
    assert r.status_code == 400


def test_a_user_certificate_export_follows_the_variant(app, auth_client, world):
    with admin_enrolment(app, world.pki.leaf) as auth_id:
        base = f'/api/v2/user-certificates/{auth_id}/export?format=pem&include_chain=true&include_root=true'
        assert _roots(_loads(auth_client.get(f'{base}&chain_variant=cross:{world.xid}').data)[1:], world) == [
            'int', 'cross', 'A']
        assert auth_client.get(f'{base}&chain_variant=bogus').status_code == 400


# --- deploy bindings -------------------------------------------------------------------------------------

def _binding(auth_client, w, **extra):
    from tests.test_deploy_hooks import BASE, _create_target, post_json
    target = _create_target(auth_client)
    return post_json(auth_client, f'{BASE}/bindings', {
        'target_id': target['id'], 'certificate_id': w.leaf_id, 'fullchain_path': '/etc/ssl/ucm/fullchain.pem',
        'include_root': True, **extra})


def test_a_binding_defaults_to_auto_and_stores_a_valid_variant(app, auth_client, world):
    r = _binding(auth_client, world)
    assert r.status_code == 201, r.data
    assert r.get_json()['data']['chain_variant'] == 'auto'
    r = _binding(auth_client, world, chain_variant=f'cross:{world.xid}')
    assert r.status_code == 201, r.data
    assert r.get_json()['data']['chain_variant'] == f'cross:{world.xid}'


@pytest.mark.parametrize('bad', BAD)
def test_a_binding_refuses_an_unknown_variant(auth_client, world, bad):
    assert _binding(auth_client, world, chain_variant=bad).status_code == 400


def test_patching_a_binding_validates_and_applies_its_variant(app, auth_client, world):
    from tests.test_deploy_hooks import BASE, patch_json
    binding_id = _binding(auth_client, world).get_json()['data']['id']
    assert patch_json(auth_client, f'{BASE}/bindings/{binding_id}', {'chain_variant': 'bogus'}).status_code == 400
    r = patch_json(auth_client, f'{BASE}/bindings/{binding_id}', {'chain_variant': 'primary'})
    assert r.status_code == 200, r.data
    with app.app_context():
        assert db.session.get(DeployBinding, binding_id).chain_variant == 'primary'


def test_the_deployed_fullchain_follows_the_binding_variant(app, auth_client, world):
    from services.deploy.service import DeployService
    set_served(auth_client, world, True)
    with app.app_context():
        leaf = db.session.get(Certificate, world.leaf_id)

        def deployed(variant):
            binding = DeployBinding(fullchain_path='/srv/fullchain.pem', include_root=True, chain_variant=variant)
            return _roots(_loads(DeployService.resolve_files(binding, leaf)[0][1])[1:], world)

        assert deployed('auto') == ['int', 'cross', 'A']
        assert deployed('primary') == ['int', 'B']


def test_a_binding_naming_a_detached_cross_certificate_fails_instead_of_pushing_a_short_chain(
        app, auth_client, world):
    from services.deploy.service import DeployService
    from utils.ca_chain import ChainVariantError
    variant = f'cross:{world.xid}'
    assert auth_client.delete(f'/api/v2/cas/{world.b_id}/cross-certificates/{world.xid}').status_code in (200, 204)
    with app.app_context():
        binding = DeployBinding(fullchain_path='/srv/fullchain.pem', include_root=True, chain_variant=variant)
        with pytest.raises(ChainVariantError):
            DeployService.resolve_files(binding, db.session.get(Certificate, world.leaf_id))


# --- bulk CA export ----------------------------------------------------------------------------------------

def _bulk(client, option):
    suffix = f'&chain_variant={option}' if option is not None else ''
    return client.get(f'/api/v2/cas/export?format=pem{suffix}')


def test_the_bulk_ca_export_lists_cross_certificates_only_when_asked(auth_client, world):
    cross = _der(world.pki.cross_b)

    def has_cross(option):
        r = _bulk(auth_client, option)
        assert r.status_code == 200, r.data
        return cross in {_der(c) for c in _loads(r.data)}

    assert not has_cross(None) and not has_cross('primary') and not has_cross('auto')
    assert has_cross('all') and has_cross(f'cross:{world.xid}')
    set_served(auth_client, world, True)
    assert has_cross('auto') and not has_cross('primary')


@pytest.mark.parametrize('bad', ['bogus', 'cross:999999', 'cross:'])
def test_the_bulk_ca_export_refuses_an_unknown_variant(auth_client, world, bad):
    assert _bulk(auth_client, bad).status_code == 400
    r = auth_client.post('/api/v2/cas/export', json={'format': 'pem', 'chain_variant': bad})
    assert r.status_code == 400

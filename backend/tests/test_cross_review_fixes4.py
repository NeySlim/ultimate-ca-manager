"""Fourth review pass on the cross-certificate chain consumers (#400)."""
import base64
import json
from datetime import timedelta

import pytest

from cryptography.hazmat.primitives.serialization import Encoding

from models import CA, Certificate, DeployBinding, db
from models.ca_cross_certificate import CACrossCertificate
from tests.fixtures.cross_pki import make_cert, pem
from tests.fixtures.cross_world import build_world, set_served
from tests.test_cross_chain_paths import _der, _loads
from tests.test_cross_review_fixes3 import sibling_records  # noqa: F401
from utils.datetime_utils import utc_now


@pytest.fixture
def world(app, auth_client):
    return build_world(app, auth_client)


def _push_chain(app, world, variant):
    from services.deploy.service import DeployService
    with app.app_context():
        binding = DeployBinding(fullchain_path='/srv/fullchain.pem', include_root=True, chain_variant=variant)
        files = DeployService.resolve_files(binding, db.session.get(Certificate, world.leaf_id))
    return [_der(c) for c in _loads(files[0][1])]


@pytest.mark.parametrize('field,delta', [('valid_to', -1), ('valid_from', 200)])
def test_a_binding_pinned_to_a_cross_certificate_outside_its_validity_still_pushes_the_leaf(
        app, auth_client, world, field, delta):
    pinned = _push_chain(app, world, f'cross:{world.xid}')
    with app.app_context():
        setattr(db.session.get(CACrossCertificate, world.xid), field, utc_now() + timedelta(days=delta))
        db.session.commit()
    chain = _push_chain(app, world, f'cross:{world.xid}')
    assert chain == _push_chain(app, world, 'auto') and chain != pinned
    assert _der(world.pki.cross_b) not in chain


def test_an_intermediate_export_applies_the_served_rule_above_it_when_it_serves_its_own_cross(app, auth_client, world):
    pki = world.pki
    ix = make_cert(f'Cross Int B {pki.tag}', pki.key_int, pki.name_a, pki.key_a, days=300, path_length=0)
    base = f'/api/v2/cas/{world.int_id}'
    r = auth_client.post(f'{base}/cross-certificates', json={'certificate': pem(ix), 'served': True})
    assert r.status_code == 201, r.data
    set_served(auth_client, world, True)
    r = auth_client.post(f'{base}/export', json={'format': 'pem', 'include_chain': True})
    assert r.status_code == 200, r.data
    assert [_der(c) for c in _loads(r.data)] == [_der(pki.int_b), _der(pki.cross_b), _der(pki.root_a)]


def test_a_not_yet_valid_cross_certificate_is_refused_with_its_own_reason(app, auth_client, world):
    with app.app_context():
        db.session.get(CACrossCertificate, world.xid).valid_from = utc_now() + timedelta(days=200)
        db.session.commit()
    url = f'/api/v2/cas/{world.b_id}/cross-certificates/{world.xid}'
    r = auth_client.patch(url, json={'served': True})
    assert r.status_code == 409
    assert 'not yet valid' in r.get_json()['message']
    rows = auth_client.get(f'/api/v2/cas/{world.b_id}/cross-certificates').get_json()['data']
    row = next(x for x in rows if x['id'] == world.xid)
    assert row['not_yet_valid'] is True and row['expired'] is False


def test_a_revocation_routed_through_the_rest_api_is_held_by_the_policy_on_the_sibling_record(
        app, world, create_user, sibling_records):
    from tests.test_approval_revoke_renew import _json, _login
    with app.app_context():
        leaf = db.session.get(Certificate, world.leaf_id)
        leaf.caref = db.session.get(CA, sibling_records.bx_id).refid
        db.session.commit()
    operator, _ = _login(app, create_user)
    r = _json(operator, 'post', f'/api/v2/certificates/{world.leaf_id}/revoke', {'reason': 'keyCompromise'})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['data'].get('approval_id'), r.get_json()


def test_the_chain_status_lists_the_issuing_ca_and_ten_levels_at_most(app, auth_client):
    tag = utc_now().strftime('%H%M%S%f')
    with app.app_context():
        parent, ids = None, []
        for level in range(14):
            ca = CA(refid=f'deep-{tag}-{level}', descr=f'Deep {tag} {level}', subject=f'CN=deep {tag} {level}',
                    issuer=f'CN=deep {tag} {level + 1}', caref=f'deep-{tag}-{level + 1}',
                    crt=base64.b64encode(b'x').decode())
            db.session.add(ca)
            ids.append(ca)
        leaf = Certificate(refid=f'deep-leaf-{tag}', descr=f'deep leaf {tag}', caref=f'deep-{tag}-0',
                           source='imported', crt=base64.b64encode(b'x').decode(), subject='CN=leaf',
                           issuer='CN=deep')
        db.session.add(leaf)
        db.session.commit()
        leaf_id, created = leaf.id, [c.id for c in ids]
    try:
        from api.v2.certificates.cert_get import _validate_cert_chain
        with app.app_context():
            assert _validate_cert_chain(db.session.get(Certificate, leaf_id))['chain_length'] == 11
    finally:
        with app.app_context():
            db.session.delete(db.session.get(Certificate, leaf_id))
            for cid in created:
                db.session.delete(db.session.get(CA, cid))
            db.session.commit()


def test_a_binding_pinned_to_a_revoked_cross_certificate_still_pushes_leaf_and_key_with_the_auto_chain(
        app, auth_client, world):
    from services.deploy.service import DeployService
    r = auth_client.post(f'/api/v2/cas/{world.b_id}/cross-certificates/{world.xid}/revoke', json={})
    assert r.status_code == 200, r.data
    with app.app_context():
        binding = DeployBinding(cert_path='/srv/cert.pem', key_path='/srv/key.pem',
                                fullchain_path='/srv/fullchain.pem', include_root=True,
                                chain_variant=f'cross:{world.xid}')
        files = {f[0]: f[1] for f in DeployService.resolve_files(binding, db.session.get(Certificate, world.leaf_id))}
    assert set(files) == {'/srv/cert.pem', '/srv/key.pem', '/srv/fullchain.pem'}
    assert _der(world.pki.cross_b) not in [_der(c) for c in _loads(files['/srv/fullchain.pem'])]

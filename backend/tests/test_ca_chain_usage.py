"""GET /api/v2/cas/<id>/chain-usage: what still chains to a CA (#400)."""
import base64
import uuid
from datetime import timedelta

import pytest

from models import CA, Certificate, DeployBinding, DeployTarget, db
from models.ca_cross_certificate import CACrossCertificate
from services.smart_import.importer import SmartImporter
from tests.fixtures.cross_pki import make_cert, new_key, pem
from tests.fixtures.cross_world import build_world, set_served
from utils.datetime_utils import utc_now


@pytest.fixture
def world(app, auth_client):
    return build_world(app, auth_client)


def usage(client, ca_id):
    r = client.get(f'/api/v2/cas/{ca_id}/chain-usage')
    assert r.status_code == 200, r.data
    return r.get_json()['data']


def counts(client, ca_id):
    d = usage(client, ca_id)
    return d['issued']['count'], d['via_cross']['count'], d['deployments']['count']


def add_leaf(app, caref, **over):
    with app.app_context():
        base = Certificate.query.filter_by(caref=caref).first()
        leaf = Certificate(refid=uuid.uuid4().hex, descr=f'extra {uuid.uuid4().hex[:6]}', caref=caref,
                           source='imported', crt=base.crt if base else 'x',
                           subject_cn='extra', valid_from=utc_now(), valid_to=utc_now() + timedelta(days=30),
                           revoked=False)
        for k, v in over.items():
            setattr(leaf, k, v)
        db.session.add(leaf)
        db.session.commit()
        return leaf.id


def bind(app, cert_id, variant='auto', fullchain='/srv/fc.pem', include_root=False, enabled=True,
         target_enabled=True):
    with app.app_context():
        target = DeployTarget(name=f't-{uuid.uuid4().hex[:8]}', host='h.example', username='u',
                              private_key='k', enabled=target_enabled)
        db.session.add(target)
        db.session.flush()
        b = DeployBinding(target_id=target.id, certificate_id=cert_id, fullchain_path=fullchain,
                          cert_path='/srv/c.pem' if not fullchain else None, include_root=include_root,
                          chain_variant=variant, enabled=enabled)
        db.session.add(b)
        db.session.commit()
        return b.id


def cross_row(app, xid, **over):
    with app.app_context():
        row = db.session.get(CACrossCertificate, xid)
        for k, v in over.items():
            setattr(row, k, v)
        db.session.commit()


def int_ca_refid(w):
    return w.int_refid


# --- issued / via_cross ----------------------------------------------------------------------------------

def test_certificates_issued_below_a_ca_count_as_issued_whatever_the_depth(auth_client, world):
    assert counts(auth_client, world.b_id)[0] == 1
    assert counts(auth_client, world.int_id)[0] == 1
    assert counts(auth_client, world.a_id)[0] == 0
    item = usage(auth_client, world.b_id)['issued']['items'][0]
    assert item['id'] == world.leaf_id and item['valid_to'] and item['ca']


def test_a_served_cross_puts_the_certificates_via_cross_of_its_issuer(auth_client, world):
    assert counts(auth_client, world.a_id)[1] == 0
    set_served(auth_client, world, True)
    d = usage(auth_client, world.a_id)
    assert d['via_cross']['count'] == 1
    assert d['via_cross']['items'][0]['id'] == world.leaf_id
    assert d['via_cross']['cross_certificates'] == [
        {'id': world.xid, 'ca_id': world.b_id, 'ca_name': world.pki.name_b, 'served': True}]
    assert counts(auth_client, world.b_id)[1] == 0  # B is not the cross's issuer


def test_a_cross_that_is_not_servable_is_not_counted(app, auth_client, world):
    set_served(auth_client, world, True)
    cross_row(app, world.xid, revoked=True)
    assert counts(auth_client, world.a_id)[1] == 0


def test_an_expired_cross_is_not_counted(app, auth_client, world):
    set_served(auth_client, world, True)
    cross_row(app, world.xid, valid_to=utc_now() - timedelta(days=1))
    assert counts(auth_client, world.a_id)[1] == 0


def test_an_unserved_cross_is_not_in_the_default_chain(auth_client, world):
    assert counts(auth_client, world.a_id)[1] == 0


def test_a_served_cross_lower_in_the_chain_masks_the_one_issued_by_x(app, auth_client, world):
    set_served(auth_client, world, True)
    key_c = new_key()
    pki = world.pki
    root_c = make_cert('Cross Root C ' + pki.tag, key_c)
    int_cross = make_cert(f'Cross Int B {pki.tag}', pki.key_int, 'Cross Root C ' + pki.tag, key_c, path_length=0)
    with app.app_context():
        SmartImporter().execute(pem(root_c))
        c_id = CA.query.filter_by(descr='Cross Root C ' + pki.tag).one().id
    r = auth_client.post(f'/api/v2/cas/{world.int_id}/cross-certificates',
                         json={'certificate': pem(int_cross), 'served': True})
    assert r.status_code == 201, r.data
    assert counts(auth_client, world.a_id)[1] == 0
    assert counts(auth_client, c_id)[1] == 1


def test_a_cross_issued_by_a_record_of_the_same_key_counts_for_x(app, auth_client, world):
    set_served(auth_client, world, True)
    with app.app_context():
        a = db.session.get(CA, world.a_id)
        twin = CA(refid=uuid.uuid4().hex, descr='twin of A', crt=a.crt, subject=a.subject, issuer=a.issuer)
        db.session.add(twin)
        db.session.commit()
        twin_ref = twin.refid
    cross_row(app, world.xid, issuer_caref=twin_ref)
    assert counts(auth_client, world.a_id)[1] == 1


@pytest.mark.parametrize('over', [{'revoked': True}, {'valid_to': utc_now() - timedelta(days=1)}])
def test_revoked_and_expired_certificates_are_excluded(app, auth_client, world, over):
    set_served(auth_client, world, True)
    with app.app_context():
        for k, v in over.items():
            setattr(db.session.get(Certificate, world.leaf_id), k, v)
        db.session.commit()
    assert counts(auth_client, world.b_id) == (0, 0, 0)
    assert counts(auth_client, world.a_id) == (0, 0, 0)


def test_sections_are_sorted_by_expiry_and_capped_at_100(app, auth_client, world):
    with app.app_context():
        base = db.session.get(Certificate, world.leaf_id)
        for i in range(104):
            db.session.add(Certificate(refid=uuid.uuid4().hex, descr=f'bulk{i}', caref=world.int_refid,
                                       crt=base.crt, subject_cn=f'bulk{i}', valid_from=utc_now(),
                                       valid_to=utc_now() + timedelta(days=100 + i), revoked=False))
        db.session.commit()
    sec = usage(auth_client, world.b_id)['issued']
    assert sec['count'] == 105 and len(sec['items']) == 100 and sec['truncated'] is True
    dates = [i['valid_to'] for i in sec['items']]
    assert dates == sorted(dates) and sec['items'][0]['id'] == world.leaf_id


def test_unknown_ca_is_404(auth_client):
    assert auth_client.get('/api/v2/cas/999999/chain-usage').status_code == 404


def test_the_note_says_what_ucm_cannot_see(auth_client, world):
    assert 'cached' in usage(auth_client, world.b_id)['note']


def test_the_default_chain_is_resolved_once_per_ca(app, auth_client, world, monkeypatch):
    import services.ca.chain_usage as mod
    calls = []
    real = mod.issuer_chain
    monkeypatch.setattr(mod, 'issuer_chain', lambda *a, **k: calls.append(1) or real(*a, **k))
    usage(auth_client, world.a_id)
    before = len(calls)
    for _ in range(5):
        add_leaf(app, world.int_refid)
    calls.clear()
    usage(auth_client, world.a_id)
    assert len(calls) == before and before >= 1


# --- deployments -----------------------------------------------------------------------------------------

def test_case1_a_binding_pinned_to_a_servable_cross_of_x(app, auth_client, world):
    bid = bind(app, world.leaf_id, f'cross:{world.xid}')
    d = usage(auth_client, world.a_id)['deployments']
    assert d['count'] == 1 and d['items'][0]['id'] == bid and d['items'][0]['variant'] == f'cross:{world.xid}'
    assert d['items'][0]['certificate_id'] == world.leaf_id and d['items'][0]['target']


def test_case1_a_pin_on_a_cross_that_is_not_servable_is_not_counted(app, auth_client, world):
    bind(app, world.leaf_id, f'cross:{world.xid}')
    cross_row(app, world.xid, revoked=True)
    assert counts(auth_client, world.a_id)[2] == 0


def test_case2_an_auto_binding_follows_the_default_chain(app, auth_client, world):
    bind(app, world.leaf_id, 'auto')
    assert counts(auth_client, world.a_id)[2] == 0
    set_served(auth_client, world, True)
    assert counts(auth_client, world.a_id)[2] == 1


def test_a_primary_binding_does_not_chain_through_a_cross(app, auth_client, world):
    set_served(auth_client, world, True)
    bind(app, world.leaf_id, 'primary')
    assert counts(auth_client, world.a_id)[2] == 0


def test_case3_a_full_chain_that_carries_the_root_of_x(app, auth_client, world):
    bind(app, world.leaf_id, 'primary', include_root=True)
    assert counts(auth_client, world.b_id)[2] == 1


def test_case3_a_chain_without_any_ca_certificate_is_not_counted(app, auth_client, world):
    with app.app_context():
        # issued directly by a root, the root left out: nothing of X is pushed
        a = db.session.get(CA, world.a_id)
        cid = add_leaf(app, a.refid, crt=base64.b64encode(pem(world.pki.leaf).encode()).decode())
    bind(app, cid, 'primary', include_root=False)
    assert counts(auth_client, world.a_id)[2] == 0
    bind(app, cid, 'primary', include_root=True)
    assert counts(auth_client, world.a_id)[2] == 1


def test_bindings_without_full_chain_or_disabled_are_ignored(app, auth_client, world):
    bind(app, world.leaf_id, f'cross:{world.xid}', fullchain=None)
    bind(app, world.leaf_id, f'cross:{world.xid}', enabled=False)
    bind(app, world.leaf_id, f'cross:{world.xid}', target_enabled=False)
    assert counts(auth_client, world.a_id)[2] == 0


# --- permissions -----------------------------------------------------------------------------------------

def _key_with(auth_client, permissions):
    r = auth_client.post('/api/v2/account/apikeys',
                         json={'name': 'cu' + uuid.uuid4().hex[:8], 'permissions': permissions})
    assert r.status_code == 201, r.data
    return r.get_json()['data']['key']


@pytest.mark.parametrize('perms,status', [(['read:cas', 'read:certificates'], 200), (['read:cas'], 403),
                                           (['read:certificates'], 403)])
def test_both_read_permissions_are_required(app, auth_client, world, perms, status):
    key = _key_with(auth_client, perms)
    r = app.test_client().get(f'/api/v2/cas/{world.b_id}/chain-usage', headers={'X-API-Key': key})
    assert r.status_code == status


def test_the_unauthenticated_are_refused(client, world):
    assert client.get(f'/api/v2/cas/{world.b_id}/chain-usage').status_code == 401

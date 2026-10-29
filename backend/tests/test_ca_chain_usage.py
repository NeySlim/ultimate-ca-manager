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


@pytest.fixture(autouse=True)
def _remove_what_the_test_added(app):
    """Placeholder certificates and bindings must not outlive the test: other files score every certificate."""
    with app.app_context():
        floor = {m: (db.session.query(db.func.max(m.id)).scalar() or 0) for m in (Certificate, DeployBinding, DeployTarget)}
    yield
    with app.app_context():
        db.session.rollback()
        for model in (DeployBinding, DeployTarget, Certificate):
            model.query.filter(model.id > floor[model]).delete()
        db.session.commit()


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
        {'id': world.xid, 'ca_id': world.b_id, 'ca_name': world.pki.name_b, 'served': True, 'servable': True}]
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


# --- chains through an intermediate, orphans, unresolved issuers (review of #400) ---------------------------

def _b64(cert):
    return base64.b64encode(pem(cert).encode()).decode()


def _leaf_row(app, cert, caref, **over):
    with app.app_context():
        row = Certificate(refid=uuid.uuid4().hex, descr=f'leaf {uuid.uuid4().hex[:6]}', caref=caref, source='imported',
                          crt=_b64(cert), serial_number=str(cert.serial_number), subject=cert.subject.rfc4514_string(),
                          issuer=cert.issuer.rfc4514_string(), subject_cn='leaf', valid_from=utc_now(),
                          valid_to=utc_now() + timedelta(days=30), revoked=False)
        for k, v in over.items():
            setattr(row, k, v)
        db.session.add(row)
        db.session.commit()
        return row.id


class YWorld:
    """Root A > Y; Root B > Int B > leaf; B cross-signed by Y (not by A)."""


def build_y_world(app, auth_client, served=True, import_a=True, attach=True):
    w = YWorld()
    tag = uuid.uuid4().hex[:8]
    w.tag = tag
    ka, ky, kb, ki, kl = (new_key() for _ in range(5))
    na, ny, nb, ni = (f'Y {n} {tag}' for n in ('Root A', 'Mid Y', 'Root B', 'Int B'))
    w.root_a = make_cert(na, ka)
    w.y = make_cert(ny, ky, na, ka, path_length=1)
    w.root_b = make_cert(nb, kb)
    w.cross = make_cert(nb, kb, ny, ky)
    w.int_b = make_cert(ni, ki, nb, kb, path_length=0)
    w.leaf = make_cert(f'leaf-{tag}.example', kl, ni, ki, ca=False, days=90, san=f'leaf-{tag}.example')
    order = [w.root_b, w.int_b] + ([w.root_a, w.y] if import_a else [])
    with app.app_context():
        for c in order[:2]:
            SmartImporter().execute(pem(c))
    w.names = (na, ny, nb, ni)
    if attach:
        with app.app_context():
            w.b_id = CA.query.filter_by(descr=nb).one().id
        r = auth_client.post(f'/api/v2/cas/{w.b_id}/cross-certificates', json={'certificate': pem(w.cross), 'served': served})
        assert r.status_code == 201, r.data
        w.xid = r.get_json()['data']['id']
    if import_a:
        import_ay(app, w)
    with app.app_context():
        w.int_refid = CA.query.filter_by(descr=ni).one().refid
        w.b_id = CA.query.filter_by(descr=nb).one().id
    w.leaf_id = _leaf_row(app, w.leaf, w.int_refid)
    return w


def import_ay(app, w):
    with app.app_context():
        for c in (w.root_a, w.y):
            SmartImporter().execute(pem(c))
        w.a_id = CA.query.filter_by(descr=w.names[0]).one().id
        w.y_id = CA.query.filter_by(descr=w.names[1]).one().id


def test_p1_a_cross_signed_by_an_intermediate_counts_for_the_root_above(app, auth_client):
    w = build_y_world(app, auth_client)
    assert counts(auth_client, w.a_id)[1] == 1
    assert counts(auth_client, w.y_id)[1] == 1
    assert counts(auth_client, w.b_id)[:2] == (1, 0)
    bind(app, w.leaf_id, 'auto')
    assert counts(auth_client, w.a_id)[2] == 1
    assert counts(auth_client, w.y_id)[2] == 1


def test_p1_a_binding_pinned_to_a_cross_signed_by_an_intermediate(app, auth_client):
    w = build_y_world(app, auth_client, served=False)
    assert counts(auth_client, w.a_id) == (0, 0, 0)
    bind(app, w.leaf_id, f'cross:{w.xid}')
    assert counts(auth_client, w.a_id)[2] == 1


def test_case1_pin_on_a_cross_attached_before_its_issuer_was_imported(app, auth_client):
    w = build_y_world(app, auth_client, import_a=False)
    with app.app_context():
        assert db.session.get(CACrossCertificate, w.xid).issuer_caref is None
    import_ay(app, w)
    bind(app, w.leaf_id, f'cross:{w.xid}')
    assert counts(auth_client, w.a_id)[2] == 1
    assert counts(auth_client, w.a_id)[1] == 1


def test_case1_pin_on_a_cross_whose_issuer_link_dangles(app, auth_client):
    w = build_y_world(app, auth_client, served=False)
    cross_row(app, w.xid, issuer_caref='gone-' + uuid.uuid4().hex[:8])
    bind(app, w.leaf_id, f'cross:{w.xid}')
    assert counts(auth_client, w.a_id)[2] == 1


def test_a_certificate_without_caref_counts_with_the_ca_that_issued_it(app, auth_client, world):
    cid = _leaf_row(app, world.pki.leaf, None)
    assert counts(auth_client, world.b_id)[0] == 2
    assert counts(auth_client, world.int_id)[0] == 2
    ids = {i['id'] for i in usage(auth_client, world.int_id)['issued']['items']}
    assert cid in ids
    assert counts(auth_client, world.a_id)[0] == 0


def test_orphan_bindings_are_evaluated(app, auth_client, world):
    cid = _leaf_row(app, world.pki.leaf, None)
    bind(app, cid, 'auto', include_root=True)
    assert counts(auth_client, world.b_id)[2] == 1
    assert counts(auth_client, world.a_id)[2] == 0


def test_a_certificate_whose_caref_dangles_is_resolved_like_an_orphan(app, auth_client, world):
    _leaf_row(app, world.pki.leaf, 'gone-' + uuid.uuid4().hex[:8])
    assert counts(auth_client, world.b_id)[0] == 2


def test_an_orphan_with_no_known_issuer_is_not_counted(app, auth_client, world):
    other = build_y_world(app, auth_client, attach=False, import_a=False)
    _leaf_row(app, other.leaf, None, revoked=False)
    with app.app_context():
        CA.query.filter(CA.descr.in_([other.names[2], other.names[3]])).update({'subject': 'CN=elsewhere'}, synchronize_session=False)
        db.session.commit()
    assert counts(auth_client, world.b_id)[0] == 1


# --- cross-certificates that stay on offer ---------------------------------------------------------------

def test_cross_certificates_of_the_issuer_are_always_listed(auth_client, world):
    d = usage(auth_client, world.a_id)
    assert counts(auth_client, world.a_id) == (0, 0, 0)
    assert d['via_cross']['cross_certificates'] == [
        {'id': world.xid, 'ca_id': world.b_id, 'ca_name': world.pki.name_b, 'served': False, 'servable': True}]


def test_a_cross_that_cannot_be_served_is_listed_as_such(app, auth_client, world):
    cross_row(app, world.xid, revoked=True)
    row = usage(auth_client, world.a_id)['via_cross']['cross_certificates'][0]
    assert row['servable'] is False


def test_crosses_issued_by_a_ca_below_are_listed_for_the_root(app, auth_client):
    w = build_y_world(app, auth_client, served=False)
    rows = usage(auth_client, w.a_id)['via_cross']['cross_certificates']
    assert [r['id'] for r in rows] == [w.xid]
    assert usage(auth_client, w.b_id)['via_cross']['cross_certificates'] == []


# --- cost ------------------------------------------------------------------------------------------------

def _queries(app, fn):
    from sqlalchemy import event
    seen = []
    def hook(conn, cursor, statement, *a):
        seen.append(statement)
    with app.app_context():
        event.listen(db.engine, 'before_cursor_execute', hook)
        try:
            fn()
        finally:
            event.remove(db.engine, 'before_cursor_execute', hook)
    return len(seen)


def test_the_number_of_queries_does_not_grow_with_the_bindings(app, auth_client, world):
    set_served(auth_client, world, True)
    bind(app, world.leaf_id, 'auto')
    bind(app, world.leaf_id, f'cross:{world.xid}', include_root=True)
    small = _queries(app, lambda: usage(auth_client, world.a_id))
    for _ in range(30):
        bind(app, world.leaf_id, 'auto')
        bind(app, world.leaf_id, f'cross:{world.xid}', include_root=True)
    big = _queries(app, lambda: usage(auth_client, world.a_id))
    assert counts(auth_client, world.a_id)[2] == 62
    assert big <= small + 4, (small, big)


def test_unrelated_bindings_cost_nothing(app, auth_client, world):
    other = build_world(app, auth_client)
    base = _queries(app, lambda: usage(auth_client, world.a_id))
    for _ in range(25):
        bind(app, other.leaf_id, 'primary', include_root=True)
    assert _queries(app, lambda: usage(auth_client, world.a_id)) <= base + 3
    assert counts(auth_client, world.a_id)[2] == 0
    assert counts(auth_client, world.b_id)[2] == 0


# --- information ------------------------------------------------------------------------------------------

def test_without_read_deploy_the_bindings_are_counted_but_not_named(app, auth_client, world):
    bind(app, world.leaf_id, f'cross:{world.xid}')
    key = _key_with(auth_client, ['read:cas', 'read:certificates'])
    r = app.test_client().get(f'/api/v2/cas/{world.a_id}/chain-usage', headers={'X-API-Key': key})
    d = r.get_json()['data']['deployments']
    assert r.status_code == 200 and d['count'] == 1 and d['items'] == [] and d['truncated'] is False
    key = _key_with(auth_client, ['read:cas', 'read:certificates', 'read:deploy'])
    r = app.test_client().get(f'/api/v2/cas/{world.a_id}/chain-usage', headers={'X-API-Key': key})
    d = r.get_json()['data']['deployments']
    assert d['count'] == 1 and d['items'][0]['target']


# --- states the first tests left unpinned ---------------------------------------------------------------

def test_archived_certificates_are_excluded(app, auth_client, world):
    add_leaf(app, world.int_refid, archived=True)
    assert counts(auth_client, world.b_id)[0] == 1


def test_a_row_without_certificate_is_excluded(app, auth_client, world):
    add_leaf(app, world.int_refid, crt=None)
    assert counts(auth_client, world.b_id)[0] == 1


def test_a_certificate_without_expiry_is_included_and_listed_last(app, auth_client, world):
    nid = add_leaf(app, world.int_refid, valid_to=None)
    items = usage(auth_client, world.b_id)['issued']['items']
    assert [i['id'] for i in items] == [world.leaf_id, nid] and items[-1]['valid_to'] is None


def test_an_empty_full_chain_path_is_ignored(app, auth_client, world):
    bind(app, world.leaf_id, f'cross:{world.xid}', fullchain='')
    assert counts(auth_client, world.a_id)[2] == 0


def test_case3_only_bindings_of_the_ca_are_counted(app, auth_client, world):
    other = build_world(app, auth_client)
    bind(app, other.leaf_id, 'primary', include_root=True)
    assert counts(auth_client, world.b_id)[2] == 0
    assert counts(auth_client, other.b_id)[2] == 1


def _drop_cas(app, ids):
    with app.app_context():
        db.session.rollback()
        CA.query.filter(CA.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()


def test_certificates_below_a_record_of_the_same_key_count_for_the_ca(app, auth_client, world):
    with app.app_context():
        a = db.session.get(CA, world.a_id)
        twin = CA(refid=uuid.uuid4().hex, descr='twin of A', crt=a.crt, subject=a.subject, issuer=a.issuer)
        db.session.add(twin)
        db.session.flush()
        child = CA(refid=uuid.uuid4().hex, descr='below twin', caref=twin.refid, crt='')
        db.session.add(child)
        db.session.commit()
        child_ref, made = child.refid, [twin.id, child.id]
    try:
        add_leaf(app, child_ref)
        assert counts(auth_client, world.a_id)[0] == 1
    finally:
        _drop_cas(app, made)


def test_a_cross_issued_by_a_ca_without_certificate_counts_for_it(app, auth_client, world):
    set_served(auth_client, world, True)
    with app.app_context():
        pending = CA(refid=uuid.uuid4().hex, descr='pending issuer', crt='')
        db.session.add(pending)
        db.session.commit()
        pid, pref = pending.id, pending.refid
    cross_row(app, world.xid, issuer_caref=pref)
    try:
        assert counts(auth_client, pid)[1] == 1
    finally:
        _drop_cas(app, [pid])


def test_reading_the_usage_logs_nothing_about_deployments(app, auth_client, world, caplog):
    bind(app, world.leaf_id, f'cross:{world.xid}')
    cross_row(app, world.xid, revoked=True)
    with caplog.at_level('WARNING'):
        usage(auth_client, world.a_id)
    assert not [r for r in caplog.records if r.getMessage().startswith('Deploy:')]

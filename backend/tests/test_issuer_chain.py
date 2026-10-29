"""issuer_chain and chain_variants: one substitution per chain, never a stale cross-certificate (#400)."""
from datetime import timedelta

import pytest
from cryptography import x509

from models import CA, db
from models.ca_cross_certificate import CACrossCertificate
from tests.fixtures.cross_pki import make_cert, new_key, openssl_verify, pem
from tests.fixtures.cross_world import build_world, set_served
from utils.ca_chain import (ChainVariantError, anchor_chain, chain_variants, issuer_chain, parse_variant,
                            variant_ids)
from utils.datetime_utils import utc_now


@pytest.fixture
def world(app, auth_client):
    return build_world(app, auth_client)


def _certs(links):
    return [x509.load_pem_x509_certificate(link.pem) for link in links]


def test_without_a_cross_certificate_the_chain_is_the_caref_walk(app, world):
    with app.app_context():
        links = issuer_chain(db.session.get(CA, world.int_id))
        assert [link.ca.id for link in links] == [world.int_id, world.b_id]
        assert all(link.cross is None for link in links)


def test_n_cross_certificates_give_n_plus_one_variants(app, auth_client, world):
    other = make_cert(world.pki.name_b, world.pki.key_b, f'Cross Root C {world.pki.tag}', new_key())
    r = auth_client.post(f'/api/v2/cas/{world.b_id}/cross-certificates', json={'certificate': pem(other)})
    assert r.status_code == 201, r.data
    with app.app_context():
        ids = [v['id'] for v in chain_variants(db.session.get(CA, world.int_id))]
        assert ids == ['primary', f'cross:{world.xid}', f"cross:{r.get_json()['data']['id']}"]


def test_a_cross_variant_replaces_the_root_with_the_cross_certificate_and_continues_with_its_issuer(app, world):
    pki = world.pki
    with app.app_context():
        links = issuer_chain(db.session.get(CA, world.int_id), f'cross:{world.xid}')
        certs = _certs(links)
        assert [c.subject.rfc4514_string() for c in certs] == [
            pki.int_b.subject.rfc4514_string(), pki.root_b.subject.rfc4514_string(),
            pki.root_a.subject.rfc4514_string()]
        assert links[1].cross.id == world.xid
        ok, out = openssl_verify(pki.leaf, [pki.root_a], certs[:-1])
        assert ok, out


def test_the_primary_variant_does_not_verify_under_the_other_root(app, world):
    pki = world.pki
    with app.app_context():
        certs = _certs(issuer_chain(db.session.get(CA, world.int_id), 'primary'))
        assert openssl_verify(pki.leaf, [pki.root_b], certs[:-1])[0]
        assert not openssl_verify(pki.leaf, [pki.root_a], certs[:-1])[0]


def test_auto_follows_the_served_flag(app, auth_client, world):
    with app.app_context():
        assert [l.cross for l in issuer_chain(db.session.get(CA, world.int_id))] == [None, None]
    set_served(auth_client, world, True)
    with app.app_context():
        start = db.session.get(CA, world.int_id)
        assert [l.ca.id for l in issuer_chain(start)] == [world.int_id, world.b_id, world.a_id]
        defaults = [v['id'] for v in chain_variants(start) if v['default']]
        assert defaults == [f'cross:{world.xid}']
    set_served(auth_client, world, False)
    with app.app_context():
        assert [v['id'] for v in chain_variants(db.session.get(CA, world.int_id)) if v['default']] == ['primary']


@pytest.mark.parametrize('spoil', ['expired', 'revoked'])
def test_auto_never_picks_an_expired_or_revoked_cross_certificate(app, auth_client, world, spoil):
    set_served(auth_client, world, True)
    with app.app_context():
        row = db.session.get(CACrossCertificate, world.xid)
        if spoil == 'expired':
            row.valid_to = utc_now() - timedelta(days=1)
        else:
            row.revoked = True
        db.session.commit()
        start = db.session.get(CA, world.int_id)
        assert all(link.cross is None for link in issuer_chain(start))
        # an explicit choice still gets it: it stays exportable
        assert issuer_chain(start, f'cross:{world.xid}')[1].cross.id == world.xid


def test_include_root_false_drops_the_self_signed_top_of_either_chain(app, world):
    with app.app_context():
        start = db.session.get(CA, world.int_id)
        assert [l.ca.id for l in issuer_chain(start, 'primary', include_root=False)] == [world.int_id]
        assert [l.ca.id for l in issuer_chain(start, f'cross:{world.xid}', include_root=False)] == [
            world.int_id, world.b_id]


def test_a_cross_certificate_whose_issuer_is_not_held_ends_the_chain(app, auth_client, world):
    with app.app_context():
        db.session.delete(db.session.get(CA, world.a_id))
        db.session.commit()
        links = issuer_chain(db.session.get(CA, world.int_id), f'cross:{world.xid}')
        assert [l.cross is not None for l in links] == [False, True]


def test_a_cross_certificate_issued_by_its_own_descendant_does_not_loop(app, world):
    with app.app_context():
        row = db.session.get(CACrossCertificate, world.xid)
        row.issuer_caref = world.int_refid
        db.session.commit()
        links = issuer_chain(db.session.get(CA, world.int_id), f'cross:{world.xid}')
        assert [l.ca.id for l in links] == [world.int_id, world.b_id]


def test_only_the_nearest_served_cross_certificate_replaces_a_ca(app, auth_client, world):
    set_served(auth_client, world, True)
    other = make_cert(f'Cross Int B {world.pki.tag}', world.pki.key_int, f'Cross Root D {world.pki.tag}', new_key(), path_length=0)
    r = auth_client.post(f'/api/v2/cas/{world.int_id}/cross-certificates',
                         json={'certificate': pem(other), 'served': True})
    assert r.status_code == 201, r.data
    with app.app_context():
        links = issuer_chain(db.session.get(CA, world.int_id))
        assert [(l.ca.id, l.cross is not None) for l in links] == [(world.int_id, True)]
        both = [v['id'] for v in chain_variants(db.session.get(CA, world.int_id))]
        assert len(both) == 3


@pytest.mark.parametrize('bad', ['', 'cross:', 'cross:x', 'cross:-1', 'Cross:1', 'cross:1:2', 5, ['auto']])
def test_a_malformed_variant_is_refused(bad):
    if bad == '':
        assert parse_variant(bad) == 'auto'
        return
    with pytest.raises(ChainVariantError):
        parse_variant(bad)


def test_a_variant_outside_the_chain_is_refused(app, world):
    with app.app_context():
        with pytest.raises(ChainVariantError):
            issuer_chain(db.session.get(CA, world.int_id), 'cross:999999')
        assert 'cross:999999' not in variant_ids(db.session.get(CA, world.int_id))


def test_anchor_chain_adds_the_served_cross_certificate_and_keeps_every_primary_certificate(app, auth_client, world):
    set_served(auth_client, world, True)
    with app.app_context():
        links = anchor_chain(db.session.get(CA, world.int_id))
        assert [(l.ca.id, l.cross is not None) for l in links] == [
            (world.int_id, False), (world.b_id, False), (world.b_id, True)]

"""ACME server: the default chain follows the served cross-certificate, the other chains are RFC 8555 7.4.2 alternates (#400)."""
import json
import re
from datetime import timedelta

import pytest
from cryptography import x509

from models import db
from models.acme_models import AcmeAccount, AcmeOrder
from models.ca_cross_certificate import CACrossCertificate
from tests.fixtures.cross_pki import openssl_verify, pem
from tests.fixtures.cross_world import build_world, set_served
from tests.test_acme_security_paths import _build_jws, _gen_key_and_jwk, _nonce, _thumbprint
from tests.test_cross_chain_paths import _der, _loads
from utils.datetime_utils import utc_now

BASE = 'http://localhost'


@pytest.fixture
def world(app, auth_client):
    return build_world(app, auth_client)


def _account(app, status='valid'):
    key, jwk = _gen_key_and_jwk()
    with app.app_context():
        acct = AcmeAccount(jwk=json.dumps(jwk), jwk_thumbprint=_thumbprint(jwk), status=status)
        db.session.add(acct)
        db.session.commit()
        return {'key': key, 'jwk': jwk, 'id': acct.account_id}


@pytest.fixture
def order(app, world):
    acct = _account(app)
    with app.app_context():
        row = AcmeOrder(account_id=acct['id'], status='valid', certificate_id=world.leaf_id,
                        identifiers=json.dumps([{'type': 'dns', 'value': 'leaf.example'}]))
        db.session.add(row)
        db.session.commit()
        return {'id': row.order_id, 'acct': acct}


def _fetch(client, acct, path, *, url=None, payload=None, jwk_only=False):
    url = url or f'{BASE}{path}'
    kid = None if jwk_only else f'{BASE}/acme/acct/{acct["id"]}'
    jws = _build_jws(url, payload, acct['key'], jwk=acct['jwk'], kid=kid, nonce=_nonce(client))
    return client.post(path, data=json.dumps(jws), content_type='application/jose+json')


def _links(response):
    return [m for h in response.headers.getlist('Link')
            for m in re.findall(r'<([^>]+)>;\s*rel="([^"]+)"', h)]


def _alternates(response):
    return [url for url, rel in _links(response) if rel == 'alternate']


def _chain(response):
    return [_der(c) for c in _loads(response.data)]


def test_default_chain_is_the_primary_one_and_the_cross_chain_is_the_alternate(client, world, order):
    r = _fetch(client, order['acct'], f'/acme/cert/{order["id"]}')
    assert r.status_code == 200, r.data
    pki = world.pki
    assert _chain(r) == [_der(pki.leaf), _der(pki.int_b), _der(pki.root_b)]
    assert _alternates(r) == [f'{BASE}/acme/cert/{order["id"]}/alt/cross:{world.xid}']
    assert (f'{BASE}/acme/directory', 'index') in _links(r)


def test_serving_the_cross_certificate_swaps_default_and_alternate_with_stable_ids(app, auth_client, client, world, order):
    set_served(auth_client, world, True)
    r = _fetch(client, order['acct'], f'/acme/cert/{order["id"]}')
    pki = world.pki
    assert _chain(r) == [_der(pki.leaf), _der(pki.int_b), _der(pki.cross_b), _der(pki.root_a)]
    assert _alternates(r) == [f'{BASE}/acme/cert/{order["id"]}/alt/primary']


def test_an_alternate_verifies_against_the_root_it_leads_to(client, world, order):
    pki = world.pki
    r = _fetch(client, order['acct'], f'/acme/cert/{order["id"]}/alt/cross:{world.xid}')
    assert r.status_code == 200, r.data
    assert r.headers['Content-Type'] == 'application/pem-certificate-chain'
    assert _chain(r) == [_der(pki.leaf), _der(pki.int_b), _der(pki.cross_b), _der(pki.root_a)]
    ok, out = openssl_verify(pki.leaf, [pki.root_a], untrusted=[pki.int_b, pki.cross_b])
    assert ok, out
    ok, _ = openssl_verify(pki.leaf, [pki.root_a], untrusted=[pki.int_b, pki.root_b])
    assert not ok
    primary = _fetch(client, order['acct'], f'/acme/cert/{order["id"]}/alt/primary')
    assert _chain(primary) == [_der(pki.leaf), _der(pki.int_b), _der(pki.root_b)]


@pytest.mark.parametrize('mutation', ['revoked', 'expired'])
def test_a_cross_certificate_that_cannot_be_served_is_neither_offered_nor_fetchable(
        app, auth_client, client, world, order, mutation):
    if mutation == 'revoked':
        r = auth_client.post(f'/api/v2/cas/{world.b_id}/cross-certificates/{world.xid}/revoke', json={})
        assert r.status_code == 200, r.data
    else:
        with app.app_context():
            db.session.get(CACrossCertificate, world.xid).valid_to = utc_now() - timedelta(days=1)
            db.session.commit()
    assert _alternates(_fetch(client, order['acct'], f'/acme/cert/{order["id"]}')) == []
    r = _fetch(client, order['acct'], f'/acme/cert/{order["id"]}/alt/cross:{world.xid}')
    assert r.status_code == 404


@pytest.mark.parametrize('variant', ['auto', 'cross:999999', 'cross:x', 'nonsense'])
def test_an_unknown_variant_is_not_found(client, world, order, variant):
    r = _fetch(client, order['acct'], f'/acme/cert/{order["id"]}/alt/{variant}')
    assert r.status_code == 404, r.data


class TestAlternateSecurity:
    """The six checks the main certificate route makes, on the alternate route."""

    def _path(self, world, order):
        return f'/acme/cert/{order["id"]}/alt/cross:{world.xid}'

    def test_get_is_refused(self, client, world, order):
        assert client.get(self._path(world, order)).status_code in (404, 405)

    def test_missing_jws(self, client, world, order):
        r = client.post(self._path(world, order), data='{}', content_type='application/jose+json')
        assert r.status_code == 400 and r.get_json()['type'].endswith(':malformed')

    def test_non_empty_payload(self, client, world, order):
        r = _fetch(client, order['acct'], self._path(world, order), payload={'a': 1})
        assert r.status_code == 400 and r.get_json()['type'].endswith(':malformed')

    def test_account_key_required_not_a_bare_jwk(self, client, world, order):
        r = _fetch(client, order['acct'], self._path(world, order), jwk_only=True)
        assert r.status_code == 403 and b'BEGIN CERTIFICATE' not in r.data

    def test_another_account_cannot_read_the_order(self, app, client, world, order):
        r = _fetch(client, _account(app), self._path(world, order))
        assert r.status_code == 403 and r.get_json()['type'].endswith(':unauthorized')

    def test_a_deactivated_account_is_refused(self, app, client, world, order):
        with app.app_context():
            AcmeAccount.query.filter_by(account_id=order['acct']['id']).one().status = 'deactivated'
            db.session.commit()
        r = _fetch(client, order['acct'], self._path(world, order))
        assert r.status_code == 401 and b'BEGIN CERTIFICATE' not in r.data

    def test_the_jws_must_name_the_exact_url(self, client, world, order):
        path = self._path(world, order)
        for wrong in (f'{BASE}/acme/cert/{order["id"]}', f'{BASE}/acme/cert/{order["id"]}/alt/primary'):
            r = _fetch(client, order['acct'], path, url=wrong)
            assert r.status_code == 400 and b'BEGIN CERTIFICATE' not in r.data, wrong

    def test_the_main_route_refuses_a_jws_signed_for_an_alternate(self, client, world, order):
        r = _fetch(client, order['acct'], f'/acme/cert/{order["id"]}', url=f'{BASE}{self._path(world, order)}')
        assert r.status_code == 400

    def test_a_bad_signature_is_refused(self, client, world, order):
        other = _gen_key_and_jwk()[0]
        forged = dict(order['acct'], key=other)
        r = _fetch(client, forged, self._path(world, order))
        assert r.status_code == 400 and b'BEGIN CERTIFICATE' not in r.data

    def test_an_order_that_is_not_valid_has_no_alternate(self, app, client, world, order):
        with app.app_context():
            AcmeOrder.query.filter_by(order_id=order['id']).one().status = 'processing'
            db.session.commit()
        r = _fetch(client, order['acct'], self._path(world, order))
        assert r.status_code == 403 and r.get_json()['type'].endswith(':orderNotReady')

    def test_an_unknown_order_is_not_found(self, client, world, order):
        r = _fetch(client, order['acct'], f'/acme/cert/nope/alt/cross:{world.xid}')
        assert r.status_code == 404

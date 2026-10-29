"""An intermediate re-signed after a root rollover replaces its certificate; a real cross-certificate is refused (#400).

The refusal depends on the issuer's DN: the same DN under a new key is a rollover,
another DN is another hierarchy. Both routes judge alike, and a real revocation in
the chain (not a loop) lets the intermediate be replaced.
"""
import base64
import json

import pytest
from cryptography import x509

from models import CA, db
from tests.test_ca_external_csr import (
    _create_external, _make_external_root, _next_cn, _sign_csr_as_external_root, post_json,
)
from tests.test_ca_external_cross_offer import _active_under, _crt

BASE = '/api/v2/cas'


def _serial(pem):
    return x509.load_pem_x509_certificate(pem.encode()).serial_number


def _stored_serial(app, ca_id):
    return x509.load_pem_x509_certificate(base64.b64decode(_crt(app, ca_id))).serial_number


def _via_certificate(client, ca_id, pem, **extra):
    return post_json(client, f'{BASE}/{ca_id}/certificate', {'pem_content': pem, **extra})


def _via_import(client, ca_id, pem, **extra):
    return client.post(f'{BASE}/import', data={'pem_content': pem, **extra}, content_type='multipart/form-data')


ROUTES = pytest.mark.parametrize('route', [_via_certificate, _via_import], ids=['certificate', 'import'])


@pytest.fixture
def intermediate(auth_client):
    cn = _next_cn('Roll')
    key_a, cert_a = _make_external_root(cn=cn)
    ca_id, csr, _ = _active_under(auth_client, key_a, cert_a)
    return ca_id, csr, cn


@ROUTES
def test_a_root_rollover_replaces_the_certificate(app, auth_client, intermediate, route):
    ca_id, csr, cn = intermediate
    key_new, cert_new = _make_external_root(cn=cn)
    resigned = _sign_csr_as_external_root(csr, key_new, cert_new, days=200)
    r = route(auth_client, ca_id, resigned)
    assert r.status_code in (200, 201), r.data
    assert _stored_serial(app, ca_id) == _serial(resigned)


@ROUTES
def test_another_issuer_name_is_refused_with_both_options(app, auth_client, intermediate, route):
    ca_id, csr, _ = intermediate
    key_b, cert_b = _make_external_root(cn=_next_cn('RollOther'))
    before = _crt(app, ca_id)
    other = _sign_csr_as_external_root(csr, key_b, cert_b, days=200)
    r = route(auth_client, ca_id, other)
    assert r.status_code == 409, r.data
    details = json.loads(r.data)['details']
    assert details['code'] == 'cross_certificate_detected' and details['options'] == ['attach', 'replace']
    assert _crt(app, ca_id) == before


@ROUTES
def test_a_revoked_ancestor_lets_another_issuer_replace_the_certificate(app, auth_client, route):
    key_a, cert_a = _make_external_root(cn=_next_cn('RollRev'))
    parent = _import_parent(auth_client, cert_a)
    ca_id, csr, _ = _active_under(auth_client, key_a, cert_a)
    with app.app_context():
        db.session.get(CA, parent).revoked = True
        db.session.commit()
        assert db.session.get(CA, ca_id).chain_revocation == 'revoked'
    key_b, cert_b = _make_external_root(cn=_next_cn('RollRevB'))
    other = _sign_csr_as_external_root(csr, key_b, cert_b, days=200)
    r = route(auth_client, ca_id, other)
    assert r.status_code in (200, 201), r.data
    assert _stored_serial(app, ca_id) == _serial(other)


@ROUTES
def test_a_looping_chain_is_not_a_revocation(app, auth_client, intermediate, monkeypatch, route):
    ca_id, csr, _ = intermediate
    monkeypatch.setattr(CA, 'chain_revocation', property(lambda self: 'broken'))
    key_b, cert_b = _make_external_root(cn=_next_cn('RollLoop'))
    other = _sign_csr_as_external_root(csr, key_b, cert_b, days=200)
    assert route(auth_client, ca_id, other).status_code == 409


def _import_parent(auth_client, cert):
    from tests.test_ca_external_csr import _import_root_cert_only
    return _import_root_cert_only(auth_client, cert)['id']


@pytest.mark.parametrize('mode', ['attach', 'refuse', 'nope'])
def test_the_certificate_route_takes_auto_or_replace_only(app, auth_client, intermediate, mode):
    ca_id, csr, cn = intermediate
    key_new, cert_new = _make_external_root(cn=cn)
    before = _crt(app, ca_id)
    r = _via_certificate(auth_client, ca_id, _sign_csr_as_external_root(csr, key_new, cert_new), cross_mode=mode)
    assert r.status_code == 400 and 'auto or replace' in json.loads(r.data)['message']
    assert _crt(app, ca_id) == before

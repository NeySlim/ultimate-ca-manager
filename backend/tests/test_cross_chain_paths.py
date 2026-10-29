"""Every consumer that presents a chain follows the served cross-certificate; anchor bags and SCEP do not (#400)."""
import base64
import json
import re
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12, pkcs7

from models import CA, Certificate, SystemConfig, db
from tests.fixtures.cross_pki import openssl_verify, pem
from tests.fixtures.cross_world import admin_enrolment, build_world, set_served

PEM_BLOCK = re.compile(rb'-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----', re.S)


def _loads(blob):
    return [x509.load_pem_x509_certificate(m.group(0)) for m in PEM_BLOCK.finditer(blob)]


def _der(cert):
    return cert.public_bytes(serialization.Encoding.DER)


def _chain_order(certs, w):
    """PKCS#7 sorts its certificate set: put the certificates back in chain order."""
    order = [_der(c) for c in (w.pki.leaf, w.pki.int_b, w.pki.cross_b, w.pki.root_b, w.pki.root_a)]
    return sorted(certs, key=lambda c: order.index(_der(c)))


def _without(certs, *excluded):
    drop = {_der(c) for c in excluded}
    return [c for c in certs if _der(c) not in drop]


# --- consumers: each returns the chain certificates a relying party receives, the leaf and Int B excluded ---

def ca_service(app, client, w):
    from services.ca_service import CAService
    with app.app_context():
        return _loads(b''.join(CAService.get_ca_chain(w.int_id)))


def est_enroll(app, client, w):
    from api.est_protocol import _certs_only_response
    with app.app_context():
        db.session.add(SystemConfig(key='est_response_include_chain', value='true'))
        db.session.commit()
        try:
            ca = db.session.get(CA, w.int_id)
            body = _certs_only_response(w.pki.leaf, ca).get_data()
            return _chain_order(pkcs7.load_der_pkcs7_certificates(base64.b64decode(body)), w)
        finally:
            SystemConfig.query.filter_by(key='est_response_include_chain').delete()
            db.session.commit()


def wstep_cmc(app, client, w):
    from api.wstep_protocol import _cmc_response_der_for
    with app.app_context():
        ca = db.session.get(CA, w.int_id)
        blob = _cmc_response_der_for(ca, w.pki.leaf, SimpleNamespace(was_pkcs7_wrapped=True, cmc_body_part_id=1))
    assert blob
    return [c for c in (w.pki.cross_b, w.pki.root_b, w.pki.root_a, w.pki.int_b) if _der(c) in blob]


def tsa(app, client, w):
    from services.tsa_service import _load_issuer_chain
    with app.app_context():
        return _load_issuer_chain(w.int_refid)


def https_file(app, client, w):
    from services.https_binding import with_ca_chain
    with app.app_context():
        cert = db.session.get(Certificate, w.leaf_id)
        return _loads(with_ca_chain(cert, pem(w.pki.leaf)).encode())


def https_materialized(app, client, w, tmp_path=None):
    import services.https_binding as https_binding
    with app.app_context():
        cert = db.session.get(Certificate, w.leaf_id)
        written = {}
        original = (https_binding._paths, https_binding.os.chmod)
        out = __import__('pathlib').Path(__import__('tempfile').mkdtemp())
        https_binding._paths = lambda: (out / 'cert.pem', out / 'key.pem')
        https_binding.os.chmod = lambda *a, **k: None
        try:
            https_binding.materialize_https_cert(cert)
            written = (out / 'cert.pem').read_bytes()
        finally:
            https_binding._paths, https_binding.os.chmod = original
        return _loads(written)


def cert_export_pem(app, client, w):
    r = client.get(f'/api/v2/certificates/{w.leaf_id}/export?format=pem&include_chain=true&include_root=true')
    assert r.status_code == 200, r.data
    return _loads(r.data)


def cert_export_p7b(app, client, w):
    r = client.post(f'/api/v2/certificates/{w.leaf_id}/export',
                    json={'format': 'p7b', 'include_chain': True, 'include_root': True})
    assert r.status_code == 200, r.data
    return _chain_order(pkcs7.load_der_pkcs7_certificates(r.data), w)


def cert_export_p12(app, client, w):
    r = client.post(f'/api/v2/certificates/{w.leaf_id}/export',
                    json={'format': 'pkcs12', 'include_chain': True, 'include_root': True,
                          'password': 'Sup3r-secret-pw!'})
    assert r.status_code == 200, r.data
    return list(pkcs12.load_key_and_certificates(r.data, b'Sup3r-secret-pw!')[2])


def deploy_fullchain(app, client, w):
    from models import DeployBinding
    from services.deploy.service import DeployService
    with app.app_context():
        binding = DeployBinding(fullchain_path='/srv/fullchain.pem', include_root=True, chain_variant='auto')
        files = DeployService.resolve_files(binding, db.session.get(Certificate, w.leaf_id))
    return _loads(files[0][1])


def user_cert_export(app, client, w):
    with admin_enrolment(app, w.pki.leaf) as auth_id:
        r = client.get(f'/api/v2/user-certificates/{auth_id}/export?format=pem&include_chain=true&include_root=true')
    assert r.status_code == 200, r.data
    return _loads(r.data)


def ca_export(app, client, w):
    r = client.post(f'/api/v2/cas/{w.int_id}/export', json={'format': 'pem', 'include_chain': True})
    assert r.status_code == 200, r.data
    return _loads(r.data)


def acme_cert(app, client, w):
    from api.acme import acme_api
    service = SimpleNamespace(base_url='https://ca.example', generate_nonce=lambda: 'n',
                              get_order=lambda order_id: SimpleNamespace(
                                  account_id='acct', status='valid', certificate_id=w.leaf_id))
    saved = (acme_api.get_acme_service, acme_api.verify_jws, acme_api._account_id_from_jws)
    acme_api.get_acme_service = lambda: service
    acme_api.verify_jws = lambda body, url: (True, None, {}, None)
    acme_api._account_id_from_jws = lambda body: 'acct'
    try:
        r = client.post('/acme/cert/order1', data=json.dumps({'payload': ''}), content_type='application/jose+json')
    finally:
        acme_api.get_acme_service, acme_api.verify_jws, acme_api._account_id_from_jws = saved
    assert r.status_code == 200, r.data
    return _loads(r.data)


def key_recovery(app, client, w):
    r = client.post(f'/api/v2/certificates/{w.leaf_id}/key-recovery', json={'reason': 'chain test'})
    assert r.status_code == 201, r.data
    rid = r.get_json()['data']['id']
    with app.app_context():
        row = SystemConfig.query.filter_by(key='key_recovery_dual_control').first()
        if row is None:
            db.session.add(SystemConfig(key='key_recovery_dual_control', value='false'))
        else:
            row.value = 'false'
        db.session.commit()
    assert client.post(f'/api/v2/key-recovery/{rid}/approve', json={}).status_code == 200
    r = client.post(f'/api/v2/key-recovery/{rid}/recover', json={'password': 'Sup3r-secret-pw!'})
    assert r.status_code == 200, r.data
    return list(pkcs12.load_key_and_certificates(r.data, b'Sup3r-secret-pw!')[2])


CONSUMERS = [ca_service, est_enroll, wstep_cmc, tsa, https_file, https_materialized, cert_export_pem,
             cert_export_p7b, cert_export_p12, deploy_fullchain, user_cert_export, ca_export, acme_cert,
             key_recovery]


@pytest.fixture
def world(app, auth_client):
    return build_world(app, auth_client)


def _presented(consumer, app, client, w):
    return _without(consumer(app, client, w), w.pki.leaf, w.pki.int_b)


@pytest.mark.parametrize('consumer', CONSUMERS, ids=lambda f: f.__name__)
def test_the_unserved_chain_ends_at_the_self_signed_root_b(consumer, app, auth_client, world):
    certs = _presented(consumer, app, auth_client, world)
    assert [_der(c) for c in certs] == [_der(world.pki.root_b)]


@pytest.mark.parametrize('consumer', CONSUMERS, ids=lambda f: f.__name__)
def test_a_served_cross_certificate_replaces_root_b_and_leads_to_root_a(consumer, app, auth_client, world):
    set_served(auth_client, world, True)
    certs = _presented(consumer, app, auth_client, world)
    assert [_der(c) for c in certs] == [_der(world.pki.cross_b), _der(world.pki.root_a)]
    ok, out = openssl_verify(world.pki.leaf, [world.pki.root_a], [world.pki.int_b, *certs[:-1]])
    assert ok, out


@pytest.mark.parametrize('consumer', CONSUMERS, ids=lambda f: f.__name__)
def test_an_expired_served_cross_certificate_is_not_presented(consumer, app, auth_client, world):
    from datetime import timedelta
    from models.ca_cross_certificate import CACrossCertificate
    from utils.datetime_utils import utc_now
    set_served(auth_client, world, True)
    with app.app_context():
        db.session.get(CACrossCertificate, world.xid).valid_to = utc_now() - timedelta(days=1)
        db.session.commit()
    certs = _presented(consumer, app, auth_client, world)
    assert [_der(c) for c in certs] == [_der(world.pki.root_b)]


def test_the_certificate_detail_chain_goes_through_the_served_cross_certificate(app, auth_client, world):
    r = auth_client.get(f'/api/v2/certificates/{world.leaf_id}')
    assert r.status_code == 200
    status = r.get_json()['data']['chain_status']
    assert [n['name'] for n in status['chain']] == [world.pki.int_b.subject.rfc4514_string()[3:],
                                                     world.pki.name_b]
    assert status['status'] == 'complete' and status['trust_anchor'] == world.pki.name_b
    assert [v['id'] for v in status['variants']] == ['primary', f'cross:{world.xid}']
    set_served(auth_client, world, True)
    status = auth_client.get(f'/api/v2/certificates/{world.leaf_id}').get_json()['data']['chain_status']
    assert [n['name'] for n in status['chain']] == [world.pki.int_b.subject.rfc4514_string()[3:],
                                                     world.pki.name_b, world.pki.name_a]
    assert status['trust_anchor'] == world.pki.name_a
    assert [v['id'] for v in status['variants'] if v['default']] == [f'cross:{world.xid}']


# --- anchor bags and SCEP -----------------------------------------------------------------------------------

def _set_config(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if row is None:
        db.session.add(SystemConfig(key=key, value=value))
    else:
        row.value = value
    db.session.commit()


@pytest.fixture
def est_on(app, world):
    with app.app_context():
        previous = {k: (r.value if (r := SystemConfig.query.filter_by(key=k).first()) else None)
                    for k in ('est_enabled', 'est_ca_refid')}
        _set_config('est_enabled', 'true')
        _set_config('est_ca_refid', world.int_refid)
    yield
    with app.app_context():
        for key, value in previous.items():
            if value is None:
                SystemConfig.query.filter_by(key=key).delete()
            else:
                _set_config(key, value)
        db.session.commit()


def _est_cacerts(client, w):
    r = client.get('/.well-known/est/cacerts')
    assert r.status_code == 200, r.data
    return _chain_order(pkcs7.load_der_pkcs7_certificates(base64.b64decode(r.data)), w)


def test_est_cacerts_lists_the_primary_chain_alone_when_no_cross_certificate_is_served(auth_client, world, est_on):
    assert [_der(c) for c in _est_cacerts(auth_client, world)] == [_der(world.pki.int_b), _der(world.pki.root_b)]


def test_est_cacerts_adds_the_served_cross_certificate_and_never_substitutes_it(auth_client, world, est_on):
    set_served(auth_client, world, True)
    assert [_der(c) for c in _est_cacerts(auth_client, world)] == [
        _der(world.pki.int_b), _der(world.pki.cross_b), _der(world.pki.root_b)]


def test_est_cacerts_never_adds_an_expired_cross_certificate(app, auth_client, world, est_on):
    from datetime import timedelta
    from models.ca_cross_certificate import CACrossCertificate
    from utils.datetime_utils import utc_now
    set_served(auth_client, world, True)
    with app.app_context():
        db.session.get(CACrossCertificate, world.xid).valid_to = utc_now() - timedelta(days=1)
        db.session.commit()
    assert [_der(c) for c in _est_cacerts(auth_client, world)] == [_der(world.pki.int_b), _der(world.pki.root_b)]


def test_scep_chain_and_ca_certificate_are_unchanged_by_a_served_cross_certificate(app, auth_client, world):
    from services.scep.scep_service import SCEPService
    from tests.fixtures.cross_pki import key_pem
    from utils.key_codec import store_pem_bytes
    set_served(auth_client, world, True)
    with app.app_context():
        db.session.get(CA, world.int_id).prv = store_pem_bytes(key_pem(world.pki.key_int).encode())
        db.session.commit()
        service = SCEPService(world.int_refid)
        assert [_der(c) for c in service.get_ca_chain()] == [_der(world.pki.int_b), _der(world.pki.root_b)]
        assert service.get_ca_cert() == _der(world.pki.int_b)


def test_mtls_boot_trust_is_unchanged_by_a_served_cross_certificate(app, auth_client, world):
    from boot_config import client_ca_chain
    from sqlalchemy import text

    class Database:
        def one(self, sql, params):
            return db.session.execute(text(sql.replace('?', ':p')), {'p': params[0]}).fetchone()

    set_served(auth_client, world, True)
    with app.app_context():
        chain, _ = client_ca_chain(Database(), world.int_refid)
        assert [_der(c) for c in _loads(chain.encode())] == [_der(world.pki.int_b), _der(world.pki.root_b)]

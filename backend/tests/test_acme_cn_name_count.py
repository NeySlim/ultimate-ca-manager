"""ACME: a DNS name carried by the CN alone counts against a policy's name limit.

RFC 8555 §7.4 lets a dns identifier appear in the CSR's commonName only. The
signing trunk counted the SAN's DNS names alone, so an order whose extra name
sat in the CN was issued past ``max_dns_names``. Driven through the ACME routes:
newOrder, authorizations made valid as the other ACME tests do, finalize.
"""
import base64 as b64
import ipaddress
import json
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from models import Certificate, CertificatePolicy, db
from models.acme_models import AcmeAccount, AcmeLocalDomain, AcmeOrder
from tests.test_acme_server_rfc_conformance import _b64u, _new_account, _signed

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')

IP = '192.0.2.77'


@pytest.fixture(scope='module', autouse=True)
def _drop_the_rows_of_this_module(app):
    """The orders and accounts these tests create leave with the module."""
    models = (AcmeOrder, AcmeAccount)
    with app.app_context():
        floors = {m: db.session.query(db.func.coalesce(db.func.max(m.id), 0)).scalar() for m in models}
    yield
    with app.app_context():
        for model in models:
            for row in model.query.filter(model.id > floors[model]).all():
                db.session.delete(row)
            db.session.commit()


@pytest.fixture(autouse=True)
def _no_caa(monkeypatch):
    from utils import caa_checker
    monkeypatch.setattr(caa_checker, 'check_caa_for_domains', lambda *a, **k: (True, 'allowed'))


@pytest.fixture
def served(app, create_ca):
    """(account, ca_id, d, two-d): both names issued by a fresh CA limited to one DNS name."""
    ca = create_ca(cn=f'ACME CN count CA {uuid.uuid4().hex[:6]}')
    base = f'u{uuid.uuid4().hex[:10]}.example.com'
    d, two = f'd.{base}', f'two-d.{base}'
    with app.app_context():
        for name in (d, two):
            db.session.add(AcmeLocalDomain(domain=name, issuing_ca_id=ca['id']))
        policy = CertificatePolicy(name=f'acme-cn-count-{uuid.uuid4().hex[:6]}', policy_type='issuance',
                                   ca_id=ca['id'], requires_approval=False, min_approvers=1,
                                   is_active=True, priority=100)
        policy.set_rules({'san_restrictions': {'max_dns_names': 1}})
        db.session.add(policy)
        db.session.commit()
        policy_id = policy.id
    yield _new_account(app), ca['id'], d, two
    # Before the module drops the CA, which its local domains would hold
    with app.app_context():
        AcmeLocalDomain.query.filter(AcmeLocalDomain.domain.in_([d, two])).delete(
            synchronize_session=False)
        db.session.delete(db.session.get(CertificatePolicy, policy_id))
        db.session.commit()


def _new_order(app, client, account, identifiers):
    """newOrder through the route, then its authorizations valid: the order is ready."""
    r = _signed(client, account, '/acme/new-order', {'identifiers': identifiers})
    assert r.status_code == 201, r.get_data(as_text=True)
    order_id = r.headers['Location'].rstrip('/').split('/')[-1]
    with app.app_context():
        order = AcmeOrder.query.filter_by(order_id=order_id).one()
        for authz in order.authorizations:
            authz.status = 'valid'
            for challenge in authz.challenges:
                challenge.status = 'valid'
        order.status = 'ready'
        db.session.commit()
    return order_id


def _finalize(app, client, account, identifiers, cn, dns=(), ips=()):
    """(response, order as read back, certificate rows created) of one finalize."""
    order_id = _new_order(app, client, account, identifiers)
    key = ec.generate_private_key(ec.SECP256R1())
    names = [x509.DNSName(n) for n in dns] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
           .add_extension(x509.SubjectAlternativeName(names), critical=False)
           .sign(key, hashes.SHA256()))
    with app.app_context():
        before = Certificate.query.count()
    r = _signed(client, account, f'/acme/order/{order_id}/finalize',
                {'csr': _b64u(csr.public_bytes(serialization.Encoding.DER))})
    read = _signed(client, account, f'/acme/order/{order_id}', None).get_json()
    with app.app_context():
        created = Certificate.query.count() - before
    return r, read, created


def _issued_names(app, read):
    assert read['status'] == 'valid', read
    with app.app_context():
        order = AcmeOrder.query.filter_by(order_id=read['finalize'].rstrip('/').split('/')[-2]).one()
        row = db.session.get(Certificate, order.certificate_id)
        cert = x509.load_pem_x509_certificate(b64.b64decode(row.crt))
    return cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value


def _refusal(r, read, created):
    return (r.status_code, r.get_json().get('type'), read['status'],
            (read.get('error') or {}).get('type'), created)


def test_a_dns_name_carried_by_the_cn_alone_is_refused_as_a_san_overrun(app, client, served):
    """Order [d, two-d], one name allowed, CN=two-d and SAN=[d]: refused as the SAN would be."""
    account, _ca_id, d, two = served
    identifiers = [{'type': 'dns', 'value': d}, {'type': 'dns', 'value': two}]
    by_san = _finalize(app, client, account, identifiers, cn=two, dns=[d, two])
    by_cn = _finalize(app, client, account, identifiers, cn=two, dns=[d])
    assert _refusal(*by_cn) == _refusal(*by_san) == (
        400, 'urn:ietf:params:acme:error:badCSR', 'invalid', 'urn:ietf:params:acme:error:badCSR', 0)
    assert 'DNS names exceed' in by_cn[1]['error']['detail'], by_cn[1]
    with app.app_context():
        assert Certificate.query.filter(Certificate.subject_cn == two).count() == 0


def test_the_cn_is_compared_without_case_or_final_dot(app, client, served):
    """CN=Two-D. names the two-d of the SAN: one name, issued."""
    account, _ca_id, _d, two = served
    r, read, created = _finalize(app, client, account, [{'type': 'dns', 'value': two}],
                                 cn=two.replace('two-d', 'Two-D') + '.', dns=[two])
    assert r.status_code == 200, r.get_json()
    assert created == 1
    assert [n.value for n in _issued_names(app, read)] == [two]


def test_a_cn_repeating_the_san_is_not_counted_twice(app, client, served):
    account, _ca_id, d, _two = served
    r, read, created = _finalize(app, client, account, [{'type': 'dns', 'value': d}], cn=d, dns=[d])
    assert r.status_code == 200, r.get_json()
    assert created == 1
    assert [n.value for n in _issued_names(app, read)] == [d]


def test_an_ip_address_cn_is_not_a_dns_name(app, client, served):
    account, _ca_id, d, _two = served
    r, read, created = _finalize(app, client, account,
                                 [{'type': 'dns', 'value': d}, {'type': 'ip', 'value': IP}],
                                 cn=IP, dns=[d], ips=[IP])
    assert r.status_code == 200, r.get_json()
    assert created == 1
    san = _issued_names(app, read)
    assert san.get_values_for_type(x509.DNSName) == [d]

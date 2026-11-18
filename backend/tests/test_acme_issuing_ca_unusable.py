"""An ACME issuing CA that was chosen but cannot sign refuses the order.

A CA chosen for a domain, or as the default, that has no private key is never
replaced by another CA: the order is refused as a server error and nothing is
issued. Only when nothing was chosen does the first CA able to sign issue.
"""
import json
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from models import CA, Certificate, SystemConfig, db
from models.acme_models import AcmeAccount, AcmeDomain, AcmeLocalDomain, AcmeOrder, DnsProvider
from services.acme.acme_service import AcmeService

# drop_local_domains is torn down first: a mapping left behind would block the CA deletion
pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates', 'drop_local_domains')
_LOCAL_DOMAINS = []

KEY = 'acme.issuing_ca_id'
NO_KEY = 'has no private key'
_FORMS = {'refid': lambda ca: ca.refid, 'id': lambda ca: str(ca.id), 'padded': lambda ca: f' +0{ca.id} '}


@pytest.fixture(scope='module', autouse=True)
def _drop_the_orders_of_this_module(app):
    """The ACME orders and accounts these tests create leave with the module."""
    from models.acme_models import AcmeAccount, AcmeOrder
    with app.app_context():
        orders = db.session.query(db.func.coalesce(db.func.max(AcmeOrder.id), 0)).scalar()
        accounts = db.session.query(db.func.coalesce(db.func.max(AcmeAccount.id), 0)).scalar()
    yield
    with app.app_context():
        for row in AcmeOrder.query.filter(AcmeOrder.id > orders).all():
            db.session.delete(row)
        for row in AcmeAccount.query.filter(AcmeAccount.id > accounts).all():
            db.session.delete(row)
        db.session.commit()


@pytest.fixture(scope='module')
def drop_local_domains(app):
    yield
    with app.app_context():
        AcmeLocalDomain.query.filter(AcmeLocalDomain.domain.in_(_LOCAL_DOMAINS)).delete(
            synchronize_session=False)
        db.session.commit()


@pytest.fixture
def default_setting(app):
    """acme.issuing_ca_id as the test sets it, put back afterwards."""
    with app.app_context():
        row = SystemConfig.query.filter_by(key=KEY).first()
        before = None if row is None else row.value
    yield
    with app.app_context():
        row = SystemConfig.query.filter_by(key=KEY).first()
        if before is None:
            if row is not None:
                db.session.delete(row)
        else:
            row.value = before
        db.session.commit()


def _set_default(value):
    row = SystemConfig.query.filter_by(key=KEY).first()
    if row is None:
        db.session.add(SystemConfig(key=KEY, value=value))
    else:
        row.value = value
    db.session.commit()


def _drop_key(ca_id):
    ca = db.session.get(CA, ca_id)
    ca.prv = None
    ca.hsm_key_id = None
    db.session.commit()
    assert not ca.has_private_key
    return ca


def _domain():
    return f'w{uuid.uuid4().hex[:12]}.example.com'


def _finalize(monkeypatch, domain, **kwargs):
    """(success, error, service, order) of finalizing a fresh order for *domain*."""
    from utils import caa_checker
    monkeypatch.setattr(caa_checker, 'check_caa_for_domains', lambda *a, **k: (True, 'allowed'))
    acct = AcmeAccount(jwk='{}', jwk_thumbprint=uuid.uuid4().hex + uuid.uuid4().hex[:11], status='valid')
    db.session.add(acct)
    db.session.flush()
    order = AcmeOrder(account_id=acct.account_id, status='ready',
                      identifiers=json.dumps([{'type': 'dns', 'value': domain}]))
    db.session.add(order)
    db.session.commit()
    key = ec.generate_private_key(ec.SECP256R1())
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)]))
           .add_extension(x509.SubjectAlternativeName([x509.DNSName(domain)]), False)
           .sign(key, hashes.SHA256()))
    service = AcmeService(base_url='http://localhost')
    assert service.begin_order_processing(order)
    service._finalizing_order_id = order.order_id
    try:
        success, error = service.finalize_order(
            order.order_id, csr.public_bytes(serialization.Encoding.PEM).decode(), **kwargs)
    finally:
        service._finalizing_order_id = None
    db.session.refresh(order)
    return success, error, service, order


def _issuer_refid(order):
    return db.session.get(Certificate, order.certificate_id).caref


def _assert_refused(success, error, service, order, words):
    assert not success
    assert words in error, error
    # A server-side failure; the route puts the order back to ready (tested through the route below)
    assert service._last_finalize_error_type == 'serverInternal'
    assert order.status == 'processing' and order.certificate_id is None


def test_a_local_domain_ca_without_key_refuses_despite_a_valid_default(app, monkeypatch, create_ca,
                                                                        default_setting):
    valid = create_ca(cn='Valid ACME default')
    chosen = create_ca(cn='Local domain CA without key')
    domain = _domain()
    with app.app_context():
        _set_default(db.session.get(CA, valid['id']).refid)
        _drop_key(chosen['id'])
        _LOCAL_DOMAINS.append(domain)
        db.session.add(AcmeLocalDomain(domain=domain, issuing_ca_id=chosen['id']))
        db.session.commit()
        result = _finalize(monkeypatch, domain)
        _assert_refused(*result, words=NO_KEY)
        assert domain in result[1]


def test_a_dns_domain_ca_without_key_refuses_despite_a_valid_default(app, monkeypatch, create_ca,
                                                                      default_setting):
    valid = create_ca(cn='Valid ACME default for DNS')
    chosen = create_ca(cn='DNS domain CA without key')
    domain = _domain()
    with app.app_context():
        _set_default(db.session.get(CA, valid['id']).refid)
        _drop_key(chosen['id'])
        provider = DnsProvider(name=f'manual-{uuid.uuid4().hex[:8]}', provider_type='manual')
        db.session.add(provider)
        db.session.flush()
        mapping = AcmeDomain(domain=domain, dns_provider_id=provider.id, issuing_ca_id=chosen['id'])
        db.session.add(mapping)
        db.session.commit()
        try:
            result = _finalize(monkeypatch, domain)
            _assert_refused(*result, words=NO_KEY)
            assert domain in result[1]
        finally:
            db.session.delete(mapping)
            db.session.commit()
            db.session.delete(provider)
            db.session.commit()


@pytest.mark.parametrize('form', sorted(_FORMS))
def test_a_default_ca_without_key_refuses(app, monkeypatch, create_ca, default_setting, form):
    """Each form of the value names the keyless CA: the refusal says so, never 'no longer exists'."""
    create_ca(cn='A CA able to sign')
    chosen = create_ca(cn=f'Default ACME CA without key ({form})')
    with app.app_context():
        ca = _drop_key(chosen['id'])
        _set_default(_FORMS[form](ca))
        success, error, service, order = _finalize(monkeypatch, _domain())
        _assert_refused(success, error, service, order, words=NO_KEY)
        assert 'ACME settings' in error and 'no longer exists' not in error


def test_a_domain_choice_able_to_sign_wins_over_an_unusable_default(app, monkeypatch, create_ca,
                                                                     default_setting):
    chosen = create_ca(cn='Local domain CA able to sign')
    keyless = create_ca(cn='Default ACME CA without key, unused')
    domain = _domain()
    with app.app_context():
        _set_default(_drop_key(keyless['id']).refid)
        _LOCAL_DOMAINS.append(domain)
        db.session.add(AcmeLocalDomain(domain=domain, issuing_ca_id=chosen['id']))
        db.session.commit()
        success, error, _service, order = _finalize(monkeypatch, domain)
        assert success, error
        assert _issuer_refid(order) == db.session.get(CA, chosen['id']).refid


def test_nothing_chosen_signs_with_the_first_ca_able_to_sign(app, monkeypatch, create_ca, default_setting):
    """Today's behaviour kept: no domain mapping and no default, the lowest-numbered CA able to sign."""
    create_ca(cn='Some CA able to sign')
    with app.app_context():
        _set_default('')
        able = [c for c in CA.query.order_by(CA.id.asc())
                if c.has_private_key and c.crt and not c.offline and not c.revoked_in_chain]
        success, error, _service, order = _finalize(monkeypatch, _domain())
        assert success, error
        assert _issuer_refid(order) == able[0].refid


def test_the_refusal_issues_and_counts_nothing(app, monkeypatch, create_ca, default_setting):
    create_ca(cn='A CA that would have signed')
    chosen = create_ca(cn='Default ACME CA without key, counted')
    with app.app_context():
        _set_default(_drop_key(chosen['id']).refid)
        certificates = Certificate.query.count()
        counted = db.session.query(db.func.coalesce(db.func.sum(CA.serial), 0)).scalar()
        success, error, service, order = _finalize(monkeypatch, _domain())
        _assert_refused(success, error, service, order, words=NO_KEY)
        assert Certificate.query.count() == certificates
        assert db.session.query(db.func.coalesce(db.func.sum(CA.serial), 0)).scalar() == counted


def _finalize_by_route(app, client, monkeypatch, domain, caa=(True, 'allowed')):
    """(response, order_id) of a finalize sent to the ACME route for a ready order on *domain*."""
    from tests.test_acme_server_rfc_conformance import _b64u, _new_account, _ready_order, _signed
    from utils import caa_checker
    monkeypatch.setattr(caa_checker, 'check_caa_for_domains', lambda *a, **k: caa)
    acct = _new_account(app)
    order_id = _ready_order(app, acct, [{'type': 'dns', 'value': domain}])
    key = ec.generate_private_key(ec.SECP256R1())
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)]))
           .add_extension(x509.SubjectAlternativeName([x509.DNSName(domain)]), False)
           .sign(key, hashes.SHA256()))
    response = _signed(client, acct, f'/acme/order/{order_id}/finalize',
                       {'csr': _b64u(csr.public_bytes(serialization.Encoding.DER))})
    return response, order_id


def _assert_refused_by_route(app, response, order_id, cause):
    """serverInternal with a generic detail, the order ready again, the cause in the audit only."""
    from models import AuditLog
    assert response.status_code == 500, response.get_data(as_text=True)
    problem = response.get_json()
    assert problem['type'] == 'urn:ietf:params:acme:error:serverInternal'
    assert cause not in json.dumps(problem)
    with app.app_context():
        order = AcmeOrder.query.filter_by(order_id=order_id).one()
        assert order.status == 'ready' and order.certificate_id is None
        line = (AuditLog.query.filter_by(action='acme.order.finalize', resource_id=str(order_id))
                .order_by(AuditLog.id.desc()).first())
        assert line is not None and not line.success and cause in line.details, line and line.details


def test_the_finalize_route_answers_a_server_error_and_the_order_stays_ready(app, client, monkeypatch,
                                                                              create_ca, default_setting):
    """What UPGRADE.md says of the refusal: serverInternal, the order ready again, the cause audited
    and kept from the client."""
    chosen = create_ca(cn='Default CA without key, by the route')
    with app.app_context():
        _set_default(db.session.get(CA, chosen['id']).refid)
        _drop_key(chosen['id'])
        certificates = Certificate.query.count()
    response, order_id = _finalize_by_route(app, client, monkeypatch, _domain())
    _assert_refused_by_route(app, response, order_id, NO_KEY)
    with app.app_context():
        assert Certificate.query.count() == certificates


def test_a_chosen_ca_offline_with_its_key_is_named_in_the_audit_only(app, client, monkeypatch,
                                                                      create_ca, default_setting):
    """An offline CA keeping its key is refused before signing: never another CA instead."""
    create_ca(cn='A CA able to sign, not chosen')
    chosen = create_ca(cn='Default CA offline keeping its key')
    with app.app_context():
        ca = db.session.get(CA, chosen['id'])
        _set_default(ca.refid)
        ca.offline = True
        db.session.commit()
        certificates = Certificate.query.count()
    try:
        response, order_id = _finalize_by_route(app, client, monkeypatch, _domain())
        _assert_refused_by_route(app, response, order_id, "'Default CA offline keeping its key' chosen in the ACME settings is offline")
        with app.app_context():
            assert Certificate.query.count() == certificates
    finally:
        with app.app_context():
            db.session.get(CA, chosen['id']).offline = False
            db.session.commit()


def test_a_chosen_ca_outside_its_signing_window_is_named_in_the_audit_only(app, client, monkeypatch,
                                                                            create_ca, default_setting):
    """A signing-path failure (here the CA certificate's window) names the CA for the administrator."""
    from services.cert_service import CertificateService
    from utils.ca_signing_window import IssuerWindowError

    def outside_window(*_a, **_k):
        raise IssuerWindowError('Issuing CA certificate has expired (since 2020-01-01T00:00:00Z)')

    chosen = create_ca(cn='Default CA outside its window')
    with app.app_context():
        _set_default(db.session.get(CA, chosen['id']).refid)
    monkeypatch.setattr(CertificateService, 'sign_csr', staticmethod(outside_window))
    response, order_id = _finalize_by_route(app, client, monkeypatch, _domain())
    _assert_refused_by_route(app, response, order_id, "issuing CA 'Default CA outside its window'")
    assert 'expired' not in response.get_data(as_text=True)


def test_a_chosen_ca_taken_offline_is_named_as_offline(app, monkeypatch, create_ca, default_setting):
    chosen = create_ca(cn='Default CA taken offline')
    with app.app_context():
        ca = db.session.get(CA, chosen['id'])
        _set_default(ca.refid)
        ca.prv, ca.hsm_key_id, ca.offline = None, None, True
        db.session.commit()
        success, error, service, order = _finalize(monkeypatch, _domain())
        assert not success and 'is offline' in error and NO_KEY not in error, error
        assert service._last_finalize_error_type == 'serverInternal' and order.certificate_id is None


def test_a_ca_named_with_caa_without_key_is_still_a_server_error(app, client, monkeypatch,
                                                                 create_ca, default_setting):
    """A server-side refusal is never read as a CAA denial, whatever the CA is called."""
    chosen = create_ca(cn='Corp CAA Issuing')
    with app.app_context():
        _set_default(db.session.get(CA, chosen['id']).refid)
        _drop_key(chosen['id'])
    response, order_id = _finalize_by_route(app, client, monkeypatch, _domain())
    _assert_refused_by_route(app, response, order_id, NO_KEY)
    assert 'Corp CAA Issuing' not in response.get_data(as_text=True)


def test_a_ca_named_with_caa_outside_its_window_is_still_a_server_error(app, client, monkeypatch,
                                                                        create_ca, default_setting):
    from services.cert_service import CertificateService
    from utils.ca_signing_window import IssuerWindowError

    def outside_window(*_a, **_k):
        raise IssuerWindowError('Issuing CA certificate has expired (since 2020-01-01T00:00:00Z)')

    chosen = create_ca(cn='Window CAA CA')
    with app.app_context():
        _set_default(db.session.get(CA, chosen['id']).refid)
    monkeypatch.setattr(CertificateService, 'sign_csr', staticmethod(outside_window))
    response, order_id = _finalize_by_route(app, client, monkeypatch, _domain())
    _assert_refused_by_route(app, response, order_id, "issuing CA 'Window CAA CA'")
    assert 'Window CAA CA' not in response.get_data(as_text=True)


def test_a_ca_whose_name_is_a_word_of_the_refusal_is_still_named(app, client, monkeypatch, create_ca,
                                                                 default_setting):
    from services.cert_service import CertificateService
    from utils.ca_signing_window import IssuerWindowError

    def outside_window(*_a, **_k):
        raise IssuerWindowError('Issuing CA certificate has expired (since 2020-01-01T00:00:00Z)')

    chosen = create_ca(cn='Issuing CA')
    with app.app_context():
        _set_default(db.session.get(CA, chosen['id']).refid)
    monkeypatch.setattr(CertificateService, 'sign_csr', staticmethod(outside_window))
    response, order_id = _finalize_by_route(app, client, monkeypatch, _domain())
    _assert_refused_by_route(app, response, order_id, "issuing CA 'Issuing CA'")


def test_a_domain_with_a_caa_label_mapped_to_a_keyless_ca_is_a_server_error(app, client, monkeypatch,
                                                                            create_ca, default_setting):
    chosen = create_ca(cn='Local domain CA without key, caa label')
    domain = f'caa.{_domain()}'
    with app.app_context():
        _drop_key(chosen['id'])
        _LOCAL_DOMAINS.append(domain)
        db.session.add(AcmeLocalDomain(domain=domain, issuing_ca_id=chosen['id']))
        db.session.commit()
    response, order_id = _finalize_by_route(app, client, monkeypatch, domain)
    _assert_refused_by_route(app, response, order_id, NO_KEY)


def test_a_real_caa_denial_still_invalidates_the_order(app, client, monkeypatch):
    """The CAA check's own refusal stays a terminal caa error."""
    domain = _domain()
    response, order_id = _finalize_by_route(app, client, monkeypatch, domain,
                                            caa=(False, f'CAA record forbids issuance for {domain}'))
    assert response.status_code == 400, response.get_data(as_text=True)
    assert response.get_json()['type'] == 'urn:ietf:params:acme:error:caa'
    with app.app_context():
        assert AcmeOrder.query.filter_by(order_id=order_id).one().status == 'invalid'
